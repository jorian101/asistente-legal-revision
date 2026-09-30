"""Tests bloqueantes Fase 3 G1: cableo AnalizadorVicios -> PlantillaMarkdownAdapter.

Verifica que cuando se pasan vicios reales al resolver la plantilla, el
condicional {{CONDICIONAL_LOGICA_SANEAMIENTO: SI_EXISTE_VICIO_DE_NULIDAD}}
se renderiza con el listado de vicios en vez del placeholder hardcodeado.

RG3: 1 test minimo por regla bloqueante.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters.plantillas.plantilla_markdown_adapter import (
    PlantillaMarkdownAdapter,
)
from src.domain.value_objects.resultado_vicios import (
    ResultadoVicios,
    VicioDetectado,
)
from tests._factories import make_expediente


class FakeExpedienteRepo:
    """ExpedienteRepo in-memory para tests."""

    def __init__(self, existentes: list | None = None) -> None:
        self._por_id: dict[int, any] = {}
        self._next_id = 1
        for e in existentes or []:
            e.id = self._next_id
            self._por_id[self._next_id] = e
            self._next_id += 1

    async def obtener(self, expediente_id: int):
        return self._por_id.get(expediente_id)


@pytest.fixture
def adapter(tmp_path: Path) -> PlantillaMarkdownAdapter:
    """Adapter con plantilla que incluye el condicional G1."""
    plantilla = tmp_path / "proyecto_auto_vista_consulta.md"
    plantilla.write_text(
        "EXPEDIENTE {{NUMERO_CASO}}\n"
        "{{CONDICIONAL_LOGICA_SANEAMIENTO: SI_EXISTE_VICIO_DE_NULIDAD}}\n"
        "{{contexto_expandido}}\n",
        encoding="utf-8",
    )

    expediente = make_expediente(
        id=None,
        numero_caso="TSJM-C-2024-001",
        tipo_proceso="consulta",
        procesado_nombre="Juan Perez",
        procesado_grado="Capitan",
        delito="Desobediencia",
    )
    repo = FakeExpedienteRepo(existentes=[expediente])

    return PlantillaMarkdownAdapter(
        plantillas_dir=tmp_path,
        expediente_repo=repo,
    )


@pytest.mark.asyncio
async def test_condicional_vicios_nulidad_se_renderiza_con_vicios_reales(
    adapter: PlantillaMarkdownAdapter,
) -> None:
    """Bloqueante G1: condicional SI_EXISTE_VICIO_DE_NULIDAD se llena con vicios reales.

    Cuando el caller pasa un ResultadoVicios con vicios detectados, el
    adapter debe renderizar un listado textual de los vicios en vez del
    fallback "[No se detectó vicio...]".

    Esto valida el cableo completo:
    GenerarBorrador -> analizar_vicios() -> resolver(vicios=...) ->
    _resolver_condicionales() -> _render_vicios_nulidad().
    """
    # Arrange: vicios reales detectados (simula AnalizadorVicios)
    vicio_1 = VicioDetectado(
        tipo="indefension",
        fragmento_id=42,
        foja_referida="23",
        snippet="El procesado no fue notificado de la acusacion en foja 23",
        norma_vulnerada="CPPM Art. 361",
    )
    vicio_2 = VicioDetectado(
        tipo="falta_firma",
        fragmento_id=55,
        foja_referida=None,
        snippet="El auto carece de firma del vocal relator",
        norma_vulnerada="CPPM Art. 75",
    )
    vicios = ResultadoVicios.de_lista([vicio_1, vicio_2])

    # Act: resolver la plantilla pasando los vicios
    resultado = await adapter.resolver("auto_vista_consulta", expediente_id=1, vicios=vicios)

    # Assert: el condicional fue reemplazado con listado de vicios
    assert "Que," in resultado, "El bloque debe iniciar con 'Que,'"
    assert "se advierten los siguientes vicios procesales" in resultado
    assert "indefension" in resultado
    assert "CPPM Art. 361" in resultado
    assert "foja 23" in resultado
    assert "falta_firma" in resultado
    assert "CPPM Art. 75" in resultado


@pytest.mark.asyncio
async def test_condicional_vicios_nulidad_fallback_si_sin_vicios(
    adapter: PlantillaMarkdownAdapter,
) -> None:
    """Sin vicios (None o vacio) -> fallback conservador actual.

    Mantiene compatibilidad con callers que no cablean AnalizadorVicios
    y con tests existentes que no pasan vicios.
    """
    # Sin vicios (kwarg omitido = None)
    resultado_none = await adapter.resolver("auto_vista_consulta", expediente_id=1)
    assert (
        "Que, del análisis automático efectuado sobre el contexto recuperado "
        "no se advierten vicios de nulidad que ameriten declaratoria de oficio."
    ) in resultado_none

    # Con vicios vacios
    resultado_vacio = await adapter.resolver(
        "auto_vista_consulta", expediente_id=1, vicios=ResultadoVicios.vacio()
    )
    assert (
        "Que, del análisis automático efectuado sobre el contexto recuperado "
        "no se advierten vicios de nulidad que ameriten declaratoria de oficio."
    ) in resultado_vacio


@pytest.mark.asyncio
async def test_condicional_vicios_no_afecta_otras_plantillas(
    adapter: PlantillaMarkdownAdapter,
) -> None:
    """El condicional solo existe en auto_vista_consulta; otras plantillas
    no deben romperse aunque pasemos vicios (ignorados silenciosamente)."""
    # Crear plantilla simple sin el condicional
    plantilla_simple = adapter._dir / "consulta_simple.md"
    plantilla_simple.write_text(
        "Simple: {{contexto_expandido}} {{consulta_usuario}}",
        encoding="utf-8",
    )
    # Cache del lru_cache debe invalidarse manualmente si queremos recargar
    # pero aqui solo probamos que no rompa
    vicio = VicioDetectado(
        tipo="plazo_vencido",
        fragmento_id=1,
        foja_referida=None,
        snippet="plazo vencido",
        norma_vulnerada="CPPM Art. 105",
    )
    vicios = ResultadoVicios.de_lista([vicio])

    resultado = await adapter.resolver("consulta_simple", expediente_id=None, vicios=vicios)

    assert "Simple:" in resultado
    assert "vicios" not in resultado.lower()  # no se inyecta nada
