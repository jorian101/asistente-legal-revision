"""Tests unitarios de DetectorPatrones (F1.4 — pre-segmentacion).

Usa muestras de texto con los patrones reales de cada corpus para verificar
que el detector asigna la abreviatura correcta con confianza > 0.
"""

from __future__ import annotations

from src.domain.services.segmentacion.detector_patrones import DetectorPatrones

CPPM = """LIBRO PRIMERO
TITULO I
DISPOSICIONES GENERALES
CAPITULO UNICO

ARTICULO 22°— (Extraccion de expedientes). — La extraccion de expedientes
del tribunal sera efectuada con autorizacion del presidente.

ARTICULO 25°— (Terminos). — Los terminos judiciales son perentorios e
improrrogables.

ARTICULO 126°— (Impedimento de testigos). — Los testigos no podran ser
familiares de las partes.
1) Primer supuesto.
2) Segundo supuesto.
10) Ultimo supuesto.
"""

CPE = """PRIMERA PARTE
BASES FUNDAMENTALES DEL ESTADO
TITULO I
CAPITULO PRIMERO

Articulo 1. El Estado Plurinacional de Bolivia se constituye en un Estado
Unitario Social de Derecho Plurinacional Comunitario.

Articulo 5. I. Son idiomas oficiales del Estado el castellano y todos los
idiomas de las naciones indigenas.
II. El Gobierno plurinacional y los gobiernos departamentales deben utilizar
al menos dos idiomas oficiales.

Articulo 298. Las competencias privativas del nivel central del Estado son:
I. Las previstas en la Constitucion.
II. La administracion de justicia.
III. La defensa nacional.
IV. Las relaciones internacionales.
"""

# Los segmentadores de la Ley 1970 reconocen "Articulo N." sin tilde (el PDF real la
# pierde en algunos artículos): la muestra sin evidencia usa "Art. N".
CPE_SIN_ENCABEZADOS = CPE.replace("Articulo ", "Art. ")

CPM = """LIBRO PRIMERO
PARTE GENERAL
TITULO I
CAPITULO I

ARTICULO 1°— (Aplicacion material). — El presente codigo se aplica a los
arts de guerra cometidos en el territorio nacional.

ARTICULO 13°— La obediencia jerarquica no sera admitida.
1) Primer inciso.
2) Segundo inciso.
 1) sub-numeral de 2.
"""

LOJM = """SEGUNDA SECCION
TITULO II
CAPITULO UNICO

ARTICULO 38°— (Atribuciones del Tribunal Militar). — El Tribunal Supremo
Militar tiene las siguientes atribuciones:
1) Conocer en sala casacional los recursos de casacion.
2) Revisar las sentencias en grado de apelacion.

ARTICULO 70°— (Obligaciones del Secretario). — El Secretario tiene la
obligacion de recibir, distribuir, y despachar:
1) Actos de juicio.
2) Informes de oficio.
"""

LOFA = """TITULO PRIMERO
CAPITULO III

ARTICULO 40°.- El Comando en Jefe estara a cargo del Comandante del General.
a) Planificar.
b) Integrar.

ARTICULO 113°.- Los derechos fundamentales de los militares son:

a) Profesionales:
   1) Continuidad en la formacion militar.
   2) Contar con recursos tecnicos.
b) Economicos:
   1) Remuneracion puntual de beneficios.
   2) Fondo de inversion de ahorro militar.
"""

LEY1970 = """LIBRO PRIMERO
TITULO IV
CAPITULO UNICO

Artículo 20. (Delitos dolos y culposos). Son dolos los delitos cometidos por
dolo y culposos los cometidos por culpa.

Artículo 251. (Evasion). La evasion de convictos no sera castigada si el
detenido retorna voluntariamente antes de que se descubra.
"""


def test_detector_assigns_cppm():
    detector = DetectorPatrones()
    result = detector.detectar(CPPM)
    assert result.mejor is not None
    assert result.mejor.abreviatura in ("CPPM", "CPM")
    assert result.mejor.articulos_matcheados >= 2
    assert result.mejor.confianza > 0.0


def test_detector_assigns_cpe():
    detector = DetectorPatrones()
    result = detector.detectar(CPE_SIN_ENCABEZADOS)
    # Muestra sin encabezados "Artículo N.": cero evidencia -> sin sugerencia
    # (antes devolvía candidatos[0] por orden alfabético del registry).
    assert result.mejor is None


def test_detector_assigns_cpm():
    detector = DetectorPatrones()
    result = detector.detectar(CPM)
    assert result.mejor.abreviatura == "CPM"


def test_detector_assigns_lofa():
    detector = DetectorPatrones()
    result = detector.detectar(LOFA)
    assert result.mejor.abreviatura == "LOFA"


def test_detector_assigns_lojm():
    detector = DetectorPatrones()
    result = detector.detectar(LOJM)
    assert result.mejor.abreviatura == "LOJM"


def test_detector_assigns_ley_1970():
    detector = DetectorPatrones()
    result = detector.detectar(LEY1970)
    assert result.mejor.abreviatura in ("CP", "CPP")


def test_documento_mal_rotulado_cpe_como_cppm():
    detector = DetectorPatrones()
    result = detector.detectar(CPE_SIN_ENCABEZADOS)
    # Sin evidencia de artículos no se sugiere nada (y menos CPPM).
    assert result.mejor is None
    cppms = [c for c in result.candidatos if c.abreviatura == "CPPM"]
    assert len(cppms) == 0 or cppms[0].confianza == 0.0


def test_texto_vacio():
    detector = DetectorPatrones()
    result = detector.detectar("   \n\n")
    assert result.error is not None
    assert result.mejor is None
