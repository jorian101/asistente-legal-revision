# actualizar.ps1 — Pasa la instalacion a otra version (Windows), con respaldo y vuelta atras.
# Mismos pasos que actualizar.sh. Uso:
#   powershell -ExecutionPolicy Bypass -File .\actualizar.ps1 X.Y.Z
param([Parameter(Mandatory = $true)][ValidatePattern('^\d+\.\d+\.\d+$')][string]$Nueva)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
function Dc { docker compose -f compose.usuario.yml @args; if ($LASTEXITCODE) { throw "docker compose $args fallo ($LASTEXITCODE)" } }
$cfg = @{}
Get-Content .env | Where-Object { $_ -match "^\s*([A-Z_]+)=(.*)$" } | ForEach-Object { $cfg[$Matches[1]] = $Matches[2] }
$anterior = $cfg.VERSION
if ($Nueva -eq $anterior) { Write-Host "Ya esta instalada la $Nueva."; exit 0 }
$respaldo = "respaldos\$(Get-Date -Format yyyyMMdd-HHmmss)-v$anterior"

function Volumen($accion, $nombre) {
    $cmd = if ($accion -eq "restaurar") { "find /d -mindepth 1 -delete && tar xzf /b/$nombre.tgz -C /d" } else { "tar czf /b/$nombre.tgz -C /d ." }
    docker run --rm -v "asistente-legal-usuario_${nombre}:/d" -v "${PWD}\${respaldo}:/b" --entrypoint sh postgres:16-alpine -c $cmd
    if ($LASTEXITCODE) { throw "respaldo del volumen $nombre fallo" }
}
function FijarVersion($v) {
    $t = (Get-Content .env -Raw) -replace "(?m)^VERSION=.*$", "VERSION=$v"
    [IO.File]::WriteAllText("$PWD\.env", $t)
}
function EsperarApp {
    for ($i = 0; $i -lt 60; $i++) {
        try { Invoke-WebRequest "http://localhost:$($cfg.PUERTO_APP)" -UseBasicParsing -TimeoutSec 4 | Out-Null; return $true } catch { Start-Sleep 5 }
    }
    return $false
}

Write-Host "== 1/4 respaldo en $respaldo"
New-Item -ItemType Directory -Force $respaldo | Out-Null
Dc stop app
try {
    # pg_dump se escribe dentro del contenedor y se copia: la redireccion de PowerShell corrompe binarios.
    Dc exec -T postgres sh -c "pg_dump -U `$POSTGRES_USER -d `$POSTGRES_DB -Fc -f /tmp/respaldo.dump"
    Dc cp postgres:/tmp/respaldo.dump "$respaldo\postgres.dump"
    Dc stop qdrant
    Volumen guardar qdrant_data
    Volumen guardar uploads
    Dc start qdrant

    Write-Host "== 2/4 imagen $Nueva"
    if (Test-Path "imagen-$Nueva.tar") { docker load -i "imagen-$Nueva.tar"; if ($LASTEXITCODE) { throw "docker load fallo" } } else { $env:VERSION = $Nueva; Dc pull app; Remove-Item Env:VERSION }
} catch {
    Remove-Item Env:VERSION -ErrorAction SilentlyContinue
    Write-Host "Fallo antes del cambio de version: se vuelve a levantar la $anterior." -ForegroundColor Red
    docker compose -f compose.usuario.yml up -d qdrant app
    throw
}

Write-Host "== 3/4 cambio a $Nueva"
FijarVersion $Nueva
Dc up -d app

Write-Host "== 4/4 verificar"
if (EsperarApp) { Write-Host "Actualizado a $Nueva. Respaldo de la $anterior en $respaldo"; exit 0 }

Write-Host "La $Nueva no arranco: volviendo a la $anterior y restaurando el respaldo..." -ForegroundColor Red
docker compose -f compose.usuario.yml logs --tail 50 app *> "$respaldo\app-$Nueva-fallo.log"
Dc stop app qdrant
FijarVersion $anterior
Dc cp "$respaldo\postgres.dump" postgres:/tmp/respaldo.dump
Dc exec -T postgres sh -c "pg_restore -U `$POSTGRES_USER -d `$POSTGRES_DB --clean --if-exists /tmp/respaldo.dump"
Volumen restaurar qdrant_data
Volumen restaurar uploads
Dc up -d qdrant app
if (EsperarApp) { Write-Host "Quedo la $anterior como estaba. Log del fallo: $respaldo\app-$Nueva-fallo.log" -ForegroundColor Red }
exit 1
