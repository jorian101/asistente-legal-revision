# Asistente Legal

Asistente jurídico para un tribunal militar: responde consultas sobre un corpus
de normas, jurisprudencia y doctrina, y genera borradores de dictámenes y autos
de vista a partir de los obrados de cada expediente, con trazabilidad de fuentes.

**Corre completamente local.** Bases de datos, búsqueda vectorial y modelos de
lenguaje funcionan en la propia máquina. Los expedientes y las consultas nunca
salen del equipo.

## Arquitectura

- **Backend**: Python 3.13 + FastAPI (`backend/`), gestionado con `uv`.
- **Frontend**: TypeScript + React + Vite (`frontend/`), gestionado con `pnpm`.
- **Bases de datos**: PostgreSQL (relacional) y Qdrant (vectores), en Docker.
- **Modelos**: Ollama on-premise (LLM y embeddings).
- **Extracción de documentos**: PDF/Word con OCR local (`tools/formatos/`).

## Requisitos

- Docker y Docker Compose.
- [`uv`](https://docs.astral.sh/uv/) y Node 24 + `pnpm`.
- [Ollama](https://ollama.com/) (o el servicio `ollama` del compose, perfil `ai`).
- 8 GB de RAM como mínimo: el modelo por defecto, `llama3:8b`, es el más exigente.

## Puesta en marcha

1. Configuración, bases de datos y modelos:

   ```bash
   cp .env.example .env        # generá SECRET_KEY: python -c "import secrets; print(secrets.token_urlsafe(48))"
   docker compose up -d postgres qdrant
   ollama pull llama3:8b
   ollama pull nomic-embed-text
   ```

2. Backend:

   ```bash
   cd backend
   uv sync
   uv run alembic upgrade head
   uv run python scripts/seed_usuarios.py     # usuarios de ejemplo
   ```

3. API + web en desarrollo:

   ```bash
   pnpm install
   pnpm dev        # API en http://localhost:8000, web en http://localhost:5173
   ```

## Sobre el corpus

El corpus jurídico **no se distribuye en este repositorio**: por su volumen y su
carácter reservado se entrega aparte. Sin él la aplicación arranca y es
navegable, pero las consultas no devuelven resultados.

## Estructura

```
backend/      API FastAPI, dominio, adaptadores, migraciones y tests
frontend/     SPA React (Vite)
tools/        extracción de documentos (PDF/Word + OCR)
docker/       entrada del contenedor y preparación de datos
instalacion/  instaladores para el despliegue en la máquina del usuario final
docs/         manual de usuario y plantillas de documentos
```

## Licencia

Uso no comercial. Ver [`LICENSE`](LICENSE) y [`NOTICE`](NOTICE).
