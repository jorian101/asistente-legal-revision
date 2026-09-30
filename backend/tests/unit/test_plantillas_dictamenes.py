"""Alineación vocal (U-D): dictámenes contra wiki/estilo-documental/dictamenes-auditor.md.

Cubre dictamen_radicatoria_consulta.md, dictamen_radicatoria_apelacion.md,
dictamen_fondo.md y relacion_obrados.md — encabezado "DICTAMEN N°", cierre
"Regístrese, Archívese y Notifíquese.", firma del Auditor con default real
(nunca hardcodeada) y las 6 variables antes huérfanas (RECURSO_DESCRIPCION,
ARTICULO_CPM, RESOLUCION_PRINCIPAL, SUGERENCIA_DICTAMEN, VIA_PROCESAL,
SENTIDO_RESOLUCION) resueltas o mapeadas a una variable existente.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.adapters.plantillas.plantilla_markdown_adapter import PlantillaMarkdownAdapter
from tests._factories import make_expediente

RAIZ_DOCS = Path(__file__).resolve().parents[3] / "docs" / "plantillas"

_SLOTS_DIFERIDOS = (
    "{{contexto_expandido}}",
    "{{sugerencia_argumentacion}}",
    "{{criterio_vocal}}",
    "{{consulta_usuario}}",
)


class _FakeExpedienteRepo:
    def __init__(self, expediente) -> None:
        self._expediente = expediente

    async def obtener(self, expediente_id: int):
        self._expediente.id = expediente_id
        return self._expediente


def _texto(nombre: str) -> str:
    return (RAIZ_DOCS / nombre).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "nombre",
    [
        "dictamen_radicatoria_consulta.md",
        "dictamen_radicatoria_apelacion.md",
        "dictamen_fondo.md",
    ],
)
def test_dictamen_tiene_numero_y_cierre_real(nombre: str) -> None:
    """U7: cierre propio de la familia dictamen — nunca el de los autos
    de vista ("tómese razón y notifíquese")."""
    texto = _texto(nombre)

    assert "DICTAMEN N°" in texto or "DICTAMEN DE FONDO N°" in texto
    assert "Regístrese, Archívese y Notifíquese." in texto
    assert "tómese razón" not in texto


def test_dictamenes_radicatoria_base_legal_y_sin_opinar_fondo() -> None:
    for nombre in ("dictamen_radicatoria_consulta.md", "dictamen_radicatoria_apelacion.md"):
        texto = _texto(nombre)
        assert "Artículo 63 Núm. 1) de la Ley de Organización Judicial Militar" in texto
        assert "No es un dictamen de fondo" in texto or "No resuelve los agravios" in texto


@pytest.mark.parametrize(
    "nombre",
    [
        "dictamen_radicatoria_consulta.md",
        "dictamen_radicatoria_apelacion.md",
        "dictamen_fondo.md",
        "relacion_obrados.md",
    ],
)
def test_ninguna_plantilla_hardcodea_el_firmante(nombre: str) -> None:
    """El firmante (Auditor o Vocal Relator) es siempre variable, nunca un
    nombre real hardcodeado en el .md — regla 10 del plan aprobado."""
    texto = _texto(nombre)

    assert "<NOMBRE DEL AUDITOR>" not in texto
    assert "<NOMBRE DEL VOCAL RELATOR>" not in texto


@pytest.mark.asyncio
async def test_dictamen_radicatoria_consulta_render_sin_huerfanas() -> None:
    expediente = make_expediente(
        id=None,
        numero_caso="3352",
        tipo_proceso="consulta",
        delito="Abandono de Servicio",
        sentencia_origen="SENTENCIA Nº 28/2025 (29/11/2025) ABSOLUTORIA",
    )
    adapter = PlantillaMarkdownAdapter(
        plantillas_dir=RAIZ_DOCS, expediente_repo=_FakeExpedienteRepo(expediente)
    )

    result = await adapter.resolver("dictamen_radicatoria_consulta", expediente_id=1)

    for slot in _SLOTS_DIFERIDOS:
        result = result.replace(slot, "")
    assert "{{" not in result
    assert "<NOMBRE DEL AUDITOR>" in result  # FIRMA_AUDITOR real
    assert "3352" in result


@pytest.mark.asyncio
async def test_dictamen_radicatoria_apelacion_render_sin_huerfanas() -> None:
    expediente = make_expediente(
        id=None,
        numero_caso="9999",
        tipo_proceso="apelacion_incidental",
        delito="Abandono de Servicio",
        sentencia_origen="RESOLUCION Nº 17/2025 (12/11/2025) Auto Interlocutorio",
    )
    adapter = PlantillaMarkdownAdapter(
        plantillas_dir=RAIZ_DOCS, expediente_repo=_FakeExpedienteRepo(expediente)
    )

    result = await adapter.resolver("dictamen_radicatoria_apelacion", expediente_id=1)

    for slot in _SLOTS_DIFERIDOS:
        result = result.replace(slot, "")
    assert "{{" not in result
    assert "<NOMBRE DEL AUDITOR>" in result


@pytest.mark.asyncio
async def test_dictamen_fondo_render_sin_huerfanas_y_resuelve_las_6_variables() -> None:
    expediente = make_expediente(
        id=None,
        numero_caso="3142",
        tipo_proceso="apelacion_restringida",
        delito="Abandono del Servicio en Época de Paz",
        sentencia_origen="SENTENCIA Nº 27/2024 (05/08/2024) CONDENATORIA",
    )
    adapter = PlantillaMarkdownAdapter(
        plantillas_dir=RAIZ_DOCS, expediente_repo=_FakeExpedienteRepo(expediente)
    )

    result = await adapter.resolver("dictamen_fondo", expediente_id=1)

    for slot in _SLOTS_DIFERIDOS:
        result = result.replace(slot, "")
    assert "{{" not in result
    assert "SENTENCIA N° 27/2024" in result  # RESOLUCION_PRINCIPAL
    assert "Apelación Restringida" in result  # VIA_PROCESAL
    assert "<NOMBRE DEL AUDITOR>" in result  # FIRMA_AUDITOR
    assert "[CONFIRME / REVOQUE" in result  # instrucción, no dato inventado


@pytest.mark.asyncio
async def test_relacion_obrados_render_sin_huerfanas_reusa_firma_vocal_relator() -> None:
    expediente = make_expediente(
        id=None,
        numero_caso="3288",
        tipo_proceso="consulta",
        delito="Maltrato a Inferiores",
        sentencia_origen="SENTENCIA Nº 12/2025 (10/03/2025) ABSOLUTORIA",
    )
    adapter = PlantillaMarkdownAdapter(
        plantillas_dir=RAIZ_DOCS, expediente_repo=_FakeExpedienteRepo(expediente)
    )

    result = await adapter.resolver("relacion_obrados", expediente_id=1)

    for slot in _SLOTS_DIFERIDOS:
        result = result.replace(slot, "")
    assert "{{" not in result
    assert "ABSOLUTORIA" in result  # SENTIDO_SENTENCIA_INFERIOR (reusada, no SENTIDO_RESOLUCION)
    assert "<NOMBRE DEL VOCAL RELATOR>" in result  # FIRMA_VOCAL_RELATOR real
