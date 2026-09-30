#!/usr/bin/env bash
# actualizar.sh — Pasa la instalación a otra versión, con respaldo y vuelta atrás automática.
#
# Uso: ./actualizar.sh X.Y.Z      (si viene imagen-X.Y.Z.tar en esta carpeta, se usa esa)
#
#   1. respaldo   PostgreSQL (pg_dump) + volúmenes de Qdrant y de archivos subidos
#   2. imagen     docker load de imagen-X.Y.Z.tar, o descarga
#   3. cambio     VERSION en .env y reinicio: el contenedor migra el esquema solo al arrancar
#   4. verificar  si la app no responde en 5 minutos, vuelve a la versión anterior y restaura
# Volver a mano a una versión anterior: ./actualizar.sh <versión vieja> no alcanza si hubo
# migración; usar el respaldo (ver manual, "Restaurar un respaldo").
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
DC=(docker compose -f compose.usuario.yml)
NUEVA="${1:-}"
[[ "$NUEVA" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Uso: $0 X.Y.Z" >&2; exit 2; }
set -a; . ./.env; set +a
ANTERIOR="$VERSION"
unset VERSION
[[ "$NUEVA" != "$ANTERIOR" ]] || { echo "Ya está instalada la $NUEVA."; exit 0; }
PROYECTO=asistente-legal-usuario   # = name: de compose.usuario.yml
RESPALDO="respaldos/$(date +%Y%m%d-%H%M%S)-v$ANTERIOR"

volumen() {  # volumen <accion: guardar|restaurar> <nombre>
    local cmd="tar czf /b/$2.tgz -C /d ."
    [[ "$1" == restaurar ]] && cmd="find /d -mindepth 1 -delete && tar xzf /b/$2.tgz -C /d"
    docker run --rm -v "${PROYECTO}_$2:/d" -v "$PWD/$RESPALDO:/b" --entrypoint sh \
        postgres:16-alpine -c "$cmd"
}
esperar_app() {
    for _ in $(seq 1 60); do
        curl -fsS -o /dev/null "http://localhost:${PUERTO_APP}" && return 0
        sleep 5
    done
    return 1
}
fijar_version() { sed -i.bak "s/^VERSION=.*/VERSION=$1/" .env && rm -f .env.bak; }

echo "== 1/4 respaldo en $RESPALDO"
mkdir -p "$RESPALDO"
"${DC[@]}" stop app
trap 'echo "Falló antes del cambio de versión: se vuelve a levantar la $ANTERIOR." >&2; "${DC[@]}" up -d qdrant app || true' ERR
"${DC[@]}" exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$RESPALDO/postgres.dump"
test -s "$RESPALDO/postgres.dump"
"${DC[@]}" stop qdrant
volumen guardar qdrant_data
volumen guardar uploads
"${DC[@]}" start qdrant

echo "== 2/4 imagen $NUEVA"
if [[ -f "imagen-$NUEVA.tar" ]]; then docker load -i "imagen-$NUEVA.tar"; else VERSION="$NUEVA" "${DC[@]}" pull app; fi

trap - ERR

echo "== 3/4 cambio a $NUEVA"
fijar_version "$NUEVA"
"${DC[@]}" up -d app

echo "== 4/4 verificar"
if esperar_app; then
    echo "Actualizado a $NUEVA. Respaldo de la $ANTERIOR en $RESPALDO"
    exit 0
fi

echo "La $NUEVA no arrancó: volviendo a la $ANTERIOR y restaurando el respaldo..." >&2
"${DC[@]}" logs --tail 50 app > "$RESPALDO/app-$NUEVA-fallo.log" 2>&1 || true
"${DC[@]}" stop app qdrant
fijar_version "$ANTERIOR"
"${DC[@]}" exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
    < "$RESPALDO/postgres.dump"
volumen restaurar qdrant_data
volumen restaurar uploads
"${DC[@]}" up -d qdrant app
esperar_app && echo "Quedó la $ANTERIOR como estaba. Log del fallo: $RESPALDO/app-$NUEVA-fallo.log" >&2
exit 1
