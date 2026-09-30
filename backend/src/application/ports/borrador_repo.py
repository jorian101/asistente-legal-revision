"""Port: BorradorRepo — Repositorio de borradores (tabla `borrador`).

Protocol (structural typing) — la implementación no necesita heredar.

Sprint 6 (Regla 7 Trail of Bits BLOQUEANTE): el filtro de propiedad
`propietario_id == usuario_id` vive en el adapter. El use case pasa
`usuario_id` (JWT); el repo filtra sin confiar en parametros opcionales.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.borrador import Borrador


class BorradorRepo(Protocol):
    """Repositorio de borradores (tabla `borrador`)."""

    async def crear(self, borrador: Borrador) -> Borrador:
        """Inserta un borrador en estado 'borrador'. Devuelve con id y created_at."""
        ...

    async def obtener_por_id(self, borrador_id: int) -> Borrador | None:
        """Obtiene un borrador por id. Sin filtro de propietario.

        El filtro de propietario lo aplica el use case publicar (Regla 7)
        comparando `borrador.propietario_id == usuario_id`. Devolver la
        entidad completa permite al use case decidir la validacion.

        Returns:
            Borrador o None si no existe.
        """
        ...

    async def listar_por_expediente(
        self,
        expediente_id: int,
        propietario_id: int,
    ) -> list[Borrador]:
        """Lista borradores de un expediente filtrados por propietario.

        Regla 7: solo el propietario ve sus borradores en estado 'borrador'.
        Los 'publicado' los podrian ver otros, pero Sprint 6 limita a
        `propietario_id == user` (sinthood del usuario actual).

        Returns:
            Lista ordenada por created_at desc.
        """
        ...

    async def actualizar_estado(
        self,
        borrador_id: int,
        estado: str,
        propietario_id: int,
    ) -> Borrador | None:
        """Cambia estado del borrador ('borrador' -> 'publicado').

        Regla 7 (BLOQUEANTE): el filtro `propietario_id == usuario_id` vive
        en el adapter. Devuelve el borrador actualizado o None si el caller
        no es propietario (sin diferenciar de 'no existe' para evitar
        information leak por timing/oracle — igual que ObraRepo).
        """
        ...

    async def actualizar_estado_supervisor(
        self,
        borrador_id: int,
        estado: str,
        desde: str,
    ) -> Borrador | None:
        """Cambia el estado de un borrador activo sin filtrar propietario (supervisor).

        Solo transiciona si el estado ACTUAL es `desde` (devuelve None si no): asi el
        supervisor no puede oficializar un borrador privado ni desoficializar uno que
        no es oficial. El guard de rol vive en el router (require_supervisor).
        """
        ...

    async def actualizar_contenido(
        self,
        borrador_id: int,
        contenido: str,
    ) -> Borrador | None:
        """Actualiza el contenido de un borrador tras streaming del LLM.

        Invocado por GenerarBorrador (Fase 3.1) cuando el stream termina.
        NO filtra por propietario — el flujo interno del sistema lo llama,
        no el usuario final. Devuelve la entidad o None si no existe.
        """
        ...

    async def eliminar_soft(
        self,
        borrador_id: int,
        propietario_id: int,
    ) -> bool:
        """Soft delete: activo=False SOLO si el borrador es del propietario.

        Regla 7 (BLOQUEANTE): el filtro `propietario_id == usuario_id` vive
        en el adapter. True si se elimino; False si no existe o es ajeno.
        """
        ...

    async def actualizar_contenido_propietario(
        self,
        borrador_id: int,
        propietario_id: int,
        contenido: str,
        layout: list[dict] | None = None,
    ) -> Borrador | None:
        """Actualiza contenido (+ layout fiel opcional) de un borrador, Regla 7.

        Si layout es None no se toca la columna (compat). Si se provee se
        persiste el layout fiel editado en Mis Borradores (guardar todo).
        """
        ...

    async def actualizar_contenido_supervisor(
        self,
        borrador_id: int,
        contenido: str,
        layout: list[dict] | None = None,
    ) -> Borrador | None:
        """Supervisor corrige un borrador en revision ('pendiente_oficial') ajeno.

        Solo aplica a ese estado activo; el guard de rol vive en el router.
        """
        ...

    async def actualizar_contenido_con_fuentes(
        self,
        borrador_id: int,
        contenido: str,
        fuentes: dict | None,
        razonamiento: str = "",
    ) -> Borrador | None:
        """Actualiza contenido + contexto_recuperado (+ razonamiento) de un borrador.

        Invocado por GuardarBorrador al pulsar 'Actualizar mi borrador'
        (flujo interno del sistema sobre un borrador ya propiedad-verificado
        via obtener_por_chat). Toca updated_at.
        """
        ...

    async def listar_por_propietario(
        self,
        propietario_id: int,
    ) -> list[Borrador]:
        """Lista todos los borradores del propietario (vista 'Mis Borradores').

        Regla 7: solo los del propietario, sin exigir expediente.
        Ordenados por updated_at desc (los mas recientes primero).
        """
        ...

    async def obtener_por_chat(
        self,
        chat_id: int,
        propietario_id: int,
    ) -> Borrador | None:
        """Obtiene el borrador generado en un chat por su propietario.

        Permite el boton 'Actualizar mi borrador': si el chat ya genero un
        borrador, se actualiza en vez de crear uno nuevo. Regla 7: solo el
        propietario.
        """
        ...
