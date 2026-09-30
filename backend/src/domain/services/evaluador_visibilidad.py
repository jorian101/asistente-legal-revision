"""Servicio de dominio: EvaluadorVisibilidad — Regla 6 Trail of Bits.

Filtra fragmentos cuyo obra_id apunta a una obra privada ajena, por diseno
del ExpansorJerarquico (Sprint 5).

Regla 6 (arquitectura.md §8):
    "El contexto expandido nunca debe incluir fragmentos de obras privadas
    de otros usuarios, por diseno del ExpansorJerarquico."

Diseno del adapter (Q3): el adapter hace UN batch ObraRepo.obtener_por_ids
que aplica filtro Regla 5 (propietario_id = usuario OR publicado). La
ausencia de una obra en obras_por_id es la senal suficiente para podar
sus fragmentos — el EvaluadorVisibilidad no necesita re-query.

Stateless pure function: no DI de repos, recibe todo por parametro. Testable
sin mocks.
"""

from __future__ import annotations

from src.domain.entities.fragmento import Fragmento
from src.domain.entities.obra import Obra


def evaluar_visibilidad(
    fragmentos: list[Fragmento],
    usuario_id: int,
    obras_por_id: dict[int, Obra],
) -> list[Fragmento]:
    """Filtra fragmentos que violan Regla 6.

    Args:
        fragmentos: Candidatos a incluir en ContextoExpandido.
        usuario_id: ID del usuario que pidio la consulta (Regla 4).
        obras_por_id: dict obra_id -> Obra ya filtrado por el adapter con
            Regla 5 (propias + publicadas). Las obras privadas ajenas NO
            aparecen aca — esa ausencia es la senal para podar sus fragmentos.

    Returns:
        Lista de fragmentos visibles al usuario (Regla 6 cumplida).
    """
    visibles: list[Fragmento] = []
    for frag in fragmentos:
        # Fragmento de corpus normativo (sin obra_id): siempre pasa.
        if frag.obra_id is None:
            visibles.append(frag)
            continue

        obra = obras_por_id.get(frag.obra_id)
        # Obra ausente del dict: el batch la filtro por ser privada ajena.
        if obra is None:
            # ponytail: no raise, no warn — podar es el contrato del dict.
            continue

        # Obra presente: pasa si es propia o publicada (el batch ya garantizo
        # esto, pero la validacion explicita aclara la intencion Regla 6).
        if obra.propietario_id == usuario_id or obra.estado_visibilidad == "publicado":
            visibles.append(frag)
        # else: obra presente pero el dict fue mal poblado — no deberia pasar
        # si el adapter respeta Regla 5. Ponytail: dejar caer en silencio.

    return visibles
