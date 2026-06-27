[CmdletBinding()]
param(
    [ValidateSet('Install','Uninstall','Start','Stop','Restart','Status')]
    [string]$Action = 'Status',
    [string]$TaskName = 'KairosWeb',
    [string]$Repo = '',
    [int]$Port = 8000
)

$ErrorActionPreference = 'Stop'
if(-not $Repo){
    $scriptRoot = $PSScriptRoot
    if(-not $scriptRoot){
        $scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
    $Repo = Split-Path -Parent $scriptRoot
}
$Repo = (Resolve-Path -LiteralPath $Repo).Path
$venvPythonw = Join-Path $Repo '.venv\Scripts\pythonw.exe'
$venvPython = Join-Path $Repo '.venv\Scripts\python.exe'

function Resolve-KairosPython {
    if (Test-Path -LiteralPath $venvPythonw) { return $venvPythonw }
    if (Test-Path -LiteralPath $venvPython) { return $venvPython }
    $command = Get-Command pythonw.exe, python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) { throw 'No se encontró Python. Creá .venv o instalá Python.' }
    return $command.Source
}

function Get-KairosTask {
    return Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
}

switch ($Action) {
    'Install' {
        $python = Resolve-KairosPython
        $runner = Join-Path $Repo 'scripts\run_windows_service.py'
        $arguments = "`"$runner`" --repo `"$Repo`" --port $Port"
        $taskAction = New-ScheduledTaskAction -Execute $python -Argument $arguments -WorkingDirectory $Repo
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
        Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Principal $principal -Settings $settings -Description 'Kairos web y descubrimiento LAN' -Force | Out-Null
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $isAdmin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if ($isAdmin) {
            Remove-NetFirewallRule -DisplayName 'Kairos HTTP LAN' -ErrorAction SilentlyContinue
            Remove-NetFirewallRule -DisplayName 'Kairos Discovery LAN' -ErrorAction SilentlyContinue
            New-NetFirewallRule -DisplayName 'Kairos HTTP LAN' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Private -RemoteAddress LocalSubnet | Out-Null
            New-NetFirewallRule -DisplayName 'Kairos Discovery LAN' -Direction Inbound -Action Allow -Protocol UDP -LocalPort 42429 -Profile Private -RemoteAddress LocalSubnet | Out-Null
        } else {
            Write-Warning 'Ejecutá una vez como administrador para crear las reglas de firewall LAN.'
        }
        Start-ScheduledTask -TaskName $TaskName
        Write-Output "Instalado e iniciado: $TaskName"
    }
    'Uninstall' {
        if (Get-KairosTask) {
            Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        }
        if (([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
            Remove-NetFirewallRule -DisplayName 'Kairos HTTP LAN' -ErrorAction SilentlyContinue
            Remove-NetFirewallRule -DisplayName 'Kairos Discovery LAN' -ErrorAction SilentlyContinue
        }
        Write-Output "Desinstalado: $TaskName"
    }
    'Start' {
        Enable-ScheduledTask -TaskName $TaskName | Out-Null
        Start-ScheduledTask -TaskName $TaskName
    }
    'Stop' { Stop-ScheduledTask -TaskName $TaskName }
    'Restart' {
        Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
        Enable-ScheduledTask -TaskName $TaskName | Out-Null
        Start-ScheduledTask -TaskName $TaskName
    }
    'Status' {
        $task = Get-KairosTask
        if (-not $task) { Write-Output 'No instalado'; exit 1 }
        $info = Get-ScheduledTaskInfo -TaskName $TaskName
        [pscustomobject]@{ TaskName = $TaskName; State = $task.State; LastRunTime = $info.LastRunTime; LastTaskResult = $info.LastTaskResult }
    }
}
