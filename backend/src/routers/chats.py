"""Router de chats privados (Sprint 4 — Opcion B fork #133).

Endopints:
  GET    /chats/                                  — Listar chats del usuario
  POST   /chats/                                  — Crear chat en un expediente
  GET    /chats/{chat_id}                         — Obtener un chat
  POST   /chats/{chat_id}/archivar                — Cambiar estado a 'archivado'
  GET    /chats/{chat_id}/mensajes                — Listar mensajes (paginado)
  POST   /chats/{chat_id}/mensajes                — Enviar mensaje

Sprint 4 (Opcion B): backend de chats reemplaza chatStore localStorage
del sidebar del Asistente. `consulta_historial` sigue como log inmutable
de auditoria/KPIs.

Seguridad:
- usuario_id SIEMPRE del JWT (current_user.id), no del body (Regla 4).
- Regla 5 (adapter-side): todos los metodos del repo filtran por propietario_id.
- El router valida que el chat exista y pertenece al usuario antes de operar.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.adapters.http.dependencies import (
    ChatRepoDep,
    ExpedienteRepoDep,
    MensajeChatRepoDep,
    require_permiso,
)
from src.adapters.http.dependencies_borradores import BorradorRepoDep
from src.application.services.memoria_conversacional import (
    ConstructorMemoriaConversacional,
)
from src.domain.entities.chat_privado import ChatPrivado
from src.domain.entities.mensaje_chat import MensajeChat
from src.domain.entities.usuario import Usuario

router = APIRouter(prefix="/chats", tags=["chats"])


# ----- DTOs -----


class ChatDTO(BaseModel):
    """DTO de un chat privado."""

    id: int
    expediente_id: int | None
    espacio_trabajo_id: int | None
    propietario_id: int
    titulo: str
    estado: str
    prioridad: str
    contexto_legal: str | None
    created_at: str | None
    updated_at: str | None
    ultimo_mensaje_at: str | None


class CrearChatBody(BaseModel):
    """Body POST /chats/."""

    expediente_id: int | None = Field(default=None, ge=1)
    titulo: str = Field(min_length=1, max_length=200)
    espacio_trabajo_id: int | None = None
    prioridad: str = Field(default="media", pattern="^(baja|media|alta|critica)$")
    contexto_legal: str | None = Field(
        default=None,
        pattern="^(caso_legal|audiencia|reunion|antecedente|documento_legal|consulta_general)$",
    )


class CrearChatResp(BaseModel):
    """Response POST /chats/."""

    chat: ChatDTO


class MensajeDTO(BaseModel):
    """DTO de un mensaje de chat."""

    id: int
    chat_id: int
    usuario_id: int
    tipo: str
    contenido: str
    razonamiento: str
    estado: str
    posicion: int
    created_at: str | None


class EnviarMensajeBody(BaseModel):
    """Body POST /chats/{id}/mensajes."""

    tipo: str = Field(pattern="^(user|bot)$")
    contenido: str = Field(min_length=1)
    razonamiento: str = ""
    metadatos: dict | None = None


class PaginaMensajesResp(BaseModel):
    """Response GET /chats/{id}/mensajes."""

    chat_id: int
    items: list[MensajeDTO]
    total: int
    pagina: int
    por_pagina: int


class ArchivarResp(BaseModel):
    """Response POST /chats/{id}/archivar."""

    chat: ChatDTO


# ----- Helpers -----


def _chat_to_dto(chat: ChatPrivado) -> ChatDTO:
    return ChatDTO(
        id=chat.id,  # type: ignore[arg-type]
        expediente_id=chat.expediente_id,
        espacio_trabajo_id=chat.espacio_trabajo_id,
        propietario_id=chat.propietario_id,
        titulo=chat.titulo,
        estado=chat.estado,
        prioridad=chat.prioridad,
        contexto_legal=chat.contexto_legal,
        created_at=chat.created_at.isoformat() if chat.created_at else None,
        updated_at=chat.updated_at.isoformat() if chat.updated_at else None,
        ultimo_mensaje_at=(chat.ultimo_mensaje_at.isoformat() if chat.ultimo_mensaje_at else None),
    )


def _msg_to_dto(msg: MensajeChat) -> MensajeDTO:
    return MensajeDTO(
        id=msg.id,  # type: ignore[arg-type]
        chat_id=msg.chat_id,
        usuario_id=msg.usuario_id,
        tipo=msg.tipo,
        contenido=msg.contenido,
        razonamiento=msg.razonamiento,
        estado=msg.estado,
        posicion=msg.posicion,
        created_at=msg.created_at.isoformat() if msg.created_at else None,
    )


# ----- Endpoints -----


@router.get(
    "/",
    response_model=list[ChatDTO],
    summary="Listar chats del usuario autenticado",
)
async def get_chats(
    current_user: Annotated[Usuario, Depends(require_permiso("chats", "leer"))],
    chat_repo: ChatRepoDep,
    expediente_id: int | None = Query(None),
    estado: str | None = Query(None, pattern="^(activo|archivado|eliminado)$"),
) -> list[ChatDTO]:
    """Lista chats del usuario. Filtros opcionales por expediente/estado."""
    chats = await chat_repo.listar_por_usuario(
        usuario_id=current_user.id,
        expediente_id=expediente_id,
        estado=estado,
    )
    return [_chat_to_dto(c) for c in chats]


@router.post(
    "/",
    response_model=CrearChatResp,
    status_code=status.HTTP_201_CREATED,
    summary="Crear un nuevo chat (opcionalmente atado a un expediente)",
)
async def post_crear_chat(
    body: CrearChatBody,
    current_user: Annotated[Usuario, Depends(require_permiso("chats", "crear"))],
    chat_repo: ChatRepoDep,
    expediente_repo: ExpedienteRepoDep,
) -> CrearChatResp:
    """Crea un chat privado, opcionalmente atado a un expediente.

    Sin expediente_id se crea un chat GENERAL que consulta solo el corpus
    vectorial (migración b7c8d9e0f1a2). El propietario es el usuario
    autenticado (no se acepta del body). Si viene expediente_id, valida que
    el expediente exista antes de crear el chat (mejor UX que dejar que FK
    CASCADE rechace con 500 al insertar — bug finding review no-mistakes).
    """
    if body.expediente_id is not None:
        expediente = await expediente_repo.obtener(body.expediente_id)
        if expediente is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Expediente id={body.expediente_id} no existe.",
            )
    chat = ChatPrivado(
        id=None,
        expediente_id=body.expediente_id,
        espacio_trabajo_id=body.espacio_trabajo_id,
        propietario_id=current_user.id,
        titulo=body.titulo,
        estado="activo",
        prioridad=body.prioridad,
        contexto_legal=body.contexto_legal,
    )
    guardado = await chat_repo.guardar(chat)
    return CrearChatResp(chat=_chat_to_dto(guardado))


@router.get(
    "/{chat_id}",
    response_model=ChatDTO,
    summary="Obtener un chat por id",
)
async def get_chat(
    chat_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("chats", "leer"))],
    chat_repo: ChatRepoDep,
) -> ChatDTO:
    """Obtiene un chat. None si no existe o no es del usuario (Regla 5)."""
    chat = await chat_repo.obtener(chat_id, current_user.id)
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat id={chat_id} no encontrado.",
        )
    return _chat_to_dto(chat)


@router.post(
    "/{chat_id}/archivar",
    response_model=ArchivarResp,
    summary="Archivar un chat (estado='archivado')",
)
async def post_archivar(
    chat_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("chats", "actualizar"))],
    chat_repo: ChatRepoDep,
) -> ArchivarResp:
    """Cambia estado del chat a 'archivado'. Solo el dueno puede archivar."""
    actualizado = await chat_repo.actualizar_estado(
        chat_id=chat_id,
        propietario_id=current_user.id,
        estado="archivado",
    )
    if actualizado is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat id={chat_id} no encontrado.",
        )
    return ArchivarResp(chat=_chat_to_dto(actualizado))


@router.get(
    "/{chat_id}/mensajes",
    response_model=PaginaMensajesResp,
    summary="Listar mensajes visibles de un chat (paginado)",
)
async def get_mensajes(
    chat_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("chats", "leer"))],
    mensaje_repo: MensajeChatRepoDep,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(50, ge=1, le=200),
) -> PaginaMensajesResp:
    """Lista mensajes visibles (activo/editado) de un chat del usuario."""
    items, total = await mensaje_repo.listar_por_chat(
        chat_id=chat_id,
        usuario_id=current_user.id,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return PaginaMensajesResp(
        chat_id=chat_id,
        items=[_msg_to_dto(m) for m in items],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
    )


@router.get(
    "/{chat_id}/contexto",
    summary="Caja de cristal: memoria conversacional que se inyectaria al LLM",
)
async def get_contexto_chat(
    chat_id: int,
    current_user: Annotated[Usuario, Depends(require_permiso("chats", "leer"))],
    chat_repo: ChatRepoDep,
    mensaje_repo: MensajeChatRepoDep,
    borrador_repo: BorradorRepoDep,
) -> dict:
    """Dry-run del ConstructorMemoriaConversacional para este chat.

    Transparencia total (principio caja de cristal del marco-practico):
    permite auditar que sabe el asistente en este chat sin generar nada.
    """
    chat = await chat_repo.obtener(chat_id, current_user.id)
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat id={chat_id} no encontrado.",
        )

    constructor = ConstructorMemoriaConversacional(
        mensaje_repo=mensaje_repo,
        borrador_repo=borrador_repo,
    )
    texto = await constructor.construir(chat_id, current_user.id, consulta_actual="")
    turnos = texto.count("Usuario: ") + texto.count("Asistente: ")
    return {
        "chat_id": chat_id,
        "turnos_incluidos": turnos,
        "presupuesto_chars": 6000,
        "texto": texto,
    }


@router.post(
    "/{chat_id}/mensajes",
    response_model=MensajeDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Enviar un mensaje al chat",
)
async def post_mensaje(
    chat_id: int,
    body: EnviarMensajeBody,
    current_user: Annotated[Usuario, Depends(require_permiso("chats", "crear"))],
    chat_repo: ChatRepoDep,
    mensaje_repo: MensajeChatRepoDep,
) -> MensajeDTO:
    """Envia un mensaje al chat. Verifica propiedad del chat primero."""
    # Validar chat existe y es del usuario
    chat = await chat_repo.obtener(chat_id, current_user.id)
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Chat id={chat_id} no encontrado.",
        )

    # Calcular siguiente posicion (Regla 5: solo cuenta mensajes de chats propios)
    posicion = await mensaje_repo.obtener_ultima_posicion(
        chat_id=chat_id, usuario_id=current_user.id
    )

    mensaje = MensajeChat(
        id=None,
        chat_id=chat_id,
        usuario_id=current_user.id,
        tipo=body.tipo,
        contenido=body.contenido,
        razonamiento=body.razonamiento,
        estado="activo",
        posicion=posicion,
        metadatos=body.metadatos,
    )
    guardado = await mensaje_repo.guardar(mensaje)

    # Marcar Timestamp del ultimo mensaje en el chat.
    # ponytail: actualizamos el chat.ultimo_mensaje_at en background —
    # si falla, el mensaje igual se persiste, y la proxima lectura del
    # sidebar mostrara el mensaje sin actualizar el orden. Upgrade path:
    # usar evento / outbox pattern cuando se mueva a microservicios.
    import contextlib

    with contextlib.suppress(Exception):
        await chat_repo.actualizar_ultimo_mensaje_at(
            chat_id=chat_id, propietario_id=current_user.id
        )

    return _msg_to_dto(guardado)
