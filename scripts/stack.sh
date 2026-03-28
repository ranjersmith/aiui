#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCH_COMPOSE="$ROOT_DIR/infra/docker-compose.orchestrator.yml"
STANDALONE_COMPOSE="$ROOT_DIR/infra/docker-compose.standalone.yml"

DEFAULT_MODE="orchestrator"
MODE="$DEFAULT_MODE"
FOLLOW_LOGS="false"

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/stack.sh <command> [--standalone] [--orchestrator] [--follow]

Commands:
  up         Start stack (build + detached)
  down       Stop stack
  restart    Restart stack
  status     Show compose service status
  health     Query UI /health endpoint
  logs       Show compose logs (use --follow for live tail)
  help       Show this message

Modes:
  --orchestrator (default)
  --standalone

Examples:
  ./scripts/stack.sh up
  ./scripts/stack.sh status
  ./scripts/stack.sh health
  ./scripts/stack.sh logs --follow
  ./scripts/stack.sh up --standalone
USAGE
}

command="${1:-help}"
if [[ $# -gt 0 ]]; then
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --standalone)
      MODE="standalone"
      ;;
    --orchestrator)
      MODE="orchestrator"
      ;;
    --follow)
      FOLLOW_LOGS="true"
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
  shift
done

compose_file="$ORCH_COMPOSE"
health_url="http://127.0.0.1:${AIUI_ORCH_UI_PORT:-3311}/health"
if [[ "$MODE" == "standalone" ]]; then
  compose_file="$STANDALONE_COMPOSE"
  health_url="http://127.0.0.1:${AIUI_UI_PORT:-3310}/health"
fi

if [[ ! -f "$compose_file" ]]; then
  echo "Compose file not found: $compose_file" >&2
  exit 1
fi

compose() {
  docker compose -f "$compose_file" "$@"
}

echo "Mode: $MODE"
echo "Compose: $compose_file"

case "$command" in
  up)
    compose up -d --build
    ;;
  down)
    compose down
    ;;
  restart)
    compose down
    compose up -d --build
    ;;
  status)
    compose ps
    ;;
  health)
    curl -fsS "$health_url"
    echo
    ;;
  logs)
    if [[ "$FOLLOW_LOGS" == "true" ]]; then
      compose logs -f
    else
      compose logs --tail=200
    fi
    ;;
  help|--help|-h)
    usage
    ;;
  *)
    echo "Unknown command: $command" >&2
    usage
    exit 1
    ;;
esac
