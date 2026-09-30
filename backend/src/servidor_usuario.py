"""App de la instalacion de usuario: la API en /api y el frontend compilado en /.

Un solo proceso sirve todo (uvicorn src.servidor_usuario:servidor). En desarrollo no
se usa: Vite sirve el frontend y su proxy reescribe /api hacia src.main:app.
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

from src.main import app as api
from src.main import lifespan


class _SPA(StaticFiles):
    """Las rutas del cliente (/consultas, /admin/...) no son archivos: devuelven index.html."""

    async def get_response(self, path: str, scope: Scope):  # type: ignore[no-untyped-def]
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


# Starlette no corre el lifespan de una app montada: se reutiliza el de la API.
servidor = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
servidor.mount("/api", api)
servidor.mount(
    "/", _SPA(directory=os.environ.get("FRONTEND_DIST", "/app/frontend/dist"), html=True)
)
