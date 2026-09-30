"""Tests unitarios de use cases de expedientes (Sprint 4 Fase 6).

Use cases puros — sin DB, sin HTTP. Fakes que cumplen los Protocol
``ExpedienteRepo``, ``ObraRepo``, ``TextExtractor`` (structural typing).

Cobertura:
- AbrirExpediente: exito, numero_caso duplicado
- CargarObra: exito, validacion Regla 3 fallida, extraccion fallida (422)
- PublicarObra: exito, obra no propia (Regla 5 bloqueante)
- ListarHistorialExpediente: exito, solo_propias, es_propia flag, Regla 5
  (el adapter filtra — aca solo verificamos empaquetado DTO)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import override

import pytest

from src.application.expedientes.abrir import (
    AbrirExpediente,
    AbrirExpedienteRequest,
    NumeroCasoDuplicadoError,
)
from src.application.expedientes.cargar_obra import (
    CargaObraExtraccionError,
    CargaObraValidacionError,
    CargarObra,
    CargarObraRequest,
)
from src.application.expedientes.listar_historial import (
    ListarHistorialExpediente,
    ListarHistorialRequest,
)
from src.application.expedientes.publicar_obra import (
    ObraNoPropiaError,
    PublicarObra,
    PublicarObraRequest,
)
from src.application.ports.text_extractor import ExtractionResult, TextExtractor
from src.domain.entities.expediente import Expediente
from src.domain.entities.obra import Obra
from src.domain.services.validador_upload import UploadInvalidoError, ValidadorUpload
from tests._factories import make_expediente

# ---------- Fakes ----------


class FakeExpedienteRepo:
    """ExpedienteRepo in-memory para tests."""

    def __init__(self, existentes: list[Expediente] | None = None) -> None:
        self._por_numero: dict[str, Expediente] = {}
        self._por_id: dict[int, Expediente] = {}
        self._next_id = 1
        for exp in existentes or []:
            exp.id = self._next_id
            exp.created_at = datetime.now(UTC)
            self._por_id[self._next_id] = exp
            self._por_numero[exp.numero_caso] = exp
            self._next_id += 1

    @override
    async def guardar(self, expediente: Expediente) -> Expediente:
        if expediente.numero_caso in self._por_numero:
            # Simula UNIQUE constraint real (defensiva: el use case checkea antes)
            raise ValueError("numero_caso duplicado (UNIQUE)")
        expediente.id = self._next_id
        expediente.created_at = datetime.now(UTC)
        self._por_id[self._next_id] = expediente
        self._por_numero[expediente.numero_caso] = expediente
        self._next_id += 1
        return expediente

    @override
    async def obtener(self, expediente_id: int) -> Expediente | None:
        return self._por_id.get(expediente_id)

    @override
    async def obtener_por_numero_caso(self, numero_caso: str) -> Expediente | None:
        return self._por_numero.get(numero_caso)

    @override
    async def listar_por_usuario(
        self,
        usuario_id: int,
        estado: str | None = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> tuple[list[Expediente], int]:
        items = [e for e in self._por_id.values() if e.abierto_por == usuario_id]
        if estado is not None:
            items = [e for e in items if e.estado == estado]
        total = len(items)
        start = (pagina - 1) * por_pagina
        return items[start : start + por_pagina], total

    @override
    async def actualizar_estado(self, expediente_id: int, estado: str) -> Expediente | None:
        if expediente_id not in self._por_id:
            return None
        self._por_id[expediente_id].estado = estado
        return self._por_id[expediente_id]


class FakeObraRepo:
    """ObraRepo in-memory que aplica Regla 5 (filtro visibilidad)."""

    def __init__(self, existentes: list[Obra] | None = None) -> None:
        self._por_id: dict[int, Obra] = {}
        self._next_id = 1
        for o in existentes or []:
            o.id = self._next_id
            o.created_at = datetime.now(UTC)
            self._por_id[self._next_id] = o
            self._next_id += 1

    @override
    async def guardar(self, obra: Obra) -> Obra:
        obra.id = self._next_id
        obra.created_at = datetime.now(UTC)
        self._por_id[self._next_id] = obra
        self._next_id += 1
        return obra

    @override
    async def obtener(self, obra_id: int, usuario_id: int) -> Obra | None:
        o = self._por_id.get(obra_id)
        if o is None:
            return None
        # Regla 5: propietario OR publicado
        if o.propietario_id == usuario_id or o.estado_visibilidad == "publicado":
            return o
        return None

    @override
    async def listar_por_expediente(
        self,
        expediente_id: int,
        usuario_id: int,
        solo_propias: bool = False,
    ) -> list[Obra]:
        out: list[Obra] = []
        for o in self._por_id.values():
            if o.expediente_id != expediente_id:
                continue
            if solo_propias:
                if o.propietario_id != usuario_id:
                    continue
            else:
                # Regla 5: propietario OR publicado
                if o.propietario_id != usuario_id and o.estado_visibilidad != "publicado":
                    continue
            out.append(o)
        return out

    @override
    async def publicar(self, obra_id: int, propietario_id: int) -> Obra | None:
        o = self._por_id.get(obra_id)
        if o is None or o.propietario_id != propietario_id:
            return None  # Regla 5: no es propietario OR no existe
        o.estado_visibilidad = "publicado"
        return o

    @override
    async def actualizar_estado_procesamiento(self, obra_id: int, estado: str) -> Obra | None:
        o = self._por_id.get(obra_id)
        if o is None:
            return None
        o.estado_procesamiento = estado  # type: ignore[assignment]
        return o


class FakeTextExtractorOk(TextExtractor):
    """Extractor que siempre devuelve texto vacío (ok)."""

    @override
    async def extract(
        self,
        file_path: Path,
        pages: list[int] | None = None,
    ) -> ExtractionResult:
        return ExtractionResult(
            full_text="texto de prueba",
            blocks=[],
            pages_count=1,
            extracted_pages=[1],
            metadata={},
        )

    @override
    async def extract_pages(
        self,
        file_path: Path,
        pages: list[int],
    ) -> ExtractionResult:
        return await self.extract(file_path, pages)


class FakeTextExtractorFail(TextExtractor):
    """Extractor que siempre falla (simula PyMuPDF exception)."""

    @override
    async def extract(
        self,
        file_path: Path,
        pages: list[int] | None = None,
    ) -> ExtractionResult:
        raise RuntimeError("PDF malformado simulado")

    @override
    async def extract_pages(
        self,
        file_path: Path,
        pages: list[int],
    ) -> ExtractionResult:
        return await self.extract(file_path, pages)


class ValidadorAceptaTodo(ValidadorUpload):
    """Validador que acepta todo (bypasa Regla 3 para tests de CargarObra ok)."""

    @override
    def validar(self, filename: str, content_type: str, data: bytes) -> None:
        return None


class ValidadorRechazaTodo(ValidadorUpload):
    """Validador que siempre levanta UploadInvalidoError."""

    @override
    def validar(self, filename: str, content_type: str, data: bytes) -> None:
        raise UploadInvalidoError("upload rechazado (test)")


# ---------- Helpers ----------

PDF_MAGIC = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
PDF_VALID_NAME = "sentencia_001.pdf"
PDF_VALID_CT = "application/pdf"


def _obra(
    *,
    id_: int | None,
    expediente_id: int = 1,
    propietario_id: int = 1,
    estado_visibilidad: str = "privado",
    estado_procesamiento: str = "completado",
    tipo_documento: str = "sentencia",
) -> Obra:
    return Obra(
        id=id_,
        expediente_id=expediente_id,
        propietario_id=propietario_id,
        tipo_documento=tipo_documento,
        nombre_archivo=PDF_VALID_NAME,
        contenido_texto="texto x",
        ruta_archivo=None,
        estado_visibilidad=estado_visibilidad,  # type: ignore[arg-type]
        estado_procesamiento=estado_procesamiento,  # type: ignore[arg-type]
    )


# ---------- AbrirExpediente ----------


class TestAbrirExpediente:
    async def test_apertura_exitosa(self) -> None:
        repo = FakeExpedienteRepo()
        uc = AbrirExpediente(repo)

        resp = await uc.ejecutar(
            AbrirExpedienteRequest(
                numero_caso="TSJM-C-2024-001",
                tipo_proceso="consulta",
                tribunal_origen="TSJM",
                procesado_nombre="Juan Perez",
                delito="Desobedencia",
                abierto_por=5,
            )
        )

        assert resp.expediente_id == 1
        assert resp.numero_caso == "TSJM-C-2024-001"
        assert resp.estado == "activo"
        assert resp.creado_at_iso != ""

    async def test_numero_caso_duplicado(self) -> None:
        existente = make_expediente(numero_caso="DUP-001", abierto_por=1)
        repo = FakeExpedienteRepo(existentes=[existente])
        uc = AbrirExpediente(repo)

        with pytest.raises(NumeroCasoDuplicadoError):
            await uc.ejecutar(
                AbrirExpedienteRequest(
                    numero_caso="DUP-001",
                    tipo_proceso="consulta",
                    tribunal_origen="TSJM",
                    procesado_nombre="X",
                    delito="Y",
                    abierto_por=2,
                )
            )


# ---------- CargarObra ----------


class TestCargarObra:
    async def test_carga_exitosa(self, tmp_path: Path) -> None:
        repo = FakeObraRepo()
        uc = CargarObra(
            validador_upload=ValidadorAceptaTodo(),
            text_extractor=FakeTextExtractorOk(),
            obra_repo=repo,
            storage_path=tmp_path,
        )

        resp = await uc.ejecutar(
            CargarObraRequest(
                expediente_id=1,
                propietario_id=7,
                filename=PDF_VALID_NAME,
                content_type=PDF_VALID_CT,
                contenido_bytes=PDF_MAGIC + b"contenido x",
                tipo_documento="sentencia",
            )
        )

        assert resp.obra_id == 1
        # Piezas de entrada (taxonomía A) nacen publicadas — commit 99b2c8d.
        assert resp.estado_visibilidad == "publicado"
        assert resp.estado_procesamiento == "completado"
        # D-S4K-01: el disco usa nombre UUID interno, no el del usuario.
        obra_guardada = await repo.obtener(1, usuario_id=7)
        assert obra_guardada is not None
        assert obra_guardada.nombre_archivo == PDF_VALID_NAME
        assert obra_guardada.ruta_archivo is not None
        assert Path(obra_guardada.ruta_archivo).parent == tmp_path
        assert Path(obra_guardada.ruta_archivo).stem != PDF_VALID_NAME
        assert Path(obra_guardada.ruta_archivo).exists()
        # Persistencia tamano_archivo
        assert obra_guardada.tamano_archivo == len(PDF_MAGIC + b"contenido x")

    async def test_mismo_filename_no_sobrescribe(self, tmp_path: Path) -> None:
        """D-S4K-01: dos cargas con igual nombre guardan bytes propios."""
        repo = FakeObraRepo()
        uc = CargarObra(
            validador_upload=ValidadorAceptaTodo(),
            text_extractor=FakeTextExtractorOk(),
            obra_repo=repo,
            storage_path=tmp_path,
        )
        req = {
            "expediente_id": 1,
            "propietario_id": 7,
            "filename": "Informe.pdf",
            "content_type": "application/pdf",
            "tipo_documento": "sentencia",
        }
        await uc.ejecutar(CargarObraRequest(contenido_bytes=PDF_MAGIC + b"A", **req))
        await uc.ejecutar(CargarObraRequest(contenido_bytes=PDF_MAGIC + b"B", **req))

        obras = [await repo.obtener(oid, usuario_id=7) for oid in (1, 2)]
        rutas = [Path(o.ruta_archivo) for o in obras]
        assert rutas[0] != rutas[1]
        contenidos = {r.read_bytes() for r in rutas}
        assert contenidos == {PDF_MAGIC + b"A", PDF_MAGIC + b"B"}

    async def test_otro_nace_privado(self, tmp_path: Path) -> None:
        """'otro' NO es pieza de entrada: conserva el flujo privado."""
        repo = FakeObraRepo()
        uc = CargarObra(
            validador_upload=ValidadorAceptaTodo(),
            text_extractor=FakeTextExtractorOk(),
            obra_repo=repo,
            storage_path=tmp_path,
        )

        resp = await uc.ejecutar(
            CargarObraRequest(
                expediente_id=1,
                propietario_id=7,
                filename=PDF_VALID_NAME,
                content_type=PDF_VALID_CT,
                contenido_bytes=PDF_MAGIC + b"x",
                tipo_documento="otro",
            )
        )

        assert resp.estado_visibilidad == "privado"

    async def test_doctrina_y_criterio_no_son_entrada(self, tmp_path: Path) -> None:
        """Candado: doctrina/criterio conservan su flujo propio (Plan A).

        Si alguien los agrega a TIPOS_ENTRADA, este test lo detecta: su
        visibilidad la maneja el flujo de aprobación de doctrina, no la
        regla de piezas de entrada.
        """
        for tipo in ("doctrina", "criterio"):
            repo = FakeObraRepo()
            uc = CargarObra(
                validador_upload=ValidadorAceptaTodo(),
                text_extractor=FakeTextExtractorOk(),
                obra_repo=repo,
                storage_path=tmp_path,
            )

            resp = await uc.ejecutar(
                CargarObraRequest(
                    expediente_id=None,
                    propietario_id=7,
                    filename=PDF_VALID_NAME,
                    content_type=PDF_VALID_CT,
                    contenido_bytes=PDF_MAGIC + b"x",
                    tipo_documento=tipo,  # type: ignore[arg-type]
                )
            )

            assert resp.estado_visibilidad == "privado", tipo

    async def test_global_no_se_degrada(self, tmp_path: Path) -> None:
        """El upgrade es solo privado→publicado: 'global' explícito queda igual."""
        repo = FakeObraRepo()
        uc = CargarObra(
            validador_upload=ValidadorAceptaTodo(),
            text_extractor=FakeTextExtractorOk(),
            obra_repo=repo,
            storage_path=tmp_path,
        )

        resp = await uc.ejecutar(
            CargarObraRequest(
                expediente_id=1,
                propietario_id=7,
                filename=PDF_VALID_NAME,
                content_type=PDF_VALID_CT,
                contenido_bytes=PDF_MAGIC + b"x",
                tipo_documento="sentencia",
                estado_visibilidad="global",
            )
        )

        assert resp.estado_visibilidad == "global"

    async def test_validacion_fallida_lanza_excepcion_regla3(self, tmp_path: Path) -> None:
        uc = CargarObra(
            validador_upload=ValidadorRechazaTodo(),
            text_extractor=FakeTextExtractorOk(),
            obra_repo=FakeObraRepo(),
            storage_path=tmp_path,
        )

        with pytest.raises(CargaObraValidacionError):
            await uc.ejecutar(
                CargarObraRequest(
                    expediente_id=1,
                    propietario_id=7,
                    filename="malicioso.exe",
                    content_type="application/x-msdownload",
                    contenido_bytes=b"MZ",
                    tipo_documento="otro",
                )
            )

    async def test_extraccion_fallida_lanza_422_no_500(self, tmp_path: Path) -> None:
        repo = FakeObraRepo()
        uc = CargarObra(
            validador_upload=ValidadorAceptaTodo(),
            text_extractor=FakeTextExtractorFail(),
            obra_repo=repo,
            storage_path=tmp_path,
        )

        with pytest.raises(CargaObraExtraccionError):
            await uc.ejecutar(
                CargarObraRequest(
                    expediente_id=1,
                    propietario_id=7,
                    filename=PDF_VALID_NAME,
                    content_type=PDF_VALID_CT,
                    contenido_bytes=PDF_MAGIC,
                    tipo_documento="sentencia",
                )
            )

        # ponytail: garanteia que NO se persistio obra basura con estado='fallido'
        assert len(repo._por_id) == 0
        # F-11: tampoco debe quedar el archivo huerfano en disco.
        assert list(tmp_path.iterdir()) == []


# ---------- PublicarObra ----------


class FakeVectorVisibilidad:
    """Registra las sincronizaciones de visibilidad hacia Qdrant."""

    def __init__(self, falla: bool = False) -> None:
        self.llamadas: list[tuple[int, str]] = []
        self._falla = falla

    async def actualizar_visibilidad_obra(self, obra_id: int, visibilidad: str) -> None:
        if self._falla:
            raise RuntimeError("qdrant caido")
        self.llamadas.append((obra_id, visibilidad))


class TestPublicarObra:
    async def test_publicar_propietario_exitoso(self) -> None:
        obra = _obra(id_=None, propietario_id=10)
        repo = FakeObraRepo(existentes=[obra])
        vectores = FakeVectorVisibilidad()
        uc = PublicarObra(repo, vectores)

        resp = await uc.ejecutar(PublicarObraRequest(obra_id=1, propietario_id=10))

        assert resp.obra_id == 1
        assert resp.estado_visibilidad == "publicado"
        # F-12: el payload de Qdrant debe reflejar la publicacion.
        assert vectores.llamadas == [(1, "publicado")]

    async def test_publicar_no_falla_si_qdrant_cae(self) -> None:
        obra = _obra(id_=None, propietario_id=10)
        uc = PublicarObra(FakeObraRepo(existentes=[obra]), FakeVectorVisibilidad(falla=True))

        resp = await uc.ejecutar(PublicarObraRequest(obra_id=1, propietario_id=10))

        assert resp.estado_visibilidad == "publicado"

    async def test_publicar_no_propietario_lanza_regla5(self) -> None:
        obra = _obra(id_=None, propietario_id=10)
        repo = FakeObraRepo(existentes=[obra])
        uc = PublicarObra(repo, FakeVectorVisibilidad())

        with pytest.raises(ObraNoPropiaError):
            await uc.ejecutar(PublicarObraRequest(obra_id=1, propietario_id=99))

    async def test_publicar_obra_inexistente_lanza(self) -> None:
        uc = PublicarObra(FakeObraRepo(), FakeVectorVisibilidad())
        with pytest.raises(ObraNoPropiaError):
            await uc.ejecutar(PublicarObraRequest(obra_id=999, propietario_id=1))


# ---------- ListarHistorialExpediente ----------


class TestListarHistorialExpediente:
    async def test_lista_incluye_propias_y_publicadas(self) -> None:
        obras = [
            _obra(id_=None, propietario_id=10),  # propia
            _obra(  # ajena publicada
                id_=None,
                propietario_id=20,
                estado_visibilidad="publicado",
            ),
            _obra(  # ajena privada (Regla 5)
                id_=None,
                propietario_id=20,
                estado_visibilidad="privado",
            ),
        ]
        repo = FakeObraRepo(existentes=obras)
        uc = ListarHistorialExpediente(repo)

        resp = await uc.ejecutar(ListarHistorialRequest(expediente_id=1, usuario_id=10))

        assert resp.total == 2  # la obra privada ajena NO debe aparecer
        ids = [o.id for o in resp.obras]
        assert 1 in ids and 2 in ids
        assert 3 not in ids

    async def test_es_propia_flag_correcta(self) -> None:
        obras = [
            _obra(id_=None, propietario_id=10),  # propia -> es_propia
            _obra(  # ajena -> es_propia False
                id_=None,
                propietario_id=20,
                estado_visibilidad="publicado",
            ),
        ]
        repo = FakeObraRepo(existentes=obras)
        uc = ListarHistorialExpediente(repo)

        resp = await uc.ejecutar(ListarHistorialRequest(expediente_id=1, usuario_id=10))

        propia = next(o for o in resp.obras if o.id == 1)
        ajena = next(o for o in resp.obras if o.id == 2)
        assert propia.es_propia is True
        assert ajena.es_propia is False

    async def test_solo_propias_filtra_solo_propietario(self) -> None:
        obras = [
            _obra(id_=None, propietario_id=10),  # propia
            _obra(id_=None, propietario_id=20, estado_visibilidad="publicado"),  # ajena publicada
        ]
        repo = FakeObraRepo(existentes=obras)
        uc = ListarHistorialExpediente(repo)

        resp = await uc.ejecutar(
            ListarHistorialRequest(expediente_id=1, usuario_id=10, solo_propias=True)
        )

        assert resp.total == 1
        assert resp.obras[0].id == 1

    async def test_doctrina_no_se_lista_como_obra_del_historial(self) -> None:
        """Plan C (C1.4): la doctrina/criterio del expediente solo sale en el
        desplegable 'doctrina privada', no en el historial de obras (evita
        duplicación en el chat)."""
        obras = [
            _obra(id_=None, propietario_id=10, tipo_documento="sentencia"),
            _obra(
                id_=None,
                propietario_id=10,
                tipo_documento="doctrina",
                estado_visibilidad="publicado",
            ),
            _obra(id_=None, propietario_id=10, tipo_documento="criterio"),
        ]
        repo = FakeObraRepo(existentes=obras)
        uc = ListarHistorialExpediente(repo)

        resp = await uc.ejecutar(ListarHistorialRequest(expediente_id=1, usuario_id=10))

        assert resp.total == 1
        assert resp.obras[0].tipo_documento == "sentencia"

    async def test_lista_vacia(self) -> None:
        uc = ListarHistorialExpediente(FakeObraRepo())
        resp = await uc.ejecutar(ListarHistorialRequest(expediente_id=999, usuario_id=10))
        assert resp.total == 0
        assert resp.obras == []
