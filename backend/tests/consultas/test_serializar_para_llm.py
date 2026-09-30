"""Tests de serializar_para_llm (P4) — inyección anti-alucinación de fojas.

Cubre:
- Formatea bloques de hecho/derecho/vicio con foja y norma.
- Incluye instrucción anti-alucinación (no inventar fojas).
- Caso vacío: nota de "sin hitos estructurados".
"""

from __future__ import annotations

from src.application.consultas.sugerir_argumentacion import (
    BloqueArgumentacion,
    SugerenciaArgumentacion,
    serializar_para_llm,
)


def _sugerencia_con_bloque() -> SugerenciaArgumentacion:
    return SugerenciaArgumentacion(
        tipo_respuesta="auto_vista_consulta",
        fundamentos_hecho=(
            BloqueArgumentacion(
                titulo="Hecho: Resolucion Judicial",
                tipo="hecho",
                contenido="La sentencia N 24/2025 fue absolutoria.",
                fojas_referidas=("fs. 600 a 605",),
                normas_citadas=("Art. 178 Num. 3 CPM",),
                prioridad="alta",
            ),
        ),
        fundamentos_derecho=(),
        vicios_sanear=(),
        alertas_competencia=(),
        alertas_plazos=(),
        resumen_ejecutivo="1 fundamento de hecho",
    )


def test_serializar_incluye_instruccion_anti_alucinacion() -> None:
    """La salida debe prohibir inventar fojas."""
    texto = serializar_para_llm(_sugerencia_con_bloque())
    assert "NO la inventes" in texto
    assert "Datos verificados del expediente" in texto


def test_serializar_incluye_foja_y_norma_del_bloque() -> None:
    """La foja y norma verificadas del bloque deben aparecer en el prompt."""
    texto = serializar_para_llm(_sugerencia_con_bloque())
    assert "fs. 600 a 605" in texto
    assert "Art. 178 Num. 3 CPM" in texto
    assert "La sentencia N 24/2025 fue absolutoria" in texto


def test_serializar_vacio_no_inventa() -> None:
    """Sin bloques: nota de no inventar fojas, sin contenido fabricado."""
    vacia = SugerenciaArgumentacion.vacia("auto_vista_consulta")
    texto = serializar_para_llm(vacia)
    assert "Sin hitos estructurados" in texto
    assert "NO la inventes" in texto


def test_serializar_no_ordena_escribir_foja_no_disponible() -> None:
    """Esa frase se copiaba tal cual en cada agravio («foja no disponible»).
    Sin foja verificada se omite la referencia; no se escribe un relleno."""
    texto = serializar_para_llm(_sugerencia_con_bloque())
    assert "foja no disponible" not in texto.lower()
    assert "omite" in texto.lower()

    vacia = serializar_para_llm(SugerenciaArgumentacion.vacia("auto_vista_consulta"))
    assert "foja no disponible" not in vacia.lower()
