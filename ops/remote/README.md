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
python ops/remote/kairos_remote.py health --node linux
python ops/remote/kairos_remote.py pull --node linux
python ops/remote/kairos_remote.py restart --node linux
python ops/remote/kairos_remote.py logs --node linux --lines 200
python ops/remote/kairos_remote.py chat --node linux --message "respondé solo pong"
```

## Design

- SSH is the first operational transport.
- HTTP is used for live Kairos health and chat checks.
- Actions should produce short, useful output.
- Future Kairos tools should call this layer or reuse its contracts.
- Secrets stay local; committed files only contain examples.
