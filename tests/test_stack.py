"""Optional stack tests use fictional content, real CPU training and mocked providers."""
from __future__ import annotations
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from services.api.features import Features
from services.api.knowledge import KnowledgeBase
from services.api.profile import ROOT, load_profile, load_manifest
from services.api.knowledge_graph.ingestion import build_snapshot, SnapshotGraphStore, chunk_id
from services.api.knowledge_graph.store import Neo4jGraphStore
from services.api.retrieval_engine import RetrievalEngine
from services.api.history import PersistentOpenAIChatSession, PostgresSessionStore
from services.api.chat_pipeline.openai_provider import OpenAIChatModel
from services.api.chat_pipeline.gnn_canary import GNNCanaryController
from services.graph.gnn_dataset import export_gnn_dataset, validate_gnn_dataset
from services.evaluation.showcase import load_cases, compare_retrieval, write_comparison, evaluate_answers


@pytest.fixture(autouse=True)
def isolated_flags(monkeypatch):
    for name in ['POSTGRES_ENABLED', 'PERSISTENT_CHAT_HISTORY_ENABLED', 'KNOWLEDGE_GRAPH_ENABLED',
                 'GRAPH_RETRIEVAL_ENABLED', 'GNN_SHADOW_ENABLED', 'GNN_RERANKING_ENABLED']:
        monkeypatch.setenv(name, 'false')
    monkeypatch.setenv('GNN_CANARY_PERCENT', '0')
    monkeypatch.setenv('GRAPH_BACKEND', 'snapshot')
    monkeypatch.setenv('LOAD_DOTENV', 'false')
    monkeypatch.setenv('PRIVATE_CV_ENABLED', 'false')
    monkeypatch.delenv('CV_API_PROXY_SECRET', raising=False)
    monkeypatch.setenv('PAID_AI_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-test-key')


@pytest.fixture
def knowledge():
    return KnowledgeBase(load_profile(ROOT / 'config/profile.example.json'),
                         load_manifest(ROOT / 'config/content.example.json'), ROOT)


def test_flags_default_off_and_reject_incomplete_activation(monkeypatch):
    features = Features.from_env()
    assert not any([features.graph, features.gnn_active, features.persistent_history])
    monkeypatch.setenv('GNN_RERANKING_ENABLED', 'true')
    with pytest.raises(ValueError, match='graph retrieval'):
        Features.from_env()
    monkeypatch.setenv('GNN_RERANKING_ENABLED', 'false')
    monkeypatch.setenv('GNN_CANARY_PERCENT', 'nan')
    with pytest.raises(ValueError):
        Features.from_env()


def test_graph_is_deterministic_current_and_manifest_only(knowledge, tmp_path):
    first, second = build_snapshot(knowledge), build_snapshot(knowledge)
    assert first.model_dump() == second.model_dump()
    assert first.ingestion_version.startswith('portfolio-graph-v1:')
    sources = {node.source_path for node in first.nodes}
    assert sources <= {'profile', *knowledge.documents}
    store = SnapshotGraphStore(first)
    rows = store.search_evidence('Community Events Explorer React')
    assert rows
    for row in rows:
        chunk = knowledge.chunks[row['chunk_index']]
        assert row['evidence_id'] == chunk_id(row['chunk_index'], chunk)
        assert row['source'] == chunk.source
    knowledge.profile.resume.personalInfo.name = 'Taylor Hart'
    assert build_snapshot(knowledge).ingestion_version != first.ingestion_version


def test_generic_identity_supports_non_latin_names_and_distinct_technologies():
    from services.api.knowledge_graph.models import stable_id, normalize_name
    assert stable_id('Skill', 'C++') != stable_id('Skill', 'C#')
    assert stable_id('Person', '山田') != stable_id('Person', '佐藤')
    assert normalize_name('山田') == '山田'


def test_neo4j_filters_foreign_or_modified_evidence_and_parameterizes_query(knowledge):
    snapshot = build_snapshot(knowledge)
    valid = SnapshotGraphStore(snapshot).search_evidence('Community Events Explorer')[0]
    class Driver:
        def execute_query(self, query, **parameters):
            self.query, self.parameters = query, parameters
            return [valid, {**valid, 'evidence_id': 'foreign-evidence'}, {**valid, 'source': 'not-listed'}], None, None
    driver = Driver()
    store = Neo4jGraphStore(snapshot, driver)
    rows = store.search_evidence('Community Events Explorer')
    assert rows == [valid]
    assert driver.parameters['version'] == snapshot.ingestion_version
    assert '$version' in driver.query and 'Community Events Explorer' not in driver.query


def test_graph_failure_keeps_baseline_retrieval(knowledge):
    class Broken:
        def search_evidence(self, *args):
            raise RuntimeError('synthetic database outage')
    engine = RetrievalEngine(knowledge, Features(graph=True, graph_retrieval=True), graph_store=Broken())
    chunks, diagnostic = engine.rank('Python SQL', mode='baseline')
    assert chunks
    assert engine.status()['graph_failures'] == 1


def test_dataset_is_owner_bound_and_tampering_is_rejected(knowledge, tmp_path):
    snapshot = build_snapshot(knowledge)
    report = export_gnn_dataset(snapshot, tmp_path)
    assert set(report['source_splits'].values()) == {'train', 'validation', 'test'}
    assert report['source_splits']['profile'] == 'train'
    assert validate_gnn_dataset(tmp_path, expected_graph_version=snapshot.ingestion_version) == report
    (tmp_path / 'edges.jsonl').write_text('{}\n')
    with pytest.raises(ValueError, match='checksum'):
        validate_gnn_dataset(tmp_path)


@pytest.fixture(scope='module')
def trained(tmp_path_factory):
    pytest.importorskip('torch')
    pytest.importorskip('torch_geometric')
    pytest.importorskip('sklearn')
    from services.gnn.training import (load_gnn_dataset, normalized_text_features, build_training_bundle,
        train_graphsage, write_embedding_artifact)
    directory = tmp_path_factory.mktemp('fictional-graphsage')
    shutil.copytree(ROOT / 'examples', directory / 'examples')
    kb = KnowledgeBase(load_profile(ROOT / 'config/profile.example.json'),
                       load_manifest(ROOT / 'config/content.example.json'), directory)
    snapshot = build_snapshot(kb)
    export_gnn_dataset(snapshot, directory / 'dataset')
    manifest, nodes, edges = load_gnn_dataset(directory / 'dataset')
    data, examples, local_index, stable_ids = build_training_bundle(nodes, edges, normalized_text_features(nodes, 32), seed=42)
    negatives = [{(row['source_id'], row['type'], row['target_id']) for row in examples[split] if row['negative']}
                 for split in ['train', 'validation', 'test']]
    assert not (negatives[0] & negatives[1] or negatives[1] & negatives[2] or negatives[0] & negatives[2])
    assert sum(data[edge_type].edge_index.shape[1] for edge_type in data.edge_types) == 2 * sum(row['split'] == 'train' for row in edges)
    model, embeddings, metrics = train_graphsage(data, examples, local_index, embedding_dimensions=8,
                                                 epochs=3, patience=3, seed=42)
    artifact = write_embedding_artifact(directory / 'artifact', manifest=manifest, embeddings=embeddings,
        stable_ids=stable_ids, metrics=metrics, model_state=model.state_dict(), training_config={'seed': 42})
    assert metrics['epochs_trained'] >= 1
    assert 0 <= metrics['test']['auc'] <= 1
    return kb, directory, artifact


def engine_for(trained, **kwargs):
    kb, directory, _ = trained
    return RetrievalEngine(kb, Features(graph=True, graph_retrieval=True, gnn_shadow=True, **kwargs),
        artifact_dir=directory / 'artifact', gate_path=directory / 'evaluation/gate.json')


def test_shadow_ranking_preserves_order_and_scores_real_embeddings(trained):
    engine = engine_for(trained)
    baseline, _ = engine.rank('Community Events Explorer', mode='baseline')
    actual, diagnostic = engine.rank('Community Events Explorer')
    candidate, scored = engine.rank('Community Events Explorer', mode='candidate')
    assert actual == baseline
    assert diagnostic['mode'] == 'shadow'
    assert scored['mode'] == 'active' and candidate
    assert diagnostic['artifact_version'] == trained[2]['artifact_version']


def test_real_graphsage_artifact_runs_through_grounded_chat_api(trained, monkeypatch):
    from test_portfolio import FakeClient
    from services.api.main import create_app
    knowledge, directory, _ = trained
    monkeypatch.setenv('GNN_ARTIFACT_DIR', 'artifact')
    monkeypatch.setenv('GNN_ACTIVATION_GATE', 'evaluation/gate.json')
    provider = FakeClient(kind='persona', replies=['I built Community Events Explorer with React [S1].'])
    app = create_app(profile_path=ROOT / 'config/profile.example.json',
        manifest_path=ROOT / 'config/content.example.json', root=directory,
        features=Features(graph=True, graph_retrieval=True, gnn_shadow=True),
        client_factory=lambda: provider)
    observed = []
    original_rank = app.state.retrieval.rank
    def rank(*args, **kwargs):
        result = original_rank(*args, **kwargs)
        observed.append(result[1])
        return result
    app.state.retrieval.rank = rank
    with TestClient(app) as client:
        health = client.get('/health').json()
        assert health['gnn_artifact'] == 'ready' and health['graph_backend'] == 'snapshot'
        answer = client.post('/chat', json={'message': 'Tell me about Community Events Explorer'}).text
        assert observed[0]['mode'] == 'shadow'
        assert 'React [S1]' in answer and '[Error:' not in answer


def test_paired_evaluation_binds_gate_to_exact_model_and_report(trained):
    engine = engine_for(trained)
    report = compare_retrieval(engine, ROOT / 'examples/evaluation/retrieval.jsonl')
    assert report['case_count'] == 12
    gate = write_comparison(report, trained[1] / 'evaluation')
    assert gate['passed'] == report['gate_eligible']
    checked = engine_for(trained, gnn_active=True, canary_percent=100)
    assert checked.gate['active'] == gate['passed']
    if gate['passed']:
        candidate, _ = checked.rank('Community Events Explorer', mode='candidate')
        runtime, diagnostic = checked.rank('Community Events Explorer', session_id='synthetic')
        assert runtime == candidate and diagnostic['mode'] == 'active'
    # A failed gate must remain failed even with a 100% canary.
    report['gate_eligible'] = False
    write_comparison(report, trained[1] / 'evaluation')
    checked = engine_for(trained, gnn_active=True, canary_percent=100)
    assert checked.gate['active'] is False
    assert checked.rank('Community Events Explorer')[1]['mode'] == 'shadow'
    report['gate_eligible'] = True  # Synthetic positive gate tests artifact binding only.
    write_comparison(report, trained[1] / 'evaluation')
    checked = engine_for(trained, gnn_active=True, canary_percent=100)
    assert checked.gate['active'] is True
    (trained[1] / 'evaluation/comparison.json').write_text('{}')
    checked = engine_for(trained, gnn_active=True, canary_percent=100)
    assert not checked.gate['active']


def test_missing_stale_or_tampered_artifact_falls_back(knowledge, trained, tmp_path):
    kb, directory, _ = trained
    missing = RetrievalEngine(knowledge, Features(graph=True, graph_retrieval=True, gnn_shadow=True),
                             artifact_dir=tmp_path / 'missing')
    assert missing.rank('Python')[1]['mode'] == 'fallback'
    profile = load_profile(ROOT / 'config/profile.example.json')
    profile.resume.personalInfo.name = 'Taylor Hart'
    other = KnowledgeBase(profile, knowledge.manifest, ROOT)
    stale = RetrievalEngine(other, Features(graph=True, graph_retrieval=True, gnn_shadow=True),
                            artifact_dir=directory / 'artifact')
    assert stale.index is None
    target = tmp_path / 'artifact'
    shutil.copytree(directory / 'artifact', target)
    with (target / 'embeddings.npz').open('ab') as stream:
        stream.write(b'modified')
    bad = RetrievalEngine(kb, Features(graph=True, graph_retrieval=True, gnn_shadow=True), artifact_dir=target)
    assert bad.index is None and bad.artifact_status == 'missing_or_stale'


def test_canary_is_stable_and_trips_after_failures():
    controller = GNNCanaryController(100, salt='fictional', minimum_samples=2, maximum_fallback_rate=.1)
    first = controller.decide('visitor-bound-session')
    assert first['bucket'] == controller.decide('visitor-bound-session')['bucket']
    controller.record(first, 'fallback', 1, 'gnn_unavailable')
    controller.record(first, 'fallback', 1, 'gnn_unavailable')
    assert not controller.decide('other')['selected']
    assert controller.status()['circuit_open']


class MemoryStore:
    def __init__(self):
        self.rows = {}
    def initialize(self):
        pass
    def load(self, identifier):
        return json.loads(json.dumps(self.rows.get(identifier)))
    def save(self, identifier, state):
        self.rows[identifier] = json.loads(json.dumps(state))


def test_persistent_history_retains_first_message_and_only_accepted_turns():
    model = OpenAIChatModel(SimpleNamespace(with_options=lambda **kw: SimpleNamespace()), 'synthetic-model', 'synthetic-persona', recent_limit=4)
    store = MemoryStore()
    first = PersistentOpenAIChatSession(model, store, 'visitor-a')
    for question in ['hello', 'about your work', 'about SQL', 'more about projects']:
        first.begin_turn()
        first.record_turn('retrieval prompt must never persist', 'rejected draft')
        first.persist_turn(question, 'accepted response')
    state = store.rows['visitor-a']
    assert len(state['messages']) == 4
    assert 'retrieval prompt must never persist' not in json.dumps(state)
    assert 'rejected draft' not in json.dumps(state)
    restored = PersistentOpenAIChatSession(model, store, 'visitor-a')
    assert restored.conversation_memory()['first_user_message'] == 'hello'
    assert restored.conversation_memory()['completed_turns'] == 4
    assert 'hello' in restored.conversation_summary
    assert not PersistentOpenAIChatSession(model, store, 'visitor-b').history


def test_postgres_queries_bind_owner_and_session_and_validate_ttl():
    queries = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, parameters=None): queries.append((sql, parameters))
        def fetchone(self): return None
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
    store = PostgresSessionStore('owner-fingerprint', Connection)
    identifier = "visitor'; DROP TABLE important; --"
    assert store.load(identifier) is None
    store.save(identifier, {'messages': []})
    assert all(identifier not in query for query, _ in queries)
    assert queries[0][1] == ('owner-fingerprint', identifier)
    assert any('expires_at<=now()' in query for query, _ in queries)
    with pytest.raises(ValueError):
        PostgresSessionStore('owner', Connection, ttl_seconds=0)


def test_api_rehydrates_visitor_bound_history_and_exercises_shared_retrieval(monkeypatch):
    from test_portfolio import FakeClient
    from services.api.main import create_app
    monkeypatch.setenv('PRIVATE_CV_ENABLED', 'true')
    monkeypatch.setenv('CV_API_PROXY_SECRET', 'x' * 40)
    features = Features(postgres=True, persistent_history=True, graph=True, graph_retrieval=True)
    store = MemoryStore()
    client = FakeClient(replies=['Hello!', 'Hello again!', 'Hello new visitor!'])
    arguments = dict(profile_path=ROOT / 'config/profile.example.json', manifest_path=ROOT / 'config/content.example.json',
                     features=features, history_store=store, client_factory=lambda: client)
    headers = {'X-CV-Proxy-Key': 'x' * 40, 'X-CV-Visitor': 'a' * 64}
    with TestClient(create_app(**arguments)) as api:
        assert api.post('/chat', json={'message': 'hi', 'session_id': 'same'}, headers=headers).status_code == 200
    app = create_app(**arguments)
    with TestClient(app) as api:
        assert api.post('/chat', json={'message': 'hello', 'session_id': 'same'}, headers=headers).status_code == 200
        entry = next(iter(app.state.sessions.values()))
        assert entry.chat.conversation_memory()['first_user_message'] == 'hi'
        assert entry.chat.conversation_memory()['completed_turns'] == 2
        api.post('/chat', json={'message': 'hello', 'session_id': 'same'},
                 headers={**headers, 'X-CV-Visitor': 'b' * 64})
        assert len(store.rows) == 2
        assert api.get('/health').json()['persistent_chat_history_enabled'] is True
    factual_client = FakeClient(kind='persona', replies=['I use Python [S1].'])
    app = create_app(**{**arguments, 'client_factory': lambda: factual_client})
    calls = []
    rank = app.state.retrieval.rank
    def tracking_rank(*args, **kwargs):
        calls.append(args[0])
        return rank(*args, **kwargs)
    app.state.retrieval.rank = tracking_rank
    with TestClient(app) as api:
        answer = api.post('/chat', json={'message': 'What Python work have you done?'}, headers=headers).text
        assert calls and '[S1]' in answer
        assert 'retrieval prompt' not in json.dumps(store.rows)


def test_evaluation_refuses_other_owner_unknown_sources_and_checks_answer_ids(knowledge, tmp_path):
    path = ROOT / 'examples/evaluation/retrieval.jsonl'
    _, cases = load_cases(path, knowledge)
    knowledge.profile.resume.personalInfo.name = 'Taylor Hart'
    with pytest.raises(ValueError, match='another owner'):
        load_cases(path, knowledge)
    answers = tmp_path / 'answers.jsonl'
    answers.write_text(json.dumps({'id': cases[0]['id'], 'answer': 'An unsupported citation [S99].', 'sources': {'S1': 'events-project'}}))
    report = evaluate_answers(answers, cases)
    assert not report['cases'][0]['valid_citation_ids']
    assert not report['cases'][0]['cites_relevant_source']
