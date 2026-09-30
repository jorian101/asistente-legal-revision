"""Tests del AnalizadorVicios (pure domain service — Sprint 7, G2).

Arquitectura.md §3.2 + §6.2: AnalizadorVicios detecta vicios procesales
sobre texto de fragmentos por regex + heuristica. Servicio stateless, sin
DI, sin IO, sin datetime.

Estrategia (RG3 — 1 test minimo por regla):
- 1 test bloqueante por cada tipo de vicio (indefension, falta_notificacion,
  plazo_vencido, falta_firma).
- Caso base: texto neutro no detecta nada (NO false positive).
- Caso vacio: texto vacio y lote vacio devuelven vacio() (no raise).
- Match acumulativo: un fragmento con 2+ vicios detecta todos.
- Foja: cuando el snippet menciona foja, se extrae.
- Snippet: respeta limite de radio con elipsis en los bordes.
- Determinismo: misma entrada, mismo output (mismas posiciones).
"""

from __future__ import annotations

from src.domain.services.analizador_vicios import analizar_vicios
from src.domain.value_objects.resultado_vicios import (
    ResultadoVicios,
    TipoVicio,
)

# === Tests bloqueantes por tipo de vicio (RG3) ==============================


def test_detecta_indefension_bloqueante() -> None:
    """Bloqueante: el sistema detecta indefension por regex textual.

    Caso: fragmento describe que el procesado no fue notificado.
    Esperado: 1 vicio de tipo 'indefension' con norma CPPM Art. 361.
    """
    texto = (
        "Se constata que el procesado Juan PEREZ no fue notificado con la "
        "acusacion fiscal, por lo que se le causo indefension procesal."
    )

    resultado = analizar_vicios([(1, texto)])

    assert resultado.hay_vicios, "Debio detectar indefension"
    indefensiones = [v for v in resultado.vicios if v.tipo == "indefension"]
    assert len(indefensiones) == 1
    assert indefensiones[0].norma_vulnerada == "CPPM Art. 361"
    assert indefensiones[0].fragmento_id == 1


def test_detecta_falta_notificacion_bloqueante() -> None:
    """Bloqueante: acta de notificacion sin firma del actuario -> nulidad.

    CPPM Arts. 161-164: las notificaciones vician de nulidad si el acta
    carece de firma del actuario o si la notificacion fue defectuosa.
    """
    texto = (
        "El acta de notificacion se realizo sin firma del actuario, "
        "lo que configura una notificacion defectuosa conforme a CPPM."
    )

    resultado = analizar_vicios([(42, texto)])

    assert resultado.hay_vicios
    notifs = [v for v in resultado.vicios if v.tipo == "falta_notificacion"]
    assert len(notifs) == 1
    assert notifs[0].norma_vulnerada == "CPPM Arts. 161-164"
    assert notifs[0].fragmento_id == 42


def test_detecta_plazo_vencido_bloqueante() -> None:
    """Bloqueante: texto explicito de plazo vencido.

    NO detecta plazos calculados contra fecha del expediente (eso es
    EvaluadorCompetencia, G5). Solo patrones textuales explicitos.
    """
    texto = (
        "Vencio el plazo de tres dias para emitir el dictamen, por lo que "
        "el recurrente alega extemporaneidad en la presentacion."
    )

    resultado = analizar_vicios([(99, texto)])

    assert resultado.hay_vicios
    plazos = [v for v in resultado.vicios if v.tipo == "plazo_vencido"]
    assert len(plazos) >= 1  # matchea "vencio el plazo" o "extemporaneidad"
    assert plazos[0].norma_vulnerada == "CPPM Art. 105"
    assert plazos[0].fragmento_id == 99


def test_detecta_falta_firma_bloqueante() -> None:
    """Bloqueante: pieza procesal sin firma del vocal o auditor.

    CPPM Art. 75: la falta de firma del vocal o secretario en una
    resolucion judicial constituye vicio formal insanable.
    """
    texto = (
        "El auto de vista fue pronunciado sin firma del vocal relator, "
        "por lo que se advierte ausencia de firma en el documento."
    )

    resultado = analizar_vicios([(7, texto)])

    assert resultado.hay_vicios
    firmas = [v for v in resultado.vicios if v.tipo == "falta_firma"]
    assert len(firmas) >= 1
    assert firmas[0].norma_vulnerada == "CPPM Art. 75"
    assert firmas[0].fragmento_id == 7


# === Caso base / no false positives ========================================


def test_texto_neutro_no_detecta_vicios() -> None:
    """Texto procesal normal sin vicios no debe generar falsos positivos.

    Escenario: descripcion de hechos y normas SIN mencion de vicios.
    """
    texto = (
        "El Tribunal de Justicia Militar analizo los elementos probatorios "
        "aportados por el Ministerio Publico y resolvio dictar sentencia "
        "condenatoria conforme al articulo 154 del Codigo Penal Militar."
    )

    resultado = analizar_vicios([(1, texto)])

    assert resultado == ResultadoVicios.vacio(), (
        f"No debio detectar vicios. Encontrados: {resultado.vicios}"
    )


# === Casos limite: entradas vacias =========================================


def test_texto_vacio_devuelve_vacio() -> None:
    """Texto '' no genera vicios ni raise."""
    resultado = analizar_vicios([(1, "")])

    assert resultado == ResultadoVicios.vacio()


def test_lote_vacio_devuelve_vacio() -> None:
    """Sin fragmentos no genera vicios ni raise."""
    resultado = analizar_vicios([])

    assert resultado == ResultadoVicios.vacio()


def test_texto_none_o_falsy_devuelve_vacio() -> None:
    """Textos vacios explicitos (strings vacios) no rompen."""
    resultado = analizar_vicios([(1, ""), (2, ""), (3, "")])

    assert resultado == ResultadoVicios.vacio()


# === Multiples vicios en un mismo fragmento =================================


def test_detecta_multiples_vicios_en_un_fragmento() -> None:
    """Un fragmento con 2+ vicios debe detectarlos TODOS.

    Cubre la propiedad 'acumular' del servicio: si en un mismo texto hay
    multiples matches de distintos patrones, todos aparecen en el resultado.
    """
    texto = (
        "El procesado sufrio indefension procesal: no fue notificado y "
        "vencio el plazo fatal. Ademas, el auto carece de firma del "
        "vocal relator."
    )

    resultado = analizar_vicios([(1, texto)])

    tipos_encontrados = {v.tipo for v in resultado.vicios}
    # Esperados: indefension + falta_notificacion (no fue notificado)
    # + plazo_vencido (vencio el plazo) + falta_firma (carece de firma)
    assert "indefension" in tipos_encontrados
    assert "falta_notificacion" in tipos_encontrados
    assert "plazo_vencido" in tipos_encontrados
    assert "falta_firma" in tipos_encontrados
    assert resultado.total >= 4


def test_multiples_fragmentos_acumulan() -> None:
    """Vicios en fragmentos distintos se acumulan en un solo resultado."""
    frag1 = "El procesado sufrio indefension procesal total."
    frag2 = "Vencio el plazo fatal de 48 horas para el proyecto."
    frag3 = "Texto neutro sin vicios."

    resultado = analizar_vicios([(1, frag1), (2, frag2), (3, frag3)])

    tipos = {v.tipo for v in resultado.vicios}
    assert "indefension" in tipos
    assert "plazo_vencido" in tipos
    # Cada vicio conserva el id de su fragmento origen
    indefensiones = [v for v in resultado.vicios if v.tipo == "indefension"]
    plazos = [v for v in resultado.vicios if v.tipo == "plazo_vencido"]
    assert indefensiones[0].fragmento_id == 1
    assert plazos[0].fragmento_id == 2


# === Extraccion de foja ====================================================


def test_extraccion_foja_simple() -> None:
    """Si el snippet menciona 'foja 23', se extrae como '23'."""
    # Texto que matchea un patron de vicio + menciona foja cercana.
    texto = (
        "Se observa indefension en foja 23 del expediente por falta de notificacion al procesado."
    )

    resultado = analizar_vicios([(1, texto)])
    indefensiones = [v for v in resultado.vicios if v.tipo == "indefension"]
    assert len(indefensiones) == 1
    assert indefensiones[0].foja_referida == "23"


def test_extraccion_foja_rango() -> None:
    """'fojas 23-25' se extrae como '23-25' para citas de rango."""
    texto = "Plazo vencido conforme a fojas 23-25 del expediente."

    resultado = analizar_vicios([(1, texto)])
    plazos = [v for v in resultado.vicios if v.tipo == "plazo_vencido"]
    assert len(plazos) == 1
    assert plazos[0].foja_referida == "23-25"


def test_sin_foja_devuelve_none() -> None:
    """Vicio sin mencion de foja devuelve foja_referida=None."""
    texto = "El procesado sufrio indefension procesal manifiesta."

    resultado = analizar_vicios([(1, texto)])
    indefensiones = [v for v in resultado.vicios if v.tipo == "indefension"]
    assert len(indefensiones) == 1
    assert indefensiones[0].foja_referida is None


# === Snippet: limites y elipsis ============================================


def test_snippet_incluye_contexto_alrededor() -> None:
    """Snippet debe incluir ~50 chars antes y despues del match."""
    texto = (
        "Larga exposicion de antecedentes procesales del expediente numero "
        "123/2024 donde el procesado sufrio indefension manifiesta durante "
        "toda la tramitacion del proceso penal militar."
    )

    resultado = analizar_vicios([(1, texto)])
    vicio = resultado.vicios[0]
    assert "indefension" in vicio.snippet.lower()
    # Snippet debe ser mas largo que el match puro (incluye contexto)
    assert len(vicio.snippet) > len("indefension")
    # No debe incluir el texto completo (recortado)
    assert len(vicio.snippet) < len(texto)


def test_snippet_usa_elipsis_en_bordes_si_truncado() -> None:
    """Snippet truncado muestra '...' al inicio y/o final."""
    texto = (
        "Muchos muchos antecedentes procesales del expediente. "
        "Mas y mas texto irrelevante. "
        "Y finalmente el vicio: el procesado sufrio indefension procesal. "
        "Texto adicional despues del vicio para forzar truncamiento."
    )

    resultado = analizar_vicios([(1, texto)])
    vicio = resultado.vicios[0]
    # Como hay texto antes y despues del match, snippet debe tener elipsis
    # en ambos extremos
    assert vicio.snippet.startswith("..."), f"Debe tener elipsis izq: {vicio.snippet}"
    assert vicio.snippet.endswith("..."), f"Debe tener elipsis der: {vicio.snippet}"


# === Determinismo ==========================================================


def test_misma_entrada_mismo_output() -> None:
    """Determinismo: misma entrada produce mismo output (regex pura)."""
    texto = "El procesado sufrio indefension procesal total."

    r1 = analizar_vicios([(1, texto)])
    r2 = analizar_vicios([(1, texto)])

    assert r1.total == r2.total
    assert r1.vicios == r2.vicios
    # Mismas posiciones del snippet (verificable si texto fuera mas largo)
    if r1.vicios:
        assert r1.vicios[0].snippet == r2.vicios[0].snippet


def test_tipo_vicio_es_literal_type() -> None:
    """TipoVicio es Literal type: previene typos en el catalogo."""
    # Si alguien agrega un valor no-Literal, este test rompe.
    # No es runtime check: validamos que el VO se construyo con Literal.
    import typing

    assert getattr(TipoVicio, "__origin__", None) is typing.Literal


# === Inmunidad a mayusculas / acentos =======================================


def test_case_insensitive() -> None:
    """Mayusculas no afectan la deteccion (regex IGNORECASE)."""
    texto = "EL PROCESADO SUFRIO INDEFENSION PROCESAL TOTAL."

    resultado = analizar_vicios([(1, texto)])

    assert resultado.hay_vicios
    assert any(v.tipo == "indefension" for v in resultado.vicios)


def test_acentos_opcionales() -> None:
    """Patrones aceptan la keyword CON o SIN acento en la vocal critica.

    Relevante porque los PDFs viejos vienen sin acentos y los nuevos con
    acentos. Un regex que solo acepta acento genera falsos negativos.
    """
    texto_sin_acento = "se le causo indefension procesal total"  # sin 'ó'
    texto_con_acento = "se le causó indefensión procesal total"  # con 'ó' y 'ó'

    r1 = analizar_vicios([(1, texto_sin_acento)])
    r2 = analizar_vicios([(1, texto_con_acento)])

    # Ambos matchean (regex con [oó])
    assert r1.hay_vicios, "Debio detectar 'indefension' sin acento"
    assert r2.hay_vicios, "Debio detectar 'indefensión' con acento"


# === Tipos de vicio: API publica ===========================================


def test_tipo_vicio_contiene_los_7_valores() -> None:
    """El Literal TypeVicio tiene exactamente 7 valores esperados.

    ponytail: si agregas un vicio nuevo, suma el test bloqueante arriba
    y este test sigue verde solo si lo agregas al Literal.
    """
    import typing

    valores = typing.get_args(TipoVicio)
    assert set(valores) == {
        "indefension",
        "falta_notificacion",
        "plazo_vencido",
        "falta_firma",
        "articulo_incongruente",
        "via_incongruente",
        "foja_futura",
    }


# === Plan D (D5): detección de inconsistencias (criterio del Vocal) =========


def test_articulo_incongruente_caso_3352() -> None:
    """Detecta que el Art. 125 (Deserción) no corresponde al delito imputado
    'Abandono de Servicio' (caso real 3352: el inferior citó la figura de la
    Deserción cuando el delito juzgado era Abandono de Servicio)."""
    texto = (
        "el tribunal transcribió de manera errónea el Art. 125.-\n"
        "(Deserción) correspondiente a la figura jurídica de la deserción, "
        "cuando el tipo penal imputado fue el Artículo 140 del Código Penal "
        "Militar Abandono de Servicio"
    )
    resultado = analizar_vicios([(1, texto)], delito_esperado="Abandono de Servicio")
    assert any(v.tipo == "articulo_incongruente" for v in resultado.vicios)


def test_articulo_concordante_no_marca() -> None:
    """Si el articulo citado corresponde al delito, no marca incongruencia."""
    texto = "el delito de 'Abandono de Servicio' previsto en el Art. 140 (Abandono de Servicio)"
    resultado = analizar_vicios([(1, texto)], delito_esperado="Abandono de Servicio")
    assert not any(v.tipo == "articulo_incongruente" for v in resultado.vicios)


def test_via_incongruente_apelacion_vs_consulta() -> None:
    """El texto dice 'elevar en grado de apelacion' pero la sentencia es
    absolutoria sin apelacion (regla de oro: consulta, caso 3288)."""
    texto = (
        "elevar obrados en grado de apelación la sentencia absolutoria, "
        "pues ninguna de las partes apeló"
    )
    resultado = analizar_vicios([(1, texto)])
    assert any(v.tipo == "via_incongruente" for v in resultado.vicios)
