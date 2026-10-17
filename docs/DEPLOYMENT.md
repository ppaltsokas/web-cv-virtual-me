# Railway frontend and Cloud Run backend

These instructions create your own services. Nothing in the template is connected to an existing account, domain, deployment trigger or cloud project. Use one frontend instance and one backend worker initially because access sessions, conversation memory and admission limits are process-local.

## Choose the content source deliberately

A Git-based deployment sees tracked files only. Ignored `.local.json` files and `content/private/` on your laptop do not automatically reach Railway or Cloud Build.

For a fictional sample deployment, build directly from the template repository. For your real portfolio, use the explicit private bundle workflow:

```powershell
python scripts/manage.py check
python scripts/manage.py bundle
```

This creates `data/deploy-context/`, containing application source, the selected profile and selected document files. It omits dotenv credentials, dependency directories, chats and unrelated local files. It is ignored by Git and must remain private. The command refuses to overwrite an existing context. Move an old reviewed context aside or remove it deliberately before creating a fresh one.

If a valid current-owner semantic index exists locally, the bundle includes it and rebinds its fingerprint to the bundled document paths without calling an API. Otherwise the deployed app uses keyword retrieval. To enable semantic search, build an index explicitly before bundling. Do not build embeddings automatically during a container build.

The ordinary repository `.dockerignore` excludes real local owner data. The generated context has its own deliberate build boundary that includes selected owner data and excludes secrets. Do not use a private deployment context as a public template download.

## Runtime variables

| Variable | Frontend | Backend |
| --- | --- | --- |
| `PRIVATE_CV_ENABLED=true` | Yes | Yes |
| `CV_PUBLIC_ORIGIN` | Exact HTTPS portfolio origin | Not required |
| `CV_API_ORIGIN` | Exact HTTPS Cloud Run origin | Not required |
| `CV_ACCESS_PASSWORD_HASH` | Owner's generated scrypt hash | No |
| `CV_API_PROXY_SECRET` | Owner's generated shared secret | Same value |
| `OPENAI_API_KEY` | No | Owner's provider key |
| `OPENAI_CHAT_MODEL` | No | Compatible model, default `gpt-4.1-mini` |
| `PAID_AI_ENABLED` | No | Start `false`; enable when configured |
| `CHAT_MAX_OUTPUT_TOKENS` | No | Default `1536`; maximum `1536` |
| `LOAD_DOTENV=false` | Optional | Yes |

Set secrets through the hosting platform's secret/variable controls. Do not commit `.env.local`, pass its complete contents to a secret field, or put the plaintext sign-in password in `CV_ACCESS_PASSWORD_HASH`. Hosted frontend access requires HTTPS origins and complete credentials. The plaintext local convenience value `CV_ACCESS_PASSWORD` is not needed by either hosted service.

## Backend on Google Cloud

1. Select your Google Cloud project, billing account and region. Enable Cloud Build, Artifact Registry, Cloud Run and Secret Manager. Create a Docker repository in Artifact Registry. Give the build identity permission to write images and deploy according to your project's policy.
2. Add your provider key and generated proxy secret as separate Secret Manager secrets. Grant only the backend runtime service account access to the needed secrets. Use the actual secret versions you created.
3. Build the backend using `infra/cloudbuild.api.yaml` from your chosen context. The build needs no model API key. In PowerShell, substitute your own values:

```powershell
$projectId = 'YOUR_PROJECT_ID'
$region = 'YOUR_REGION'
$repository = 'YOUR_ARTIFACT_REPOSITORY'
$image = "$region-docker.pkg.dev/$projectId/$repository/portfolio-api:v1"
gcloud builds submit data/deploy-context --config infra/cloudbuild.api.yaml --project $projectId --region $region --substitutions "_IMAGE=$image"
```

For a sample-only build, replace `data/deploy-context` with `.`. The config path above refers to the config in the checkout from which you run the command.

4. Deploy that image to a new Cloud Run service. Configure the backend variables and Secret Manager references in the Cloud Run UI, or adapt this command with your own secret names and numeric versions:

```powershell
gcloud run deploy portfolio-api --image $image --project $projectId --region $region --allow-unauthenticated --concurrency 4 --max-instances 1 --set-env-vars 'LOAD_DOTENV=false,PRIVATE_CV_ENABLED=true,PAID_AI_ENABLED=false,OPENAI_CHAT_MODEL=gpt-4.1-mini,CHAT_MAX_OUTPUT_TOKENS=1536' --set-secrets 'OPENAI_API_KEY=YOUR_OPENAI_SECRET:1,CV_API_PROXY_SECRET=YOUR_PROXY_SECRET:1'
```

Cloud Run's unauthenticated network access permits the Node proxy to connect; the application still requires its private proxy key and visitor identity for chat. The public `/health` endpoint should return healthy. Direct `/me/cv` and `/chat` requests without the proxy headers should return 403. Do not connect the generic template to someone else's service account or project.

## Frontend on Railway

For the fictional demo, create a new Railway service from your copy of the GitHub template, with the repository root as its root directory. `railway.json` selects the root `Dockerfile`; it builds and serves the frontend. Keep one replica.

For a real owner profile whose files remain private locally, upload only the deliberately prepared context using Railway's CLI, linked to **your new frontend service**:

```powershell
railway link
railway up data/deploy-context --path-as-root --no-gitignore --service YOUR_FRONTEND_SERVICE
```

Here `--no-gitignore` is limited to the reviewed context, which contains selected owner inputs and no dotenv credentials. Never run that flag against the original working checkout. CLI uploads respect Git ignore rules by default, so using the explicit context boundary matters. See the [Railway upload reference](https://docs.railway.com/cli/up).

Generate a Railway domain or attach your own domain. Configure the frontend runtime values in the table using that exact HTTPS origin and your backend's HTTPS origin. Use the same proxy secret on both services. No provider API key belongs on Railway's frontend service. Restart after changing access credentials.

Disable Git auto-deploys for this real-content service if they would replace your private uploaded configuration with the repository's fictional sample. For continuous deployment, provide the same reviewed owner configuration and documents from an owner-controlled private source before building; do not assume local ignored files are present in CI.

## End-to-end verification

- Open the exact public domain in a fresh browser session. Confirm private assets, CV downloads and API requests are blocked before sign-in.
- Sign in, confirm your own profile and current CV appear, and inspect the chatbot's health/setup state.
- Enable `PAID_AI_ENABLED=true` on the backend when you are ready for paid calls. Ask a greeting, an experience question, a project question and a conversation-recall question.
- Verify no fictional example claims survive in your real profile/summary and that sources refer to your selected documents.
- Test a wrong password, a mobile screen, a missing source and an unsupported claim. Inspect platform logs for errors without logging raw messages or credentials.

The template's local build, mocked provider tests and browser checks do not themselves establish a successful hosted deployment. Container builds and actual cloud deployment should be checked in your own environment.

Provider integration follows the [official OpenAI Chat Completions reference](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create). Cloud commands follow the official [build submit](https://cloud.google.com/sdk/gcloud/reference/builds/submit) and [Cloud Run deploy](https://cloud.google.com/sdk/gcloud/reference/run/deploy) references.
