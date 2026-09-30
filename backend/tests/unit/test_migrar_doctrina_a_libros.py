"""Plan de migración de la doctrina subida como obra a libros del corpus."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.migrar_doctrina_a_libros import planificar


def _obra(id_, **kw):
    base = {
        "id": id_,
        "tipo_documento": "doctrina",
        "estado_visibilidad": "global",
        "expediente_id": None,
        "propietario_id": 26,
        "nombre_archivo": "doctrina-apelacion-incidental.txt",
        "contenido_texto": "Texto de doctrina " * 50,
        "corpus_ref": None,
        "activo": True,
    }
    return SimpleNamespace(**{**base, **kw})


def test_la_visibilidad_de_la_obra_decide_el_estado_del_libro():
    plan = planificar(
        [
            _obra(1, estado_visibilidad="privado"),
            _obra(2, estado_visibilidad="publicado"),
            _obra(3, estado_visibilidad="global"),
        ]
    )

    assert [(a.obra_id, a.estado) for a in plan] == [
        (1, "privado"),
        (2, "pendiente"),
        (3, "global"),
    ]


def test_el_nombre_del_libro_sale_del_archivo_sin_extension():
    (accion,) = planificar([_obra(1, nombre_archivo="doctrina-apelacion-incidental.txt")])

    assert accion.nombre == "doctrina apelacion incidental"


def test_una_obra_de_expediente_conserva_el_vinculo_como_puntero():
    plan = planificar([_obra(1, expediente_id=8), _obra(2)])

    assert [a.puntero_expediente_id for a in plan] == [8, None]


def test_no_toca_lo_que_no_es_doctrina_de_usuario():
    plan = planificar(
        [
            _obra(1, tipo_documento="sentencia"),
            _obra(2, corpus_ref="LIB-X"),  # ya es puntero
            _obra(3, activo=False),
            _obra(4, contenido_texto="   "),
            _obra(5, estado_visibilidad="rechazado"),
            _obra(6, tipo_documento="criterio"),
        ]
    )

    assert plan == []


def test_material_caso_tambien_es_doctrina():
    assert [a.obra_id for a in planificar([_obra(1, tipo_documento="material_caso")])] == [1]


def test_las_sentencias_no_son_libros():
    """SCP y Corte IDH son jurisprudencia: las migra migrar_sentencias_a_normas."""
    plan = planificar(
        [
            _obra(1, nombre_archivo="scp-0623-2024-s4.txt"),
            _obra(2, nombre_archivo="corte-idh-tc-peru.txt"),
            _obra(3),
        ]
    )

    assert [a.obra_id for a in plan] == [3]
