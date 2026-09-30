#!/bin/sh
# Arranque del contenedor de la app (instalación de usuario).
# Cada paso es idempotente: en cada inicio el esquema queda al día con la versión instalada,
# así que actualizar es cambiar VERSION y reiniciar.
set -eu
cd /app/backend

echo "== esquema PostgreSQL (alembic upgrade head)"
alembic upgrade head

echo "== colecciones Qdrant (solo crea las que falten)"
python qdrant_migrations/create_corpus_juridico_collection.py
python qdrant_migrations/create_fuentes_collections.py

echo "== app en :8000"
exec uvicorn src.servidor_usuario:servidor --host 0.0.0.0 --port 8000
