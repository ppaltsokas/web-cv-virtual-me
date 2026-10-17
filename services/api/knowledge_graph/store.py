"""Owner-version-scoped Neo4j storage with parameterized, bounded traversal."""
from __future__ import annotations
import os
from .ingestion import SnapshotGraphStore


class Neo4jGraphStore(SnapshotGraphStore):
    def __init__(self, snapshot, driver, database='neo4j'):
        super().__init__(snapshot)
        self.driver, self.database = driver, database

    @classmethod
    def from_env(cls, snapshot):
        from neo4j import GraphDatabase
        uri, password = os.getenv('NEO4J_URI'), os.getenv('NEO4J_PASSWORD')
        if not uri or not password:
            raise ValueError('Configure NEO4J_URI and NEO4J_PASSWORD privately')
        driver = GraphDatabase.driver(uri,
            auth=(os.getenv('NEO4J_USERNAME', 'neo4j'), password),
            connection_timeout=5, max_transaction_retry_time=0)
        return cls(snapshot, driver, os.getenv('NEO4J_DATABASE', 'neo4j'))

    def verify(self):
        self.driver.verify_connectivity()
        records, _, _ = self.driver.execute_query(
            'MATCH (run:PortfolioGraph {version: $version}) RETURN run.nodes AS nodes, run.edges AS edges',
            version=self.snapshot.ingestion_version, database_=self.database)
        if not records or records[0]['nodes'] != len(self.snapshot.nodes) or records[0]['edges'] != len(self.snapshot.relationships):
            raise ValueError('Neo4j graph is absent or stale. Run showcase.py graph --neo4j for this owner first.')

    def ingest(self):
        self.driver.execute_query(
            'CREATE CONSTRAINT portfolio_evidence_unique IF NOT EXISTS '
            'FOR (node:PortfolioEvidence) REQUIRE (node.version, node.id) IS UNIQUE',
            database_=self.database)
        nodes = [{'id': node.id, 'kind': node.label.value, 'name': node.name,
                  'text': node.properties.get('text', ''), 'chunk_index': node.properties.get('chunk_index', -1),
                  'source': node.source_path} for node in self.snapshot.nodes]
        edges = [{'source': edge.source_id, 'target': edge.target_id, 'kind': edge.type.value}
                 for edge in self.snapshot.relationships]
        def write(tx):
            tx.run('UNWIND $rows AS row MERGE (node:PortfolioEvidence {version: $version, id: row.id}) '
                   'SET node += row', rows=nodes, version=self.snapshot.ingestion_version).consume()
            tx.run('UNWIND $rows AS row '
                   'MATCH (source:PortfolioEvidence {version: $version, id: row.source}) '
                   'MATCH (target:PortfolioEvidence {version: $version, id: row.target}) '
                   'MERGE (source)-[edge:PORTFOLIO_RELATION {kind: row.kind}]->(target)',
                   rows=edges, version=self.snapshot.ingestion_version).consume()
            tx.run('MERGE (run:PortfolioGraph {version: $version}) SET run.nodes=$nodes, run.edges=$edges',
                   version=self.snapshot.ingestion_version, nodes=len(nodes), edges=len(edges)).consume()
        with self.driver.session(database=self.database) as session:
            session.execute_write(write)

    def search_evidence(self, query, limit=12):
        anchors = self.anchors(query)
        if not anchors:
            return []
        records, _, _ = self.driver.execute_query(
            'MATCH (anchor:PortfolioEvidence) WHERE anchor.version=$version AND anchor.id IN $anchors '
            'MATCH path=(anchor)-[:PORTFOLIO_RELATION*1..2]-(evidence:PortfolioEvidence) '
            'WHERE evidence.version=$version AND evidence.kind=$kind '
            'AND all(node IN nodes(path) WHERE node.version=$version) '
            'WITH evidence, min(length(path)) AS distance '
            'RETURN evidence.id AS evidence_id, evidence.chunk_index AS chunk_index, '
            'evidence.source AS source, distance ORDER BY distance, evidence_id LIMIT $limit',
            version=self.snapshot.ingestion_version, anchors=anchors, kind='Chunk',
            limit=max(1, min(limit, 20)), database_=self.database)
        # Never trust database text as new evidence. Match IDs back to this owner's
        # current, validated snapshot before a retrieved chunk can reach a prompt.
        rows = []
        for record in records:
            row = dict(record)
            node = self.nodes.get(row.get('evidence_id'))
            if node and node.label.value == 'Chunk' and node.source_path == row.get('source') and node.properties['chunk_index'] == row.get('chunk_index'):
                rows.append(row)
        return rows

    def close(self):
        self.driver.close()
