"""Use case: GuardarBorrador — guarda explicitamente un borrador generado en el chat.

Sprint 6 + integracion con chat. El borrador se genera en el chat de Consultar
(y NO se persiste en /consultas/responder). Este UC se ejecuta cuando el
usuario pulsa 'Guardar en Mis Borradores' o 'Actualizar mi borrador':

- Si el chat ya tiene un borrador guardado (obtener_por_chat), se ACTUALIZA
  su contenido y fuentes (nueva version sobre el mismo registro).
- Si no, se crea uno nuevo con chat_id/mensaje_id.

Regla 7 (BLOQUEANTE): propietario_id viene del JWT, nunca del body.
"""

from __future__ import annotations

from typing import cast

from src.domain.entities.borrador import Borrador, TipoBorrador

#: Mapeo tipo_respuesta (pipeline) -> tipo_borrador (dominio). Solo los tipos
#: que producen borrador; consulta_simple no aplica.
_TIPO_BORRADOR_MAP: dict[str, str] = {
    "auto_vista_consulta": "proyecto_auto_vista_consulta",
    "auto_vista_apelacion_incidental": "proyecto_auto_vista_apelacion",
    "dictamen_radicatoria_consulta": "dictamen_radicatoria",
    "dictamen_radicatoria_apelacion": "dictamen_radicatoria",
}


class TipoNoGeneraBorradorError(ValueError):
    """El tipo de respuesta no produce borrador (consulta_simple)."""


class ExpedienteObligatorioError(ValueError):
    """Los tipos de borrador requieren expediente_id."""


async def guardar(
    borrador_repo,
    *,
    propietario_id: int,
    expediente_id: int,
    tipo_respuesta: str,
    contenido: str,
    fuentes: dict | None = None,
    chat_id: int | None = None,
    mensaje_id: int | None = None,
    razonamiento: str = "",
) -> Borrador:
    """Guarda (crea o actualiza) el borrador de la conversacion del chat.

    Args:
        borrador_repo: BorradorRepo.
        propietario_id: id del usuario (JWT). Regla 7.
        expediente_id: expediente al que pertenece el borrador.
        tipo_respuesta: tipo clasificado por el pipeline (auto_vista_* / dictamen_*).
        contenido: texto final del borrador.
        fuentes: contexto serializado (fragmentos RAG + sugerencia).
        chat_id: chat donde se genero (si el chat esta persistido).
        mensaje_id: mensaje bot origen.

    Returns:
        Borrador creado o actualizado.

    Raises:
        TipoNoGeneraBorradorError: tipo no mapea a borrador.
        ExpedienteObligatorioError: falta expediente_id para tipo de borrador.
    """
    tipo_borrador = _TIPO_BORRADOR_MAP.get(tipo_respuesta)
    if tipo_borrador is None:
        raise TipoNoGeneraBorradorError(f"tipo_respuesta={tipo_respuesta!r} no genera borrador.")
    if expediente_id is None:
        raise ExpedienteObligatorioError("Guardar un borrador requiere expediente_id.")

    # Actualizar version si el chat ya tiene borrador guardado.
    if chat_id is not None:
        existente = await borrador_repo.obtener_por_chat(chat_id, propietario_id)
        if existente is not None:
            actualizado = await borrador_repo.actualizar_contenido_con_fuentes(
                existente.id or 0,
                contenido=contenido,
                fuentes=fuentes,
                razonamiento=razonamiento,
            )
            if actualizado is not None:
                return actualizado

    borrador = Borrador(
        id=None,
        expediente_id=expediente_id,
        propietario_id=propietario_id,
        tipo=cast(TipoBorrador, tipo_borrador),
        contenido=contenido,
        plantilla_usada=f"{tipo_borrador}.md",
        contexto_recuperado=fuentes,
        estado="borrador",
        activo=True,
        chat_id=chat_id,
        mensaje_id=mensaje_id,
        razonamiento=razonamiento,
    )
    return await borrador_repo.crear(borrador)


__all__ = [
    "guardar",
    "TipoNoGeneraBorradorError",
    "ExpedienteObligatorioError",
]
