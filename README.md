# aiui

Minimal modular LLM web UI.

## What This Product Is

- Frontend: Solid-based static web UI
- Runtime: Nginx container serving static assets and runtime config
- LLM access: OpenAI-compatible streaming API via same-origin reverse proxy
- Optional backend bridge: `/chat` via `app.py` for `aiui-proxy` mode

## Active Runtime Path

- Compose entry: `docker-compose.frontend.yml`
- Frontend image: `Dockerfile.frontend`
- Frontend source entry: `frontend/app.ts`
- Built bundle: `static/app.js`

## Quick Start

```bash
cd /home/ra/aiui
sudo docker compose -f docker-compose.frontend.yml up -d --build
```

Open: `http://127.0.0.1:3311`

## Runtime Configuration

Container env vars (see `docker-compose.frontend.yml`):

- `LLM_UI_PROVIDER`: `openai` or `aiui-proxy`
- `LLM_UI_BASE_URL`: default `/llm` for openai mode
- `LLM_UI_PROXY_TARGET`: upstream LLM server base (for nginx proxy)
- `LLM_UI_PROXY_AUTH_HEADER`: optional `Bearer <token>` passed server-side only
- `LLM_UI_MODEL`
- `LLM_UI_TEMPERATURE`
- `LLM_UI_MAX_TOKENS`

## Security Model

- Browser runtime config never contains API keys
- Auth header is injected by nginx proxy from server env
- `/llm` proxy allows only `GET`, `POST`, `OPTIONS`

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
