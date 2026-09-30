"""Tests de segmentadores de jurisprudencia (F2.1): SCP y Corte IDH.

Estructura rígida por tesis Tabla 19: maestro no indexable + bloques
HECHO (I, II) / DERECHO (III) / FALLO (resolutiva). Muestras sintéticas
mínimas con la forma real (sangrías y líneas unidas incluidas).
"""

from __future__ import annotations

import pytest

from src.application.corpus.indexar_norma import tipo_jerarquia_para
from src.domain.services.segmentacion.base import partir_bloque_por_tamano
from src.domain.services.segmentacion.registro import SegmentadorRegistry

SCP_MUESTRA = """SENTENCIA CONSTITUCIONAL PLURINACIONAL 0623/2024-S4
Sucre, 17 de septiembre de 2024

SALA CUARTA ESPECIALIZADA
Magistrado Relator: Gonzalo Miguel Hurtado Zamorano
Acción de libertad

Expediente: 49413-2022-99-AL

              I. ANTECEDENTES CON RELEVANCIA JURÍDICA

I.1. Contenido de la demanda

El impetrante refirió indefensión por prueba impedida.

                               II. CONCLUSIONES

II.1. Por acta de audiencia consta la indefensión alegada.

                 III. FUNDAMENTOS JURÍDICOS DEL FALLO

III.1. El debido proceso está vinculado a la libertad.

en revisión, resuelve: CONFIRMAR la Resolución 13/2022 y DENEGAR la tutela.

Regístrese, notifíquese y publíquese en la Gaceta Constitucional
Plurinacional.
"""

CIDH_MUESTRA = """Corte Interamericana de Derechos Humanos

Caso del Tribunal Constitucional Vs. Perú

Sentencia de 31 de enero de 2001
(Fondo, Reparaciones y Costas)

                                     I
                          INTRODUCCIÓN DE LA CAUSA

1. El 2 de julio de 1999 la Comisión sometió el caso.

                                     IX
                          CONSIDERACIONES PREVIAS

50. La Corte analiza su competencia.

                                     XV
                             PUNTOS RESOLUTIVOS

130. Por tanto,

1. declara que el Estado violó el artículo 8 de la Convención.
"""


def _tipos(arbol) -> dict[str, int]:
    from collections import Counter

    return dict(Counter(f.tipo_chunk for f in arbol.fragmentos))


def test_scp_bloques_hecho_derecho_fallo() -> None:
    """SCP: maestro + HECHO (I, II) + DERECHO (III) + FALLO (resuelve)."""
    import src.domain.services.segmentacion as _s  # noqa: F401 (auto-registro)

    seg = SegmentadorRegistry.obtener("SCP-0623-2024-S4")
    arbol = seg.segmentar(SCP_MUESTRA)
    tipos = _tipos(arbol)
    assert tipos.get("fundamento_de_hecho", 0) >= 2
    assert tipos.get("fundamento_de_derecho_analisis", 0) >= 1
    assert tipos.get("fundamentacion_del_fallo", 0) >= 1
    # Maestro no indexable con metadatos jurisdiccionales.
    maestros = [n for k, n in arbol.nodos.items() if "MASTER" in k]
    assert len(maestros) == 1
    assert maestros[0].metadatos.get("no_indexable") is True
    assert maestros[0].metadatos.get("numero") == "0623/2024-S4"
    # Claves únicas por sentencia (sin colisión entre SCP).
    assert all("SCP-0623-2024-S4" in (f.padre_ref_key or "") for f in arbol.fragmentos)


def test_scp_rechaza_texto_sin_estructura() -> None:
    """Sin secciones I/II/III no es SCP: ValueError claro."""
    import src.domain.services.segmentacion as _s  # noqa: F401 (auto-registro)

    seg = SegmentadorRegistry.obtener("SCP-0663-2025-S2")
    with pytest.raises(ValueError, match="no parece SCP"):
        seg.segmentar("Texto cualquiera sin estructura de sentencia.")


def test_cidh_secciones_romanas_y_fallo() -> None:
    """CIDH: secciones romanas clasificadas + PUNTOS RESOLUTIVOS al fallo."""
    import src.domain.services.segmentacion as _s  # noqa: F401 (auto-registro)

    seg = SegmentadorRegistry.obtener("CIDH-TC-PERU-2001")
    arbol = seg.segmentar(CIDH_MUESTRA)
    tipos = _tipos(arbol)
    assert tipos.get("fundamento_de_hecho", 0) >= 1  # INTRODUCCIÓN
    assert tipos.get("fundamento_de_derecho_analisis", 0) >= 1  # CONSIDERACIONES
    assert tipos.get("fundamentacion_del_fallo", 0) >= 1  # PUNTOS RESOLUTIVOS
    maestros = [n for k, n in arbol.nodos.items() if "MASTER" in k]
    assert len(maestros) == 1
    # Sin falsos positivos tipo "L" de "LA CORTE".
    assert not [k for k in arbol.nodos if k.endswith("_L")]


def test_detector_reconoce_scp_y_cidh() -> None:
    """Muestras con marcadores I.1/III.2 y secciones romanas dan match."""
    from src.domain.services.segmentacion.detector_patrones import (
        DetectorPatrones,
    )

    detector = DetectorPatrones()
    r_scp = detector.detectar(SCP_MUESTRA)
    assert r_scp.mejor is not None
    # Familia SCP (SC-*/SCP-* empatan por mismos marcadores I/II/III).
    assert r_scp.mejor.abreviatura.split("-")[0] in ("SCP", "SC")
    assert r_scp.mejor.articulos_matcheados >= 2
    r_cidh = detector.detectar(CIDH_MUESTRA)
    assert r_cidh.mejor is not None
    assert r_cidh.mejor.abreviatura.startswith("CIDH-")


def test_tipo_jerarquia_prefijos_jurisprudencia() -> None:
    """SCP-*/CIDH-* resuelven (tipo, jerarquia) sin entrada explícita."""
    assert tipo_jerarquia_para("SCP-0623-2024-S4") == ("scp_tcp", "jurisprudencia")
    assert tipo_jerarquia_para("SCP-9999-2030-S1") == ("scp_tcp", "jurisprudencia")
    assert tipo_jerarquia_para("CIDH-TC-PERU-2001") == (
        "sentencia_cidh",
        "jurisprudencia",
    )
    assert tipo_jerarquia_para("CPPM") == ("codigo_militar", "militar")


def test_partir_bloque_respeta_tope_y_no_vacios() -> None:
    """Bloques largos se parten por párrafos sin producir vacíos."""
    texto = "\n\n".join(f"Párrafo {i} con contenido suficiente." for i in range(30))
    partes = partir_bloque_por_tamano(texto, max_chars=200)
    assert len(partes) > 1
    assert all(p.strip() for p in partes)
    assert all(len(p) <= 400 for p in partes)
