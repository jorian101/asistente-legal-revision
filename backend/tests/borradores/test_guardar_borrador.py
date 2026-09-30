"""Tests del use case GuardarBorrador (guardado explicito desde el chat).

Verifica:
- Crea borrador con chat_id/mensaje_id cuando no existe.
- Actualiza (nueva version) cuando el chat ya tiene borrador.
- Rechaza tipos que no generan borrador (consulta_simple).
- Exige expediente_id.
"""

from __future__ import annotations

from typing import override

import pytest

from src.application.borradores.guardar_borrador import (
    ExpedienteObligatorioError,
    TipoNoGeneraBorradorError,
    guardar,
)
from src.domain.entities.borrador import Borrador


class FakeBorradorRepo:
    def __init__(self, existente: Borrador | None = None) -> None:
        self.existente = existente
        self.creados: list[Borrador] = []
        self.actualizados: list[tuple[int, str, dict | None]] = []

    @override
    async def obtener_por_chat(self, chat_id: int, propietario_id: int) -> Borrador | None:
        if self.existente is not None and self.existente.chat_id == chat_id:
            return self.existente
        return None

    @override
    async def crear(self, borrador: Borrador) -> Borrador:
        borrador.id = 1
        self.creados.append(borrador)
        return borrador

    @override
    async def actualizar_contenido_con_fuentes(
        self, borrador_id: int, contenido: str, fuentes: dict | None, razonamiento: str = ""
    ) -> Borrador | None:
        self.actualizados.append((borrador_id, contenido, fuentes, razonamiento))
        return self.existente


async def test_guardar_crea_borrador_nuevo():
    repo = FakeBorradorRepo()
    result = await guardar(
        repo,
        propietario_id=7,
        expediente_id=3,
        tipo_respuesta="auto_vista_consulta",
        contenido="Auto de vista...",
        fuentes={"fragmentos_count": 2},
        chat_id=55,
        mensaje_id=101,
    )
    assert result.id == 1
    assert repo.creados[0].tipo == "proyecto_auto_vista_consulta"
    assert repo.creados[0].chat_id == 55
    assert repo.creados[0].mensaje_id == 101
    assert repo.creados[0].propietario_id == 7
    assert repo.creados[0].plantilla_usada == "proyecto_auto_vista_consulta.md"


async def test_guardar_actualiza_version_cuando_ya_existe():
    existente = Borrador(
        id=9,
        expediente_id=3,
        propietario_id=7,
        tipo="proyecto_auto_vista_consulta",
        contenido="Viejo",
        chat_id=55,
    )
    repo = FakeBorradorRepo(existente=existente)

    result = await guardar(
        repo,
        propietario_id=7,
        expediente_id=3,
        tipo_respuesta="auto_vista_consulta",
        contenido="Nueva version",
        fuentes={"fragmentos_count": 1},
        chat_id=55,
        mensaje_id=102,
    )

    assert result.id == 9  # no creo uno nuevo
    assert repo.actualizados == [(9, "Nueva version", {"fragmentos_count": 1}, "")]
    assert repo.creados == []


async def test_guardar_persiste_razonamiento_del_modo_pensar():
    """El razonamiento del chat (modo pensar) se guarda con el borrador."""
    repo = FakeBorradorRepo()
    result = await guardar(
        repo,
        propietario_id=7,
        expediente_id=3,
        tipo_respuesta="auto_vista_consulta",
        contenido="Auto de vista...",
        chat_id=55,
        razonamiento="Analicé fojas 1-8 y la competencia es clara.",
    )
    assert repo.creados[0].razonamiento == "Analicé fojas 1-8 y la competencia es clara."
    assert result.razonamiento.startswith("Analicé")


async def test_guardar_rechaza_consulta_simple():
    repo = FakeBorradorRepo()
    with pytest.raises(TipoNoGeneraBorradorError):
        await guardar(
            repo,
            propietario_id=7,
            expediente_id=3,
            tipo_respuesta="consulta_simple",
            contenido="x",
        )


async def test_guardar_requiere_expediente():
    repo = FakeBorradorRepo()
    with pytest.raises(ExpedienteObligatorioError):
        await guardar(
            repo,
            propietario_id=7,
            expediente_id=None,  # type: ignore[arg-type]
            tipo_respuesta="auto_vista_consulta",
            contenido="x",
        )
