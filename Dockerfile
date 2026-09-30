# Imagen de la instalación de usuario: API + frontend compilado + OCR, todo offline.
# Imagen de la aplicación: backend + frontend compilado + OCR offline.
# Desarrollo no la usa (pnpm dev).

FROM node:24-slim AS frontend
WORKDIR /src/frontend
RUN npm install -g pnpm@11
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build


FROM python:3.13-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy

# OCR de escaneos (tools/formatos: Docling + Tesseract spa) en su venv, como en desarrollo.
# Va antes del backend: es la capa más pesada y no cambia con el código de la app.
# ponytail: torch CPU (el lock de formatos trae CUDA, ~6 GB); sin lock propio, se fija a mano si rompe.
COPY tools/formatos /app/tools/formatos
RUN cd /app/tools/formatos \
    && uv venv -q .venv \
    && uv pip install -q --python .venv/bin/python --torch-backend cpu \
        "docling>=2.5" "pymupdf>=1.24" "python-docx>=1.1" "onnxruntime>=1.29.0"
# Una pasada de OCR al construir descarga los modelos de Docling: en la máquina del usuario no hay internet.
COPY docker/precalentar_ocr.py /tmp/precalentar_ocr.py
RUN /app/tools/formatos/.venv/bin/python /tmp/precalentar_ocr.py && rm /tmp/precalentar_ocr.py

# Backend (dependencias primero: se cachean mientras no cambie el lock).
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./

COPY --from=frontend /src/frontend/dist /app/frontend/dist
COPY docker/arranque.sh docker/preparar_datos.sh /app/

ENV PATH=/app/backend/.venv/bin:$PATH \
    FRONTEND_DIST=/app/frontend/dist \
    HF_HUB_OFFLINE=1 \
    ENV=production
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=120s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=4)"
ENTRYPOINT ["sh", "/app/arranque.sh"]
