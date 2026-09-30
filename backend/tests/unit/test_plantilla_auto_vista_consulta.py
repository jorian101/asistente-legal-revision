"""Auditoría (Arreglo 3): refuerzo de las reglas de redacción en el auto de
vista de consulta — regla "Que," repetida junto a cada Considerando, citas de
ejemplo marcadas como no verificadas y firmas sin inventar."""

from __future__ import annotations

from pathlib import Path

PLANTILLA = (
    Path(__file__).resolve().parents[3] / "docs" / "plantillas" / "proyecto_auto_vista_consulta.md"
)


def _texto() -> str:
    return PLANTILLA.read_text(encoding="utf-8")


def test_regla_que_junto_a_cada_considerando():
    """La regla "Que," aparece antes de CONSIDERANDO I y II — el auto de
    consulta real tiene solo dos considerandos (Gem del vocal + 3 autos
    reales de consulta) — y aclara que aplica a listas, sub-encabezados y
    bloques condicionales."""
    texto = _texto()

    antes_i, resto = texto.split("### CONSIDERANDO I (ANTECEDENTES):", 1)
    assert 'deben iniciar con la palabra "Que,"' in antes_i
    assert "listas numeradas" in antes_i
    assert "sub-encabezados" in antes_i

    antes_ii, resto = resto.split("### CONSIDERANDO II (ANÁLISIS Y FUNDAMENTO JURÍDICO):", 1)
    assert "Que," in antes_ii
    assert "### CONSIDERANDO III" not in texto  # el auto real de consulta tiene solo I y II


def test_citas_de_ejemplo_marcadas_como_no_verificadas():
    """Art. 11 CPM y Art. 175/183 CPPM están marcados inline como ejemplo
    de la plantilla, con instrucción de usar [pendiente: cita no verificada]
    si no figuran en el contexto recuperado."""
    texto = _texto()

    assert "Art. 11 CPM **es un EJEMPLO de esta plantilla" in texto
    assert "Art. 175 y 183 Núm. 2 CPPM son EJEMPLO de esta plantilla" in texto
    assert texto.count("[pendiente: cita no verificada]") >= 2


def test_firmas_nunca_inventan_fdo():
    """Regla explícita: si una firma no está disponible, se deja el
    marcador o "[pendiente: firma no disponible]", nunca se inventa un
    nombre ni la abreviatura "(Fdo.)"."""
    texto = _texto()

    assert '"(Fdo.)"' in texto
    assert "nunca inventes un nombre" in texto
    assert "[pendiente: firma no disponible]" in texto


def test_encabezado_real_con_parte_recurrente_y_vocal_relator():
    """Alineación vocal (U1): el encabezado real de consulta (11/2026,
    16/2026, 3349) trae Expediente N°, Parte Recurrente, Proceso, Procesado
    y Vocal Relator como lista de campos, con "AUTO DE VISTA: Nº X/AAAA" —
    antes faltaban Parte Recurrente y Vocal Relator."""
    texto = _texto()

    assert "**AUTO DE VISTA: Nº {{AUTO_DE_VISTA_CORRELATIVO}}/{{ANIO}}**" in texto
    assert "**Expediente N°:** {{NUMERO_CASO}}" in texto
    assert "**Parte Recurrente:** En CONSULTA de Oficio (Art. 194 CPPM)" in texto
    assert "**Procesado:** {{PROCESADO_GRADO_Y_NOMBRE}}" in texto
    assert "**Vocal Relator:** {{VOCAL_RELATOR}}" in texto
    assert "DISTRITO" not in texto  # no existe en ningún auto real


def test_firmas_son_las_4_reales_de_la_sala():
    """Alineación vocal (U5): los 5 autos reales firman siempre los mismos
    4 — Vocal Presidente, Vocal Relator, Vocal Propietario y Secretario de
    Cámara — sin rótulo "FIRMAS:" previo. Antes faltaban Propietario y
    Secretario, y sobraba un "Vocal Ministro" sin equivalente real."""
    texto = _texto()

    assert "{{FIRMA_VOCAL_PRESIDENTE}}" in texto
    assert "{{FIRMA_VOCAL_RELATOR}}" in texto
    assert "{{FIRMA_VOCAL_PROPIETARIO}}" in texto
    assert "{{FIRMA_SECRETARIO_CAMARA}}" in texto
    assert "SECRETARIO DE CÁMARA" in texto
    assert "FIRMA_VOCAL_MINISTRO" not in texto
    assert "**FIRMAS:**" not in texto


def test_resuelve_tiene_ordinales_y_cuatro_opciones():
    """Alineación vocal (U4): la parte resolutiva real usa ordinales
    ("PRIMERO: CONFIRMAR..."), no "1. 2. 3.", y el Gem agrega
    Aprobar/Improbar como verbo específico de la consulta."""
    texto = _texto()

    assert "**PRIMERO: CONFIRMAR**" in texto
    assert "**PRIMERO: APROBAR**" in texto
    assert "**PRIMERO: REVOCAR**" in texto
    assert "**PRIMERO: ANULAR OBRADOS**" in texto
    assert "MAYÚSCULAS SOSTENIDAS" in texto


def test_cierre_es_el_de_los_autos_no_el_de_dictamenes():
    """Los autos de vista cierran "Regístrese, tómese razón y
    notifíquese." — distinto del cierre de los dictámenes ("Regístrese,
    Archívese y Notifíquese."). No hay que mezclarlos entre familias."""
    texto = _texto()

    assert "Regístrese, tómese razón y notifíquese." in texto
    assert "Archívese" not in texto
