#!/bin/bash
set -euo pipefail

ENV_FILE="/etc/back2blaze/.env"
test -f "$ENV_FILE" && source "$ENV_FILE"

APP_DIR="${APP_DIR:-/opt/back2blaze}"
VENV_DIR="$APP_DIR/venv"
PYTHON_SCRIPT="$APP_DIR/main.py"
COMPILED_BIN="$APP_DIR/bin/back2blaze"

if [ -x "$COMPILED_BIN" ]; then
  exec "$COMPILED_BIN" "$@"
elif [ -f "$PYTHON_SCRIPT" ] && [ -x "$VENV_DIR/bin/python" ]; then
  exec "$VENV_DIR/bin/python" "$PYTHON_SCRIPT" "$@"
else
  echo "Error: Neither compiled binary nor Python script found or executable." >&2
  exit 1
fi
