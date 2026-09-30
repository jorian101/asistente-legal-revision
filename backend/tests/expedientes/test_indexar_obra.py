from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.application.expedientes.indexar_obra import IndexarObra
from src.domain.entities.obra import Obra


@dataclass
class FakeEmbedder:
    calls: list[list[str]]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[float(index)] for index, _ in enumerate(texts)]

    async def close(self) -> None:
        return None


class FakeFragmentoRepo:
    def __init__(self) -> None:
        self.fragmentos: list[Any] = []

    async def save_many(self, fragmentos: list[Any]) -> list[Any]:
        self.fragmentos.extend(fragmentos)
        return fragmentos

    async def delete_by_obra(self, obra_id: int) -> int:
        self.fragmentos.clear()
        return 0


class FakeVectorRepo:
    def __init__(self) -> None:
        self.points: list[dict[str, Any]] = []

    async def upsert_corpus(self, points: list[dict[str, Any]]) -> None:
        self.points.extend(points)

    async def delete_by_obra(self, obra_id: int) -> None:
        self.points.clear()


class FakeObraRepo:
    def __init__(self, obra: Obra) -> None:
        self.obra = obra
        self.states: list[str] = []

    async def actualizar_estado_procesamiento(self, obra_id: int, estado: str) -> Obra:
        self.states.append(estado)
        self.obra.estado_procesamiento = estado  # type: ignore[assignment]
        return self.obra


@pytest.mark.asyncio
async def test_indexa_obra_con_filtro_de_expediente_y_privacidad() -> None:
    obra = Obra(
        id=7,
        expediente_id=42,
        propietario_id=9,
        tipo_documento="sentencia",
        nombre_archivo="sentencia.pdf",
        contenido_texto="a" * 700,
        fojas_inicio=10,
        fojas_fin=20,
        estado_procesamiento="pendiente",
    )
    embedder = FakeEmbedder([])
    fragmentos = FakeFragmentoRepo()
    vectors = FakeVectorRepo()
    obras = FakeObraRepo(obra)

    indexador = IndexarObra(
        obra_repo=obras,
        fragmento_repo=fragmentos,
        embedder=embedder,
        vector_repo=vectors,
        chunk_size=500,
        overlap=50,
    )
    result = await indexador.ejecutar(obra)

    assert result.fragmentos_creados == 2
    assert len(fragmentos.fragmentos) == 2
    assert len(vectors.points) == 2
    assert all(point["payload"]["obra_id"] == 7 for point in vectors.points)
    assert all(point["payload"]["expediente_id"] == 42 for point in vectors.points)
    assert all(point["payload"]["propietario_id"] == 9 for point in vectors.points)
    assert all(point["payload"]["visibilidad"] == "privado" for point in vectors.points)
    assert obras.states == ["procesando", "completado"]

    first_ids = [point["id"] for point in vectors.points]
    await indexador.ejecutar(obra)
    assert [point["id"] for point in vectors.points] == first_ids
    assert len(fragmentos.fragmentos) == 2


@pytest.mark.asyncio
async def test_criterio_del_vocal_no_se_vectoriza() -> None:
    """Los criterios se inyectan al prompt, no son fuente RAG: no se indexan."""
    obra = Obra(
        id=25,
        expediente_id=None,
        propietario_id=26,
        tipo_documento="criterio",
        nombre_archivo="verificacion-consistencia.md",
        contenido_texto="a" * 700,
        estado_visibilidad="global",
        estado_procesamiento="completado",
    )
    embedder = FakeEmbedder([])
    fragmentos = FakeFragmentoRepo()
    vectors = FakeVectorRepo()
    obras = FakeObraRepo(obra)

    indexador = IndexarObra(
        obra_repo=obras,
        fragmento_repo=fragmentos,
        embedder=embedder,
        vector_repo=vectors,
        chunk_size=500,
        overlap=50,
    )
    result = await indexador.ejecutar(obra)

    assert result.fragmentos_creados == 0
    assert result.vectores_indexados == 0
    assert embedder.calls == []  # no se embebe
    assert vectors.points == []  # no se upsertea
    assert fragmentos.fragmentos == []
    assert obras.states == []  # no cambia estado_procesamiento
