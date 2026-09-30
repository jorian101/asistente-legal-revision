import pytest

from src.domain.services.evaluador_requisitos import faltantes, nombres_legibles


def test_consulta_completo_sin_faltantes():
    assert faltantes("consulta", {"sentencia", "acta_audiencia", "oficio_elevacion"}) == set()


def test_consulta_falta_acta():
    assert faltantes("consulta", {"sentencia", "oficio_elevacion"}) == {"acta_audiencia"}


def test_apelacion_incidental_completo():
    assert (
        faltantes(
            "apelacion_incidental",
            {"auto_interlocutorio", "memorial_apelacion", "oficio_elevacion"},
        )
        == set()
    )


def test_apelacion_restringida_falta_memorial():
    assert faltantes("apelacion_restringida", {"sentencia", "oficio_elevacion"}) == {
        "memorial_apelacion"
    }


def test_case_insensitive():
    assert faltantes("consulta", {"SENTENCIA", "Acta_Audiencia", "OFICIO_ELEVACION"}) == set()


def test_tipo_desconocido_lanza():
    with pytest.raises(ValueError):
        faltantes("inexistente", set())


def test_nombres_legibles_ordenados():
    assert nombres_legibles({"oficio_elevacion", "acta_audiencia"}) == [
        "Acta de Audiencia Pública de Lectura",
        "Oficio de Elevación del TPJM",
    ]
