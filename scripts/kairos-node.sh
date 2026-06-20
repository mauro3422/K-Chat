#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTROL_CONFIG="${KAIROS_CONTROL_CONFIG:-$ROOT/.kairos/remote-control.env}"
if [[ -f "$CONTROL_CONFIG" ]]; then
  # Configuración local de despliegue; no se versiona.
  # shellcheck disable=SC1090
  source "$CONTROL_CONFIG"
fi
SERVICE="${KAIROS_SERVICE:-kairos}"
SERVICE_SCOPE="${KAIROS_SERVICE_SCOPE:-system}"
PORT="${PORT:-8000}"
ACTION="${1:-help}"
health() { curl --fail --silent --show-error "http://127.0.0.1:${PORT}/health"; printf '\n'; }
wait_for_health() {
  local response
  for _ in {1..30}; do
    if response="$(curl --fail --silent --show-error "http://127.0.0.1:${PORT}/health" 2>/dev/null)"; then
      printf '%s\n' "$response"
      return 0
    fi
    sleep 1
  done
  service_control status --no-pager
  return 1
}
service_control() {
  if [[ "$SERVICE_SCOPE" == "user" ]]; then
    systemctl --user "$@" "$SERVICE"
  elif [[ "$SERVICE_SCOPE" == "system" ]]; then
    sudo systemctl "$@" "$SERVICE"
  else
    echo "KAIROS_SERVICE_SCOPE debe ser 'user' o 'system'." >&2
    return 2
  fi
}
case "$ACTION" in
  update)
    cd "$ROOT"
    if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
      echo "Hay cambios versionados sin confirmar; se cancela la actualización." >&2; exit 2
    fi
    git pull --ff-only
    if [[ -x .venv/bin/pip ]]; then .venv/bin/pip install -r requirements.txt; fi
    npm ci
    npm run build
    service_control restart
    wait_for_health
    ;;
  restart) service_control restart; wait_for_health ;;
  status) service_control status --no-pager ;;
  logs)
    if [[ "$SERVICE_SCOPE" == "user" ]]; then journalctl --user -u "$SERVICE" -n "${2:-150}" --no-pager
    else sudo journalctl -u "$SERVICE" -n "${2:-150}" --no-pager; fi
    ;;
  follow-logs)
    if [[ "$SERVICE_SCOPE" == "user" ]]; then journalctl --user -u "$SERVICE" -f
    else sudo journalctl -u "$SERVICE" -f; fi
    ;;
  health) health ;;
  platform) uname -a; printf 'node='; curl --fail --silent "http://127.0.0.1:${PORT}/api/node/state"; printf '\n' ;;
  *) echo "Uso: $0 {update|restart|status|logs [líneas]|follow-logs|health|platform}" >&2; exit 2 ;;
esac
