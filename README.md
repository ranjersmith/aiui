# aiui

Minimal modular LLM web UI.

## What This Product Is

- Frontend: Solid-based static web UI
- Runtime: Node.js HTTP server streaming static assets and injecting runtime config
- LLM access: OpenAI-compatible streaming API via same-origin reverse proxy
- Optional backend bridge: `/chat` via `app.py` for `aiui-proxy` mode (legacy)

## Active Runtime Path

- Compose entry: `docker-compose.frontend.yml`
- Frontend image: `Dockerfile.frontend`
- Frontend source entry: `frontend/app.ts`
- Built bundle: `static/app.js`

## Security Model

### Architecture
The aiui runtime is **completely static once built**:
1. **Browser config injection**: Runtime environment variables (provider, base URL, model, etc.) are injected **server-side into `runtime-config.js`** — the browser **never receives raw API keys or secrets**.
2. **Same-origin proxy**: In OpenAI-compatible mode, the frontend talks to `/llm` or a configured base URL. Proxy auth headers are **injected server-side by nginx** or forwarded infrastructure, never exposed to the browser.
3. **Zero client-side secrets**: The static JavaScript bundle contains no credentials, only configuration for public endpoints.

### Request Security
- **Rate limiting**: 10 requests/second per server by default. Override with `AIUI_MAX_REQUESTS_PER_SECOND`.
- **Attachment guardrails**:
  - Max 4 attachments per request (configurable: `AIUI_MAX_ATTACHMENTS`)
  - Max 25 MB total attachment payload (configurable: `AIUI_MAX_ATTACHMENT_BYTES_PER_REQUEST`)
  - Max 16 KB text extracted per document (configurable: `AIUI_MAX_DOCUMENT_TEXT_CHARS`)
- **External extractors disabled by default**: `.doc` and `.ppt` format extraction (via `catdoc`, `catppt`, `antiword`) requires explicit opt-in: `AIUI_ENABLE_EXTERNAL_EXTRACTORS=1`.

### HTTP Headers
The static server injects baseline security headers on all responses:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: SAMEORIGIN`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`

## Quick Start

```bash
cd /home/ra/aiui
sudo docker compose -f docker-compose.frontend.yml up -d --build
```

Open: `http://127.0.0.1:3311`

## Runtime Configuration

Container env vars (see `docker-compose.frontend.yml`):

- `LLM_UI_PROVIDER`: `openai` (default) — OpenAI-compatible API mode
- `LLM_UI_BASE_URL`: The **browser**-facing URL for the LLM API proxy (default: `/llm` for same-origin, or full URL like `http://your-host:8081`)
- `LLM_UI_MODEL`: Model name sent to the upstream API
- `LLM_UI_TEMPERATURE`: Sampling temperature
- `LLM_UI_MAX_TOKENS`: Max completion length
- `LLM_UI_SYSTEM_PROMPT`: Optional system prompt override

### Backend Security Configuration (when using `app.py`)
- `AIUI_OPENAI_API_KEY`: API key for upstream LLM service (optional; injected server-side)
- `AIUI_MAX_REQUESTS_PER_SECOND`: Rate limit (default 10)
- `AIUI_MAX_ATTACHMENTS`: Max attachments per request (default 4)
- `AIUI_MAX_ATTACHMENT_BYTES_PER_REQUEST`: Max total attachment size in bytes (default 25 MB)
- `AIUI_ENABLE_EXTERNAL_EXTRACTORS`: Set to `1` to enable `.doc`/`.ppt` extraction (disabled by default)

## Development Checks

```bash
cd /home/ra/aiui
npm install
npm run build:frontend
npm run test:frontend
npm run lint:css
npm run lint:html
```

## Backend API

`app.py` provides the backend chat endpoint and health checks:

- `POST /chat` — Stream completions with message history and attachments
- `GET /health` — Health check with upstream reachability
- `GET /modules` — Module catalog (for agent/tool support)

**Note**: The generated `static/runtime-config.js` file should **not be versioned** in git. It is injected at container startup and must reflect the deployment environment's configuration.

## Development Checks

```bash
cd /home/ra/aiui
npm install
npm run build:frontend
npm run test:frontend
npm run lint:css
npm run lint:html
```

## Backend API (Kept)

`app.py` keeps the chat API path used by `aiui-proxy` mode:

- `POST /chat`
- `GET /health`
- `GET /modules`

Legacy static web UI serving is removed from the backend root path.
