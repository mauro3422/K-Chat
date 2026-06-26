[CmdletBinding()]
param(
    [ValidateSet('Shell','Exec','Preflight','Backup','Pull','Restore','Update','Rollback','Restart','Status','Logs','FollowLogs','Health','Platform','Doctor','ListNodes','Chat')]
    [string]$Action='Status',
    [string]$Node=$env:KAIROS_REMOTE_NODE,
    [string]$HostName=$env:KAIROS_LINUX_HOST,
    [string]$User=$env:KAIROS_LINUX_USER,
    [string]$RemoteRepo=$env:KAIROS_LINUX_REPO,
    [string]$Command='', [string]$BackupId='', [int]$Lines=150,
    [string]$IdentityFile="$HOME\.ssh\kairos_linux_ed25519",
    [string]$Message='', [string]$SessionId='', [string]$Model=''
)
$ErrorActionPreference='Stop'
$root=(Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$client=Join-Path $root 'ops\remote\kairos_remote.py'
if(-not (Test-Path -LiteralPath $client)){throw "No existe el cliente remoto: $client"}
if(-not $Node){$Node='linux'}

$env:KAIROS_LINUX_HOST=$HostName
$env:KAIROS_LINUX_USER=$User
$env:KAIROS_LINUX_REPO=$RemoteRepo
$env:KAIROS_LINUX_IDENTITY=$IdentityFile

function Invoke-RemoteClient([string[]]$ArgsList){
    & python $client @ArgsList
    exit $LASTEXITCODE
}
function Quote-Bash([string]$Value){
    if($Value.Contains("'")){throw 'El valor remoto no puede contener comillas simples.'}
    return "'$Value'"
}

switch($Action){
    'ListNodes' { Invoke-RemoteClient @('list') }
    'Doctor' { Invoke-RemoteClient @('doctor','--node',$Node) }
    'Health' { Invoke-RemoteClient @('health','--node',$Node) }
    'Pull' { Invoke-RemoteClient @('pull','--node',$Node) }
    'Restart' { Invoke-RemoteClient @('restart','--node',$Node) }
    'Status' { Invoke-RemoteClient @('status','--node',$Node) }
    'Logs' { Invoke-RemoteClient @('logs','--node',$Node,'--lines',"$Lines") }
    'Platform' { Invoke-RemoteClient @('platform','--node',$Node) }
    'Exec' {
        if(-not $Command){throw 'Pasá -Command para ejecutar una orden remota.'}
        Invoke-RemoteClient @('exec','--node',$Node,'--command',$Command)
    }
    'Chat' {
        if(-not $Message){throw 'Pasá -Message para enviar una consulta remota.'}
        $args=@('chat','--node',$Node,'--message',$Message)
        if($SessionId){$args += @('--session-id',$SessionId)}
        if($Model){$args += @('--model',$Model)}
        Invoke-RemoteClient $args
    }
    'Shell' {
        if(-not $HostName){throw 'Definí KAIROS_LINUX_HOST o pasá -HostName.'}
        if(-not $User){throw 'Definí KAIROS_LINUX_USER o pasá -User.'}
        if(-not (Test-Path -LiteralPath $IdentityFile)){throw "No existe la clave privada: $IdentityFile"}
        & ssh -i $IdentityFile -o BatchMode=yes -o IdentitiesOnly=yes "${User}@${HostName}"
        exit $LASTEXITCODE
    }
    default {
        $legacy=switch($Action){
            'Preflight' {'preflight'}
            'Backup' {'backup'}
            'Restore' {if(-not $BackupId){throw 'Pasá -BackupId con el identificador del backup.'}; "restore $(Quote-Bash $BackupId)"}
            'Update' {'update'}
            'Rollback' {'rollback'}
            'FollowLogs' {'follow-logs'}
        }
        if(-not $legacy){throw "Acción no soportada: $Action"}
        Invoke-RemoteClient @('exec','--node',$Node,'--command',"cd '$RemoteRepo' && ./scripts/kairos-node.sh $legacy")
    }
}
