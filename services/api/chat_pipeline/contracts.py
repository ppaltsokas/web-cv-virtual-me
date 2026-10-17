from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Protocol


@dataclass
class ChatPipelineInput:
    message: str
    session_id: str
    chat_session: Any
    intent_plan: Any = None


@dataclass
class RetrievedContext:
    message: str
    session_id: str
    chat_session: Any
    has_history: bool
    conversation_summary: str = ""
    persona_context: str = ""
    kb_context: str = ""
    qa_context: str = ""
    referenced_images: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PreparedGeneration:
    user_message: str
    context: RetrievedContext


class ContextRetriever(Protocol):
    def retrieve(self, pipeline_input: ChatPipelineInput) -> RetrievedContext: ...


class ChatModelAdapter(Protocol):
    def stream(self, chat_session: Any, message: str) -> Iterable[str]: ...
