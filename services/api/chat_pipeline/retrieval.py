from __future__ import annotations
from .contracts import RetrievedContext
from .citations import register_citation_source

class PortfolioRetriever:
    def __init__(self, knowledge, client):
        self.knowledge, self.client = knowledge, client

    def retrieve(self, request):
        session = request.chat_session
        plan = request.intent_plan
        context = RetrievedContext(message=request.message, session_id=request.session_id,
            chat_session=session, has_history=bool(session.history),
            metadata={'intent_kind': plan.kind, 'grounding_required': plan.kind not in {'social', 'conversation'}})
        if plan.kind in {'social', 'conversation'}:
            return context
        previous = getattr(session, 'last_grounded_evidence', {})
        if plan.kind == 'source_followup' and previous.get('citation_sources'):
            context.persona_context = previous['persona_context']
            context.kb_context = previous['kb_context']
            context.metadata['citation_sources'] = previous['citation_sources']
            return context
        profile = self.knowledge.chunks[0]
        profile_id = register_citation_source(context, profile.label, ['persona'])
        context.persona_context = f'[{profile_id}] {profile.label}\n<evidence>\n{self.knowledge.profile.evidence()}\n</evidence>'
        evidence = []
        for chunk in self.knowledge.search(plan.query, self.client()):
            if chunk.source == 'profile':
                continue
            source = register_citation_source(context, chunk.label, ['documents'])
            evidence.append(f'[{source}] {chunk.label}\n<evidence>\n{chunk.text}\n</evidence>')
        context.kb_context = '\n\n'.join(evidence)[:14000]
        return context
