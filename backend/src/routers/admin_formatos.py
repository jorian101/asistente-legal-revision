"""Router admin: Gestión de Formatos TSJM (módulo formatos).

Sprint: formatos (pipeline alta fidelidad). Solo admin autenticado.

Endpoints:
  GET    /admin/formatos                      — listar con filtros
  GET    /admin/formatos/{formato_id}         — obtener por id
  GET    /admin/formatos/slug/{slug}          — obtener por slug
  PATCH  /admin/formatos/{formato_id}/bloques/{block_key} — corregir bloque
  POST   /admin/formatos/{formato_id}/promover — marcar como canonico del tipo
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from src.adapters.http.dependencies import AuditLogRepoDep, FormatoRepoDep, require_permiso
from src.application.admin.audit import registrar_auditoria_segura
from src.application.formatos.actualizar_bloque import ActualizarBloque
from src.application.formatos.actualizar_configuracion import ActualizarConfiguracionFormato
from src.application.formatos.eliminar_bloque import EliminarBloque
from src.application.formatos.importar_formatos import ImportarFormatos
from src.application.formatos.listar_formatos import ListarFormatos
from src.application.formatos.obtener_formato import ObtenerFormato
from src.application.formatos.promover_formato import PromoverFormato
from src.application.formatos.reordenar_bloques import ReordenarBloques
from src.config import get_settings
from src.domain.entities.usuario import Usuario  # noqa: F401 — usado en Annotated

router = APIRouter(prefix="/admin/formatos", tags=["admin", "formatos"])


class BloquePatch(BaseModel):
    text: str | None = Field(default=None, description="Nuevo texto del primer run")
    align: str | None = Field(default=None, description="left|center|right|justify")
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    size_pt: float | None = None
    font: str | None = None
    note: str | None = None


class ConfiguracionFormatoPatch(BaseModel):
    """PATCH /admin/formatos/{id}/configuracion — config global de página/fuente.

    page: tamaño de hoja + márgenes (lo que el usuario ve en el preview).
    base: fuente/tamaño de fuente globales.
    Merge parcial: solo se actualizan las claves enviadas.
    """

    tamano_hoja: str | None = Field(default=None, pattern="^(carta|oficio|a4)$")
    margin_top_mm: float | None = None
    margin_right_mm: float | None = None
    margin_bottom_mm: float | None = None
    margin_left_mm: float | None = None
    font: str | None = None
    size_pt: float | None = None


def _to_response(formato: Any) -> dict[str, Any]:
    return {
        "id": formato.id,
        "tipo_documento": formato.tipo_documento,
        "slug": formato.slug,
        "autor": formato.autor,
        "engine": formato.engine,
        "estado": formato.estado,
        "version": formato.version,
        "meta": formato.meta,
        "bloques": formato.bloques,
        "esqueleto": formato.esqueleto,
        "hash_fuente": formato.hash_fuente,
        "created_at": formato.created_at.isoformat() if formato.created_at else None,
        "updated_at": formato.updated_at.isoformat() if formato.updated_at else None,
    }


class ReordenPatch(BaseModel):
    orden: list[str] = Field(description="Lista ordenada de block_key pN:iM")


@router.get("", status_code=status.HTTP_200_OK)
async def listar_formatos(
    current_user: Annotated[Usuario, Depends(require_permiso("formatos", "leer"))],
    formato_repo: FormatoRepoDep,
    tipo_documento: str | None = Query(default=None),
    autor: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    use_case = ListarFormatos(formato_repo)
    items, total = await use_case.ejecutar(
        tipo_documento=tipo_documento,
        autor=autor,
        estado=estado,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return {
        "items": [_to_response(i) for i in items],
        "total": total,
        "pagina": pagina,
        "por_pagina": por_pagina,
    }


@router.get("/slug/{slug}", status_code=status.HTTP_200_OK)
async def obtener_por_slug(
    slug: str,
    current_user: Annotated[Usuario, Depends(require_permiso("formatos", "leer"))],
    formato_repo: FormatoRepoDep,
) -> dict[str, Any]:
    _ = current_user
    use_case = ObtenerFormato(formato_repo)
    try:
        formato = await use_case.ejecutar_por_slug(slug)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(formato)


@router.get("/{formato_id}", status_code=status.HTTP_200_OK)
async def obtener_por_id(
    formato_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("formatos", "leer"))],
    formato_repo: FormatoRepoDep,
) -> dict[str, Any]:
    _ = current_user
    use_case = ObtenerFormato(formato_repo)
    try:
        formato = await use_case.ejecutar_por_id(formato_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(formato)


@router.patch("/{formato_id}/bloques/reordenar", status_code=status.HTTP_200_OK)
async def reordenar_bloques(
    formato_id: int,
    body: ReordenPatch,
    current_user: Annotated[Usuario, Depends(require_permiso("formatos", "actualizar"))],
    formato_repo: FormatoRepoDep,
) -> dict[str, Any]:
    _ = current_user
    use_case = ReordenarBloques(formato_repo)
    try:
        formato = await use_case.ejecutar(formato_id, body.orden)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(formato)


@router.delete("/{formato_id}/bloques/{block_key}", status_code=status.HTTP_200_OK)
async def eliminar_bloque(
    formato_id: int,
    block_key: str,
    current_user: Annotated[Usuario, Depends(require_permiso("formatos", "actualizar"))],
    formato_repo: FormatoRepoDep,
    audit_repo: AuditLogRepoDep,
) -> dict[str, Any]:
    use_case = EliminarBloque(formato_repo)
    try:
        formato = await use_case.ejecutar(formato_id, block_key)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await registrar_auditoria_segura(
        audit_repo,
        accion="eliminar_bloque_formato",
        usuario_id=current_user.id,
        entidad="formato",
        entidad_id=formato_id,
        detalle={"block_key": block_key},
    )
    return _to_response(formato)


@router.patch("/{formato_id}/bloques/{block_key}", status_code=status.HTTP_200_OK)
async def actualizar_bloque(
    formato_id: int,
    block_key: str,
    patch: BloquePatch,
    current_user: Annotated[Usuario, Depends(require_permiso("formatos", "actualizar"))],
    formato_repo: FormatoRepoDep,
) -> dict[str, Any]:
    _ = current_user
    use_case = ActualizarBloque(formato_repo)
    try:
        formato = await use_case.ejecutar(
            formato_id, block_key, patch.model_dump(exclude_none=True)
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(formato)


@router.patch("/{formato_id}/configuracion", status_code=status.HTTP_200_OK)
async def actualizar_configuracion(
    formato_id: int,
    body: ConfiguracionFormatoPatch,
    current_user: Annotated[Usuario, Depends(require_permiso("formatos", "actualizar"))],
    formato_repo: FormatoRepoDep,
) -> dict[str, Any]:
    """Persiste config global de página/fuente (lo que el usuario ve en el preview).

    Merge parcial: page y base se combinan con lo existente en meta.
    """
    _ = current_user
    use_case = ActualizarConfiguracionFormato(formato_repo)
    page: dict[str, Any] = {}
    base: dict[str, Any] = {}
    if body.tamano_hoja is not None:
        page["tamano_hoja"] = body.tamano_hoja
    for clave, val in {
        "margin_top_mm": body.margin_top_mm,
        "margin_right_mm": body.margin_right_mm,
        "margin_bottom_mm": body.margin_bottom_mm,
        "margin_left_mm": body.margin_left_mm,
    }.items():
        if val is not None:
            page[clave] = val
    if body.font is not None:
        base["font"] = body.font
    if body.size_pt is not None:
        base["size_pt"] = body.size_pt
    try:
        formato = await use_case.ejecutar(formato_id, page=page or None, base=base or None)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(formato)


@router.post("/{formato_id}/promover", status_code=status.HTTP_200_OK)
async def promover(
    formato_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("formatos", "actualizar"))],
    formato_repo: FormatoRepoDep,
    audit_repo: AuditLogRepoDep,
) -> dict[str, Any]:
    use_case = PromoverFormato(formato_repo)
    try:
        formato = await use_case.ejecutar(formato_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await registrar_auditoria_segura(
        audit_repo,
        accion="promover_formato",
        usuario_id=current_user.id,
        entidad="formato",
        entidad_id=formato_id,
    )
    return _to_response(formato)


@router.post("/importar", status_code=status.HTTP_200_OK)
async def importar_formatos(
    current_user: Annotated[Usuario, Depends(require_permiso("formatos", "crear"))],
    formato_repo: FormatoRepoDep,
    audit_repo: AuditLogRepoDep,
    vault_path: str | None = Query(default=None, description="Ruta vault/sources/formatos"),
) -> dict[str, Any]:
    settings = get_settings()
    vault_default = (
        Path(__file__).resolve().parents[3].parent
        / "asistente-legal-vault"
        / "sources"
        / "formatos"
    )
    default = getattr(settings, "vault_formatos_path", None) or str(vault_default)
    root = Path(vault_path) if vault_path else Path(default)
    use_case = ImportarFormatos(formato_repo)
    result = await use_case.ejecutar(root)
    await registrar_auditoria_segura(
        audit_repo,
        accion="importar_formatos",
        usuario_id=current_user.id,
        entidad="formato",
        detalle=dict(result),
    )
    return result


@router.get("/{formato_id}/original-docx", status_code=status.HTTP_200_OK)
async def original_docx(
    formato_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("formatos", "leer"))],
    formato_repo: FormatoRepoDep,
) -> Response:
    """Sirve el .docx original del formato (para comparar con docx-preview).

    Busca por basename dentro de `Problematica docs/OBRADOS` (allowlist única),
    no confía en la ruta absoluta guardada (quedó desactualizada tras mover
    la carpeta a OBRADOS). Devuelve 404 si no hay .docx o no se encuentra.
    """
    _ = current_user
    formato = await formato_repo.obtener(formato_id)
    if formato is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Formato no encontrado")

    fuente = (formato.meta or {}).get("source_file") or ""
    basename = Path(fuente).name
    if not basename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Este formato no proviene de un .docx",
        )

    # Raíz de obrados (allowlist). Prioriza env; fallback al path conocido.
    settings = get_settings()
    raiz = os.environ.get(
        "OBRADOS_ROOT",
        str(Path("/mnt/d/Archivos/PROYECTO DE GRADO/Problematica docs/OBRADOS")),
    )
    _ = settings
    candidatos = list(Path(raiz).rglob(basename))
    if not candidatos:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No se encontró el .docx original '{basename}'",
        )

    docx_bytes = candidatos[0].read_bytes()
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
