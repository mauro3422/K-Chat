[CmdletBinding()]
param(
    [ValidateSet('Shell','Exec','Preflight','Backup','Restore','Update','Rollback','Restart','Status','Logs','FollowLogs','Health','Platform')]
    [string]$Action='Status',
    [string]$HostName=$env:KAIROS_LINUX_HOST,
    [string]$User=$env:KAIROS_LINUX_USER,
    [string]$RemoteRepo=$env:KAIROS_LINUX_REPO,
    [string]$Command='', [string]$BackupId='', [int]$Lines=150,
    [string]$IdentityFile="$HOME\.ssh\kairos_linux_ed25519"
)
$ErrorActionPreference='Stop'
if(-not $HostName){throw 'Definí KAIROS_LINUX_HOST o pasá -HostName.'}
if(-not $User){throw 'Definí KAIROS_LINUX_USER o pasá -User.'}
if(-not $RemoteRepo -and $Action -notin @('Shell','Exec')){throw 'Definí KAIROS_LINUX_REPO o pasá -RemoteRepo.'}
if(-not (Test-Path -LiteralPath $IdentityFile)){throw "No existe la clave privada: $IdentityFile"}
$target="${User}@${HostName}"
$sshArgs=@('-i',$IdentityFile,'-o','IdentitiesOnly=yes','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',$target)
function Quote-Bash([string]$Value){if($Value.Contains("'")){throw 'La ruta remota no puede contener comillas simples.'}; return "'$Value'"}
if($Action -eq 'Shell'){& ssh @sshArgs; exit $LASTEXITCODE}
if($Action -eq 'Exec'){if(-not $Command){throw 'Pasá -Command para ejecutar una orden remota.'}; & ssh @sshArgs $Command; exit $LASTEXITCODE}
$remoteScript="cd $(Quote-Bash $RemoteRepo) && ./scripts/kairos-node.sh"
$remoteAction=switch($Action){'Preflight'{'preflight'} 'Backup'{'backup'} 'Restore'{if(-not $BackupId){throw 'Pasá -BackupId con el identificador del backup.'}; "restore $(Quote-Bash $BackupId)"} 'Update'{'update'} 'Rollback'{'rollback'} 'Restart'{'restart'} 'Status'{'status'} 'Logs'{"logs $Lines"} 'FollowLogs'{'follow-logs'} 'Health'{'health'} 'Platform'{'platform'}}
& ssh @sshArgs "$remoteScript $remoteAction"
exit $LASTEXITCODE
