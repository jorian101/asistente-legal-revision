# instalar.ps1 — Instala el Asistente Legal en Windows (Docker Desktop), todo local.
# Mismos pasos que instalar.sh. Uso, desde la carpeta del paquete:
#   powershell -ExecutionPolicy Bypass -File .\instalar.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$paso = "inicio"
function Dc { docker compose -f compose.usuario.yml @args; if ($LASTEXITCODE) { throw "docker compose $args fallo ($LASTEXITCODE)" } }

try {
    $paso = "1/7 requisitos"; Write-Host "== $paso"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { throw "Falta Docker Desktop: https://docs.docker.com/desktop/install/windows-install/" }
    docker compose version | Out-Null
    $ramGb = [math]::Floor((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
    if ($ramGb -lt 8) { Write-Host "  AVISO: $ramGb GB de RAM. llama3:8b necesita ~8 GB: elegi un modelo mas liviano (ver manual)." }

    $paso = "2/7 configuracion"; Write-Host "== $paso"
    if (-not (Test-Path .env)) {
        $texto = Get-Content .env.usuario.example -Raw
        while ($texto -match "__GENERAR__") {
            $secreto = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 48 | ForEach-Object { [char]$_ })
            $texto = ([regex]"__GENERAR__").Replace($texto, $secreto, 1)
        }
        [IO.File]::WriteAllText("$PWD\.env", $texto.Replace("`r`n", "`n"))
        Write-Host "  .env creado con secretos nuevos"
    } else { Write-Host "  .env ya existe: se conserva" }
    $cfg = @{}
    Get-Content .env | Where-Object { $_ -match "^\s*([A-Z_]+)=(.*)$" } | ForEach-Object { $cfg[$Matches[1]] = $Matches[2] }

    $paso = "3/7 imagen"; Write-Host "== $paso"
    $imagen = "imagen-$($cfg.VERSION).tar"
    if (Test-Path $imagen) { docker load -i $imagen } else { Dc pull app }

    $paso = "4/7 servicios"; Write-Host "== $paso"
    Dc up -d postgres qdrant ollama

    $paso = "5/7 modelos"; Write-Host "== $paso (la primera vez descarga varios GB)"
    Dc exec -T ollama ollama pull $cfg.EMBEDDING_MODEL_NAME
    Dc exec -T ollama ollama pull $cfg.LLM_MODEL_NAME

    $paso = "6/7 datos"; Write-Host "== $paso"
    if ((Test-Path corpus-publico.tar.gz) -and -not (Test-Path corpus)) { tar xzf corpus-publico.tar.gz }
    if (Test-Path corpus\manifiesto.json) {
        Dc run --rm -v "${PWD}\corpus:/corpus:ro" --entrypoint sh app /app/preparar_datos.sh
    } else {
        Dc run --rm --entrypoint sh app /app/preparar_datos.sh
    }

    $paso = "7/7 app"; Write-Host "== $paso"
    Dc up -d app
    $url = "http://localhost:$($cfg.PUERTO_APP)"
    for ($i = 0; $i -lt 60; $i++) {
        try { Invoke-WebRequest $url -UseBasicParsing -TimeoutSec 4 | Out-Null; Write-Host "`nListo: abri $url en el navegador."; exit 0 } catch { Start-Sleep 5 }
    }
    throw "La app no respondio en $url. Ver: docker compose -f compose.usuario.yml logs app"
} catch {
    Write-Host "`n$_" -ForegroundColor Red
    Write-Host "La instalacion se detuvo en el paso: $paso. Corregi el error y volve a correr instalar.ps1" -ForegroundColor Red
    exit 1
}
