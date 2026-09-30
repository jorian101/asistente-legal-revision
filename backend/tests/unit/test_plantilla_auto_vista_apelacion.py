"""Defectos de la plantilla de auto de vista (apelación) frente al auto real 04/2026
del vocal (vault: sources/casos-tsjm/casos/exp-3145-3172-apelacion-incidental)."""

from __future__ import annotations

from pathlib import Path

PLANTILLA = (
    Path(__file__).resolve().parents[3] / "docs" / "plantillas" / "proyecto_auto_vista_apelacion.md"
)


def _texto() -> str:
    return PLANTILLA.read_text(encoding="utf-8")


def test_cierre_como_el_auto_real():
    assert "Regístrese, tómese razón y notifíquese." in _texto()
    assert "devuélvase" not in _texto()


def test_informa_el_recurso_de_nulidad_en_lugar_de_cosa_juzgada():
    texto = _texto()
    assert "Cosa Juzgada" not in texto
    assert "no admitiendo recurso ulterior" not in texto
    assert "Art. 203" in texto
    assert "cinco días" in texto


def test_firmas_de_la_sala_y_secretario():
    texto = _texto()
    assert "VOCAL PRESIDENTE" in texto
    assert "VOCAL RELATOR" in texto
    assert "Ante mí" in texto


def test_sin_datos_del_caso_salinas_como_texto_fijo():
    texto = _texto()
    assert "5 años y 4 meses" not in texto
    assert "COVID" not in texto


def test_la_modificacion_de_fundamentos_es_condicional():
    """En el auto real es CONFIRMAR simple; la variante con modificación de
    fundamentos solo aplica si el inferior fundó mal su rechazo."""
    assert "solo si" in _texto()


def test_encabezado_usa_variables_en_vez_de_corchetes_de_ejemplo():
    """Auditoría (Arreglo 2): el encabezado usaba texto literal con corchetes
    de ejemplo ('[Insertar Número, ej: 04/2026]') que el adapter no resolvía
    (solo reemplaza tokens {{...}}), asi que el LLM copiaba el corchete o el
    ejemplo tal cual. Ahora debe exponer esos campos como variables, igual
    que proyecto_auto_vista_consulta.md."""
    texto = _texto()

    assert "[Insertar" not in texto
    assert "04/2026" not in texto
    assert "{{AUTO_DE_VISTA_CORRELATIVO}}" in texto
    assert "{{NUMERO_CASO}}" in texto
    assert "{{NUMERO_CASO_SECUNDARIO}}" in texto
    assert "{{RECURRENTE}}" in texto
    assert "{{DELITOS}}" in texto
    assert "{{FECHA_ACTUAL}}" in texto


def test_firmas_usan_variables_con_fallback():
    """Las firmas (presidente, relator, propietario, secretario) deben ser
    variables resolubles por el adapter, no texto '[Insertar ...]' fijo."""
    texto = _texto()

    assert "{{FIRMA_VOCAL_PRESIDENTE}}" in texto
    assert "{{FIRMA_VOCAL_RELATOR}}" in texto
    assert "{{FIRMA_VOCAL_PROPIETARIO}}" in texto
    assert "{{FIRMA_SECRETARIO_CAMARA}}" in texto


def test_estructura_i_a_v_como_el_auto_real_04_2026():
    """Auditoría (Arreglo 3) + alineación vocal (U2): el auto real 04/2026
    tiene I Antecedentes, II Agravios (cita textual), III Marco Jurídico
    (con subsecciones 3.x), y Considerandos siguientes (aquí IV-V, el
    "los considerandos que el caso pida" del plan) antes de POR TANTO."""
    texto = _texto()

    assert "### CONSIDERANDO I (ANTECEDENTES)" in texto
    assert "### CONSIDERANDO II (AGRAVIOS DEL RECURSO DE APELACIÓN INCIDENTAL)" in texto
    assert "### CONSIDERANDO III (MARCO JURÍDICO APLICABLE)" in texto
    assert "### CONSIDERANDO IV (ANÁLISIS Y RESOLUCIÓN DE LOS AGRAVIOS)" in texto
    assert "### CONSIDERANDO V (SÍNTESIS MOTIVADA Y DECISIÓN DE LA SALA)" in texto
    assert "#### 3.1." in texto
    assert "#### 3.2." in texto


def test_regla_que_junto_a_cada_considerando():
    """La regla "Que," aparece antes de CONSIDERANDO I — y cubre listas,
    sub-apartados (3.1-3.2) y bloques condicionales — con una excepción
    explícita para los agravios citados textualmente (Considerando II).
    Los sub-apartados de CONSIDERANDO III y los ítems numerados de
    CONSIDERANDO IV abren con "Que," en el propio texto de ejemplo."""
    texto = _texto()

    antes_i, resto = texto.split("### CONSIDERANDO I (ANTECEDENTES)", 1)
    assert 'deben iniciar con la palabra "Que,"' in antes_i
    assert "sub-apartado" in antes_i
    assert "los AGRAVIOS del Considerando II se citan textualmente" in antes_i

    assert texto.count("Que, es imperativo delimitar") == 1  # 3.1
    assert texto.count("Que, revisada minuciosamente") == 1  # 3.2
    assert texto.count("Que, subsanado el error doctrinal") == 1  # IV
    assert texto.count("Que, respecto al agravio planteado") == 1  # IV (favorabilidad)
    assert texto.count("Que, la norma penal militar determina") == 1  # IV.1
    assert texto.count("Que, a diferencia de la justicia común") == 1  # IV.2
    assert texto.count("Que, consta en obrados") == 1  # IV.3
    assert texto.count("Que, asimismo, del cómputo cronológico") == 1  # IV.4


def test_agravios_citados_sin_que():
    """Los 3 agravios del Considerando II son cita textual (blockquote,
    con '>'), SIN "Que," — así los transcribe el auto real 04/2026 (con
    formato de cita)."""
    texto = _texto()

    _, bloque_agravios = texto.split(
        "### CONSIDERANDO II (AGRAVIOS DEL RECURSO DE APELACIÓN INCIDENTAL)", 1
    )
    bloque_agravios = bloque_agravios.split("### CONSIDERANDO III", 1)[0]

    assert "> **Primer Agravio" in bloque_agravios
    assert "> **Segundo Agravio" in bloque_agravios
    assert "> **Tercer Agravio" in bloque_agravios
    assert "Que, sostiene" not in bloque_agravios
    assert "Que, acusa" not in bloque_agravios
    assert "Que, manifiesta" not in bloque_agravios


def test_art_29_bis_marcado_como_condicional_y_ejemplo():
    """El apartado 3.2 (Art. 29 Bis) trae la advertencia condicional
    pegada al propio encabezado, no solo enterrada en el bloque largo de
    CONSIDERANDO III."""
    texto = _texto()

    assert "Apartado 3.2 CONDICIONAL" in texto
    assert "ÚNICAMENTE si la resolución recurrida efectivamente invocó" in texto
    assert "EJEMPLO de esta plantilla, no un dato verificado" in texto


def test_resuelve_es_rotulo_obligatorio():
    """RESUELVE debe quedar marcado como rótulo obligatorio de la parte
    resolutiva, no alcanza con POR TANTO."""
    texto = _texto()

    assert 'Nunca omitas "RESUELVE:"' in texto
    assert "no alcanza con POR TANTO solo" in texto


def test_firmas_nunca_inventan_fdo():
    """Regla explícita: si una firma no está disponible, se deja el
    marcador o "[pendiente: firma no disponible]", nunca se inventa un
    nombre ni la abreviatura "(Fdo.)"."""
    texto = _texto()

    assert '"(Fdo.)"' in texto
    assert "nunca inventes un nombre" in texto
    assert "[pendiente: firma no disponible]" in texto


def test_encabezado_real_en_tabla_de_2_columnas():
    """Alineación vocal (U1): el auto real 04/2026 usa una tabla de 2
    columnas para Expedientes/Parte Recurrente/Proceso/Resolución
    Apelada/Vocal Relator — no una lista de campos como consulta."""
    texto = _texto()

    assert "**AUTO DE VISTA: Nº {{AUTO_DE_VISTA_CORRELATIVO}}/{{ANIO}}**" in texto
    assert "|" in texto  # tabla Markdown
    assert "**Expedientes:**" in texto
    assert "**Resolución Apelada:**" in texto
    assert "{{VOCAL_RELATOR}}" in texto
    assert "DISTRITO" not in texto
    assert "AUTORIDAD RECURRIDA" not in texto


def test_resuelve_tiene_ordinales_en_letras():
    """Alineación vocal (U4): el auto real 04/2026 usa PRIMERO.–/SEGUNDO.–/
    TERCERO.– en RESUELVE, no "1. 2. 3."."""
    texto = _texto()

    assert "**PRIMERO.–**" in texto
    assert "**SEGUNDO.–**" in texto
    assert "**TERCERO.–**" in texto
    assert "MAYÚSCULAS SOSTENIDAS" in texto


def test_cierre_no_se_mezcla_con_el_de_dictamenes():
    """Distingue el cierre de los autos del cierre de los dictámenes
    ("Regístrese, Archívese y Notifíquese.") — familias distintas."""
    texto = _texto()

    assert "Regístrese, tómese razón y notifíquese." in texto
    assert "Archívese" not in texto
