"""Opt-in real database tests. Only dedicated STACK_TEST_* services are used."""
import os
import uuid
import pytest
from services.api.knowledge import KnowledgeBase
from services.api.profile import ROOT, load_profile, load_manifest
from services.api.knowledge_graph.ingestion import build_snapshot, SnapshotGraphStore
from services.api.knowledge_graph.store import Neo4jGraphStore
from services.api.history import PostgresSessionStore

pytestmark = pytest.mark.skipif(os.getenv('RUN_STACK_SERVICE_TESTS') != 'true',
                                reason='Dedicated PostgreSQL/Neo4j services were not requested')


def test_real_postgres_scope_expiry_and_session_bound():
    psycopg = pytest.importorskip('psycopg')
    url = os.environ['STACK_TEST_DATABASE_URL']
    owner = 'synthetic-test-' + uuid.uuid4().hex
    store = PostgresSessionStore(owner, lambda: psycopg.connect(url, connect_timeout=5), maximum_sessions=2)
    other = PostgresSessionStore(owner + '-other', store.connect)
    store.initialize()
    try:
        store.save('same-client-session', {'messages': [{'role': 'user', 'content': 'fictional retained turn'}]})
        assert store.load('same-client-session')['messages'][0]['content'] == 'fictional retained turn'
        assert other.load('same-client-session') is None
        with store.connect() as connection:
            connection.execute('UPDATE portfolio_session_state SET expires_at=now() WHERE owner=%s', (owner,))
        assert store.load('same-client-session') is None
        for number in range(3):
            store.save('session-' + str(number), {'messages': [], 'memory': {'completed_turns': number}})
        with store.connect() as connection:
            count = connection.execute('SELECT count(*) FROM portfolio_session_state WHERE owner=%s', (owner,)).fetchone()[0]
        assert count == 2
    finally:
        with store.connect() as connection:
            connection.execute('DELETE FROM portfolio_session_state WHERE owner=%s', (owner,))


def test_real_neo4j_ingestion_traversal_and_version_scope():
    neo4j = pytest.importorskip('neo4j')
    profile = load_profile(ROOT / 'config/profile.example.json')
    profile.resume.personalInfo.name = 'Synthetic Graph Test ' + uuid.uuid4().hex
    knowledge = KnowledgeBase(profile, load_manifest(ROOT / 'config/content.example.json'), ROOT)
    snapshot = build_snapshot(knowledge)
    driver = neo4j.GraphDatabase.driver(os.environ['STACK_TEST_NEO4J_URI'],
        auth=('neo4j', os.environ['STACK_TEST_NEO4J_PASSWORD']), connection_timeout=5,
        max_transaction_retry_time=0)
    store = Neo4jGraphStore(snapshot, driver)
    version = snapshot.ingestion_version
    try:
        store.ingest()
        store.ingest()
        store.verify()
        expected = SnapshotGraphStore(snapshot).search_evidence('Community Events Explorer')
        actual = store.search_evidence('Community Events Explorer')
        assert actual and {row['evidence_id'] for row in actual} == {row['evidence_id'] for row in expected}
        for row in actual:
            assert row['source'] in {'profile', *knowledge.documents}
        changed = snapshot.model_copy(update={'ingestion_version': version + '-absent'})
        with pytest.raises(ValueError, match='absent or stale'):
            Neo4jGraphStore(changed, driver).verify()
    finally:
        driver.execute_query('MATCH (node:PortfolioEvidence {version:$version}) DETACH DELETE node',
                             version=version, database_='neo4j')
        driver.execute_query('MATCH (node:PortfolioGraph {version:$version}) DELETE node',
                             version=version, database_='neo4j')
        store.close()
