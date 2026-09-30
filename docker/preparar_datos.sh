#!/bin/sh
# Primera carga de datos de una instalación de usuario (lo llama instalar.sh, una vez).
# Esquema + colecciones + corpus público (si /corpus está montado) + primer administrador.
# Re-ejecutable: el corpus solo se importa con la BD vacía y el admin solo si no hay ninguno.
set -eu
cd /app/backend

echo "== esperando a Qdrant"
python - <<'EOF'
import time, urllib.request
from src.config import get_settings
url = get_settings().qdrant_url + "/healthz"
for _ in range(60):
    try:
        urllib.request.urlopen(url, timeout=3)
        break
    except OSError:
        time.sleep(2)
else:
    raise SystemExit(f"Qdrant no respondió en {url}")
EOF

alembic upgrade head
python qdrant_migrations/create_corpus_juridico_collection.py
python qdrant_migrations/create_fuentes_collections.py

if [ -f /corpus/manifiesto.json ]; then
    echo "== corpus público"
    python scripts/corpus_publico.py importar /corpus
fi

echo "== administrador"
python scripts/crear_admin.py
