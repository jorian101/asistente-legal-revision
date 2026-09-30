"""Tests del mapeo rol-cargo (Tabla 18 del marco-practico).

Verifica:
- La matriz CARGOS_POR_ROL cumple Tabla 18.
- cargos_validos_para_rol para cada rol.
- validar_cargo_para_rol acepta pares válidos y rechaza inválidos.
"""

from __future__ import annotations

import pytest

from src.domain.entities.usuario import (
    CARGOS_POR_ROL,
    CargoInvalidoParaRolError,
    cargos_validos_para_rol,
    validar_cargo_para_rol,
)


def test_matriz_tabla_18():
    assert CARGOS_POR_ROL["administrador"] == frozenset({"Personal Técnico"})
    assert CARGOS_POR_ROL["operador_juridico"] == frozenset(
        {"Auditor", "Fiscal", "Vocal Relator", "Secretaria de Cámara"}
    )
    assert CARGOS_POR_ROL["supervisor"] == frozenset(
        {"Vocal Presidente", "Auxiliar de Secretaría de Cámara"}
    )


def test_no_existe_cargo_otro():
    """El escape legacy 'Otro' fue eliminado (Tabla 18 estricta)."""
    for _rol, cargos in CARGOS_POR_ROL.items():
        assert "Otro" not in cargos


def test_cargos_validos_rol_desconocido_vacio():
    assert cargos_validos_para_rol("rol-inventado") == frozenset()


def test_validar_acepta_pares_validos():
    for rol, cargos in CARGOS_POR_ROL.items():
        for cargo in cargos:
            validar_cargo_para_rol(rol, cargo)  # no debe lanzar


@pytest.mark.parametrize(
    "rol,cargo",
    [
        ("operador_juridico", "Vocal Presidente"),  # cargo de supervisor
        ("supervisor", "Fiscal"),  # cargo de operador
        ("administrador", "Auditor"),  # admin no es SAC
        ("supervisor", "Personal Técnico"),  # solo admin
    ],
)
def test_validar_rechaza_pares_invalidos(rol, cargo):
    with pytest.raises(CargoInvalidoParaRolError):
        validar_cargo_para_rol(rol, cargo)
