# Memory Roadmap (Current Product)

This repository now ships a minimal modular LLM web UI.

## Current Architecture

- Frontend runtime source: `frontend/app.ts`
- Frontend providers:
  - `frontend/providers/openaiCompatible.ts`
  - `frontend/providers/aiuiProxy.ts`
- Runtime config parser: `frontend/core/config.mjs`
- SSE parser: `frontend/core/sse.mjs`
- Frontend container:
  - `Dockerfile.frontend`
  - `docker-compose.frontend.yml`
  - `docker/frontend/nginx.conf.template`
  - `docker/frontend/entrypoint.sh`

## Product Principles

- Keep browser bundle small and deterministic
- Keep LLM credentials server-side only
- Prefer OpenAI-compatible provider path for modularity
- Maintain empirical performance metrics in UI (first token latency, flush rate)

## Keep

- `frontend`
- `frontend-tests`
- `static`
- `docker`
- `docker-compose.frontend.yml`
- `Dockerfile.frontend`
- `scripts/build_frontend.mjs`
- `app.py` chat API path

## Removed Legacy Scope

- Legacy React-era frontend modules
- Legacy KaTeX static vendor payload
- Legacy backend web UI serving path
- Orchestrator-era folders removed per product scope decision

## Validation Commands

```bash
npm run build:frontend
npm run test:frontend
npm run lint:css
npm run lint:html
sudo docker compose -f docker-compose.frontend.yml up -d --build
```
