"""Tests del clasificador ClasificadorTipoRespuesta (pure domain).

Cubre:
- Detecta auto_vista_consulta por keyword.
- Detecta auto_vista_apelacion_incidental por keyword.
- Default consulta_simple cuando no hay keyword.
- Raise ConsultaSinExpedienteError si tipo auto_vista_* y sin expediente_id.
- Extrae abreviatura del corpus si esta presente.
- Acepta consulta_simple sin expediente_id (sin raise).
"""

from __future__ import annotations

import pytest

from src.application.consultas.clasificar_tipo_respuesta import (
    clasificar_tipo_respuesta,
)
from src.domain.exceptions import (
    ConsultaSinExpedienteError,
    VarianteApelacionNoSoportadaError,
)


def test_consulta_simple_sin_palabras_clave() -> None:
    """Consulta normal sin keywords -> consulta_simple."""
    tipo, filtros = clasificar_tipo_respuesta(
        consulta="Cual es el plazo para apelar una sentencia?",
        expediente_id=None,
    )
    assert tipo == "consulta_simple"
    assert filtros == {}


def test_auto_vista_consulta_detectado() -> None:
    """'auto de vista' en la consulta -> auto_vista_consulta."""
    tipo, filtros = clasificar_tipo_respuesta(
        consulta="Necesito emitir un auto de vista respecto al expediente.",
        expediente_id=10,
    )
    assert tipo == "auto_vista_consulta"
    assert filtros["expediente_id"] == "10"


def test_auto_vista_consulta_detectado_por_consulta_de_oficio() -> None:
    """Keyword alternativa: 'consulta de oficio' -> auto_vista_consulta."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Consulta de oficio sobre la aplicacion del art. 184.",
        expediente_id=5,
    )
    assert tipo == "auto_vista_consulta"


def test_auto_vista_apelacion_detectado() -> None:
    """'apelacion incidental' -> auto_vista_apelacion_incidental."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Resolver la apelacion incidental del procesado.",
        expediente_id=42,
    )
    assert tipo == "auto_vista_apelacion_incidental"


def test_auto_vista_apelacion_con_acento_detectado() -> None:
    """'apelación incidental' (con tilde) -> auto_vista_apelacion_incidental.

    Regresion del golden set (exp8-plazo-apelacion): el patron solo aceptaba
    'apelacion' sin tilde y la consulta caia a consulta_simple.
    """
    tipo, _ = clasificar_tipo_respuesta(
        consulta="cuál es el plazo para la apelación incidental",
        expediente_id=8,
    )
    assert tipo == "auto_vista_apelacion_incidental"


def test_sin_expediente_en_auto_vista_raises() -> None:
    """Consulta auto_vista_* sin expediente_id -> ConsultaSinExpedienteError."""
    with pytest.raises(ConsultaSinExpedienteError, match="requiere un expediente_id"):
        clasificar_tipo_respuesta(
            consulta="Dictar auto de vista sobre la consulta.",
            expediente_id=None,
        )


def test_sin_expediente_en_apelacion_incidental_raises() -> None:
    """apelacion incidental sin expediente_id -> raise."""
    with pytest.raises(ConsultaSinExpedienteError):
        clasificar_tipo_respuesta(
            consulta="Resolucion de apelacion incidental.",
            expediente_id=None,
        )


def test_consulta_simple_con_abreviatura_extrae_filtro() -> None:
    """Detecta abreviatura del corpus y la agrega a filtros_metadata."""
    tipo, filtros = clasificar_tipo_respuesta(
        consulta="Que dice el CPPM sobre la desobediencia?",
        expediente_id=None,
    )
    assert tipo == "consulta_simple"
    assert filtros.get("abreviatura") == "CPPM"


def test_consulta_simple_sin_abreviatura_filtros_vacio() -> None:
    """Sin abreviatura -> filtros con expediente y solo_expediente."""
    tipo, filtros = clasificar_tipo_respuesta(
        consulta="Cual es el plazo de apelacion?",
        expediente_id=99,
    )
    assert tipo == "consulta_simple"
    assert filtros == {"expediente_id": "99", "solo_expediente": "True"}


def test_consulta_simple_con_expediente_y_jurisprudencia_no_limita_a_expediente() -> None:
    """Pedir jurisprudencia con expediente no pone solo_expediente (usa doctrina global)."""
    tipo, filtros = clasificar_tipo_respuesta(
        consulta="Citame jurisprudencia sobre motivacion con expediente?",
        expediente_id=99,
    )
    assert tipo == "consulta_simple"
    assert filtros.get("expediente_id") == "99"
    assert "tipo_fuente" not in filtros
    assert "solo_expediente" not in filtros


def test_patron_keyword_case_insensitive() -> None:
    """Las heuristicas son case-insensitive."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="APELACION INCIDENTAL del fallo.",
        expediente_id=1,
    )
    assert tipo == "auto_vista_apelacion_incidental"


# --- G1: Dictamen Radicatoria (Sprint 6 DoD) ---


def test_dictamen_radicatoria_consulta_detectado() -> None:
    """'dictamen de radicatoria' con expediente -> dictamen_radicatoria_consulta."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Necesito emitir el dictamen de radicatoria del expediente.",
        expediente_id=15,
    )
    assert tipo == "dictamen_radicatoria_consulta"


def test_dictamen_radicatoria_consulta_por_radicatoria_de_la_consulta() -> None:
    """Variante keyword: 'radicatoria de la consulta'."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Sugiero radicatoria de la consulta del expediente 42.",
        expediente_id=42,
    )
    assert tipo == "dictamen_radicatoria_consulta"


def test_dictamen_radicatoria_apelacion_detectado() -> None:
    """'dictamen de radicatoria en apelacion' -> dictamen_radicatoria_apelacion."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Necesito dictamen de radicatoria en apelacion incidental.",
        expediente_id=8,
    )
    assert tipo == "dictamen_radicatoria_apelacion"


def test_dictamen_radicatoria_apelacion_por_radicatoria_incidental() -> None:
    """Variante keyword: 'radicatoria en apelacion incidental'."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Sugiero radicatoria en apelacion incidental del expediente.",
        expediente_id=8,
    )
    assert tipo == "dictamen_radicatoria_apelacion"


def test_dictamen_radicatoria_sin_expediente_raises() -> None:
    """dictamen_radicatoria_consulta sin expediente_id -> ConsultaSinExpedienteError."""
    with pytest.raises(ConsultaSinExpedienteError):
        clasificar_tipo_respuesta(
            consulta="Necesito emitir el dictamen de radicatoria.",
            expediente_id=None,
        )


def test_dictamen_radicatoria_apelacion_sin_expediente_raises() -> None:
    """dictamen_radicatoria_apelacion sin expediente_id -> raise."""
    with pytest.raises(ConsultaSinExpedienteError):
        clasificar_tipo_respuesta(
            consulta="Dictamen radicatoria incidental del recurso.",
            expediente_id=None,
        )


def test_consulta_jurisprudencia_no_restringe_el_tipo_de_fuente() -> None:
    """Pedir jurisprudencia NO filtra por tipo_fuente: el corpus juridico siempre
    esta y la jurisprudencia/doctrina llegan por su propia coleccion. El filtro
    'doctrina' excluia las normas y daba cero en la coleccion jurisprudencia."""
    tipo, filtros = clasificar_tipo_respuesta(
        consulta="Citame jurisprudencia sobre motivación de resoluciones.",
        expediente_id=None,
    )
    assert tipo == "consulta_simple"
    assert "tipo_fuente" not in filtros


def test_consulta_scp_conserva_la_abreviatura_sin_filtrar_tipo_fuente() -> None:
    """Pedir SCP no agrega tipo_fuente y conserva la abreviatura."""
    tipo, filtros = clasificar_tipo_respuesta(
        consulta="SCP sobre la Ley 1970 como supletoria del CPPM.",
        expediente_id=None,
    )
    assert tipo == "consulta_simple"
    assert "tipo_fuente" not in filtros
    assert filtros.get("abreviatura") == "CPPM"


def test_consulta_sin_jurisprudencia_no_agrega_tipo_fuente() -> None:
    """Consulta de norma sin jurisprudencia no agrega tipo_fuente."""
    tipo, filtros = clasificar_tipo_respuesta(
        consulta="¿Qué dice el artículo 115 de la CPE?",
        expediente_id=None,
    )
    assert tipo == "consulta_simple"
    assert "tipo_fuente" not in filtros


# --- Desambiguacion por via procesal del expediente (bugfix F1) ---


def test_auto_vista_en_expediente_apelacion_remapea_a_apelacion() -> None:
    """'auto de vista' sobre expediente apelacion_incidental -> via apelacion.

    Bugfix: el clasificador solo-texto elegia la plantilla consulta
    (fórmula POR TANTO del Art. 194 CPPM) para un expediente de apelacion
    incidental — base de competencia equivocada en el documento legal."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Necesito emitir un auto de vista respecto al expediente.",
        expediente_id=8,
        tipo_proceso="apelacion_incidental",
    )
    assert tipo == "auto_vista_apelacion_incidental"


def test_radicatoria_consulta_en_expediente_apelacion_remapea() -> None:
    """'dictamen de radicatoria' sobre apelacion_incidental -> via apelacion."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Necesito emitir el dictamen de radicatoria del expediente.",
        expediente_id=8,
        tipo_proceso="apelacion_incidental",
    )
    assert tipo == "dictamen_radicatoria_apelacion"


def test_keyword_apelacion_en_expediente_consulta_no_remapea() -> None:
    """Sin desambiguacion en la direccion contraria: el texto explicito
    manda si coincide con la via del expediente (no-op)."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Resolver la apelacion incidental del procesado.",
        expediente_id=42,
        tipo_proceso="consulta",
    )
    assert tipo == "auto_vista_apelacion_incidental"


def test_sin_tipo_proceso_comportamiento_viejo_intacto() -> None:
    """Backward compat: sin tipo_proceso, 'auto de vista' sigue clasificando
    auto_vista_consulta (los callers que no pasan la via no cambian)."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Necesito emitir un auto de vista respecto al expediente.",
        expediente_id=10,
    )
    assert tipo == "auto_vista_consulta"


def test_radicatoria_apelacion_en_expediente_apelacion_no_duplica() -> None:
    """Patron ya-apa: 'radicatoria en apelacion' + exp. apelacion no se toca."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Sugiero radicatoria en apelacion incidental del expediente.",
        expediente_id=8,
        tipo_proceso="apelacion_incidental",
    )
    assert tipo == "dictamen_radicatoria_apelacion"


def test_consulta_simple_en_expediente_apelacion_no_remapea() -> None:
    """consulta_simple nunca se remapea: sin keywords de documento no hay
    borrador que generar."""
    tipo, _ = clasificar_tipo_respuesta(
        consulta="Cual es el plazo para apelar una sentencia?",
        expediente_id=8,
        tipo_proceso="apelacion_incidental",
    )
    assert tipo == "consulta_simple"


def test_tipo_forzado_valido_se_usa_directo() -> None:
    """T2: tipo_forzado válido respeta la intención explícita del frontend."""
    tipo, _ = clasificar_tipo_respuesta("cualquier texto", 7, tipo_forzado="dictamen_fondo")
    assert tipo == "dictamen_fondo"
    tipo, _ = clasificar_tipo_respuesta("cualquier texto", 9, tipo_forzado="relacion_obrados")
    assert tipo == "relacion_obrados"


def test_tipo_forzado_invalido_cae_a_auto() -> None:
    """T2: tipo_forzado desconocido cae a auto con keywords (determinista)."""
    tipo, _ = clasificar_tipo_respuesta("quiero el auto de vista", 7, tipo_forzado="invalido_xxx")
    assert tipo == "auto_vista_consulta"


def test_tipo_forzado_valido_sin_expediente_422() -> None:
    """T2: tipo_forzado que requiere expediente sin él -> 422 guía (mismo que auto)."""
    with pytest.raises(ConsultaSinExpedienteError):
        clasificar_tipo_respuesta("x", None, tipo_forzado="dictamen_fondo")


# --- Via apelacion restringida: guard honesto (no hay plantilla) ---


def test_auto_vista_en_expediente_restringida_frena() -> None:
    """Expediente restringida + 'auto de vista' -> error explicito.

    La plantilla de auto de vista existente es de otra via (consulta o
    incidental): emitirla cambiaria el grado del documento. Se prefiere
    fallar (422 en el router) mientras no haya plantilla propia."""
    with pytest.raises(VarianteApelacionNoSoportadaError):
        clasificar_tipo_respuesta(
            consulta="Necesito emitir un auto de vista respecto al expediente.",
            expediente_id=8,
            tipo_proceso="apelacion_restringida",
        )


def test_radicatoria_en_expediente_restringida_frena() -> None:
    """Idem para dictamen de radicatoria (ambas plantillas son de otra via)."""
    with pytest.raises(VarianteApelacionNoSoportadaError):
        clasificar_tipo_respuesta(
            consulta="Necesito emitir el dictamen de radicatoria del expediente.",
            expediente_id=8,
            tipo_proceso="apelacion_restringida",
        )


def test_tipo_forzado_en_expediente_restringida_frena() -> None:
    """El guard cubre tambien la intencion explicita (tipo_forzado)."""
    with pytest.raises(VarianteApelacionNoSoportadaError):
        clasificar_tipo_respuesta(
            "cualquier texto",
            8,
            tipo_proceso="apelacion_restringida",
            tipo_forzado="auto_vista_consulta",
        )


def test_consulta_simple_en_expediente_restringida_no_frena() -> None:
    """Los tipos agnosticos de grado siguen habilitados en restringida."""
    tipo, filtros = clasificar_tipo_respuesta(
        consulta="Cual es el plazo para apelar una sentencia?",
        expediente_id=8,
        tipo_proceso="apelacion_restringida",
    )
    assert tipo == "consulta_simple"
    assert filtros["expediente_id"] == "8"


def test_dictamen_fondo_en_expediente_restringida_no_frena() -> None:
    """dictamen_fondo no depende del grado: no lo alcanza el guard."""
    tipo, _ = clasificar_tipo_respuesta(
        "necesito el dictamen de fondo",
        8,
        tipo_proceso="apelacion_restringida",
        tipo_forzado="dictamen_fondo",
    )
    assert tipo == "dictamen_fondo"


def test_ley_1970_se_filtra_por_la_abreviatura_real_del_corpus() -> None:
    """La Ley 1970 esta indexada como CPP: 'Ley 1970' no matchea nada."""
    _tipo, filtros = clasificar_tipo_respuesta(
        consulta="Que dice la Ley 1970 sobre la detencion preventiva?",
        expediente_id=None,
    )
    assert filtros.get("abreviatura") == "CPP"
