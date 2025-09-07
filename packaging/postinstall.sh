#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/back2blaze"
CONF_DIR="/etc/back2blaze"
DATA_DIR="/var/lib/back2blaze"
LOG_DIR="/var/log/back2blaze"
VENV_DIR="$APP_DIR/venv"
BIN_FILE="$APP_DIR/bin/back2blaze"
USER="back2blaze"
GROUP="back2blaze"

id -u "$USER" >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin "$USER"
getent group "$GROUP" >/dev/null 2>&1 || groupadd --system "$GROUP"
usermod -a -G "$GROUP" "$USER" || true

mkdir -p "$CONF_DIR"
mkdir -p "$APP_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$LOG_DIR"

if [ ! -x "$BIN_FILE" ]; then
  if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
  fi
  "$VENV_DIR/bin/pip" install --upgrade pip
  if [ -f "$APP_DIR/requirements.txt" ]; then
    "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"
  fi
  if [ -f "$APP_DIR/back2blaze-wrapper.sh" ]; then
    mkdir -p "$APP_DIR/bin"
    ln -sf "$APP_DIR/back2blaze-wrapper.sh" "$BIN_FILE"
    chmod +x "$APP_DIR/back2blaze-wrapper.sh"
  fi
fi

chown -R "$USER":"$GROUP" "$APP_DIR" "$CONF_DIR" "$DATA_DIR" "$LOG_DIR"

systemctl daemon-reload || true
echo "Post-install complete. Configure /etc/back2blaze/config.toml and enable the service."
