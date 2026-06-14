# Skill: DB Query Guide

Quick database queries for K-Chat — search sessions, messages, widgets, and debug info from the SQLite DB.

## Usage

When you need to find information about past sessions, widgets, or debugging data, use these commands directly:

### Recent sessions
```bash
sqlite3 memory/kairos_memory.db "SELECT session_id, name, created_at FROM sessions ORDER BY created_at DESC LIMIT 5;"
```

### Full conversation for a session
```bash
sqlite3 memory/kairos_memory.db "
  SELECT id, role, substr(content,1,200) as preview, created_at
  FROM messages WHERE session_id = '<id>'
  ORDER BY id;"
```

### Search messages by content
```bash
sqlite3 memory/kairos_memory.db "
  SELECT session_id, substr(content,1,100), created_at
  FROM messages WHERE content LIKE '%<term>%'
  ORDER BY created_at DESC LIMIT 10;"
```

### Debug info (model, reasoning, tools)
```bash
sqlite3 memory/kairos_memory.db "
  SELECT * FROM debug_info WHERE session_id = '<id>';"
```

### Widget states
```bash
sqlite3 memory/kairos_memory.db "
  SELECT * FROM widget_states WHERE session_id = '<id>';"
```

### Saved widgets (official)
```bash
sqlite3 memory/kairos_memory.db "
  SELECT widget_id, version, substr(code,1,60) FROM saved_widgets ORDER BY created_at DESC;"
```

### Tool calls
```bash
sqlite3 memory/kairos_memory.db "
  SELECT * FROM tool_calls WHERE session_id = '<id>' ORDER BY turn;"
```

### Memory index (custom key-value lookups)
```bash
sqlite3 memory/kairos_memory.db "
  SELECT * FROM memory_index WHERE session_id = '<id>' ORDER BY updated_at DESC;"
```

### Via API
```bash
curl localhost:8000/sessions/<id>/debug    # Debug info
curl localhost:8000/api/logs?level=E        # Server errors
curl localhost:8000/api/logs?module=<module> # By module
```

## DB location
`memory/kairos_memory.db` in the project root (K-Chat).
