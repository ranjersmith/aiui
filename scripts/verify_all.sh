#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Ensure Python tools from project venv.
if [ ! -x "$ROOT_DIR/.venv/bin/python" ]; then
  echo "Missing .venv. Create it first:"
  echo "  cd $ROOT_DIR && python3 -m venv .venv"
  exit 1
fi

# Ensure Node tools are available for HTML/CSS linters.
if ! command -v node >/dev/null 2>&1; then
  if [ -s "$HOME/.nvm/nvm.sh" ]; then
    set +u
    # shellcheck disable=SC1090
    source "$HOME/.nvm/nvm.sh"
    nvm use --lts >/dev/null 2>&1 || true
    set -u
  fi
fi

if ! command -v node >/dev/null 2>&1; then
  echo "Node is not available. Install via: bash /home/ra/react_setup_beginner.sh machine"
  exit 1
fi

if [ ! -d "$ROOT_DIR/node_modules" ]; then
  echo "Missing node_modules. Run:"
  echo "  cd $ROOT_DIR && npm install"
  exit 1
fi

if [ ! -x "$ROOT_DIR/.tools/hadolint" ]; then
  echo "Missing hadolint binary at $ROOT_DIR/.tools/hadolint"
  echo "Install with:"
  echo "  mkdir -p $ROOT_DIR/.tools"
  echo "  curl -fsSL -o $ROOT_DIR/.tools/hadolint https://github.com/hadolint/hadolint/releases/latest/download/hadolint-Linux-x86_64"
  echo "  chmod +x $ROOT_DIR/.tools/hadolint"
  exit 1
fi

echo "[1/9] Frontend unit tests (node:test)"
node --test ./frontend-tests/**/*.test.mjs

echo "[2/9] Frontend build (local bundle, no CDN runtime)"
npm run -s build:frontend

echo "[3/9] Python lint (ruff)"
"$ROOT_DIR/.venv/bin/ruff" check .

echo "[4/9] Python type-check (mypy)"
"$ROOT_DIR/.venv/bin/python" -m mypy app.py tests

echo "[5/9] Python tests (pytest)"
"$ROOT_DIR/.venv/bin/python" -m pytest -q

echo "[6/9] YAML lint (yamllint)"
"$ROOT_DIR/.venv/bin/yamllint" -c .yamllint.yml \
  docker-compose.standalone.yml \
  infra/docker-compose.orchestrator.yml

echo "[7/9] Dockerfile lint (hadolint)"
"$ROOT_DIR/.tools/hadolint" Dockerfile

echo "[8/9] CSS lint (stylelint)"
npx --no-install stylelint "static/**/*.css" --ignore-pattern "static/vendor/**/*.css"

echo "[9/9] HTML lint (htmlhint)"
npx --no-install htmlhint "static/**/*.html"

echo "All checks passed."
