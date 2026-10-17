from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace as NS
from collections import deque
import pytest
from fastapi.testclient import TestClient

os.environ['LOAD_DOTENV'] = 'false'
from services.api.profile import ROOT, Profile, Manifest, load_profile, load_manifest, document_path
from services.api.knowledge import KnowledgeBase
from services.api.main import create_app
from services.api.chat_pipeline.temporal import build_temporal_context
from scripts.manage import initialize, credentials

class Stream:
    def __init__(self, text):
        self.text = text
        self.closed = False
    def __iter__(self):
        yield NS(choices=[NS(finish_reason=None, delta=NS(content=self.text))])
        yield NS(choices=[NS(finish_reason='stop', delta=NS(content=None))])
    def close(self):
        self.closed = True

class FakeClient:
    def __init__(self, kind='social', replies=None):
        self.kind, self.replies = kind, deque(replies or ['Hello! What would you like to explore?'])
        self.calls, self.options = [], []
        self.chat = NS(completions=NS(create=self.create))
        self.embeddings = NS(create=self.embed)
    def with_options(self, **options):
        self.options.append(options)
        return self
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get('response_format'):
            message = json.loads(kwargs['messages'][-1]['content'])['message']
            return NS(choices=[NS(finish_reason='stop', message=NS(refusal=None, content=json.dumps({'kind': self.kind, 'query': message})))])
        return Stream(self.replies.popleft())
    def embed(self, **kwargs):
        return NS(data=[NS(index=i, embedding=[float(len(text) % 7 + 1), 1.0, 2.0]) for i, text in enumerate(kwargs['input'])])

@pytest.fixture(autouse=True)
def synthetic_env(monkeypatch):
    for name in ['K_SERVICE', 'RAILWAY_ENVIRONMENT_ID', 'ENVIRONMENT', 'APP_ENV', 'PORT', 'CV_API_PROXY_SECRET', 'PORTFOLIO_PROFILE', 'CONTENT_MANIFEST']:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('PRIVATE_CV_ENABLED', 'false')
    monkeypatch.setenv('PAID_AI_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-test-key')
    monkeypatch.setenv('LOAD_DOTENV', 'false')

@pytest.fixture
def owner(tmp_path):
    data = json.loads((ROOT / 'config/profile.example.json').read_text())
    data['resume']['personalInfo']['name'] = 'Sam Rivera'
    data['resume']['personalInfo']['title'] = 'Product Designer'
    data['chat']['name'] = 'Virtual Sam'
    data['timezone'] = 'America/Los_Angeles'
    data['resume']['experience'] = []
    data['resume']['education'] = []
    data['resume']['latestProjects'] = []
    data['resume']['projects'] = []
    data['resume']['skills'] = []
    summary = tmp_path / 'summary.md'
    summary.write_text('Sam Rivera is a fictional product designer. Built the Garden Planner prototype with accessible keyboard controls.')
    profile = tmp_path / 'profile.json'
    manifest = tmp_path / 'content.json'
    profile.write_text(json.dumps(data))
    manifest.write_text(json.dumps({'documents': [{'id': 'garden', 'label': 'Garden Planner notes', 'path': 'summary.md'}]}))
    return profile, manifest, tmp_path

def app_for(owner, fake):
    profile, manifest, root = owner
    return create_app(profile_path=profile, manifest_path=manifest, root=root, client_factory=lambda: fake)

@pytest.mark.parametrize('greeting', ['hi', 'Hey there', 'Good morning', 'Hello!', 'Thanks'])
def test_greetings_call_llm_without_document_refusal(owner, greeting):
    fake = FakeClient()
    app = app_for(owner, fake)
    with TestClient(app) as client:
        response = client.post('/chat', json={'message': greeting, 'session_id': 'visitor-chat'})
    assert response.status_code == 200
    assert response.text == 'Hello! What would you like to explore?'
    assert len(fake.calls) == 2  # LLM intent decision plus LLM response, not greeting templates.
    assert all(call['store'] is False for call in fake.calls)
    assert all(call['max_completion_tokens'] <= 1536 for call in fake.calls)
    assert all(options.get('max_retries') == 0 for options in fake.options)
    assert app.state.sessions['visitor-chat'].chat.conversation_memory()['first_user_message'] == greeting

def test_second_owner_retrieval_and_citations_use_only_their_content(owner):
    fake = FakeClient('project', ['I built the Garden Planner prototype with accessible keyboard controls. [S2]'])
    app = app_for(owner, fake)
    with TestClient(app) as client:
        response = client.post('/chat', json={'message': 'Tell me about Garden Planner'})
    assert response.status_code == 200
    assert 'Garden Planner notes' in response.text
    assert 'Alex Morgan' not in response.text
    generated_prompt = fake.calls[-1]['messages'][-1]['content']
    assert 'Sam Rivera' in generated_prompt
    assert 'Alex Morgan' not in generated_prompt
    assert 'Time zone: America/Los_Angeles' in fake.calls[-1]['messages'][0]['content']

def test_conversation_recall_uses_session_memory_not_documents(owner):
    fake = FakeClient('social', ['Hi!', 'Your first message was "hi".'])
    with TestClient(app_for(owner, fake)) as client:
        client.post('/chat', json={'message': 'hi', 'session_id': 'same'})
        fake.kind = 'conversation'
        response = client.post('/chat', json={'message': 'What was my first message?', 'session_id': 'same'})
    assert 'first message was "hi"' in response.text
    assert 'Sources:' not in response.text
    assert '"first_user_message": "hi"' in fake.calls[-1]['messages'][-1]['content']

def test_unknown_citations_are_not_shown_as_grounded_claims(owner):
    fake = FakeClient('project', ['I achieved a made-up result. [S99]', 'I achieved a made-up result. [S99]'])
    with TestClient(app_for(owner, fake)) as client:
        response = client.post('/chat', json={'message': 'Tell me about Garden Planner'})
    assert 'made-up result' not in response.text
    assert 'verified evidence' in response.text

def test_private_proxy_and_visitor_scope_are_enforced(owner, monkeypatch):
    monkeypatch.setenv('PRIVATE_CV_ENABLED', 'true')
    monkeypatch.setenv('CV_API_PROXY_SECRET', 'x' * 43)
    fake = FakeClient(replies=['Hi visitor one!', 'Hi visitor two!'])
    app = app_for(owner, fake)
    with TestClient(app) as client:
        assert client.get('/health').status_code == 200
        assert client.get('/me/cv').status_code == 403
        assert client.post('/chat', json={'message': 'hi'}).status_code == 403
        assert client.post('/chat', json={'message': 'hi'}, headers={'X-CV-Proxy-Key': 'x' * 43}).status_code == 403
        for visitor, message in [('a' * 64, 'hello one'), ('b' * 64, 'hello two')]:
            response = client.post('/chat', json={'message': message, 'session_id': 'same'}, headers={'X-CV-Proxy-Key': 'x' * 43, 'X-CV-Visitor': visitor})
            assert response.status_code == 200
    assert len(app.state.sessions) == 2
    assert {entry.chat.conversation_memory()['first_user_message'] for entry in app.state.sessions.values()} == {'hello one', 'hello two'}

def test_disabled_chat_has_no_provider_calls(owner, monkeypatch):
    monkeypatch.setenv('PAID_AI_ENABLED', 'false')
    fake = FakeClient()
    with TestClient(app_for(owner, fake)) as client:
        assert client.get('/health').json()['chat_available'] is False
        assert client.post('/chat', json={'message': 'hi'}).status_code == 503
    assert not fake.calls

def test_bad_input_limits_and_file_routes(owner):
    with TestClient(app_for(owner, FakeClient())) as client:
        for payload in [{'message': ''}, {'message': 'a' * 6001}, {'message': 'hi', 'session_id': '../escape'}, {'message': 'hi', 'secret': 'field'}]:
            assert client.post('/chat', json=payload).status_code == 422
        assert client.post('/chat', content='a' * 33000, headers={'Content-Type': 'application/json'}).status_code == 413
        assert client.get('/kb/pdf/garden').status_code == 404
        assert client.get('/kb/pdf/not-listed').status_code == 404
        assert client.get('/me/cv').status_code == 404

def test_only_manifest_documents_are_read_and_paths_cannot_escape(owner):
    profile, manifest, root = owner
    (root / 'unlisted-private.txt').write_text('This must not enter any prompt or search index.')
    knowledge = KnowledgeBase(load_profile(profile), load_manifest(manifest), root)
    assert all('This must not enter' not in chunk.text for chunk in knowledge.chunks)
    spec = load_manifest(manifest).documents[0]
    spec.path = '../outside.txt'
    with pytest.raises(ValueError):
        document_path(root, spec)

def test_semantic_index_refuses_another_owner_or_changed_documents(owner):
    profile, manifest, root = owner
    knowledge = KnowledgeBase(load_profile(profile), load_manifest(manifest), root)
    directory = root / 'index'
    knowledge.build_index(directory, FakeClient())
    assert KnowledgeBase(load_profile(profile), load_manifest(manifest), root, directory).index is not None
    original_profile = profile.read_text()
    data = json.loads(original_profile)
    data['resume']['personalInfo']['name'] = 'Another Owner'
    profile.write_text(json.dumps(data))
    assert KnowledgeBase(load_profile(profile), load_manifest(manifest), root, directory).index is None
    profile.write_text(original_profile)
    assert KnowledgeBase(load_profile(profile), load_manifest(manifest), root, directory).index is not None
    (root / 'summary.md').write_text('Completely different content.')
    assert KnowledgeBase(load_profile(profile), load_manifest(manifest), root, directory).index is None

def test_profile_rejects_unknown_secrets_invalid_urls_and_timezones():
    data = json.loads((ROOT / 'config/profile.example.json').read_text())
    data['apiKey'] = 'synthetic-private-value'
    with pytest.raises(ValueError):
        Profile.model_validate(data)
    del data['apiKey']
    data['resume']['personalInfo']['socials']['github'] = 'javascript:alert(1)'
    with pytest.raises(ValueError):
        Profile.model_validate(data)

def test_clock_honors_owner_timezone_and_does_not_invent_birth_facts():
    moment = datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc)
    assert 'Current date: 2025-12-31' in build_temporal_context(timezone='America/Los_Angeles', now=moment)
    assert 'Do not invent an age' in build_temporal_context(now=moment)
    assert 'Current age on 2026-01-01: 35.' in build_temporal_context('December 1990', now=moment)

def test_setup_is_idempotent_and_keeps_real_owner_inputs_private(tmp_path):
    shutil = __import__('shutil')
    shutil.copytree(ROOT / 'config', tmp_path / 'config', ignore=shutil.ignore_patterns('*.local.json'))
    shutil.copytree(ROOT / 'examples', tmp_path / 'examples')
    shutil.copyfile(ROOT / '.env.example', tmp_path / '.env.example')
    initialize(tmp_path)
    env = (tmp_path / '.env.local').read_bytes()
    (tmp_path / 'config/profile.local.json').write_text('owner edited this file')
    initialize(tmp_path)
    assert (tmp_path / '.env.local').read_bytes() == env
    assert (tmp_path / 'config/profile.local.json').read_text() == 'owner edited this file'
    with pytest.raises(ValueError):
        credentials('')

def test_private_bundle_omits_secrets_unlisted_documents_and_reuses_only_owner_index(owner, monkeypatch):
    from scripts import manage
    profile_path, manifest_path, root = owner
    (root / 'config').mkdir()
    (root / 'services/api').mkdir(parents=True)
    (root / 'services/api/source.py').write_text('# synthetic public source')
    (root / 'services/api/private.key').write_text('synthetic-do-not-copy')
    (root / '.env.local').write_text('OPENAI_API_KEY=synthetic-do-not-copy')
    (root / 'unlisted.txt').write_text('unlisted confidential notes')
    monkeypatch.setattr(manage, 'ROOT', root)
    monkeypatch.setattr(manage, 'check', lambda: None)
    monkeypatch.setenv('PORTFOLIO_PROFILE', str(profile_path))
    monkeypatch.setenv('CONTENT_MANIFEST', str(manifest_path))
    knowledge = KnowledgeBase(load_profile(profile_path), load_manifest(manifest_path), root)
    knowledge.build_index(root / 'data/index', FakeClient())
    manage.private_bundle()
    bundle = root / 'data/deploy-context'
    assert not (bundle / '.env.local').exists()
    assert not (bundle / 'services/api/private.key').exists()
    assert not (bundle / 'unlisted.txt').exists()
    assert (bundle / 'content/private/garden.md').is_file()
    bundled = KnowledgeBase(load_profile(bundle / 'config/profile.local.json'), load_manifest(bundle / 'config/content.local.json'), bundle, bundle / 'data/index')
    assert bundled.index is not None
    for path in bundle.rglob('*'):
        if path.is_file():
            assert b'synthetic-do-not-copy' not in path.read_bytes()
    with pytest.raises(ValueError):
        manage.private_bundle()
