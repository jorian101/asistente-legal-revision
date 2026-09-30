"""Tests F1: ProcesadorContexto — dedup, etiquetas SRL-lite y presupuesto.

Cobertura:
- Dedup: mismo padre ascendido por varios hijos -> un solo bloque
- Etiquetas: norma -> NORMA, obra -> OBRADO o etiqueta custom del mapa
- Presupuesto: bloques enteros, siempre >= 1, nunca corta a mitad
- Render: formato `[ETIQUETA · path]\\ntexto`
"""

from __future__ import annotations

import pytest

from src.application.services.procesador_contexto import ProcesadorContexto
from src.domain.value_objects.contexto_expandido import ContextoExpandido
from tests._factories import make_fragmento


def _contexto(*fragmentos, breadcrumbs=()) -> ContextoExpandido:
    return ContextoExpandido(
        fragmentos_con_padres=tuple(fragmentos),
        scores=tuple(1.0 for _ in fragmentos),
        query_original="q",
        tipo_respuesta="consulta_simple",
        expediente_id=None,
        breadcrumbs=breadcrumbs,
    )


def test_dedup_mismo_padre_un_solo_bloque() -> None:
    """Padre (id=10) alcanzado por dos hijos aparece UNA vez, en su primera posicion."""
    hijo_a = make_fragmento(id=1, norma_id=None, obra_id=5)
    hijo_b = make_fragmento(id=2, norma_id=None, obra_id=5)
    padre = make_fragmento(id=10, norma_id=None, obra_id=5)

    bloques = ProcesadorContexto().procesar(_contexto(hijo_a, padre, hijo_b, padre))

    assert len(bloques) == 3
    assert bloques[1].texto == padre.texto


def test_etiqueta_norma() -> None:
    frag = make_fragmento(norma_id=7, obra_id=None)
    (bloque,) = ProcesadorContexto().procesar(_contexto(frag))
    assert bloque.etiqueta == "NORMA"


def test_etiqueta_obra_default_y_custom() -> None:
    obrado = make_fragmento(id=1, norma_id=None, obra_id=3, qdrant_point_id="pt-obrado")
    doctrina = make_fragmento(id=2, norma_id=None, obra_id=9, qdrant_point_id="pt-doctrina")

    bloques = ProcesadorContexto().procesar(
        _contexto(obrado, doctrina), etiquetas_obra={9: "DOCTRINA"}
    )

    assert [b.etiqueta for b in bloques] == ["OBRADO", "DOCTRINA"]


def test_presupuesto_corta_en_bloques_enteros_y_deja_al_menos_uno() -> None:
    frags = [make_fragmento(id=i, norma_id=1, texto="x" * 50) for i in range(10)]
    # max_chars = 40*4 = 160; cada bloque rinde ~70 chars -> entran 2, no 10.
    bloques = ProcesadorContexto(max_tokens=40).procesar(_contexto(*frags))

    assert 1 <= len(bloques) < 10
    for bloque in bloques:
        assert bloque.texto == "x" * 50  # ningun texto cortado


def test_render_con_path() -> None:
    frag = make_fragmento(qdrant_point_id="pt-x")
    (bloque,) = ProcesadorContexto().procesar(_contexto(frag, breadcrumbs=(("CPPM", "184"),)))
    assert bloque.renderizar() == "[NORMA · CPPM > 184]\n" + frag.texto


def test_contexto_vacio_devuelve_tupla_vacia() -> None:
    assert ProcesadorContexto().procesar(_contexto()) == ()


def test_parametros_invalidos_rechazados() -> None:
    with pytest.raises(ValueError):
        ProcesadorContexto(max_tokens=0)
    with pytest.raises(ValueError):
        ProcesadorContexto(chars_por_token=0)
