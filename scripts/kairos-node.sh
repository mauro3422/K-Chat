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
BACKUP_ROOT="${KAIROS_BACKUP_ROOT:-$ROOT/.kairos/backups}"
BACKUP_KEEP="${KAIROS_BACKUP_KEEP:-7}"
MIN_FREE_KB="${KAIROS_MIN_FREE_KB:-1048576}"
ACTION="${1:-help}"

health() {
  curl --fail --silent --show-error "http://127.0.0.1:${PORT}/health"
  printf '\n'
}

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

require_command() {
  command -v "$1" >/dev/null 2>&1 || { echo "Falta comando requerido: $1" >&2; return 1; }
}

preflight() {
  local failed=0 free_kb listeners
  cd "$ROOT"
  for command_name in git curl sqlite3 npm systemctl; do
    require_command "$command_name" || failed=1
  done
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "No es un repositorio Git: $ROOT" >&2; failed=1; }
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Hay cambios versionados sin confirmar." >&2
    failed=1
  fi
  git rev-parse --verify '@{upstream}' >/dev/null 2>&1 || { echo "La rama actual no tiene upstream." >&2; failed=1; }
  free_kb="$(df -Pk "$ROOT" | awk 'NR==2 {print $4}')"
  if [[ ! "$free_kb" =~ ^[0-9]+$ ]] || (( free_kb < MIN_FREE_KB )); then
    echo "Espacio insuficiente: ${free_kb:-desconocido} KB libres; mínimo ${MIN_FREE_KB} KB." >&2
    failed=1
  fi
  if command -v ss >/dev/null 2>&1; then
    listeners="$(ss -ltnp 2>/dev/null | awk -v port=":${PORT}" '$4 ~ port"$" {count++} END {print count+0}')"
    (( listeners <= 1 )) || { echo "Hay múltiples listeners en el puerto ${PORT}." >&2; failed=1; }
  fi
  service_control is-active --quiet || echo "ADVERTENCIA: el servicio ${SERVICE} no está activo." >&2
  health >/dev/null 2>&1 || echo "ADVERTENCIA: /health no responde; update puede repararlo." >&2
  curl --fail --silent "http://127.0.0.1:${PORT}/api/node/runtime" >/dev/null 2>&1 || \
    echo "ADVERTENCIA: no se pudo comprobar el runtime LAN." >&2
  (( failed == 0 )) || return 1
  printf 'preflight=ok repo=%s service=%s scope=%s free_kb=%s\n' "$ROOT" "$SERVICE" "$SERVICE_SCOPE" "$free_kb"
}

backup() {
  local timestamp destination source relative target manifest
  require_command sqlite3
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  destination="$BACKUP_ROOT/$timestamp"
  while [[ -e "$destination" ]]; do
    sleep 1
    timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
    destination="$BACKUP_ROOT/$timestamp"
  done
  install -d -m 700 "$BACKUP_ROOT" "$destination" "$destination/databases" "$destination/config"
  manifest="$destination/manifest.txt"
  {
    printf 'created_utc=%s\n' "$timestamp"
    printf 'commit=%s\n' "$(git -C "$ROOT" rev-parse HEAD)"
    printf 'branch=%s\n' "$(git -C "$ROOT" branch --show-current)"
    printf 'service=%s\nservice_scope=%s\n' "$SERVICE" "$SERVICE_SCOPE"
  } > "$manifest"
  chmod 600 "$manifest"
  for database_root in "$ROOT/data" "$ROOT/memory"; do
    [[ -d "$database_root" ]] || continue
    while IFS= read -r -d '' source; do
      relative="${source#"$ROOT"/}"
      target="$destination/databases/$relative"
      install -d -m 700 "$(dirname "$target")"
      sqlite3 "$source" ".backup '$target'"
      chmod 600 "$target"
      printf 'database=%s\n' "$relative" >> "$manifest"
    done < <(find "$database_root" -xdev -type f \( -name '*.db' -o -name '*.sqlite' \) \
      -not -path "$ROOT/data/fastembed_cache/*" -not -path "$ROOT/data/huggingface/*" -print0)
  done
  for source in "$ROOT/MEMORY.md" "$ROOT/.env" "$CONTROL_CONFIG"; do
    if [[ -f "$source" ]]; then
      cp -p "$source" "$destination/config/$(basename "$source")"
      chmod 600 "$destination/config/$(basename "$source")"
    fi
  done
  find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\0' \
    | sort -z -rn | tail -z -n "+$((BACKUP_KEEP + 1))" \
    | cut -z -d' ' -f2- | xargs -0r rm -rf --
  printf 'backup=%s\n' "$destination"
}

restore_backup() {
  local backup_id="${1:-}" source_root relative source target temporary
  [[ "$backup_id" =~ ^[0-9]{8}T[0-9]{6}Z$ ]] || {
    echo "Identificador de backup inválido: $backup_id" >&2
    return 2
  }
  source_root="$BACKUP_ROOT/$backup_id"
  [[ -f "$source_root/manifest.txt" && -d "$source_root/databases" ]] || {
    echo "Backup inexistente o incompleto: $source_root" >&2
    return 2
  }
  while IFS= read -r source; do
    [[ "$(sqlite3 "$source" 'PRAGMA integrity_check;')" == "ok" ]] || {
      echo "Base inválida en backup: $source" >&2
      return 1
    }
  done < <(find "$source_root/databases" -type f \( -name '*.db' -o -name '*.sqlite' \))

  backup
  trap 'service_control start >/dev/null 2>&1 || true' RETURN
  service_control stop
  while IFS= read -r -d '' source; do
    relative="${source#"$source_root/databases/"}"
    [[ "$relative" == data/* || "$relative" == memory/* ]] || {
      echo "Ruta no permitida en backup: $relative" >&2
      return 1
    }
    target="$ROOT/$relative"
    install -d -m 700 "$(dirname "$target")"
    temporary="${target}.restore.$$"
    install -m 600 "$source" "$temporary"
    mv -f "$temporary" "$target"
  done < <(find "$source_root/databases" -type f \( -name '*.db' -o -name '*.sqlite' \) -print0)
  if [[ -f "$source_root/config/MEMORY.md" ]]; then
    install -m 600 "$source_root/config/MEMORY.md" "$ROOT/MEMORY.md.restore.$$"
    mv -f "$ROOT/MEMORY.md.restore.$$" "$ROOT/MEMORY.md"
  fi
  service_control start
  wait_for_health
  trap - RETURN
  printf 'restore=ok backup=%s\n' "$backup_id"
}

rollback_to() {
  local target="${1:-}"
  cd "$ROOT"
  if [[ -z "$target" && -f "$ROOT/.kairos/last-good-commit" ]]; then
    target="$(<"$ROOT/.kairos/last-good-commit")"
  fi
  [[ -n "$target" ]] || { echo "No hay commit de rollback registrado." >&2; return 2; }
  git cat-file -e "${target}^{commit}" 2>/dev/null || { echo "Commit de rollback inválido: $target" >&2; return 2; }
  if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "Rollback cancelado: hay cambios versionados sin confirmar." >&2
    return 2
  fi
  git reset --hard "$target"
  if [[ -x venv/bin/pip ]]; then venv/bin/pip install -r requirements.txt; fi
  npm ci
  npm run build
  service_control restart
  wait_for_health
  printf 'rollback=ok commit=%s\n' "$(git rev-parse --short HEAD)"
}

update() {
  local previous_commit
  cd "$ROOT"
  preflight
  backup
  previous_commit="$(git rev-parse HEAD)"
  install -d -m 700 "$ROOT/.kairos"
  printf '%s\n' "$previous_commit" > "$ROOT/.kairos/last-good-commit"
  git pull --ff-only
  if ! {
    if [[ -x venv/bin/pip ]]; then venv/bin/pip install -r requirements.txt; fi &&
    npm ci &&
    npm run build &&
    service_control restart &&
    wait_for_health
  }; then
    echo "Update falló; restaurando $previous_commit." >&2
    rollback_to "$previous_commit"
    return 1
  fi
  printf 'update=ok commit=%s previous=%s\n' "$(git rev-parse --short HEAD)" "${previous_commit:0:7}"
}

case "$ACTION" in
  preflight) preflight ;;
  backup) backup ;;
  restore) restore_backup "${2:-}" ;;
  update) update ;;
  rollback) rollback_to "${2:-}" ;;
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
  *) echo "Uso: $0 {preflight|backup|update|rollback [commit]|restart|status|logs [líneas]|follow-logs|health|platform}" >&2; exit 2 ;;
esac
