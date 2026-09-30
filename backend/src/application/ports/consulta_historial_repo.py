"""Port: ConsultaHistorialRepo — repositorio del historial de consultas.

Sprint 3 persiste cada consulta tras ejecutar el pipeline RAG (D9). El
repositorio guarda y lista el historial para KPIs EASI-RAG y la UI de
"Sprints 3.5 — Validacion".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from src.domain.entities.consulta_historial import ConsultaHistorial


@dataclass
class ConsultaHistorialAdmin:
    """Item del historial RAG para auditoria admin (incluye datos del usuario)."""

    id: int
    expediente_id: int | None
    usuario_id: int
    usuario_carnet: str
    usuario_nombre: str
    pregunta: str
    respuesta: str | None
    tipo_respuesta: str | None
    latencia_ms: int | None
    modelo_llm: str | None
    fuentes_recuperadas: dict[str, Any] | None
    created_at: datetime | None
    estado: str | None = None


@dataclass
class ResumenTipo:
    """Conteo de consultas por tipo_respuesta."""

    tipo_respuesta: str
    cantidad: int


@dataclass
class ResumenModelo:
    """Uso y latencia media por modelo LLM."""

    modelo_llm: str | None
    cantidad: int
    latencia_promedio_ms: float | None


@dataclass
class ResumenUsuario:
    """Conteo de consultas por usuario (join a usuario)."""

    usuario_id: int
    usuario_carnet: str
    usuario_nombre: str
    cantidad: int


@dataclass
class ResumenDia:
    """Conteo de consultas por dia (YYYY-MM-DD)."""

    fecha: str
    cantidad: int


@dataclass
class DashboardResumen:
    """Agregados para el Dashboard admin (resumen general de chats y modelos)."""

    total_consultas: int
    en_progreso: int
    completadas: int
    con_error: int
    por_tipo: list[ResumenTipo]
    por_modelo: list[ResumenModelo]
    por_usuario: list[ResumenUsuario]
    consultas_por_dia: list[ResumenDia]


class ConsultaHistorialRepo(Protocol):
    """Repositorio del historial de consultas RAG."""

    async def guardar(self, historial: ConsultaHistorial) -> ConsultaHistorial:
        """Persiste un registro de consulta. Devuelve la entidad con su id."""
        ...

    async def listar_por_usuario(
        self,
        usuario_id: int,
        expediente_id: int | None,
        pagina: int,
        por_pagina: int,
    ) -> tuple[list[ConsultaHistorial], int]:
        """Lista el historial del usuario (Regla 4: solo ve el suyo).

        Args:
            usuario_id: OBLIGATORIO (Regla 4 — siempre filtra por este).
            expediente_id: Filtro opcional por expediente.
            pagina: 1-indexed.
            por_pagina: Tamano de pagina.

        Returns:
            Tupla (items, total) — items ya paginados.
        """
        ...

    async def listar_todas(
        self,
        pagina: int,
        por_pagina: int,
    ) -> tuple[list[ConsultaHistorial], int]:
        """Lista todo el historial (solo admin, HU-22 metricas contexto).

        Sprint 5: el endpoint GET /admin/metricas/contexto agrega
        trazabilidad de expansion de las ultimas N consultas.

        Args:
            pagina: 1-indexed.
            por_pagina: Tamano de pagina.

        Returns:
            Tupla (items, total) — items ya paginados.
        """
        ...

    async def actualizar_respuesta(
        self,
        historial_id: int,
        respuesta: str,
        modelo_llm: str,
    ) -> ConsultaHistorial | None:
        """Actualiza `respuesta` + `modelo_llm` post-LLM stream (Sprint 6).

        Invocado por GenerarBorrador cuando el stream del LLM termina.
        Llena los campos NULL que RecuperarContexto dejo vacios en el
        INSERT original (D11). Devuelve la entidad actualizada o None
        si el historial_id no existe (no raise — failure tolerable).
        """
        ...

    async def actualizar_respuesta_parcial(
        self,
        historial_id: int,
        respuesta: str,
    ) -> None:
        """P1: persiste el texto acumulado SIN cerrar la consulta.

        A diferencia de `actualizar_respuesta`, NO toca `estado` (queda
        'en_progreso'): permite mostrar el parcial en vivo desde otra
        pestaña/chat mientras la generación sigue, sin que streamResume la
        de por terminada antes de tiempo. Invocado con throttle desde
        GenerarBorrador; silencioso si el historial_id no existe.
        """
        ...

    async def actualizar_metadatos(
        self,
        historial_id: int,
        *,
        tipo_respuesta: str | None,
        fuentes_recuperadas: dict | None,
        latencia_ms: int | None,
    ) -> ConsultaHistorial | None:
        """Actualiza tipo_respuesta + fuentes + latencia post-pipeline (Task A).

        GenerarBorrador persiste el historial ANTES del pipeline (para obtener
        un historial_id estable como consulta_id de los eventos SSE), y luego
        rellena los metadatos que solo se conocen tras la ejecucion del RAG.
        Devuelve la entidad actualizada o None si no existe.
        """
        ...

    async def marcar_error(self, historial_id: int) -> bool:
        """Marca una consulta como 'error' (pipeline fallo sin respuesta).

        Invocado por GenerarBorrador cuando el pipeline/plantilla falla
        despues del INSERT inicial, para que la Sala de Control muestre
        'error' en vez de quedar 'En progreso' para siempre.
        """
        ...

    async def obtener_por_id(
        self,
        historial_id: int,
        usuario_id: int,
    ) -> ConsultaHistorial | None:
        """Retorna la entrada si existe y pertenece al usuario (Regla 4).

        None si no existe, es de otro usuario o fue eliminada (soft delete).
        """
        ...

    async def eliminar_soft(
        self,
        historial_id: int,
        usuario_id: int,
    ) -> bool:
        """Soft delete de una entrada de historial (CRITICAL #4).

        Setea activo=False SOLO si la entrada pertenece al usuario
        (Regla 4: cada usuario borra su propio historial). Devuelve True
        si se elimino, False si no existe o no es del usuario.
        """
        ...

    async def listar_admin(
        self,
        *,
        usuario_id: int | None,
        expediente_id: int | None,
        tipo_respuesta: str | None,
        estado: str | None,
        fecha_desde: datetime | None,
        fecha_hasta: datetime | None,
        texto: str | None,
        pagina: int,
        por_pagina: int,
    ) -> tuple[list[ConsultaHistorialAdmin], int]:
        """Lista el historial completo con filtros (solo admin).

        Filtros opcionales: usuario_id, expediente_id, tipo_respuesta,
        estado ("en_progreso", "completado"|"terminadas", "error"), rango de
        fechas y texto dentro de la pregunta. Incluye carnet/nombre del
        usuario (join). No filtra por propietario.
        """
        ...

    async def eliminar_soft_admin(self, historial_id: int) -> bool:
        """Soft delete de CUALQUIER entrada (solo admin, sin propietario).

        Devuelve True si existia una entrada activa y se marco activo=False.
        """
        ...

    async def resumen_dashboard(self) -> DashboardResumen:
        """Agregados para el Dashboard admin (solo consultas activas)."""
        ...
