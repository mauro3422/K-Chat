#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${KAIROS_SERVICE:-kairos}"
PORT="${PORT:-8000}"
ACTION="${1:-help}"
health() { curl --fail --silent --show-error "http://127.0.0.1:${PORT}/health"; printf '\n'; }
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
    sudo systemctl restart "$SERVICE"
    for _ in {1..30}; do
      if health >/dev/null 2>&1; then health; exit 0; fi
      sleep 1
    done
    sudo systemctl status "$SERVICE" --no-pager
    exit 1
    ;;
  restart) sudo systemctl restart "$SERVICE"; health ;;
  status) sudo systemctl status "$SERVICE" --no-pager ;;
  logs) sudo journalctl -u "$SERVICE" -n "${2:-150}" --no-pager ;;
  follow-logs) sudo journalctl -u "$SERVICE" -f ;;
  health) health ;;
  platform) uname -a; printf 'node='; curl --fail --silent "http://127.0.0.1:${PORT}/api/node/state"; printf '\n' ;;
  *) echo "Uso: $0 {update|restart|status|logs [líneas]|follow-logs|health|platform}" >&2; exit 2 ;;
esac
