#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUBLIC_KEY="$ROOT/ops/ssh/kairos-codex-windows.pub"
SERVICE="${KAIROS_SERVICE:-kairos}"
SERVICE_SCOPE="${KAIROS_SERVICE_SCOPE:-system}"
REMOTE_USER="${SUDO_USER:-$USER}"
REMOTE_HOME="$(getent passwd "$REMOTE_USER" | cut -d: -f6)"
[[ -s "$PUBLIC_KEY" ]] || { echo "No se encontró la clave pública: $PUBLIC_KEY" >&2; exit 1; }
if ! command -v sshd >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then sudo apt-get update; sudo apt-get install -y openssh-server
  elif command -v pacman >/dev/null 2>&1; then sudo pacman -Sy --needed --noconfirm openssh
  elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y openssh-server
  elif command -v zypper >/dev/null 2>&1; then sudo zypper --non-interactive install openssh
  else echo "Gestor de paquetes no reconocido; instalá OpenSSH Server manualmente." >&2; exit 1; fi
fi
install -d -m 700 "$REMOTE_HOME/.ssh"
touch "$REMOTE_HOME/.ssh/authorized_keys"
grep -qxF "$(cat "$PUBLIC_KEY")" "$REMOTE_HOME/.ssh/authorized_keys" || cat "$PUBLIC_KEY" >> "$REMOTE_HOME/.ssh/authorized_keys"
chmod 600 "$REMOTE_HOME/.ssh/authorized_keys"
sudo chown -R "$REMOTE_USER:$REMOTE_USER" "$REMOTE_HOME/.ssh"
if systemctl list-unit-files --type=service | grep -q '^ssh.service'; then sudo systemctl enable --now ssh.service
else sudo systemctl enable --now sshd.service; fi
if command -v ufw >/dev/null 2>&1 && sudo ufw status | grep -q '^Status: active'; then
  sudo ufw allow from 192.168.1.0/24 to any port 22 proto tcp
elif command -v firewall-cmd >/dev/null 2>&1 && sudo firewall-cmd --state >/dev/null 2>&1; then
  sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="192.168.1.0/24" port protocol="tcp" port="22" accept'; sudo firewall-cmd --reload
fi
SUDOERS_FILE="/etc/sudoers.d/kairos-remote-$REMOTE_USER"
printf '%s ALL=(ALL) NOPASSWD: ALL\n' "$REMOTE_USER" | sudo tee "$SUDOERS_FILE" >/dev/null
sudo chmod 440 "$SUDOERS_FILE"; sudo visudo -cf "$SUDOERS_FILE"
PYTHON="$ROOT/.venv/bin/python"; [[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
if [[ "$SERVICE_SCOPE" == "system" ]]; then
  sudo tee "/etc/systemd/system/${SERVICE}.service" >/dev/null <<EOF
[Unit]
Description=Kairos web service
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
User=$REMOTE_USER
WorkingDirectory=$ROOT
EnvironmentFile=-$ROOT/.env
ExecStart=$PYTHON -m uvicorn web.server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
  sudo systemctl daemon-reload
  sudo systemctl enable --now "$SERVICE"
elif [[ "$SERVICE_SCOPE" == "user" ]]; then
  systemctl --user status "$SERVICE" --no-pager >/dev/null
else
  echo "KAIROS_SERVICE_SCOPE debe ser 'user' o 'system'." >&2
  exit 2
fi
install -d -m 700 "$ROOT/.kairos"
printf 'KAIROS_SERVICE=%q\nKAIROS_SERVICE_SCOPE=%q\n' "$SERVICE" "$SERVICE_SCOPE" > "$ROOT/.kairos/remote-control.env"
chmod +x "$ROOT/scripts/kairos-node.sh"
echo "REMOTE_USER=$REMOTE_USER"; echo "REMOTE_REPO=$ROOT"; echo "SERVICE=$SERVICE"; echo "SERVICE_SCOPE=$SERVICE_SCOPE"
