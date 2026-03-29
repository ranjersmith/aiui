#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Reference only existing compose files; docker-compose.frontend.yml is the active runtime.
FRONTEND_COMPOSE="$ROOT_DIR/docker-compose.frontend.yml"

DEFAULT_MODE="frontend"
MODE="$DEFAULT_MODE"
FOLLOW_LOGS="false"

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/stack.sh <command> [--follow]

Commands:
  up         Start frontend (build + detached)
  down       Stop frontend
  restart    Restart frontend
  status     Show compose service status
  health     Query UI /health endpoint
  logs       Show compose logs (use --follow for live tail)
  help       Show this message

Examples:
  ./scripts/stack.sh up
  ./scripts/stack.sh status
  ./scripts/stack.sh health
  ./scripts/stack.sh logs --follow
USAGE
}

command="${1:-help}"
if [[ $# -gt 0 ]]; then
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --follow)
      FOLLOW_LOGS="true"
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

compose_file="$FRONTEND_COMPOSE"
health_url="http://127.0.0.1:3311/health"

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
