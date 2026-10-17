# Web CV with Virtual-Me Chatbot

A configurable portfolio with a retro adventure entrance, password-protected CV downloads and an LLM persona that answers from your own profile and documents.

The included **Alex Morgan** profile, employers, projects and PDFs are fictional examples. Each deployment belongs to one portfolio owner. Visitors do not supply API keys.

## Quickstart

Requirements: Python 3.11 and Node.js 22+. Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r services/api/requirements.txt
npm --prefix services/frontend ci
python scripts/manage.py init
python scripts/manage.py check
```

On macOS/Linux, activate the environment with `source .venv/bin/activate` instead.

The initializer creates ignored local files and a fresh random access password. It preserves existing files and prints no credentials. Read `CV_ACCESS_PASSWORD` privately in your new `.env.local`.

Run these in two terminals with the virtual environment active:

```powershell
# Terminal 1
python scripts/manage.py backend
```

```powershell
# Terminal 2
python scripts/manage.py frontend
```

Open **http://127.0.0.1:3000/access** and enter the generated password. Use `127.0.0.1` exactly; the gate verifies the configured origin. The backend health endpoint is **http://127.0.0.1:8000/health**.

The fictional portfolio works without an API key. Chat shows a setup state and makes no provider calls until you privately add `OPENAI_API_KEY` and set `PAID_AI_ENABLED=true` in `.env.local`, then restart the backend. Set that flag back to `false` to stop paid AI calls. Never put credentials in `VITE_*`, profile JSON, Git or browser storage.

## Make it yours

1. Edit `config/profile.local.json`: name, title, summary, roles, education, certifications, skills, projects, contact links, chat identity and entrance text. Arrays may be empty; optional empty sections are hidden. Social/project links use complete HTTPS URLs.
2. Replace the sample files in `content/private/` with your CV, summary and project PDFs. List only the files you want the persona to use in `config/content.local.json`. Text-based PDF, Markdown and UTF-8 text are supported; scanned PDFs need an OCR transcript.
3. Set a project `pdfPath` to its manifest **document ID**, such as `events-project`, to enable its download. Mark that PDF `public: true`. The manifest can declare at most one `kind: "cv"` for the CV download.
4. Set the IANA timezone, such as `UTC` or `America/New_York`. Optional `birthMonthYear` uses a value such as `January 1990`; omit it to keep age unspecified. It is excluded from the public frontend bundle.
5. Run `python scripts/manage.py check`, then restart the backend and frontend. The frontend command rebuilds current profile data.

Your profile introduction and detailed summary document serve different purposes: the former is displayed on the portfolio; the latter provides additional evidence to the chatbot. Filling in a CV does not automatically rewrite your public frontend profile.

For a custom avatar, put an image in `services/frontend/public/custom/` and set `chat.avatar`, for example `/custom/avatar.webp`. This directory is ignored by Git. The entrance heading is real configurable text, with no name baked into an image. Topic questions follow the configured roles, projects, education and skill categories.

`public: false` prevents a file download; it does **not** prevent its contents from informing visitor-facing answers. Unlisted files never enter retrieval. Keep confidential material you do not want discussed outside the manifest. Public downloads still require a valid visitor session.

## Chat and semantic search

Typed and suggested questions use the same LLM intent decision and response pipeline. Social conversation and conversation recall do not require document evidence. Career and project claims use the current owner's profile and retrieved documents, with sources collapsed in the UI.

Retrieval works immediately using keyword search. For semantic retrieval, explicitly run:

```powershell
python scripts/manage.py index
```

This command uses your backend API key and incurs embedding usage. It requires `PAID_AI_ENABLED=true`. Startup and deployment do not automatically call an embedding service. The generated FAISS index stays ignored by Git and is rejected if the profile, documents or embedding model change. Rebuild it after changing your content, or continue with keyword retrieval.

Chat uses bounded in-process memory, keeps the first message separately for recall, and refreshes trusted date context on every model call. Restarting the backend clears chats. There is no chat archive, database service, graph/GNN service or optional online evaluator enabled in this template.

## Useful commands

```powershell
python scripts/manage.py check        # Validate configuration/files; no API calls
python scripts/manage.py password     # Change the local access password interactively
python scripts/manage.py bundle       # Create a private deployment context; no API calls
npm --prefix services/frontend run build
npm --prefix services/frontend run typecheck
npm --prefix services/frontend test
```

If local ports are occupied, change both origins in `.env.local`, for example `CV_PUBLIC_ORIGIN=http://127.0.0.1:3300` and `CV_API_ORIGIN=http://127.0.0.1:8300`, then restart the preview. The launcher does not kill other processes, reinstall dependencies, overwrite environments or deploy.

For visual hot reload only, use `npm --prefix services/frontend run dev`. Vite on port 3001 does not run the password gate or inject private backend headers; test authenticated chat with the full preview.

## Deploy and customize safely

See [deployment instructions](docs/DEPLOYMENT.md) for Railway frontend and Cloud Run backend setup, including how ignored owner documents reach a hosted build. No account, project, domain, secret identifier or API key is preconfigured.

See [configuration](docs/CONFIGURATION.md), [architecture](docs/ARCHITECTURE.md), [security](SECURITY.md), and [third-party notices](THIRD_PARTY_NOTICES.md).

This repository is intended to be used as a fresh template. Personal configuration, documents, generated indexes and environment files are ignored by default. Deployment bundles contain private owner content and must stay private. Decide deliberately which public profile assets, if any, to put in your own repository.

## Development checks

```powershell
python -m pip install -r services/api/requirements-dev.txt
python -m pytest -q
npm --prefix services/frontend run typecheck
npm --prefix services/frontend test
npm --prefix services/frontend run build
python scripts/release_check.py
```

Tests use fictional content and mocked providers. The release check inspects staged/tracked files for private paths and credential-like values. It does not make model requests. The browser smoke test additionally requires `playwright` and its Chromium browser; see `tests/browser_smoke.py`.

MIT licensed. Fictional samples and neutral art are included for setup and demonstration.
