#!/usr/bin/env bash
# instalar.sh — Instala el Asistente Legal en esta máquina (Linux/macOS), todo local.
#
# Requisito: Docker (Docker Desktop en macOS). Se corre desde la carpeta del paquete:
#   compose.usuario.yml, .env.usuario.example, corpus-publico.tar.gz, imagen-<versión>.tar
#
#   1. requisitos     docker + compose, RAM
#   2. configuración  .env con secretos aleatorios (si no existe)
#   3. imagen         docker load de imagen-<VERSION>.tar del paquete offline (si falta, intenta descargarla)
#   4. servicios      postgres, qdrant, ollama
#   5. modelos        ollama pull del modelo de respuestas y del de embeddings
#   6. datos          esquema + corpus público + primer administrador (clave única en pantalla)
#   7. app            arranca y espera a que responda
# Re-ejecutable: si algo falla, se corrige y se vuelve a correr; no duplica datos.
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
DC=(docker compose -f compose.usuario.yml)
trap 'echo; echo "La instalación se detuvo en el paso: ${PASO:-inicio}. Corregí el error y volvé a correr ./instalar.sh" >&2' ERR

PASO="1/7 requisitos"; echo "== $PASO"
command -v docker >/dev/null || { echo "Falta Docker: https://docs.docker.com/get-docker/" >&2; exit 1; }
docker compose version >/dev/null
if [[ -r /proc/meminfo ]]; then
    ram_gb=$(( $(awk '/MemTotal/ {print $2}' /proc/meminfo) / 1024 / 1024 ))
else
    ram_gb=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
fi
(( ram_gb >= 8 )) || echo "  AVISO: ${ram_gb} GB de RAM. llama3:8b necesita ~8 GB: elegí un modelo más liviano (ver manual)."

PASO="2/7 configuración"; echo "== $PASO"
if [[ ! -f .env ]]; then
    cp .env.usuario.example .env
    while grep -q '__GENERAR__' .env; do
        secreto=$(LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c 48)
        sed -i.bak "0,/__GENERAR__/s//${secreto}/" .env 2>/dev/null \
            || sed -i.bak "1,/__GENERAR__/s//${secreto}/" .env   # sed de macOS
    done
    rm -f .env.bak
    chmod 600 .env
    echo "  .env creado con secretos nuevos"
else
    echo "  .env ya existe: se conserva"
fi
set -a; . ./.env; set +a

PASO="3/7 imagen"; echo "== $PASO"
if [[ -f "imagen-$VERSION.tar" ]]; then docker load -i "imagen-$VERSION.tar"; else "${DC[@]}" pull app; fi

PASO="4/7 servicios"; echo "== $PASO"
"${DC[@]}" up -d postgres qdrant ollama

PASO="5/7 modelos"; echo "== $PASO (la primera vez descarga varios GB)"
"${DC[@]}" exec -T ollama ollama pull "$EMBEDDING_MODEL_NAME"
"${DC[@]}" exec -T ollama ollama pull "$LLM_MODEL_NAME"

PASO="6/7 datos"; echo "== $PASO"
if [[ -f corpus-publico.tar.gz && ! -d corpus ]]; then tar xzf corpus-publico.tar.gz; fi
montaje=()
[[ -f corpus/manifiesto.json ]] && montaje=(-v "$PWD/corpus:/corpus:ro")
"${DC[@]}" run --rm ${montaje[@]+"${montaje[@]}"} --entrypoint sh app /app/preparar_datos.sh

PASO="7/7 app"; echo "== $PASO"
"${DC[@]}" up -d app
url="http://localhost:${PUERTO_APP}"
for _ in $(seq 1 60); do
    if curl -fsS -o /dev/null "$url"; then
        echo
        echo "Listo: abrí $url en el navegador."
        exit 0
    fi
    sleep 5
done
echo "La app no respondió en $url. Ver: docker compose -f compose.usuario.yml logs app" >&2
exit 1
