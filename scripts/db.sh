#!/bin/bash
# db.sh — Quick K-Chat DB lookup
# Usage: ./scripts/db.sh search <term>
#        ./scripts/db.sh session <session_id>
#        ./scripts/db.sh recent [n]
#        ./scripts/db.sh errors
#        ./scripts/db.sh widgets
#        ./scripts/db.sh key <session_id> <key>

DB="${KAIROS_DB:-memory/kairos_memory.db}"
CDIR="$(cd "$(dirname "$0")/.." && pwd)"
DBPATH="$CDIR/$DB"

case "${1:-help}" in
  search)
    sqlite3 -header -column "$DBPATH" "
      SELECT m.session_id, substr(m.content,1,100) as msg, m.created_at
      FROM messages m
      WHERE m.content LIKE '%$2%'
      ORDER BY m.created_at DESC
      LIMIT 20;
    "
    ;;
  session)
    sqlite3 -header -column "$DBPATH" "
      SELECT m.id, m.role, substr(m.content,1,200) as msg, m.created_at
      FROM messages m
      WHERE m.session_id = '$2'
      ORDER BY m.id;
    "
    ;;
  recent)
    n="${2:-5}"
    sqlite3 -header -column "$DBPATH" "
      SELECT s.session_id, s.name, s.created_at, count(m.id) as msgs
      FROM sessions s
      LEFT JOIN messages m ON m.session_id = s.session_id
      GROUP BY s.session_id
      ORDER BY s.created_at DESC
      LIMIT $n;
    "
    ;;
  errors)
    sqlite3 -header -column "$DBPATH" "
      SELECT substr(content,1,150) as error, created_at
      FROM messages WHERE role = 'tool' AND content LIKE '%error%'
      ORDER BY created_at DESC LIMIT 10;
    "
    ;;
  widgets)
    sqlite3 -header -column "$DBPATH" "
      SELECT widget_id, version, substr(code,1,60) as code_preview, created_at
      FROM saved_widgets
      ORDER BY created_at DESC LIMIT 10;
    "
    ;;
  key)
    sqlite3 -header -column "$DBPATH" "
      SELECT key, value, updated_at
      FROM memory_index
      WHERE session_id = '$2' AND key LIKE '%$3%'
      ORDER BY updated_at DESC;
    "
    ;;
  debug)
    sqlite3 -header -column "$DBPATH" "
      SELECT model, substr(reasoning,1,100) as reasoning, substr(tool_calls,1,100) as tools, updated_at
      FROM debug_info
      WHERE session_id = '$2'
      ORDER BY updated_at DESC LIMIT 1;
    "
    ;;
  help|*)
    echo "Usage:"
    echo "  ./scripts/db.sh search <term>    — Search messages by content"
    echo "  ./scripts/db.sh session <id>     — Show full session conversation"
    echo "  ./scripts/db.sh recent [n]       — List recent sessions"
    echo "  ./scripts/db.sh errors           — Show recent tool errors"
    echo "  ./scripts/db.sh widgets          — List saved widgets"
    echo "  ./scripts/db.sh key <id> <k>     — Query memory_index by key"
    echo "  ./scripts/db.sh debug <id>       — Show debug info for session"
    echo ""
    echo "Env: KAIROS_DB=/path/to/custom.db"
    ;;
esac
