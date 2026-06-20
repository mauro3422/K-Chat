# Control remoto de la PC Linux

Instrucciones para la IA que opere la PC Linux `192.168.1.40`.

## Bootstrap inicial

Después de `git pull`, desde la raíz de Kairos:

```bash
chmod +x scripts/bootstrap-linux-remote-control.sh scripts/kairos-node.sh
./scripts/bootstrap-linux-remote-control.sh
```

Esto instala y activa OpenSSH Server, autoriza `ops/ssh/kairos-codex-windows.pub`, concede `sudo` sin contraseña al usuario actual y crea `kairos.service`.

Si la instalación ya tiene un servicio de usuario, indicarlo para no crear uno duplicado:

```bash
KAIROS_SERVICE=k-chat KAIROS_SERVICE_SCOPE=user ./scripts/bootstrap-linux-remote-control.sh
```

La selección queda guardada localmente en `.kairos/remote-control.env`.

Al finalizar, informar los valores impresos de `REMOTE_USER`, `REMOTE_REPO`, `SERVICE` y `SERVICE_SCOPE`.

## Verificación en Linux

```bash
systemctl status ssh --no-pager || systemctl status sshd --no-pager
systemctl --user status k-chat --no-pager
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/node/state
```

`/api/node/state` debe mostrar `"node_platform":"linux"`.

## Configuración en Windows

```powershell
[Environment]::SetEnvironmentVariable('KAIROS_LINUX_HOST','192.168.1.40','User')
[Environment]::SetEnvironmentVariable('KAIROS_LINUX_USER','<usuario-linux>','User')
[Environment]::SetEnvironmentVariable('KAIROS_LINUX_REPO','<ruta-absoluta-del-repo>','User')
```

Abrir otra terminal y usar:

```powershell
.\scripts\remote-kairos.ps1 -Action Preflight
.\scripts\remote-kairos.ps1 -Action Backup
.\scripts\remote-kairos.ps1 -Action Update
.\scripts\remote-kairos.ps1 -Action Rollback
.\scripts\remote-kairos.ps1 -Action Logs -Lines 200
.\scripts\remote-kairos.ps1 -Action Health
.\scripts\remote-kairos.ps1 -Action Shell
.\scripts\remote-kairos.ps1 -Action Exec -Command 'cualquier comando autorizado'
```

## Flujo robusto de actualización

`Preflight` valida comandos requeridos, repositorio limpio, upstream, espacio libre, servicio, puerto, salud y coordinación LAN. Las advertencias de salud no bloquean una actualización reparadora.

`Backup` crea copias consistentes de todas las bases SQLite mediante `.backup`, además de `MEMORY.md`, `.env` y la configuración local. Los respaldos quedan con permisos privados en `.kairos/backups/`; por defecto se conservan los siete más recientes.

`Update` ejecuta automáticamente `Preflight` y `Backup`, registra el commit anterior, actualiza dependencias, compila y reinicia. Si falla la compilación o `/health`, restaura el commit anterior y vuelve a levantar el servicio.

`Rollback` vuelve manualmente al último commit bueno registrado. También se puede ejecutar en Linux con un commit explícito:

```bash
./scripts/kairos-node.sh rollback <commit>
```

En actualizaciones posteriores, `git pull` solo no alcanza porque hay que respaldar, compilar y reiniciar. Usar `./scripts/kairos-node.sh update`.

La clave privada permanece únicamente en `C:\Users\mauro\.ssh\kairos_linux_ed25519`; nunca debe copiarse al repositorio.
