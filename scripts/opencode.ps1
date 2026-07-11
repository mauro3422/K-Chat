param(
    [string]$Repo = (Get-Location).Path,
    [ValidateSet("audit", "edit", "verify")]
    [string]$Mode = "audit",
    [string[]]$Files = @()
)

$ErrorActionPreference = "Stop"

$prompts = @{
    audit = "Primero reuni evidencia concreta por archivo. No saques conclusiones hasta terminar la evidencia. Separa hechos confirmados, inferencias, evidencia faltante, bugs reales y compatibilidad intencional. Despues decime que esta confirmado, que es inferencia, que falta y que atacarias primero. Responde corto y con prioridades."
    edit = "Toma solo esta area. Propone el cambio minimo necesario. No toques otros modulos. Si no hay bug real, no hagas cambios. Devuelve archivos a cambiar, razon y verificacion."
    verify = "Verifica solo lo cambiado. No repitas el analisis. Decime si quedo bien, que falta y si hay riesgo."
}

$arguments = @("-y", "opencode-ai", "run", $prompts[$Mode], "--dir", (Resolve-Path -LiteralPath $Repo).Path, "--format", "json")
foreach ($file in $Files) {
    $resolved = Join-Path $Repo $file
    if (-not (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        throw "Archivo no encontrado: $file"
    }
    $arguments += @("--file", $file)
}
& npx @arguments
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
