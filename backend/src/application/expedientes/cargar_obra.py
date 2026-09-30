"""Interactor: CargarObra — Caso de uso cargar obra procesal al expediente.

Sprint 4 Fase 2. Regla 5 (Trail of Bits BLOQUEANTE): upload PDF/Word a un
expediente, extracción texto PyMuPDF async, persistencia como Obra privada
por defecto.

Flujo:
1. Validar upload (extension, magic bytes, 50MB max) — ValidadorUpload (Regla 3).
2. Persistir bytes a storage (ruta_archivo).
3. Extraer texto con TextExtractor (PyMuPDF aislado — Regla 5).
4. Si extracción falla → raise CargaObraExtraccionError (router 422 limpio).
5. Persistir Obra via ObraRepo.guardar (estado_visibilidad='privado',
   estado_procesamiento='completado', fuente='carga_usuario').
6. Devolver Response con obra_id.

Clean Architecture: Dominio puro, sin I/O directo. Puertos inyectados:
- ValidadorUpload (domain/service): Regla 3 (validación bytes/mime/extension).
- TextExtractor (port/ABC): Regla 5 (extracción PyMuPDF async).
- ObraRepo (port): persistencia PostgreSQL.
- StoragePort (port): escritura bytes a disco (postergado — ponytail: ahora
  inline via stdlib pathlib; cuando se ejecute en prod, requiere storage
  aislado con cuotas y ACLs, upgrade path).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from src.application.ports.obra_repo import ObraRepo
from src.application.ports.text_extractor import TextExtractor
from src.domain.entities.obra import Obra
from src.domain.services.evaluador_requisitos import es_pieza_entrada
from src.domain.services.validador_upload import UploadInvalidoError, ValidadorUpload


@dataclass(slots=True)
class CargarObraRequest:
    """Entrada del caso de uso CargarObra.

    `contenido_bytes` y `filename` y `content_type` vienen del UploadFile
    FastAPI — el use case no sabe de HTTP, recibe bytes crudos y strings.
    """

    expediente_id: int | None
    propietario_id: int  # JWT del usuario que carga (será el dueño)
    filename: str  # ej: 'sentencia_001.pdf'
    content_type: str  # ej: 'application/pdf'
    contenido_bytes: bytes  # bytes del archivo completo
    tipo_documento: str  # Literal TipoDocumento de Obra
    fojas_inicio: int | None = None
    fojas_fin: int | None = None
    # Autor institucional (instancia inferior, ej. 'TPJM'). Si None, el autor
    # mostrado es el usuario propietario (nombre + cargo).
    autor_instancia: str | None = None
    # Plan A: estado al persistir. Default 'privado' (flujo operador). El
    # supervisor al cargar doctrina global pasa 'global' (auto-aprobación).
    estado_visibilidad: str = "privado"
    # Metadatos de doctrina (Plan A, Regla 5 de la política del vault).
    autor: str | None = None
    fecha_documento: str | None = None
    procedencia: str | None = None
    recomendada: bool = False


@dataclass(slots=True)
class CargarObraResponse:
    """Salida del caso de uso CargarObra."""

    obra_id: int
    # 'privado', salvo piezas de entrada institucionales: nacen 'publicado'.
    estado_visibilidad: str
    # 'completado'. Si la extraccion falla se lanza excepcion: no se persiste.
    estado_procesamiento: str
    created_at_iso: str


class CargaObraValidacionError(ValueError):
    """El upload falló validación Regla 3 (magic bytes, size, etc.)."""


class CargaObraExtraccionError(RuntimeError):
    """La extracción PyMuPDF falló (Regla 5: 422 limpio, no 500)."""


class CargarObra:
    """Caso de uso: Cargar un obra (pieza procesal) a un expediente.

    Regla 5 Trail of Bits: upload PDF/Word validado, extracción aislada,
    fallo → 422 mensaje claro (no 500).

    Args:
        validador_upload: servicio de dominio que valida bytes.
        text_extractor: port que abstracte PyMuPDF/python-docx.
        obra_repo: port para persistir Obra en PostgreSQL.
        storage_path: directorio base donde escribir los archivos
            subidos (postergado — en prod requiere storage con cuotas).
    """

    def __init__(
        self,
        validador_upload: ValidadorUpload,
        text_extractor: TextExtractor,
        obra_repo: ObraRepo,
        storage_path: Path,
    ) -> None:
        self._validador = validador_upload
        self._extractor = text_extractor
        self._obra_repo = obra_repo
        self._storage_path = storage_path

    async def ejecutar(self, request: CargarObraRequest) -> CargarObraResponse:
        """Ejecuta la carga de una obra.

        Raises:
            CargaObraValidacionError: upload falló validación Regla 3.
            CargaObraExtraccionError: extracción PyMuPDF falló (422).
        """
        # 1. Validar upload (Regla 3: nombre, extension, Content-Type, magic bytes, size 500MB)
        try:
            self._validador.validar(
                filename=request.filename,
                content_type=request.content_type,
                data=request.contenido_bytes,
            )
        except UploadInvalidoError as exc:
            raise CargaObraValidacionError(str(exc)) from exc

        # 2. Persistir bytes a disco (postergado: ponytail, sin storage
        # service complejo, directamente a un dir del host. Upgrade path:
        # StoragePort con cuotas + ACLs + checksum cuando se ejecute en prod).
        # ponytail: usar stdlib pathlib, no lib externa.
        ruta_archivo = self._escribir_bytes(request.filename, request.contenido_bytes)

        # 3. Extraer texto con PyMuPDF (aislado, async)
        # ponytail: si extracción falla, no persistimos Obra en estado
        # 'fallido' — ese registro basura ensucia la BD sin aportar valor
        # (el usuario va a reintentar). Upgrade path: si en el futuro se
        # quiere auditar intentos fallidos, persistir con estado_procesam=
        # 'fallido' + metadatos tray_id_usuario, pero el router ya loguea
        # suficiente info de debugging.
        try:
            result = await self._extractor.extract(ruta_archivo)
            contenido_texto = result.full_text
        except Exception as exc:
            ruta_archivo.unlink(missing_ok=True)  # no dejar el archivo huerfano en disco
            # Regla 5: fallo extracción → 422 limpio + mensaje claro.
            raise CargaObraExtraccionError(
                f"Fallo la extracción de texto del archivo '{request.filename}'. "
                f"Verifique que el PDF/Word este bien formado. Detalle: {exc}"
            ) from exc

        # 4. Persistir Obra (entrada institucional → publicado directo, vault taxonomía A)
        visibilidad = request.estado_visibilidad
        if es_pieza_entrada(request.tipo_documento) and visibilidad == "privado":
            visibilidad = "publicado"
        obra = Obra(
            id=None,
            expediente_id=request.expediente_id,
            propietario_id=request.propietario_id,
            tipo_documento=request.tipo_documento,
            nombre_archivo=request.filename,
            contenido_texto=contenido_texto or "",
            estado_visibilidad=visibilidad,
            fuente="carga_usuario",
            ruta_archivo=str(ruta_archivo),
            fojas_inicio=request.fojas_inicio,
            fojas_fin=request.fojas_fin,
            tamano_archivo=len(request.contenido_bytes),
            estado_procesamiento="completado",
            autor_instancia=request.autor_instancia,
            autor=request.autor,
            fecha_documento=request.fecha_documento,
            procedencia=request.procedencia,
            recomendada=request.recomendada,
        )
        try:
            guardada = await self._obra_repo.guardar(obra)
        except Exception:
            ruta_archivo.unlink(missing_ok=True)
            raise

        return CargarObraResponse(
            obra_id=guardada.id,  # type: ignore[arg-type]
            estado_visibilidad=guardada.estado_visibilidad,
            estado_procesamiento=guardada.estado_procesamiento,
            created_at_iso=guardada.created_at.isoformat() if guardada.created_at else "",
        )

    def _escribir_bytes(self, filename: str, data: bytes) -> Path:
        """Escribe bytes al storage_path con nombre interno unico (D-S4K-01).

        Regla 3 (igual que el corpus del Sprint 2): el disco usa UUID; el
        nombre original del usuario solo vive en Obra.nombre_archivo (display
        y descarga). Sin esto, dos cargas con el mismo nombre se sobrescriben
        entre si y la obra A queda apuntando a los bytes de la obra B.

        ponytail: stdlib pathlib, sin lib externa. Upgrade path: StoragePort
        con cuotas + ACLs + checksum SHA256 para prod.
        """
        self._storage_path.mkdir(parents=True, exist_ok=True)
        ext = PurePosixPath(filename).suffix.lower()
        if ext not in (".pdf", ".docx"):
            ext = ".bin"
        ruta = self._storage_path / f"{uuid.uuid4().hex}{ext}"
        ruta.write_bytes(data)
        return ruta
