"""Servicio de dominio: EvaluadorCompetencia (Sprint 7, G5).

Verifica competencia (materia/territorio/grado) y plazos fatales CPPM
para un expediente en la SAC. Diseado como pure function stateless:
recibe datos estructurados, devuelve ResultadoCompetencia. Sin DI, sin
IO, sin datetime.now — el caller pasa "hoy" como parámetro.

Regla arquitectonica (arquitectura.md §3.2 lines 87, 480): servicio
stateless. Complementa a AnalizadorVicios (G2): AnalizadorVicios detecta
vicios TEXTUALES (regex); EvaluadorCompetencia detecta vicios
ESTRUCTURALES (competencia, plazos calculados contra fechas reales).

Flujo CPPM (8 pasos, arquitectura.md §8 ADR-005):
1. Recepcion expediente -> Auto Representación (3 días)
2. Auto Representación -> Dictamen Radicatoria (3 días) — sugiere competencia
3. Sorteo vocal (inmediato)
4. Sorteo -> Relación Obrados (3 días)
5. Relación Obrados -> Dictamen Fondo (3 días)
6. Dictamen Fondo -> Proyecto Auto Vista (48h)
7. Proyecto Auto Vista -> Audiencia (48h)
8. Audiencia -> Auto Vista

Competencia SAC (Ley 1970 + CPPM):
- Materia: apelaciones incidentales, apelaciones restringidas (recurso
  contra sentencia) y consultas de oficio (SÍ conoce)
- Territorio: TSJM = todo territorio militar boliviano (SÍ)
- Grado: oficiales (teniente a general) vs tropa (soldado a sargento)
  * Diferentes tribunales inferiores, pero SAC es casación para ambos
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from src.domain.value_objects.resultado_competencia import (
    ChequeoCompetencia,
    ChequeoPlazo,
    PlazoEstado,
    ResultadoCompetencia,
)

if TYPE_CHECKING:
    pass

# Plazos fatales CPPM en días (o horas para auto vista/audiencia)
_PLAZOS_DIAS: dict[str, int] = {
    "auto_representacion": 3,
    "dictamen_radicatoria": 3,
    "relacion_obrados": 3,
    "dictamen_fondo": 3,
}
_PLAZOS_HORAS: dict[str, int] = {
    "proyecto_auto_vista": 48,
    "audiencia": 48,
}

# Orden cronológico de las etapas para cálculo secuencial
_ETAPAS_ORDEN: tuple[str, ...] = (
    "auto_representacion",
    "dictamen_radicatoria",
    "relacion_obrados",
    "dictamen_fondo",
    "proyecto_auto_vista",
    "audiencia",
)

# Grados oficiales (competencia tribunales superiores)
_GRADOS_OFICIALES: set[str] = {
    "general",
    "coronel",
    "teniente_coronel",
    "mayor",
    "capitan",
    "teniente",
    "subteniente",
}
# Grados tropa
_GRADOS_TROPA: set[str] = {
    "sargento_primero",
    "sargento",
    "cabo",
    "soldado",
}


def _normalizar_grado(grado: str | None) -> str:
    """Normaliza grado a clave interna (lowercase, underscore)."""
    if not grado:
        return "desconocido"
    return grado.lower().replace(" ", "_").replace("-", "_")


def _es_oficial(grado: str | None) -> bool:
    return _normalizar_grado(grado) in _GRADOS_OFICIALES


def _es_tropa(grado: str | None) -> bool:
    return _normalizar_grado(grado) in _GRADOS_TROPA


def _dias_entre(fecha_inicio: date | None, fecha_fin: date) -> int | None:
    """Días transcurridos entre dos fechas. None si falta fecha_inicio."""
    if fecha_inicio is None:
        return None
    return (fecha_fin - fecha_inicio).days


def _horas_entre(fecha_inicio: date | None, fecha_fin: date) -> int | None:
    """Horas aproximadas (días * 24). None si falta fecha_inicio."""
    dias = _dias_entre(fecha_inicio, fecha_fin)
    if dias is None:
        return None
    return dias * 24


def _evaluar_plazo_dias(
    etapa: str,
    dias_transcurridos: int | None,
    dias_limite: int,
) -> ChequeoPlazo:
    """Evalúa un plazo en días.

    Interpretación CPPM (consistente con tests): plazo de N días = hasta
    fin del día N-1 (0-indexado). Ejemplo: 3 días recibido día 0 ->
    días 0,1,2 son hábiles; día 3 = crítico (fecha límite); día 4+ = vencido.
    - dias_transcurridos <= dias_limite - 1: dentro_plazo
    - dias_transcurridos == dias_limite: critico (fecha límite exacta)
    - dias_transcurridos > dias_limite: vencido
    """
    if dias_transcurridos is None:
        return ChequeoPlazo(
            etapa=etapa,  # type: ignore[arg-type]
            estado="no_aplica",
            dias_transcurridos=None,
            dias_limite=dias_limite,
            detalle="Fecha de inicio no disponible",
        )

    if dias_transcurridos > dias_limite:
        estado: PlazoEstado = "vencido"
    elif dias_transcurridos == dias_limite:  # fecha límite exacta
        estado = "critico"
    else:
        estado = "dentro_plazo"

    return ChequeoPlazo(
        etapa=etapa,  # type: ignore[arg-type]
        estado=estado,
        dias_transcurridos=dias_transcurridos,
        dias_limite=dias_limite,
        detalle=f"{dias_transcurridos}/{dias_limite} días",
    )


def _evaluar_plazo_horas(
    etapa: str,
    horas_transcurridas: int | None,
    horas_limite: int,
) -> ChequeoPlazo:
    """Evalúa un plazo en horas (proyecto_auto_vista, audiencia).

    Consistente con lógica de días:
    - horas_transcurridas < horas_limite - 4: dentro_plazo
    - horas_limite - 4 <= horas_transcurridas < horas_limite: critico
    - horas_transcurridas >= horas_limite: vencido
    """
    if horas_transcurridas is None:
        return ChequeoPlazo(
            etapa=etapa,  # type: ignore[arg-type]
            estado="no_aplica",
            dias_transcurridos=None,
            dias_limite=horas_limite,
            detalle="Fecha de inicio no disponible",
        )

    if horas_transcurridas >= horas_limite:
        estado = "vencido"
    elif horas_transcurridas >= horas_limite - 4:  # últimas 4h = crítico
        estado = "critico"
    else:
        estado = "dentro_plazo"

    return ChequeoPlazo(
        etapa=etapa,  # type: ignore[arg-type]
        estado=estado,
        dias_transcurridos=horas_transcurridas // 24 if horas_transcurridas else None,
        dias_limite=horas_limite,
        detalle=f"{horas_transcurridas}/{horas_limite} horas",
    )


def evaluar_competencia(
    *,
    expediente_tipo_proceso: str,
    expediente_tribunal_origen: str,
    expediente_procesado_grado: str | None,
    expediente_sentencia_origen: str | None,
    expediente_created_at: date | None,
    obras: list,
    hoy: date,
) -> ResultadoCompetencia:
    """Evalúa competencia y plazos fatales para un expediente en la SAC.

    Args:
        expediente_tipo_proceso: "consulta", "apelacion_incidental" o
            "apelacion_restringida".
        expediente_tribunal_origen: Nombre del tribunal de origen.
        expediente_procesado_grado: Grado militar del procesado.
        expediente_sentencia_origen: Texto/resumen de sentencia (None si consulta).
        expediente_created_at: Fecha de creación del expediente (recepción).
        obras: Lista de Obra (con tipo_documento, created_at, fojas_inicio/fin).
        hoy: Fecha actual para calcular plazos (NO usa datetime.now).

    Returns:
        ResultadoCompetencia con chequeos de competencia y plazos.

    Notas:
        - Sin DI: recibe todo por parámetros.
        - Sin IO: lógica pura.
        - Sin datetime.now: "hoy" viene de afuera (testable, determinista).
    """
    # ---------- 1. COMPETENCIA ----------
    chequeos_comp: list[ChequeoCompetencia] = []

    # Materia: SAC conoce consultas de oficio y apelaciones (incidental y
    # restringida — recurso contra sentencia).
    if expediente_tipo_proceso in (
        "consulta",
        "apelacion_incidental",
        "apelacion_restringida",
    ):
        chequeos_comp.append(
            ChequeoCompetencia(
                criterio="materia",
                estado="competente",
                detalle=f"SAC conoce {expediente_tipo_proceso} (Ley 1970 Art. 3, CPPM Art. 400)",
                norma="Ley 1970 Art. 3; CPPM Art. 400",
            )
        )
    else:
        chequeos_comp.append(
            ChequeoCompetencia(
                criterio="materia",
                estado="incompetente",
                detalle=f"Tipo proceso '{expediente_tipo_proceso}' no es competencia SAC",
                norma="Ley 1970 Art. 3",
            )
        )

    # Territorio: TSJM = todo territorio militar boliviano
    # Cualquier tribunal militar boliviano es competencia TSJM
    if expediente_tribunal_origen:
        chequeos_comp.append(
            ChequeoCompetencia(
                criterio="territorio",
                estado="competente",
                detalle=(
                    f"Tribunal origen '{expediente_tribunal_origen}' dentro de jurisdicción TSJM"
                ),
                norma="Ley 1970 Art. 2",
            )
        )
    else:
        chequeos_comp.append(
            ChequeoCompetencia(
                criterio="territorio",
                estado="dudosa",
                detalle="Tribunal origen no especificado",
                norma=None,
            )
        )

    # Grado: oficiales vs tropa (SAC es casación para ambos)
    # Distinto tribunal inferior, pero competencia SAC es la misma
    grado_norm = _normalizar_grado(expediente_procesado_grado)
    if _es_oficial(expediente_procesado_grado):
        chequeos_comp.append(
            ChequeoCompetencia(
                criterio="grado",
                estado="competente",
                detalle=f"Procesado oficial ({grado_norm}) — SAC conoce casación oficiales",
                norma="Ley 1970 Art. 4; CPPM Art. 401",
            )
        )
    elif _es_tropa(expediente_procesado_grado):
        chequeos_comp.append(
            ChequeoCompetencia(
                criterio="grado",
                estado="competente",
                detalle=f"Procesado tropa ({grado_norm}) — SAC conoce casación tropa",
                norma="Ley 1970 Art. 4; CPPM Art. 401",
            )
        )
    else:
        chequeos_comp.append(
            ChequeoCompetencia(
                criterio="grado",
                estado="dudosa",
                detalle=f"Grado no reconocido: '{expediente_procesado_grado}'",
                norma=None,
            )
        )

    # ---------- 2. PLAZOS FATALES ----------
    # Reconstruimos la cadena temporal desde expediente_created_at
    # usando las obras como hitos (created_at de cada obra = fecha del hito)

    # Mapa etapa -> fecha de inicio (date)
    fechas_inicio: dict[str, date | None] = {}

    # Etapa 1: Auto Representación inicia en recepción expediente
    fechas_inicio["auto_representacion"] = expediente_created_at

    # Buscamos obras que marquen hitos procesales.
    # Cada obra marca el INICIO de la etapa SIGUIENTE:
    # auto_interlocutorio (auto representación) -> inicia dictamen_radicatoria
    # dictamen_radicatoria -> inicia relacion_obrados
    # relacion_obrados -> inicia dictamen_fondo
    # dictamen_fondo -> inicia proyecto_auto_vista
    # proyecto_auto_vista -> inicia audiencia
    for obra in obras:
        if obra.created_at is None:
            continue
        t = obra.tipo_documento
        # Defensa en profundidad: Obra.created_at puede ser date o datetime
        # (la entidad lo tipa datetime; algunos seeds/tests usan date).
        fecha_hito: date = (
            obra.created_at.date() if hasattr(obra.created_at, "date") else obra.created_at
        )
        if t == "auto_interlocutorio" and "dictamen_radicatoria" not in fechas_inicio:
            fechas_inicio["dictamen_radicatoria"] = fecha_hito
        elif t == "dictamen_radicatoria" and "relacion_obrados" not in fechas_inicio:
            fechas_inicio["relacion_obrados"] = fecha_hito
        elif t == "relacion_obrados" and "dictamen_fondo" not in fechas_inicio:
            fechas_inicio["dictamen_fondo"] = fecha_hito
        elif t == "dictamen_fondo" and "proyecto_auto_vista" not in fechas_inicio:
            fechas_inicio["proyecto_auto_vista"] = fecha_hito
        elif t == "proyecto_auto_vista" and "audiencia" not in fechas_inicio:
            fechas_inicio["audiencia"] = fecha_hito

    # Evaluar cada plazo en orden cronológico
    chequeos_plazos: list[ChequeoPlazo] = []

    for etapa in _ETAPAS_ORDEN:
        fecha_ini = fechas_inicio.get(etapa)
        if etapa in _PLAZOS_DIAS:
            dias = _dias_entre(fecha_ini, hoy)
            chequeos_plazos.append(_evaluar_plazo_dias(etapa, dias, _PLAZOS_DIAS[etapa]))
        else:  # horas
            horas = _horas_entre(fecha_ini, hoy)
            chequeos_plazos.append(_evaluar_plazo_horas(etapa, horas, _PLAZOS_HORAS[etapa]))

    return ResultadoCompetencia.de_listas(chequeos_comp, chequeos_plazos)
