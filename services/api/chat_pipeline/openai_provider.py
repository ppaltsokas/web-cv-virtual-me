from __future__ import annotations

from types import SimpleNamespace
from typing import Iterable

from langchain_core.messages import AIMessage, HumanMessage
from .temporal import build_temporal_context
try:
    from ..cost_controls import MAX_OUTPUT_TOKENS, require_paid_ai
except ImportError:
    from cost_controls import MAX_OUTPUT_TOKENS, require_paid_ai


class OpenAIChatModel:
    def __init__(self, client, model_name: str, system_instruction: str, recent_limit: int = 8,
                 max_output_tokens: int = MAX_OUTPUT_TOKENS, temporal_context=None):
        if not isinstance(max_output_tokens, int) or isinstance(max_output_tokens, bool) or not 1 <= max_output_tokens <= MAX_OUTPUT_TOKENS:
            raise ValueError("Invalid output token limit")
        self.client = client.with_options(timeout=45.0, max_retries=0)
        self.model_name = model_name
        self.system_instruction = system_instruction
        self.recent_limit = max(2, recent_limit)
        self.max_output_tokens = max_output_tokens
        self.temporal_context = temporal_context or build_temporal_context

    def request_system_instruction(self) -> str:
        # Keep the stored persona prompt/hash stable; refresh the clock for every call.
        return self.system_instruction + '\n\n' + self.temporal_context()

    def start_chat(self, history=None):
        return OpenAIChatSession(self, history or [])

    def generate_content(self, message: str):
        require_paid_ai()
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.request_system_instruction()},
                {"role": "user", "content": message},
            ],
            max_completion_tokens=self.max_output_tokens,
            store=False,
        )
        return SimpleNamespace(text=response.choices[0].message.content or "")


class OpenAIChatSession:
    def __init__(self, model: OpenAIChatModel, history):
        self.model = model
        self._turn_snapshot = None
        self._first_user_message_known = not bool(history)
        self._first_user_message = None
        self._completed_turns = 0
        self._recent_user_messages = []
        self.history = [
            (HumanMessage if previous["role"] == "user" else AIMessage)(content="\n".join(previous["parts"]))
            for previous in list(history)[-model.recent_limit:]
        ]

    def send_message(self, message: str, stream: bool = True):
        if not stream:
            raise ValueError("Chat sessions require streaming")
        return self._stream(message)

    def _stream(self, message: str):
        require_paid_ai()
        messages = [{"role": "system", "content": self.model.request_system_instruction()}]
        for previous in self.history:
            role = "user" if isinstance(previous, HumanMessage) else "assistant"
            messages.append({"role": role, "content": str(previous.content)})
        messages.append({"role": "user", "content": message})
        response = self.model.client.chat.completions.create(
            model=self.model.model_name, messages=messages, stream=True,
            max_completion_tokens=self.model.max_output_tokens, store=False,
        )
        answer = ""
        try:
            for chunk in response:
                require_paid_ai()
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                if choice.finish_reason in {"content_filter", "length"}:
                    raise RuntimeError("Model response was blocked or truncated; please shorten the question")
                delta = choice.delta.content or ""
                if delta:
                    answer += delta
                    yield SimpleNamespace(text=delta)
        finally:
            response.close()
        if not answer.strip():
            raise RuntimeError("Model returned no text")
        self.record_turn(message, answer)

    def record_turn(self, message: str, answer: str) -> None:
        self.history.extend([
            HumanMessage(content=message),
            AIMessage(content=answer),
        ])
        self.history = self.history[-self.model.recent_limit:]

    def persist_turn(self, user_message: str, assistant_message: str) -> None:
        if self._turn_snapshot is not None:
            self.history = self._turn_snapshot
            self._turn_snapshot = None
            self.record_turn(user_message, assistant_message)
        else:
            self.history[-2:] = [HumanMessage(content=user_message), AIMessage(content=assistant_message)]
        if self._completed_turns == 0 and self._first_user_message_known:
            self._first_user_message = user_message[:6000]
        self._completed_turns += 1
        self._recent_user_messages.append(user_message[:2000])
        self._recent_user_messages = self._recent_user_messages[-16:]

    def begin_turn(self) -> None:
        self._turn_snapshot = list(self.history)

    def discard_draft(self) -> None:
        if self._turn_snapshot is not None:
            self.history = list(self._turn_snapshot)

    def abort_turn(self) -> None:
        if self._turn_snapshot is not None:
            self.history = self._turn_snapshot
            self._turn_snapshot = None

    def conversation_memory(self) -> dict:
        return {"first_user_message": self._first_user_message,
                "first_user_message_known": self._first_user_message_known and self._first_user_message is not None,
                "completed_turns": self._completed_turns, "recent_user_messages": list(self._recent_user_messages)}


class OpenAIChatSessionAdapter:
    def stream(self, chat_session, message: str) -> Iterable[str]:
        for chunk in chat_session.send_message(message, stream=True):
            yield chunk.text
