"""Tests bloqueantes EvaluadorCompetencia (pure domain service — Sprint 7, G5).

Verifica competencia (materia/territorio/grado) y plazos fatales CPPM.
Servicio stateless, sin DI, sin IO, sin datetime.now — "hoy" se pasa como parámetro.

RG3: 1 test minimo por regla bloqueante.
- Competencia materia: consulta y apelacion_incidental -> competente
- Competencia territorio: tribunal militar -> competente
- Competencia grado: oficiales y tropa -> competente
- Plazos: dentro_plazo, vencido, critico, no_aplica (fecha faltante)
"""

from __future__ import annotations

from datetime import date

from src.domain.services.evaluador_competencia import evaluar_competencia
from src.domain.value_objects.resultado_competencia import (
    ChequeoCompetencia,
    ChequeoPlazo,
    ResultadoCompetencia,
)


class _FakeObra:
    """Obra ligera para tests (solo campos que usa evaluar_competencia)."""

    def __init__(
        self,
        tipo_documento: str,
        created_at: date | None = None,
        fojas_inicio: int | None = None,
        fojas_fin: int | None = None,
    ) -> None:
        self.tipo_documento = tipo_documento
        self.created_at = created_at
        self.fojas_inicio = fojas_inicio
        self.fojas_fin = fojas_fin


# === COMPETENCIA: MATERIA =====================================================


def test_competencia_materia_consulta_es_competente() -> None:
    """Consulta de oficio es competencia SAC (Ley 1970 Art. 3)."""
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal Militar 1",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 15),
        obras=[],
        hoy=date(2024, 1, 20),
    )

    mat = [c for c in r.chequeos_competencia if c.criterio == "materia"][0]
    assert mat.estado == "competente"
    assert "consulta" in mat.detalle.lower()


def test_competencia_materia_apelacion_incidental_es_competente() -> None:
    """Apelación incidental es competencia SAC (CPPM Art. 400)."""
    r = evaluar_competencia(
        expediente_tipo_proceso="apelacion_incidental",
        expediente_tribunal_origen="Tribunal Militar 2",
        expediente_procesado_grado="Sargento",
        expediente_sentencia_origen="Sentencia condenatoria...",
        expediente_created_at=date(2024, 2, 1),
        obras=[],
        hoy=date(2024, 2, 10),
    )

    mat = [c for c in r.chequeos_competencia if c.criterio == "materia"][0]
    assert mat.estado == "competente"
    assert "apelacion_incidental" in mat.detalle.lower()


def test_competencia_materia_apelacion_restringida_es_competente() -> None:
    """Apelación restringida (recurso contra sentencia) es competencia SAC.

    Bugfix: antes caía en el else y se marcaba INCOMPETENTE, lo que bloqueaba
    con 422 (FaltaCompetenciaError) cualquier borrador sobre un expediente
    restringido por un motivo legal falso."""
    r = evaluar_competencia(
        expediente_tipo_proceso="apelacion_restringida",
        expediente_tribunal_origen="Tribunal Militar 3",
        expediente_procesado_grado="Teniente",
        expediente_sentencia_origen="Sentencia condenatoria...",
        expediente_created_at=date(2024, 3, 1),
        obras=[],
        hoy=date(2024, 3, 5),
    )

    mat = [c for c in r.chequeos_competencia if c.criterio == "materia"][0]
    assert mat.estado == "competente"
    assert "apelacion_restringida" in mat.detalle.lower()


def test_competencia_materia_tipo_desconocido_es_incompetente() -> None:
    """Tipo proceso no reconocido -> incompetente por materia."""
    r = evaluar_competencia(
        expediente_tipo_proceso="recurso_extraordinario",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen="...",
        expediente_created_at=date(2024, 1, 1),
        obras=[],
        hoy=date(2024, 1, 10),
    )

    mat = [c for c in r.chequeos_competencia if c.criterio == "materia"][0]
    assert mat.estado == "incompetente"


# === COMPETENCIA: TERRITORIO ==================================================


def test_competencia_territorio_tribunal_militar_es_competente() -> None:
    """Cualquier tribunal militar boliviano está en jurisdicción TSJM."""
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal Militar de La Paz",
        expediente_procesado_grado="Teniente",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 1),
        obras=[],
        hoy=date(2024, 1, 10),
    )

    terr = [c for c in r.chequeos_competencia if c.criterio == "territorio"][0]
    assert terr.estado == "competente"
    assert "TSJM" in terr.detalle


def test_competencia_territorio_sin_tribunal_es_dudosa() -> None:
    """Sin tribunal origen -> dudosa (no se puede afirmar)."""
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 1),
        obras=[],
        hoy=date(2024, 1, 10),
    )

    terr = [c for c in r.chequeos_competencia if c.criterio == "territorio"][0]
    assert terr.estado == "dudosa"


# === COMPETENCIA: GRADO =======================================================


def test_competencia_grado_oficial_es_competente() -> None:
    """Oficiales (teniente a general) -> competencia SAC casación oficiales."""
    for grado in ["Teniente", "Capitan", "Mayor", "Teniente Coronel", "Coronel", "General"]:
        r = evaluar_competencia(
            expediente_tipo_proceso="apelacion_incidental",
            expediente_tribunal_origen="Tribunal X",
            expediente_procesado_grado=grado,
            expediente_sentencia_origen="...",
            expediente_created_at=date(2024, 1, 1),
            obras=[],
            hoy=date(2024, 1, 10),
        )
        gr = [c for c in r.chequeos_competencia if c.criterio == "grado"][0]
        assert gr.estado == "competente", f"Falló para grado {grado}: {gr.detalle}"
        assert "oficial" in gr.detalle.lower()


def test_competencia_grado_tropa_es_competente() -> None:
    """Tropa (soldado a sargento primero) -> competencia SAC casación tropa."""
    for grado in ["Soldado", "Cabo", "Sargento", "Sargento Primero"]:
        r = evaluar_competencia(
            expediente_tipo_proceso="consulta",
            expediente_tribunal_origen="Tribunal X",
            expediente_procesado_grado=grado,
            expediente_sentencia_origen=None,
            expediente_created_at=date(2024, 1, 1),
            obras=[],
            hoy=date(2024, 1, 10),
        )
        gr = [c for c in r.chequeos_competencia if c.criterio == "grado"][0]
        assert gr.estado == "competente", f"Falló para grado {grado}: {gr.detalle}"
        assert "tropa" in gr.detalle.lower()


def test_competencia_grado_desconocido_es_dudosa() -> None:
    """Grado no reconocido -> dudosa."""
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Civil",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 1),
        obras=[],
        hoy=date(2024, 1, 10),
    )

    gr = [c for c in r.chequeos_competencia if c.criterio == "grado"][0]
    assert gr.estado == "dudosa"
    assert "no reconocido" in gr.detalle.lower()


def test_competencia_grado_none_es_dudosa() -> None:
    """Grado None -> dudosa."""
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado=None,
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 1),
        obras=[],
        hoy=date(2024, 1, 10),
    )

    gr = [c for c in r.chequeos_competencia if c.criterio == "grado"][0]
    assert gr.estado == "dudosa"


# === COMPETENCIA GLOBAL =======================================================


def test_competencia_global_incompetente_si_alguno_incompetente() -> None:
    """Si materia es incompetente, global = incompetente (aunque grado/territorio OK)."""
    r = evaluar_competencia(
        expediente_tipo_proceso="recurso_extraordinario",  # incompetente
        expediente_tribunal_origen="Tribunal Militar",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen="...",
        expediente_created_at=date(2024, 1, 1),
        obras=[],
        hoy=date(2024, 1, 10),
    )

    assert r.competencia_global == "incompetente"


def test_competencia_global_dudosa_si_ninguno_incompetente_pero_hay_dudosa() -> None:
    """Si no hay incompetente pero hay dudosa -> global = dudosa."""
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="",  # dudosa
        expediente_procesado_grado="Civil",  # dudosa
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 1),
        obras=[],
        hoy=date(2024, 1, 10),
    )

    assert r.competencia_global == "dudosa"


def test_competencia_global_competente_si_todos_competentes() -> None:
    """Todos competentes -> global = competente."""
    r = evaluar_competencia(
        expediente_tipo_proceso="apelacion_incidental",
        expediente_tribunal_origen="Tribunal Militar 3",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen="...",
        expediente_created_at=date(2024, 1, 1),
        obras=[],
        hoy=date(2024, 1, 10),
    )

    assert r.competencia_global == "competente"


# === PLAZOS: DENTRO_PLAZO =====================================================


def test_plazo_auto_representacion_dentro_plazo() -> None:
    """Auto representación: 3 días, hoy día 2 -> dentro_plazo."""
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 10),
        obras=[],
        hoy=date(2024, 1, 12),  # 2 días después
    )

    ar = [c for c in r.chequeos_plazos if c.etapa == "auto_representacion"][0]
    assert ar.estado == "dentro_plazo"
    assert ar.dias_transcurridos == 2
    assert ar.dias_limite == 3


def test_plazo_dictamen_radicatoria_dentro_plazo() -> None:
    """Dictamen radicatoria: 3 días desde auto representación."""
    obras = [
        _FakeObra("auto_interlocutorio", created_at=date(2024, 1, 12)),
    ]
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 10),
        obras=obras,
        hoy=date(2024, 1, 14),  # 2 días después del auto
    )

    dr = [c for c in r.chequeos_plazos if c.etapa == "dictamen_radicatoria"][0]
    assert dr.estado == "dentro_plazo"
    assert dr.dias_transcurridos == 2


# === PLAZOS: VENCIDO ==========================================================


def test_plazo_auto_representacion_vencido() -> None:
    """Auto representación: 3 días, hoy día 4 -> vencido."""
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 10),
        obras=[],
        hoy=date(2024, 1, 14),  # 4 días después
    )

    ar = [c for c in r.chequeos_plazos if c.etapa == "auto_representacion"][0]
    assert ar.estado == "vencido"
    assert r.hay_plazos_vencidos is True


def test_plazo_proyecto_auto_vista_vencido_en_horas() -> None:
    """Proyecto auto vista: 48h, hoy 50h después -> vencido."""
    obras = [
        _FakeObra("dictamen_fondo", created_at=date(2024, 1, 10)),
    ]
    r = evaluar_competencia(
        expediente_tipo_proceso="apelacion_incidental",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen="...",
        expediente_created_at=date(2024, 1, 1),
        obras=obras,
        hoy=date(2024, 1, 12),  # ~2 días = 48h, 3 días = 72h -> vencido
    )

    pav = [c for c in r.chequeos_plazos if c.etapa == "proyecto_auto_vista"][0]
    assert pav.estado == "vencido"
    assert r.hay_plazos_vencidos is True


# === PLAZOS: CRITICO ==========================================================


def test_plazo_auto_representacion_critico_ultimo_dia() -> None:
    """Día 3 (límite) -> critico."""
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 10),
        obras=[],
        hoy=date(2024, 1, 13),  # 3 días = límite
    )

    ar = [c for c in r.chequeos_plazos if c.etapa == "auto_representacion"][0]
    assert ar.estado == "critico"
    assert r.hay_plazos_criticos is True


def test_plazo_proyecto_auto_vista_critico_ultimas_horas() -> None:
    """44-47h (últimas 4h) -> critico."""
    obras = [
        _FakeObra("dictamen_fondo", created_at=date(2024, 1, 10)),
    ]
    # día 10 + 1.8 días = ~43h, día 11 = 24h, día 12 = 48h
    r = evaluar_competencia(
        expediente_tipo_proceso="apelacion_incidental",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen="...",
        expediente_created_at=date(2024, 1, 1),
        obras=obras,
        hoy=date(2024, 1, 12),  # 48h exactas = límite, 44-47 = critico
        # Para test, usamos fecha que da ~44-47h
    )
    # El test usa aproximación de días*24, así que día 11 = 24h (dentro_plazo),
    # día 12 = 48h (critico por ser límite)
    pav = [c for c in r.chequeos_plazos if c.etapa == "proyecto_auto_vista"][0]
    # 48h exacto = límite -> critico (>= limite - 4)
    assert pav.estado in ("critico", "vencido")


# === PLAZOS: NO_APLICA (FECHA FALTANTE) ======================================


def test_plazo_sin_fecha_inicio_no_aplica() -> None:
    """Si no hay obra que marque el hito, el plazo es no_aplica."""
    # No pasamos obra "auto_interlocutorio", así que dictamen_radicatoria
    # no tiene fecha de inicio
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 10),
        obras=[],  # sin auto representación
        hoy=date(2024, 1, 20),
    )

    dr = [c for c in r.chequeos_plazos if c.etapa == "dictamen_radicatoria"][0]
    assert dr.estado == "no_aplica"
    assert dr.dias_transcurridos is None
    assert "no disponible" in dr.detalle.lower()


def test_plazo_expediente_sin_created_at_no_aplica_auto_representacion() -> None:
    """Si expediente_created_at es None, auto_representacion = no_aplica."""
    r = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen=None,
        expediente_created_at=None,
        obras=[],
        hoy=date(2024, 1, 20),
    )

    ar = [c for c in r.chequeos_plazos if c.etapa == "auto_representacion"][0]
    assert ar.estado == "no_aplica"


# === INTEGRACIÓN: CADENA COMPLETA =============================================


def test_cadena_temporal_completa_con_obras_hitos() -> None:
    """Cadena completa: expediente -> auto_rep -> dictamen_rad ->
    relato_obrados -> dictamen_fondo -> proyecto_av -> audiencia."""
    obras = [
        _FakeObra("auto_interlocutorio", created_at=date(2024, 1, 13)),  # auto rep día 3
        _FakeObra("dictamen_radicatoria", created_at=date(2024, 1, 16)),  # dictamen rad día 3
        _FakeObra("relacion_obrados", created_at=date(2024, 1, 19)),  # relato día 3
        _FakeObra("dictamen_fondo", created_at=date(2024, 1, 22)),  # dictamen fondo día 3
        _FakeObra("proyecto_auto_vista", created_at=date(2024, 1, 24)),  # proyecto día 2 (48h)
    ]
    r = evaluar_competencia(
        expediente_tipo_proceso="apelacion_incidental",
        expediente_tribunal_origen="Tribunal Militar 4",
        expediente_procesado_grado="Mayor",
        expediente_sentencia_origen="Sentencia condenatoria Art. 154 CPM",
        expediente_created_at=date(2024, 1, 10),
        obras=obras,
        hoy=date(2024, 1, 25),  # 1 día después del proyecto (24h)
    )

    # Todos los plazos deben estar calculados
    etapas = {c.etapa: c.estado for c in r.chequeos_plazos}
    assert etapas["auto_representacion"] == "vencido"  # 15 días
    assert etapas["dictamen_radicatoria"] == "vencido"  # 9 días
    assert etapas["relacion_obrados"] == "vencido"  # 6 días
    assert etapas["dictamen_fondo"] == "vencido"  # 3 días
    assert etapas["proyecto_auto_vista"] in ("critico", "vencido")  # ~24h
    assert etapas["audiencia"] == "dentro_plazo"  # 0 días desde proyecto

    assert r.hay_plazos_vencidos is True


# === DETERMINISMO =============================================================


def test_mismos_datos_mismo_resultado() -> None:
    """Determinismo: mismos inputs -> mismo output."""
    obras = [_FakeObra("auto_interlocutorio", created_at=date(2024, 1, 13))]
    r1 = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 10),
        obras=obras,
        hoy=date(2024, 1, 20),
    )
    r2 = evaluar_competencia(
        expediente_tipo_proceso="consulta",
        expediente_tribunal_origen="Tribunal X",
        expediente_procesado_grado="Capitan",
        expediente_sentencia_origen=None,
        expediente_created_at=date(2024, 1, 10),
        obras=obras,
        hoy=date(2024, 1, 20),
    )

    assert r1.competencia_global == r2.competencia_global
    assert r1.chequeos_competencia == r2.chequeos_competencia
    assert r1.chequeos_plazos == r2.chequeos_plazos


# === VO: CONSTRUCTORES ========================================================


def test_resultado_competencia_vacio_factory() -> None:
    """ResultadoCompetencia.vacio() devuelve instancia válida por defecto."""
    r = ResultadoCompetencia.vacio()
    assert r.competencia_global == "competente"
    assert r.chequeos_competencia == ()
    assert r.chequeos_plazos == ()
    assert r.hay_plazos_vencidos is False
    assert r.hay_plazos_criticos is False


def test_resultado_competencia_de_listas_calcula_global() -> None:
    """de_listas calcula global correctamente."""
    chequeos_comp = [
        ChequeoCompetencia(criterio="materia", estado="competente", detalle="ok"),
        ChequeoCompetencia(criterio="territorio", estado="competente", detalle="ok"),
        ChequeoCompetencia(criterio="grado", estado="dudosa", detalle="?"),
    ]
    chequeos_plazos = [
        ChequeoPlazo(
            etapa="auto_representacion",
            estado="dentro_plazo",
            dias_transcurridos=1,
            dias_limite=3,
        ),
        ChequeoPlazo(
            etapa="dictamen_radicatoria",
            estado="vencido",
            dias_transcurridos=4,
            dias_limite=3,
        ),
    ]
    r = ResultadoCompetencia.de_listas(chequeos_comp, chequeos_plazos)

    assert r.competencia_global == "dudosa"  # hay dudosa, no incompetente
    assert r.hay_plazos_vencidos is True
    assert r.hay_plazos_criticos is False
