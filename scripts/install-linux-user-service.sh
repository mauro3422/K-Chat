#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${KAIROS_SERVICE:-k-chat}"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT_FILE="$UNIT_DIR/${SERVICE}.service"

if [[ -x "$ROOT/venv/bin/uvicorn" ]]; then
  EXEC_START="$ROOT/venv/bin/uvicorn"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  EXEC_START="$ROOT/.venv/bin/python -m uvicorn"
else
  EXEC_START="$(command -v python3) -m uvicorn"
fi

install -d -m 700 "$UNIT_DIR"
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Kairos web service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
EnvironmentFile=-$ROOT/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=$EXEC_START web.server:app --host 0.0.0.0 --port 8000 --log-level info --no-access-log --timeout-graceful-shutdown 8
Restart=always
RestartSec=5
KillMode=mixed
TimeoutStopSec=12
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=read-only
ProtectSystem=full
ReadWritePaths=$ROOT

[Install]
WantedBy=default.target
EOF
chmod 600 "$UNIT_FILE"
systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE"
systemctl --user restart "$SERVICE"
echo "service=$SERVICE unit=$UNIT_FILE"
