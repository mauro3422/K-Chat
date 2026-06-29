[CmdletBinding()]
param(
    [ValidateSet('Shell','Exec','KairosPython','Preflight','MemoryPreflight','Backup','Pull','Restore','Update','Rollback','Restart','Status','Logs','FollowLogs','Health','Platform','Doctor','LanDoctor','ListNodes','Chat','TaskCreate','TaskList','TaskShow','TaskUpdate')]
    [string]$Action='Status',
    [string]$Node=$env:KAIROS_REMOTE_NODE,
    [string]$HostName=$env:KAIROS_LINUX_HOST,
    [string]$User=$env:KAIROS_LINUX_USER,
    [string]$RemoteRepo=$env:KAIROS_LINUX_REPO,
    [string]$Command='', [string]$BackupId='', [int]$Lines=150,
    [string]$PrimaryUrl=$env:KAIROS_LAN_PRIMARY_URL,
    [string]$SecondaryUrl=$env:KAIROS_LAN_SECONDARY_URL,
    [string]$IdentityFile="$HOME\.ssh\kairos_linux_ed25519",
    [string]$Message='', [string]$SessionId='', [string]$Model='',
    [string]$Title='', [string]$TaskId='', [string]$TaskStatus='', [string]$Priority='normal',
    [switch]$RawMessage,
    [switch]$Loopback,
    [switch]$DryRun,
    [switch]$Json
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
    'Doctor' {
        $args=@('doctor','--node',$Node)
        if($Json){$args += @('--json')}
        Invoke-RemoteClient $args
    }
    'LanDoctor' {
        $args=@('lan-doctor','--node',$Node)
        if($PrimaryUrl){$args += @('--primary-url',$PrimaryUrl)}
        if($SecondaryUrl){$args += @('--secondary-url',$SecondaryUrl)}
        if($Loopback){$args += @('--loopback')}
        if($Json){$args += @('--json')}
        Invoke-RemoteClient $args
    }
    'Preflight' {
        $args=@('preflight','--node',$Node)
        if($PrimaryUrl){$args += @('--primary-url',$PrimaryUrl)}
        if($SecondaryUrl){$args += @('--secondary-url',$SecondaryUrl)}
        if($Loopback){$args += @('--loopback')}
        if($Json){$args += @('--json')}
        Invoke-RemoteClient $args
    }
    'MemoryPreflight' {
        $args=@('memory-preflight','--node',$Node)
        if($DryRun){$args += @('--dry-run')}
        if($Json){$args += @('--json')}
        Invoke-RemoteClient $args
    }
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
    'KairosPython' {
        if(-not $Command){throw 'Pasá -Command con el script/argumentos para ejecutar con el Python de Kairos remoto.'}
        Invoke-RemoteClient @('kairos-python','--node',$Node,'--command',$Command)
    }
    'Chat' {
        if(-not $Message){throw 'Pasá -Message para enviar una consulta remota.'}
        $args=@('chat','--node',$Node,'--message',$Message)
        if($SessionId){$args += @('--session-id',$SessionId)}
        if($Model){$args += @('--model',$Model)}
        if($RawMessage){$args += @('--raw-message')}
        Invoke-RemoteClient $args
    }
    'TaskCreate' {
        if(-not $Title){throw 'Pasa -Title para crear una tarea Codex.'}
        if(-not $Message){throw 'Pasa -Message con el trabajo para Codex.'}
        $args=@('task-create','--node',$Node,'--title',$Title,'--message',$Message,'--priority',$Priority)
        if($SessionId){$args += @('--session-id',$SessionId)}
        Invoke-RemoteClient $args
    }
    'TaskList' {
        $args=@('task-list','--node',$Node,'--lines',"$Lines")
        if($TaskStatus){$args += @('--task-status',$TaskStatus)}
        Invoke-RemoteClient $args
    }
    'TaskShow' {
        if(-not $TaskId){throw 'Pasa -TaskId.'}
        Invoke-RemoteClient @('task-show','--node',$Node,'--task-id',$TaskId)
    }
    'TaskUpdate' {
        if(-not $TaskId){throw 'Pasa -TaskId.'}
        if(-not $TaskStatus){throw 'Pasa -TaskStatus.'}
        $args=@('task-update','--node',$Node,'--task-id',$TaskId,'--task-status',$TaskStatus)
        if($Message){$args += @('--message',$Message)}
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
