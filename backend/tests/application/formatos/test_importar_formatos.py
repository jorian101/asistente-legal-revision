"""ImportarFormatos: importa layouts del vault (layout.json) a la tabla de formatos.

Usa un vault temporal en disco (`tmp_path`) y un repo en memoria: se verifica el
upsert por slug/hash, que un formato canonico no se pise y que un layout roto se
omita sin abortar la importacion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.application.formatos.importar_formatos import ImportarFormatos
from src.domain.entities.formato_documento import FormatoDocumento


class _RepoMemoria:
    def __init__(self) -> None:
        self.por_slug: dict[str, FormatoDocumento] = {}
        self.actualizados: list[str] = []

    async def obtener_por_slug(self, slug: str) -> FormatoDocumento | None:
        return self.por_slug.get(slug)

    async def guardar(self, formato: FormatoDocumento) -> FormatoDocumento:
        self.por_slug[formato.slug] = formato
        return formato

    async def actualizar(self, formato: FormatoDocumento) -> FormatoDocumento:
        self.actualizados.append(formato.slug)
        return formato


def _layout(vault: Path, tipo: str, slug: str, meta: dict | None = None, **extra) -> Path:
    carpeta = vault / tipo / slug
    carpeta.mkdir(parents=True)
    ruta = carpeta / "layout.json"
    ruta.write_text(
        json.dumps({"meta": meta or {}, "blocks": [{"page": 1, "index": 0}]}), encoding="utf-8"
    )
    if "esqueleto" in extra:
        (carpeta / "formato.json").write_text(
            json.dumps({"esqueleto": extra["esqueleto"]}), encoding="utf-8"
        )
    return ruta


@pytest.mark.asyncio
async def test_crea_un_formato_nuevo_con_datos_del_layout(tmp_path: Path) -> None:
    _layout(
        tmp_path,
        "auto_vista",
        "auto-1",
        meta={"autor": "aliaga", "engine": "docling", "hash_fuente": "H1"},
        esqueleto=[{"page": 1, "index": 0}],
    )
    repo = _RepoMemoria()

    resumen = await ImportarFormatos(repo).ejecutar(tmp_path)

    assert resumen == {"importados": 1, "omitidos": 0, "total": 1}
    f = repo.por_slug["auto-1"]
    assert (f.tipo_documento, f.autor, f.engine, f.hash_fuente) == (
        "auto_vista",
        "aliaga",
        "docling",
        "H1",
    )
    assert f.estado == "borrador" and f.version == 1
    assert f.bloques == [{"page": 1, "index": 0}] and f.esqueleto == [{"page": 1, "index": 0}]


@pytest.mark.asyncio
async def test_sin_metadatos_usa_valores_por_defecto_y_hash_del_archivo(tmp_path: Path) -> None:
    _layout(tmp_path, "sentencia", "s-1")
    repo = _RepoMemoria()

    await ImportarFormatos(repo).ejecutar(tmp_path)

    f = repo.por_slug["s-1"]
    assert (f.autor, f.engine) == ("desconocido", "desconocido")
    assert len(f.hash_fuente) == 16  # sha256 truncado del archivo


@pytest.mark.asyncio
async def test_reimportar_lo_mismo_se_omite(tmp_path: Path) -> None:
    _layout(tmp_path, "auto_vista", "auto-1", meta={"hash_fuente": "H1"})
    repo = _RepoMemoria()
    uc = ImportarFormatos(repo)
    await uc.ejecutar(tmp_path)

    resumen = await uc.ejecutar(tmp_path)

    assert resumen == {"importados": 0, "omitidos": 1, "total": 1}
    assert repo.actualizados == []


@pytest.mark.asyncio
async def test_si_cambia_el_hash_actualiza_el_existente_y_sube_la_version(tmp_path: Path) -> None:
    ruta = _layout(tmp_path, "auto_vista", "auto-1", meta={"hash_fuente": "H1"})
    repo = _RepoMemoria()
    uc = ImportarFormatos(repo)
    await uc.ejecutar(tmp_path)
    ruta.write_text(
        json.dumps({"meta": {"hash_fuente": "H2"}, "blocks": [{"page": 2, "index": 5}]}),
        encoding="utf-8",
    )

    resumen = await uc.ejecutar(tmp_path)

    f = repo.por_slug["auto-1"]
    assert resumen["importados"] == 1
    assert (f.hash_fuente, f.version, f.bloques) == ("H2", 2, [{"page": 2, "index": 5}])
    assert repo.actualizados == ["auto-1"]


@pytest.mark.asyncio
async def test_no_pisa_un_formato_canonico(tmp_path: Path) -> None:
    _layout(tmp_path, "auto_vista", "auto-1", meta={"hash_fuente": "NUEVO"})
    repo = _RepoMemoria()
    repo.por_slug["auto-1"] = FormatoDocumento(
        id=1,
        tipo_documento="auto_vista",
        slug="auto-1",
        autor="aliaga",
        engine="x",
        meta={},
        bloques=[],
        estado="canonico",
        hash_fuente="VIEJO",
    )

    resumen = await ImportarFormatos(repo).ejecutar(tmp_path)

    assert resumen == {"importados": 0, "omitidos": 1, "total": 1}
    assert repo.por_slug["auto-1"].hash_fuente == "VIEJO" and repo.actualizados == []


@pytest.mark.asyncio
async def test_mismo_hash_pero_llega_esqueleto_lo_completa(tmp_path: Path) -> None:
    _layout(tmp_path, "auto_vista", "auto-1", meta={"hash_fuente": "H1"})
    repo = _RepoMemoria()
    uc = ImportarFormatos(repo)
    await uc.ejecutar(tmp_path)
    (tmp_path / "auto_vista" / "auto-1" / "formato.json").write_text(
        json.dumps({"esqueleto": [{"page": 1, "index": 0}]}), encoding="utf-8"
    )

    resumen = await uc.ejecutar(tmp_path)

    f = repo.por_slug["auto-1"]
    assert resumen["importados"] == 1 and f.esqueleto == [{"page": 1, "index": 0}]
    assert f.version == 2


@pytest.mark.asyncio
async def test_layout_con_json_invalido_se_omite_sin_abortar(tmp_path: Path) -> None:
    roto = tmp_path / "auto_vista" / "roto"
    roto.mkdir(parents=True)
    (roto / "layout.json").write_text("{no es json", encoding="utf-8")
    _layout(tmp_path, "auto_vista", "sano", meta={"hash_fuente": "H"})
    repo = _RepoMemoria()

    resumen = await ImportarFormatos(repo).ejecutar(tmp_path)

    assert resumen == {"importados": 1, "omitidos": 1, "total": 2}
    assert set(repo.por_slug) == {"sano"}


@pytest.mark.asyncio
async def test_esqueleto_ilegible_se_ignora(tmp_path: Path) -> None:
    _layout(tmp_path, "auto_vista", "auto-1", meta={"hash_fuente": "H1"})
    (tmp_path / "auto_vista" / "auto-1" / "formato.json").write_text("{roto", encoding="utf-8")
    repo = _RepoMemoria()

    await ImportarFormatos(repo).ejecutar(tmp_path)

    assert repo.por_slug["auto-1"].esqueleto is None


@pytest.mark.asyncio
async def test_vault_vacio(tmp_path: Path) -> None:
    resumen = await ImportarFormatos(_RepoMemoria()).ejecutar(tmp_path)

    assert resumen == {"importados": 0, "omitidos": 0, "total": 0}
