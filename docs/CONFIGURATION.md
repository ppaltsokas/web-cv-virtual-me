# Owner configuration

`config/profile.example.json` is the complete fictional example. `python scripts/manage.py init` copies it to an ignored local profile and creates a local content manifest. The frontend and backend use the same selected profile.

| Configuration | Purpose |
| --- | --- |
| `resume.personalInfo` | Public name, title, introduction, email, location and HTTPS social links |
| `resume.experience` | Roles, companies, periods, descriptions and technology tags |
| `resume.education` | Degrees, institutions, years and optional grades |
| `resume.certifications` | Credentials with optional image and HTTPS credential link |
| `resume.latestProjects` | Professional/highlighted projects |
| `resume.projects` | Personal projects; `pdfPath` is a public manifest document ID |
| `resume.skills` | Named categories and skill tags |
| `chat` | Chat display name, greeting, input hint, avatar and persona voice |
| `entrance` | Configurable title/subtitle; `{name}` expands to the configured name |
| `site` | Page title, description and optional public HTTPS URL |
| `timezone` | IANA timezone for trusted current-date context |
| `birthMonthYear` | Optional verified birth month/year, excluded from the browser profile |

Required collections may be empty arrays. The backend validates the full schema; unknown fields are rejected so API keys cannot accidentally become profile fields. Keep the public profile concise (up to 20,000 characters of evidence); place detailed material in documents. The frontend serializes only explicit display fields and uses the same manifest to show available public downloads.

The manifest's `documents` collection accepts `id`, `label`, `path`, `kind` (`summary`, `cv` or `document`) and `public`. IDs and source labels must be unique. Paths resolve inside the project root; symlinks or relative paths escaping that root are rejected. Each file must be at most 20 MiB. A PDF may contain up to 400 pages; combined extracted text is bounded. Only text-based PDFs are supported directly.

Use labels you are comfortable showing in the chat's Sources disclosure. Host filesystem paths are not source labels. A PDF can participate in retrieval without being available for download. Make the CV `public: true` to show its download button, and mark only selected project PDFs public.

Backend provider settings are in `.env.local` locally or injected by the hosting platform. The selected model is configurable; the supplied default matches the app's existing Chat Completions and structured intent interface. Choose a compatible model if changing it. There are no automatic OpenAI SDK retries. Each normal reply uses an intent call plus a response call; semantic retrieval uses a query embedding when an index is present, and invalid citations can trigger one additional bounded correction call. Output is capped at 1536 tokens per call; these are usage controls, not a monetary spending limit.

Advanced file selection uses `PORTFOLIO_PROFILE` and `CONTENT_MANIFEST`. Both services must select the same owner configuration. The default search order is the explicit path, the corresponding `.local.json`, then the fictional `.example.json`. The Node frontend's runtime profile must match the profile used for its build. Rebuild after changing display data.

The owner may use different local and hosted access passwords. `CV_ACCESS_PASSWORD` is an owner-only local convenience value; the gate verifies `CV_ACCESS_PASSWORD_HASH`. The backend receives the shared `CV_API_PROXY_SECRET`, not the plaintext visitor password. Generate a separate credential bundle for a new owner; never copy one from another portfolio.
