# Application architecture

The React/Vite portfolio is served by a Node server that handles the retro entrance, scrypt password verification, expiring HttpOnly sessions and a narrow same-origin API proxy. The frontend bundles its CSS and uses system fonts, with no tracking script or styling CDN. The UI's greeting is configured display text; actual visitor messages use the backend LLM.

FastAPI accepts the proxy key and binds chat sessions to the authenticated visitor. Direct unauthenticated chat and document requests are denied. Health is public and does not call a provider. The proxy does not forward visitor-supplied authentication keys upstream.

For chat, an OpenAI structured intent decision routes greetings, persona questions, project questions, comparisons, conversation recall and source follow-ups. LangChain composes retrieval and request preparation. Retrieved chunks and bounded memory inform the model; factual drafts pass source-ID validation before release. A failed draft gets at most one citation correction, followed by an uncertainty response if validation still fails. Source validation checks references; it does not independently prove every sentence's truth.

The configured profile and manifest are the source boundary. Only selected documents are read. Keyword retrieval works without a prebuilt index. An explicit indexing command builds normalized OpenAI embeddings into FAISS, together with a fingerprint of the owner, manifest and document bytes. Runtime rejects stale or mismatched artifacts and falls back to keyword retrieval. No previous portfolio's index is shipped.

The server supplies a fresh date in the owner's timezone for both intent and response calls. Birth facts are optional and never guessed. A known birth month/year without a day is treated as ambiguous during the birthday month.

Sessions are process-local, bounded to 256 entries with expiry, per-session concurrency protection, four concurrent generations and per-visitor request admission. SDK retries are disabled and output is bounded. This setup targets one backend worker and one frontend instance. Multi-instance deployment needs shared session storage, distributed admission and coordinated password-session state before scaling; those services are deliberately not required for initial setup.

This template packages the currently used portfolio, authentication and document-grounded conversation flow. Research graph/GNN experiments, paid online evaluation and deferred chat archiving are not included in the deployment path.
