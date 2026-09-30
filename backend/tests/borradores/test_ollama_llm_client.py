"""Tests: OllamaLLMClient — adapter streaming contra /api/generate.

Sprint 6 Fase 2.2. Mock httpx via MockTransport para evitar.red real.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from src.adapters.ollama.ollama_llm_client import OllamaLLMClient
from src.domain.value_objects.contexto_expandido import ContextoExpandido
from tests._factories import make_fragmento

# --- helpers ------------------------------------------------------------


def _make_contexto() -> ContextoExpandido:
    frag = make_fragmento(
        qdrant_point_id="pt-1",
        texto="Art 1. La justicia se administra en nombre del pueblo.",
        padre_ref_id=None,
        padre_ref_key=None,
    )
    return ContextoExpandido(
        fragmentos_con_padres=(frag,),
        scores=(0.9,),
        query_original="que dice el art 1",
        tipo_respuesta="consulta_simple",
        expediente_id=None,
        breadcrumbs=(("root", "pt-1"),),
    )


def _mock_transport(chunks: list[dict[str, Any]]) -> httpx.MockTransport:
    """Crea MockTransport que responde con NDJSON (un JSON por linea)."""
    body = "\n".join(json.dumps(c) for c in chunks)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=body.encode(),
            headers={"Content-Type": "application/x-ndjson"},
        )

    return httpx.MockTransport(handler)


def _mock_error_transport(status: int, body: str = "boom") -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body.encode())

    return httpx.MockTransport(handler)


# Hack: monkey-patch httpx.AsyncClient para usar nuestro transport.
# Ponytail: sin fixture compleja, sin respx, sin dependencia nueva.


@pytest.fixture
def patch_httpx_client(monkeypatch):
    """Permite inyectar un MockTransport en httpx.AsyncClient."""

    def _patch(transport: httpx.BaseTransport):
        orig_init = httpx.AsyncClient.__init__

        def patched_init(self, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = transport
            orig_init(self, *args, **kwargs)

        monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    return _patch


# --- tests --------------------------------------------------------------


@pytest.mark.asyncio
async def test_generar_stream_tokens(patch_httpx_client):
    """3 chunks JSON -> 3 tokens yield (el done=True final no trae token)."""
    chunks = [
        {"response": "Hola ", "done": False},
        {"response": "mundo", "done": False},
        {"response": "", "done": True},
    ]
    patch_httpx_client(_mock_transport(chunks))

    client = OllamaLLMClient("http://localhost:11434", "llama3:8b", 30.0)
    contexto = _make_contexto()

    tokens: list[str] = []
    async for tok in client.generar("prompt con {{contexto_expandido}}", contexto, 0.1):
        tokens.append(tok)

    assert tokens == ["Hola ", "mundo"]


@pytest.mark.asyncio
async def test_generar_error_http_raise_runtime(patch_httpx_client):
    """HTTP 500 -> RuntimeError (no httpx.HTTPStatusError escapa al dominio)."""
    patch_httpx_client(_mock_error_transport(500, "internal"))

    client = OllamaLLMClient("http://localhost:11434", "llama3:8b", 30.0)
    contexto = _make_contexto()

    with pytest.raises(RuntimeError, match="fallo HTTP 500"):
        async for _ in client.generar("prompt", contexto, 0.1):
            pass


@pytest.mark.asyncio
async def test_generar_error_conexion_raise_runtime(monkeypatch):
    """Error de red (ConnectError) -> RuntimeError."""

    def boom_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = httpx.MockTransport(boom_handler)

    orig_init = httpx.AsyncClient.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["transport"] = transport
        orig_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    client = OllamaLLMClient("http://localhost:11434", "llama3:8b", 30.0)
    contexto = _make_contexto()

    with pytest.raises(RuntimeError, match="no disponible"):
        async for _ in client.generar("prompt", contexto, 0.1):
            pass


@pytest.mark.asyncio
async def test_generar_inyecta_contexto_y_system_en_payload(patch_httpx_client):
    """F2: el payload separa system (marcador [SYSTEM]) del prompt con contexto."""
    capturado: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        capturado.update(_json.loads(request.content))
        return httpx.Response(
            200,
            content=b'{"response": "ok", "done": true}\n',
            headers={"Content-Type": "application/x-ndjson"},
        )

    patch_httpx_client(httpx.MockTransport(handler))

    client = OllamaLLMClient("http://localhost:11434", "llama3:8b", 30.0)
    contexto = _make_contexto()

    async for _ in client.generar("Sos vocal. [SYSTEM] P: {{contexto_expandido}}", contexto, 0.1):
        pass

    assert capturado["system"] == "Sos vocal."
    assert "[NORMA · root > pt-1]" in capturado["prompt"]
    assert "{{contexto_expandido}}" not in capturado["prompt"]
    # A.1: sin num_ctx Ollama usa 4096 y trunca el prompt real (8-14k tokens).
    assert capturado["options"]["num_ctx"] == 8192

    capturado.clear()
    client = OllamaLLMClient("http://localhost:11434", "llama3:8b", 30.0, ventana_tokens=32768)
    async for _ in client.generar("P: {{contexto_expandido}}", contexto, 0.1):
        pass
    assert capturado["options"]["num_ctx"] == 32768


def test_constructor_contexto_vacio_deja_slot_reemplazado():
    """Si no hay fragmentos, el slot se reemplaza por string vacio (no queda literal)."""
    client = OllamaLLMClient("http://localhost:11434", "llama3:8b", 30.0)
    contexto = ContextoExpandido(
        fragmentos_con_padres=(),
        scores=(),
        query_original="x",
        tipo_respuesta="consulta_simple",
        expediente_id=None,
        breadcrumbs=(),
    )

    mensajes = client._constructor.construir("P: [{{contexto_expandido}}]", contexto)

    assert mensajes.user == "P: []"


@pytest.mark.asyncio
async def test_generar_breadcrumbs_mas_cortos_no_omite_padres(patch_httpx_client):
    """FIX R1: si breadcrumbs tiene menos entradas que fragmentos_con_padres
    (caso normal: padres ascendidos), los padres igual entran al prompt con
    fallback a qdrant_point_id como path.
    """
    capturado: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json

        capturado.update(_json.loads(request.content))
        return httpx.Response(
            200,
            content=b'{"response": "ok", "done": true}\n',
            headers={"Content-Type": "application/x-ndjson"},
        )

    patch_httpx_client(httpx.MockTransport(handler))

    frag_hijo = make_fragmento(
        qdrant_point_id="pt-hijo",
        texto="Articulo hijo.",
        padre_ref_id=None,
        padre_ref_key=None,
    )
    frag_padre = make_fragmento(
        qdrant_point_id="pt-padre",
        texto="Articulo padre.",
        padre_ref_id=None,
        padre_ref_key=None,
    )
    contexto = ContextoExpandido(
        fragmentos_con_padres=(frag_hijo, frag_padre),
        scores=(0.9, 0.5),
        query_original="x",
        tipo_respuesta="auto_vista_consulta",
        expediente_id=1,
        breadcrumbs=(("root", "pt-hijo"),),  # solo breadcrumb del hijo
    )
    client = OllamaLLMClient("http://localhost:11434", "llama3:8b", 30.0)

    async for _ in client.generar("P: {{contexto_expandido}}", contexto, 0.1):
        pass

    # Ambos fragmentos presentes (hijo con breadcrumb, padre sin path:
    # el fallback al qdrant_point_id crudo fue eliminado — T0 sanitizacion).
    assert "[NORMA · root > pt-hijo]" in capturado["prompt"]
    assert "[NORMA]\nArticulo padre." in capturado["prompt"]
    assert "pt-padre" not in capturado["prompt"]
    assert "{{contexto_expandido}}" not in capturado["prompt"]
