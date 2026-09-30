"""La plantilla del chat debe fijar el idioma y no maquillar una norma ausente."""

from __future__ import annotations

from pathlib import Path

PLANTILLA = Path(__file__).resolve().parents[3] / "docs" / "plantillas" / "consulta_simple.md"


def _texto() -> str:
    return PLANTILLA.read_text(encoding="utf-8")


def test_exige_responder_en_espanol():
    """Una sentencia en otro idioma hizo que el modelo escribiera «devido processo»."""
    assert "en español" in _texto()


def test_avisa_cuando_falta_la_norma_central():
    assert "no aparece en el contexto" in _texto()


def test_indica_que_el_cpp_es_supletorio():
    assert "supletorio" in _texto()
    assert "Ley 1970" in _texto()


def test_el_derecho_civil_solo_entra_como_supletorio():
    """El vault marca el derecho civil (Ley 439) fuera de alcance salvo como supletorio."""
    texto = _texto()

    assert "- Derecho civil y procesal civil.\n" not in texto
    assert "solo cuando la consulta sea sobre derecho supletorio" in texto


async def test_termina_en_la_consulta_sin_variables_sueltas(caplog):
    """Una nota de diseño con {{expediente_id}} viajaba al prompt tras la consulta."""
    from src.adapters.plantillas.plantilla_markdown_adapter import PlantillaMarkdownAdapter

    adapter = PlantillaMarkdownAdapter(PLANTILLA.parent, expediente_repo=None)
    prompt = await adapter.resolver("consulta_simple", expediente_id=None)

    assert prompt.rstrip().endswith("{{consulta_usuario}}")
    assert "sin resolver" not in caplog.text
