"""Optional bounded PostgreSQL session state, with expiry; no archive API."""
from __future__ import annotations
import json
import os
from .chat_pipeline.openai_provider import OpenAIChatSession


class PostgresSessionStore:
    def __init__(self, owner_fingerprint, connect, ttl_seconds=86400, maximum_sessions=256):
        if not 60 <= ttl_seconds <= 604800:
            raise ValueError('CHAT_SESSION_TTL_SECONDS must be between 60 and 604800')
        self.owner, self.connect = owner_fingerprint, connect
        self.ttl, self.maximum = ttl_seconds, maximum_sessions

    @classmethod
    def from_env(cls, fingerprint):
        import psycopg
        url = os.getenv('DATABASE_URL')
        if not url:
            raise ValueError('Persistent history requires a private DATABASE_URL')
        return cls(fingerprint, lambda: psycopg.connect(url, connect_timeout=5),
                   int(os.getenv('CHAT_SESSION_TTL_SECONDS', '86400')))

    def initialize(self):
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    'CREATE TABLE IF NOT EXISTS portfolio_session_state ('
                    'owner TEXT NOT NULL, session_id TEXT NOT NULL, state JSONB NOT NULL, '
                    'updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), '
                    'expires_at TIMESTAMPTZ NOT NULL, PRIMARY KEY(owner, session_id))')
                cursor.execute('CREATE INDEX IF NOT EXISTS portfolio_session_expiry ON portfolio_session_state(expires_at)')
                cursor.execute('DELETE FROM portfolio_session_state WHERE expires_at <= now()')

    def load(self, session_id):
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT state FROM portfolio_session_state WHERE owner=%s AND session_id=%s AND expires_at>now()',
                               (self.owner, session_id))
                row = cursor.fetchone()
        return row[0] if row else None

    def save(self, session_id, state):
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM portfolio_session_state WHERE expires_at<=now()')
                cursor.execute(
                    'INSERT INTO portfolio_session_state(owner, session_id, state, expires_at) '
                    "VALUES (%s, %s, %s::jsonb, now() + (%s * interval '1 second')) "
                    'ON CONFLICT(owner, session_id) DO UPDATE SET state=EXCLUDED.state, updated_at=now(), expires_at=EXCLUDED.expires_at',
                    (self.owner, session_id, json.dumps(state), self.ttl))
                cursor.execute(
                    'DELETE FROM portfolio_session_state WHERE owner=%s AND session_id IN '
                    '(SELECT session_id FROM portfolio_session_state WHERE owner=%s ORDER BY updated_at DESC, session_id OFFSET %s)',
                    (self.owner, self.owner, self.maximum))


class PersistentOpenAIChatSession(OpenAIChatSession):
    """Persist the accepted response, never retrieval prompts or rejected drafts."""
    def __init__(self, model, store, identifier):
        self.store, self.identifier = store, identifier
        state = store.load(identifier) or {}
        history = state.get('messages', [])[-model.recent_limit:]
        super().__init__(model, [{'role': row['role'], 'parts': [row['content']]} for row in history])
        self.conversation_summary = state.get('summary', '')[:4000]
        memory = state.get('memory', {})
        self._first_user_message = memory.get('first_user_message')
        self._first_user_message_known = memory.get('first_user_message_known', not history)
        self._completed_turns = memory.get('completed_turns', 0)
        self._recent_user_messages = memory.get('recent_user_messages', [])[-16:]

    def persist_turn(self, user_message, assistant_message):
        from langchain_core.messages import HumanMessage
        previous = list(self._turn_snapshot if self._turn_snapshot is not None else self.history[:-2])
        rows = [{'role': 'user' if isinstance(message, HumanMessage) else 'assistant', 'content': str(message.content)}
                for message in previous]
        rows += [{'role': 'user', 'content': user_message}, {'role': 'assistant', 'content': assistant_message}]
        dropped = rows[:-self.model.recent_limit]
        # Extractive compaction uses quoted user text and has no extra AI charge.
        # It does not invent a summary of conversation that was never retained.
        excerpts = '\n'.join('Earlier user message (quoted): ' + row['content'][:500]
                             for row in dropped if row['role'] == 'user')
        summary = (self.conversation_summary + '\n' + excerpts).strip()[-4000:]
        memory = self.conversation_memory()
        if self._completed_turns == 0 and self._first_user_message_known:
            memory['first_user_message'] = user_message[:6000]
            memory['first_user_message_known'] = True
        memory['completed_turns'] = self._completed_turns + 1
        memory['recent_user_messages'] = (self._recent_user_messages + [user_message[:2000]])[-16:]
        self.store.save(self.identifier, {'messages': rows[-self.model.recent_limit:], 'memory': memory, 'summary': summary})
        super().persist_turn(user_message, assistant_message)
        self.conversation_summary = summary
