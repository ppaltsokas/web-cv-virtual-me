# Application architecture

The React/Vite portfolio is served by a Node server that handles the retro entrance, scrypt password verification, expiring HttpOnly sessions and a narrow same-origin API proxy. The frontend bundles its CSS and uses system fonts, with no tracking script or styling CDN. The UI's greeting is configured display text; actual visitor messages use the backend LLM.

FastAPI accepts the proxy key and binds chat sessions to the authenticated visitor. Direct unauthenticated chat and document requests are denied. Health is public and does not call a provider. The proxy does not forward visitor-supplied authentication keys upstream.

For chat, an OpenAI structured intent decision routes greetings, persona questions, project questions, comparisons, conversation recall and source follow-ups. LangChain composes retrieval and request preparation. Retrieved chunks and bounded memory inform the model; factual drafts pass source-ID validation before release. A failed draft gets at most one citation correction, followed by an uncertainty response if validation still fails. Source validation checks references; it does not independently prove every sentence's truth.

The configured profile and manifest are the source boundary. Only selected documents are read. Keyword retrieval works without a prebuilt index. An explicit indexing command builds normalized OpenAI embeddings into FAISS, together with a fingerprint of the owner, manifest and document bytes. Runtime rejects stale or mismatched artifacts and falls back to keyword retrieval. No previous portfolio's index is shipped.

The server supplies a fresh date in the owner's timezone for both intent and response calls. Birth facts are optional and never guessed. A known birth month/year without a day is treated as ambiguous during the birthday month.

Sessions default to process-local storage, bounded to 256 entries with expiry, per-session concurrency protection, four concurrent generations and per-visitor request admission. Optional PostgreSQL stores bounded accepted turns, first-message memory and extractive compaction with owner/visitor scoping and expiry. SDK retries are disabled and output is bounded. This setup targets one backend worker and one frontend instance. Multi-instance deployment still needs distributed admission and coordinated password-session state.

Optional GraphRAG traverses typed profile entities and manifest-backed chunks in an in-process snapshot or explicitly populated Neo4j. Reciprocal rank fusion combines keyword, optional FAISS and graph channels. Offline relational GraphSAGE uses PyTorch Geometric, grouped held-out sources and typed negatives. Runtime reads checksummed NumPy embeddings bound to the current graph. Shadow preserves the hybrid order; active canary ranking requires matching artifacts and a passed paired retrieval report. Missing or invalid GNN artifacts preserve ordinary retrieval.

See [technology showcase](TECHNOLOGY_SHOWCASE.md) for fictional examples, feature flags, evaluation limits, optional database setup and deployment requirements. Paid online judging and deferred chat archiving remain excluded.
