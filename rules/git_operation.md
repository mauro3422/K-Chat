# git_operation
**Run safe Git operations (status, diff, log, branch, add, commit, push, pull, clone). Destructive operations (push --force, reset --hard) are BLOCKED.**

<!-- auto:params -->
| Parámetro | Tipo | Requerido | Default | Descripción |
|---|---|---|---|---|
| `count` | integer | No |  | Number of commits for log/diff (default: 5) |
| `cwd` | string | No |  | Working directory (default: $HOME) |
| `message` | string | No |  | Commit message (required for commit operation) |
| `operation` | string | Sí |  | Git operation to perform Values: status, diff, log, branch, add, commit, push, pull, clone |
| `path` | string | No |  | File path for add operation, or clone URL/directory |
