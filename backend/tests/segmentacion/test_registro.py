"""Tests básicos del SegmentadorRegistry."""

from __future__ import annotations

import re

import pytest

from src.domain.services.segmentacion.base import SegmentadorNorma
from src.domain.services.segmentacion.registro import SegmentadorRegistry


class _DummySegmentador(SegmentadorNorma):
    """Segmentador dummy para tests."""

    ABREVIATURA = "DUMMY"
    REGEX_ARTICULO = re.compile(r"ARTICULO\s+\d+")

    def segmentar(self, texto_completo: str) -> list:  # type: ignore[override]
        return []


def test_registry_singleton() -> None:
    """El registry es singleton."""
    r1 = SegmentadorRegistry()
    r2 = SegmentadorRegistry()
    assert r1 is r2


def test_registrar_y_obtener() -> None:
    """Registrar y obtener un segmentador funciona."""
    SegmentadorRegistry.limpiar()
    SegmentadorRegistry.registrar("DUMMY", _DummySegmentador)

    seg = SegmentadorRegistry.obtener("DUMMY")
    assert isinstance(seg, _DummySegmentador)
    assert SegmentadorRegistry.disponibles() == ["DUMMY"]


def test_registrar_duplicado_misma_clase_ok() -> None:
    """Registrar la misma clase dos veces no falla."""
    SegmentadorRegistry.limpiar()
    SegmentadorRegistry.registrar("DUMMY", _DummySegmentador)
    SegmentadorRegistry.registrar("DUMMY", _DummySegmentador)  # No debe fallar
    assert SegmentadorRegistry.disponibles() == ["DUMMY"]


def test_registrar_duplicado_otra_clase_falla() -> None:
    """Registrar otra clase para la misma clave falla."""

    class _OtroDummy(SegmentadorNorma):
        regex_articulo = r"OTRO"

        def segmentar(self, texto: str, norma_id: int) -> list:  # type: ignore[override]
            return []

    SegmentadorRegistry.limpiar()
    SegmentadorRegistry.registrar("DUMMY", _DummySegmentador)

    with pytest.raises(ValueError, match="ya registrado"):
        SegmentadorRegistry.registrar("DUMMY", _OtroDummy)


def test_obtener_inexistente_falla() -> None:
    """Obtener clave no registrada lanza KeyError con lista de disponibles."""
    SegmentadorRegistry.limpiar()
    SegmentadorRegistry.registrar("ABC", _DummySegmentador)

    with pytest.raises(KeyError, match="No hay segmentador"):
        SegmentadorRegistry.obtener("XYZ")


def test_limpiar() -> None:
    """limpiar() vacía el registry."""
    SegmentadorRegistry.registrar("TEST", _DummySegmentador)
    assert "TEST" in SegmentadorRegistry.disponibles()

    SegmentadorRegistry.limpiar()
    assert SegmentadorRegistry.disponibles() == []


def test_obtener_para_norma() -> None:
    """obtener_para_norma usa abreviatura de la entidad Norma."""
    from src.domain.entities.norma import Norma

    SegmentadorRegistry.limpiar()
    SegmentadorRegistry.registrar("CPPM", _DummySegmentador)

    norma = Norma(
        id=1,
        nombre="Código de Prueba",
        abreviatura="CPPM",
        tipo="codigo_militar",
        jerarquia="militar",
    )

    seg = SegmentadorRegistry.obtener_para_norma(norma)
    assert isinstance(seg, _DummySegmentador)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
