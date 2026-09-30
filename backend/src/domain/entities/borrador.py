"""Entidad de dominio Borrador.

Regla Clean Architecture: dataclass pura, sin SQLAlchemy ni Pydantic.
El ORM vive en adapters/postgres/models/borrador.py y mapea esta entidad
a la tabla `borrador`.

Un borrador es el output del pipeline RAG + ResolvedorPlantillas + LLM
antes de ser publicado como pieza procesal definitiva. Los tipos de borrador
mapean a las plantillas de arquitectura.md seccion 5.

Regla de dominio (arquitectura.md seccion 2.2): solo el propietario ve el
borrador hasta publicar. La validacion `propietario_id == user_id` se aplica
antes de cambiar el estado a 'publicado' — nunca desde el router, siempre
en la capa de dominio (servicio PublicarBorrador en application/borradores/).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

TipoBorrador = Literal[
    "dictamen_radicatoria",
    "proyecto_auto_vista_consulta",
    "proyecto_auto_vista_apelacion",
    "sugerencia_argumentacion",
]
EstadoBorrador = Literal["borrador", "publicado", "pendiente_oficial", "oficial"]


@dataclass
class Borrador:
    """Borrador generado por el sistema para un expediente.

    Atributos:
        id: Identificador interno. None si la entidad no fue persistida aun.
        expediente_id: ID del expediente al que pertenece (FK a expediente.id).
            El dominio guarda el int; el adapter resuelve la FK y el
            ON DELETE CASCADE.
        propietario_id: ID del usuario propietario (FK a usuario.id).
            Solo el propietario puede ver/publicar el borrador mientras
            este en estado 'borrador'.
        tipo: Tipo de borrador. Ver TipoBorrador (4 valores).
        contenido: Texto del borrador producido por el LLM.
        plantilla_usada: Nombre/ref de la plantilla base usada. None si el
            borrador se genero sin plantilla (sugerencia puntual).
        contexto_recuperado: Estructura con los fragmentos RAG, scores y
            trazabilidad que dieron contexto al LLM. None si no hubo RAG.
            El dominio lo trata como diccionario opaco; el tipo exacto lo
            define el DTO ContextoEnriquecido del pipeline (application/).
        estado: Estado del borrador. Por defecto 'borrador'.
            El paso a 'publicado' exige propietario_id == usuario_actual.
        activo: Soft delete (False = borrador eliminado por su propietario).
            Default True.
        chat_id: ID del chat (chat_privado) donde se genero el borrador.
            Permite el boton 'Ver el chat' y 'Actualizar mi borrador'.
        mensaje_id: ID del mensaje bot (mensaje_chat) con la respuesta que
            origino el borrador.
        razonamiento: Razonamiento nativo del modelo (modo pensar) que origino
            el borrador. Trazabilidad del Vocal ("por que el borrador dice X").
            Default vacio (consultas concisas no generan razonamiento).
        created_at: Fecha/hora de creacion. None antes de persistir.
        updated_at: Fecha/hora de ultima edicion. None si nunca se edito.
    """

    id: int | None
    expediente_id: int
    propietario_id: int
    tipo: TipoBorrador
    contenido: str
    plantilla_usada: str | None = None
    contexto_recuperado: dict[str, Any] | None = None
    estado: EstadoBorrador = "borrador"
    activo: bool = True
    chat_id: int | None = None
    mensaje_id: int | None = None
    layout: list[dict[str, Any]] | None = None
    razonamiento: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None
