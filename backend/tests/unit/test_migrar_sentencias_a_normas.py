"""Plan de migración de sentencias sembradas como obra `doctrina` (obras 13/14/15)."""

from __future__ import annotations

from types import SimpleNamespace

from scripts.migrar_sentencias_a_normas import planificar


def _obra(id_, archivo, expediente_id=None, tipo="doctrina", activo=True):
    return SimpleNamespace(
        id=id_,
        nombre_archivo=archivo,
        expediente_id=expediente_id,
        tipo_documento=tipo,
        activo=activo,
    )


NORMAS = {"SCP-0623-2024-S4", "SCP-0663-2025-S2", "CIDH-TC-PERU-2001"}


def test_obra_de_expediente_pasa_a_puntero_y_la_global_se_desactiva():
    obras = [
        _obra(13, "scp-0623-2024-s4.txt", expediente_id=7),
        _obra(14, "scp-0663-2025-s2.txt"),
        _obra(15, "corte-idh-tc-peru.txt"),
    ]

    plan = planificar(obras, NORMAS)

    assert [(a.obra_id, a.accion, a.abreviatura) for a in plan] == [
        (13, "puntero", "SCP-0623-2024-S4"),
        (14, "desactivar", "SCP-0663-2025-S2"),
        (15, "desactivar", "CIDH-TC-PERU-2001"),
    ]


def test_no_toca_doctrina_real_ni_obras_ya_migradas():
    obras = [
        _obra(16, "doctrina-apelacion-incidental.txt", expediente_id=8),
        _obra(20, "scp-0623-2024-s4.txt", expediente_id=7, tipo="jurisprudencia"),
        _obra(21, "scp-0663-2025-s2.txt", activo=False),
    ]

    assert planificar(obras, NORMAS) == []


def test_sin_la_norma_indexada_no_migra():
    """Si la sentencia no existe como norma, migrar la perderia."""
    obras = [_obra(13, "scp-0623-2024-s4.txt", expediente_id=7)]

    assert planificar(obras, set()) == []


def test_se_puede_migrar_una_sola_obra():
    obras = [
        _obra(13, "scp-0623-2024-s4.txt", expediente_id=7),
        _obra(14, "scp-0663-2025-s2.txt"),
        _obra(15, "corte-idh-tc-peru.txt"),
    ]

    plan = planificar(obras, NORMAS, solo_obra=14)

    assert [(a.obra_id, a.accion) for a in plan] == [(14, "desactivar")]
    assert planificar(obras, NORMAS, solo_obra=99) == []
