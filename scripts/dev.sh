#!/usr/bin/env bash
# dev.sh — `pnpm dev`: levanta la API y la web con las bases locales de Docker.
#
#   pnpm dev:db   levanta PostgreSQL y Qdrant (docker compose)
#   pnpm dev      levanta API (:8000) + web (:5173)
set -euo pipefail

APP="${DEV_APP:-pnpm dev:app}"

echo "== pnpm dev: PostgreSQL + Qdrant locales (docker compose), Ollama en 127.0.0.1:11434"
exec $APP
