# Kairos Remote

Portable control layer for Kairos nodes.

This folder is the future home for multi-PC operations. The PowerShell wrapper in
`scripts/remote-kairos.ps1` is kept as a Windows convenience, but the core logic
should live here in Python so it can later become a Kairos tool.

## Config

By default the client reads:

```text
.kairos/remote-nodes.json
```

That file is local and should not be committed. Use:

```text
ops/remote/nodes.example.json
```

as the template.

If no config file exists, the client still supports the legacy environment
variables:

```text
KAIROS_LINUX_HOST
KAIROS_LINUX_USER
KAIROS_LINUX_REPO
KAIROS_LINUX_IDENTITY
KAIROS_LINUX_BASE_URL
```

## Commands

```bash
python ops/remote/kairos_remote.py list
python ops/remote/kairos_remote.py doctor --node linux
python ops/remote/kairos_remote.py doctor --node linux --json
python ops/remote/kairos_remote.py health --node linux
python ops/remote/kairos_remote.py pull --node linux
python ops/remote/kairos_remote.py restart --node linux
python ops/remote/kairos_remote.py logs --node linux --lines 200
python ops/remote/kairos_remote.py kairos-python --node linux --command "scripts/memory_audit.py"
python ops/remote/kairos_remote.py memory-preflight --node linux
python ops/remote/kairos_remote.py chat --node linux --message "respondé solo pong"
```

`doctor` is the main field check for remote operations. It validates the node
profile, SSH, repo state, control script, Python, `/health`, node state, sync and
failover. Human output includes a `likely` line when something fails; `--json`
emits the same checks as structured data for a future Kairos tool.

For Python scripts on a remote node, prefer `kairos-python` instead of `exec`
with a raw `python` command. It runs inside the repo and resolves the interpreter
in this order: `venv/bin/python`, `.venv/bin/python`, then `python3`. The doctor
also imports `fastembed`, so it fails early if the selected interpreter cannot
run the embedding stack.

Use `memory-preflight` after memory catalog changes. It runs the conservative
processing-catalog backfill and memory audit on the local node and the selected
remote node, prints the short node diff, and exits non-zero if any node remains
inconsistent.

By default, `chat` wraps the message with a short Codex delegation guide. This
lets the remote Kairos know that the request comes from an operator/agent doing
LAN checks or task delegation, not necessarily from Mauro typing in the normal
UI.

Use raw mode only when you need to test the exact user-facing chat path:

```bash
python ops/remote/kairos_remote.py chat --node linux --message "hola" --raw-message
```

## Codex task bridge

When Mauro is working from the laptop, Kairos can delegate real work to Codex on
the primary PC. This is a conversation-backed task, not automatic execution:
Codex must claim it, work, and write the result back.

```bash
python ops/remote/kairos_remote.py task-create --node pc --title "Fix laptop health" --message "Investigate /health failing on the laptop"
python ops/remote/kairos_remote.py task-list --node pc
python ops/remote/kairos_remote.py task-show --node pc --task-id ctx-abc123
python ops/remote/kairos_remote.py task-update --node pc --task-id ctx-abc123 --task-status running --message "Codex started"
python ops/remote/kairos_remote.py task-update --node pc --task-id ctx-abc123 --task-status done --message "Fixed and pushed"
```

From inside Kairos, the `delegate_to_codex` tool creates the same task through
`KAIROS_CODEX_BRIDGE_URL` or `KAIROS_PRIMARY_URL`.

## Design

- SSH is the first operational transport.
- HTTP is used for live Kairos health and chat checks.
- Actions should produce short, useful output.
- Future Kairos tools should call this layer or reuse its contracts.
- Secrets stay local; committed files only contain examples.
