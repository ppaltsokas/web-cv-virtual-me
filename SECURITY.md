# Security and privacy

Real `.env` files, owner documents, local profile configuration and generated knowledge indexes stay ignored by Git. The example environment contains no credentials and defaults paid AI to off. Run `python scripts/release_check.py` before publishing changes; inspect the staged files as well. Ignore rules do not remove data from existing Git history, so start a new repository from the template.

API keys belong on the backend. The frontend hosting service needs only the private-access runtime settings; never configure a provider key in public `VITE_*` settings, profile JSON or visitor inputs. The Node server uses an HttpOnly session cookie, verifies sign-in origins and throttles attempts. Backend chat and downloads require the shared proxy key, and chat also requires a valid visitor identity supplied by the gate.

Hosted access fails closed when credentials or HTTPS origins are incomplete. Configure your exact public origin, including `www` when applicable. Use the same proxy secret on both services. Keep the backend origin separate from the public portfolio origin. Local preview uses loopback HTTP; hosted production origins must use HTTPS.

Selected knowledge documents inform visitor-facing responses. The manifest's `public` flag governs download availability, not whether a model can discuss a document. Include only material you intend your persona to use. Secrets and confidential documents should never be part of the retrieval corpus.

Raw chat text is not logged or archived by this template. Memory disappears on restart. Provider requests use `store=false`; the provider's own account/data policies still apply. Errors shown to visitors are generic. Process-local rate limits and memory bounds do not replace platform quotas or a provider spending limit.

Never use a stale index after changing owners. Index fingerprints include the selected configuration and document bytes. Private deployment bundles include owner files and must not be committed, publicly uploaded, or used as generic downloadable template examples.

Use one frontend instance and one backend worker initially. A shared visitor password suits invitation-only portfolios; it is not per-user identity management. When changing the hosted password hash, restart the frontend to revoke its existing in-memory sessions. An actual credential disclosure requires changing the affected key and reviewing its exposure separately.

Report a suspected issue privately to the repository owner through their available GitHub contact route. Do not include credentials or personal documents in public issues.
