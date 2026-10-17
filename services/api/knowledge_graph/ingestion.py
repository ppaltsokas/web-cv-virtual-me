"""Deterministic graph from the selected owner profile and manifest only."""
from __future__ import annotations
from collections import defaultdict, deque
import hashlib
from .models import GraphNode, GraphRelationship, GraphSnapshot, NodeLabel, RelationshipType, stable_id, content_hash
from ..knowledge import tokens

SCHEMA = 'portfolio-graph-v1'


def chunk_id(index: int, chunk) -> str:
    return 'chunk:' + content_hash(f'{index}:{chunk.source}:{chunk.text}')[:24]


def build_snapshot(knowledge) -> GraphSnapshot:
    nodes, relationships = {}, {}
    def node(label, key, name, text='', source='profile', **properties):
        identifier = stable_id(label, key)
        nodes[identifier] = GraphNode(id=identifier, label=label, name=name,
            properties={'text': text, **properties}, source_path=source,
            source_hash=content_hash(text or name))
        return identifier
    def edge(source, relation, target, evidence='profile'):
        item = GraphRelationship(source_id=source, target_id=target, type=relation,
            source_path=evidence, source_hash=content_hash(evidence))
        relationships[item.id] = item

    profile = knowledge.profile.resume
    person = node(NodeLabel.PERSON, 'owner', profile.personalInfo.name, profile.personalInfo.bio)
    for role in profile.experience:
        employer = node(NodeLabel.EMPLOYER, role.company, role.company)
        job = node(NodeLabel.ROLE, role.id, role.role, role.description)
        edge(person, RelationshipType.WORKED_AT, employer)
        edge(person, RelationshipType.HELD_ROLE, job)
        edge(job, RelationshipType.WORKED_AT, employer)
        for technology in role.technologies:
            tech = node(NodeLabel.TECHNOLOGY, technology, technology)
            edge(job, RelationshipType.USES, tech)
    for project in profile.latestProjects + profile.projects:
        item = node(NodeLabel.PROJECT, project.id, project.title, project.description)
        edge(person, RelationshipType.BUILT, item)
        for technology in project.technologies:
            tech = node(NodeLabel.TECHNOLOGY, technology, technology)
            edge(item, RelationshipType.USES, tech)
    for category in profile.skills:
        for name in category.skills:
            skill = node(NodeLabel.SKILL, name, name, category=category.name)
            edge(person, RelationshipType.DEMONSTRATES, skill)
    for degree in profile.education:
        item = node(NodeLabel.EDUCATION, degree.id, degree.school, degree.degree + ' ' + degree.year)
        edge(person, RelationshipType.STUDIED_AT, item)
    for certificate in profile.certifications:
        item = node(NodeLabel.CERTIFICATION, certificate.id, certificate.title, certificate.issuer)
        edge(person, RelationshipType.EARNED, item)
    entities = list(nodes.values())
    for index, chunk in enumerate(knowledge.chunks):
        document = node(NodeLabel.DOCUMENT, chunk.source, chunk.label, source=chunk.source)
        identifier = chunk_id(index, chunk)
        nodes[identifier] = GraphNode(id=identifier, label=NodeLabel.CHUNK,
            name=chunk.label, source_path=chunk.source, source_hash=content_hash(chunk.text),
            properties={'text': chunk.text, 'chunk_index': index})
        edge(identifier, RelationshipType.DERIVED_FROM, document, chunk.source)
        # Mentions establish evidence links only; co-occurrence never invents a role
        # or a project accomplishment. Explicit career edges come from profile fields.
        content_terms = tokens(chunk.text)
        for entity in entities:
            name = tokens(entity.name)
            if name and name <= content_terms:
                edge(entity.id, RelationshipType.EVIDENCED_BY, identifier, chunk.source)
    snapshot = GraphSnapshot(ingestion_version='', nodes=sorted(nodes.values(), key=lambda value: value.id),
        relationships=sorted(relationships.values(), key=lambda value: value.id),
        source_files=len(knowledge.documents) + 1)
    # The version binds the complete graph to this owner, document bytes and schema.
    snapshot.ingestion_version = SCHEMA + ':' + hashlib.sha256(
        (knowledge.fingerprint + snapshot.canonical_json()).encode()).hexdigest()
    return snapshot


class SnapshotGraphStore:
    """Two-hop graph retrieval; evidence is always a current manifest chunk."""
    def __init__(self, snapshot: GraphSnapshot):
        self.snapshot = snapshot
        self.nodes = {node.id: node for node in snapshot.nodes}
        self.adjacency = defaultdict(set)
        for edge in snapshot.relationships:
            self.adjacency[edge.source_id].add(edge.target_id)
            self.adjacency[edge.target_id].add(edge.source_id)

    def anchors(self, query: str) -> list[str]:
        terms = tokens(query) - {'what', 'which', 'about', 'tell', 'with', 'does', 'your', 'work', 'project', 'projects'}
        matches = []
        for node in self.snapshot.nodes:
            if node.label in {NodeLabel.CHUNK, NodeLabel.DOCUMENT, NodeLabel.PERSON}:
                continue
            names = tokens(node.name)
            hits = len(terms & names)
            if hits:
                matches.append((hits / max(1, len(names)), node.id))
        return [identifier for _, identifier in sorted(matches, key=lambda value: (-value[0], value[1]))[:8]]

    def search_evidence(self, query: str, limit: int = 12):
        anchors = self.anchors(query)
        distances, queue = {identifier: 0 for identifier in anchors}, deque(anchors)
        while queue:
            current = queue.popleft()
            if distances[current] >= 2:
                continue
            for neighbor in sorted(self.adjacency[current]):
                if neighbor not in distances:
                    distances[neighbor] = distances[current] + 1
                    queue.append(neighbor)
        rows = []
        for identifier, distance in distances.items():
            node = self.nodes[identifier]
            if node.label == NodeLabel.CHUNK:
                rows.append({'evidence_id': identifier, 'chunk_index': node.properties['chunk_index'],
                    'distance': distance, 'source': node.source_path})
        return sorted(rows, key=lambda row: (row['distance'], row['evidence_id']))[:limit]

    def close(self):
        pass
