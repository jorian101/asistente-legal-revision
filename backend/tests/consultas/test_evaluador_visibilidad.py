"""Tests del EvaluadorVisibilidad (pure domain service — Sprint 5).

Regla 6 Trail of Bits (BLOQUEANTE):
- El contexto expandido nunca debe incluir fragmentos de obras privadas
  de otros usuarios, por diseno del ExpansorJerarquico.
- Las rutas de breadcrumb se resuelven contra PostgreSQL (no Qdrant).

Cubre (RG3 — 1 test minimo por regla bloqueante):
- Obras privadas ajenas se podan (BLOQUEANTE).
- Fragmentos de corpus juridico (sin obra_id) siempre pasan.
- Obra publicada de otro usuario pasa.
- Obra privada propia pasa (caso base).
- Obras privadas ajenas ausentes del dict (filtradas por batch Regla 5) podan sus fragmentos.
"""

from __future__ import annotations

from src.domain.entities.obra import Obra
from src.domain.services.evaluador_visibilidad import evaluar_visibilidad
from tests._factories import make_fragmento


def _make_obra(
    *,
    id: int,
    propietario_id: int,
    estado_visibilidad: str = "privado",
) -> Obra:
    """Helper local: Obra solo necesitada para estos tests.

    ponytail: NO se agrega `make_obra` al factory global porque es el unico
    modulo que la usa hoy. Cuando otro test la necesite, recien ahi promoveerla.
    """
    return Obra(
        id=id,
        expediente_id=1,
        propietario_id=propietario_id,
        tipo_documento="sentencia",
        nombre_archivo="sentencia.pdf",
        contenido_texto="...",
        estado_visibilidad=estado_visibilidad,  # type: ignore[arg-type]
    )


def test_obra_privada_propia_se_mantiene() -> None:
    """Obra privada del propio usuario: sus fragmentos pasan (caso base)."""
    obra = _make_obra(id=10, propietario_id=1, estado_visibilidad="privado")
    frag = make_fragmento(id=100, obra_id=10, norma_id=None)

    resultado = evaluar_visibilidad(
        fragmentos=[frag],
        usuario_id=1,
        obras_por_id={10: obra},
    )

    assert resultado == [frag]


def test_obra_privada_ajena_se_poda() -> None:
    """Regla 6 BLOQUEANTE: fragmento cuyo obra_id es privado de otro usuario se poda.

    Escenario: Operador A (usuario_id=1) no debe recibir fragmento ascendido
    de obra privada del Operador B (propietario_id=2) en el mismo expediente.
    """
    obra_privada_ajena = _make_obra(id=20, propietario_id=2, estado_visibilidad="privado")
    frag_ajeno = make_fragmento(id=200, obra_id=20, norma_id=None)

    resultado = evaluar_visibilidad(
        fragmentos=[frag_ajeno],
        usuario_id=1,
        obras_por_id={20: obra_privada_ajena},
    )

    assert resultado == [], "Regla 6 Poda la obra privada ajena — bug PermitirVisibility si pass"


def test_fragmento_norma_sin_obra_pasa() -> None:
    """Fragmento de corpus juridico (norma_id seteado, obra_id None) siempre pasa.

    Las obras privadas no aplican al corpus normativo cargado por el admin.
    """
    frag_norma = make_fragmento(id=300, norma_id=1, obra_id=None)

    resultado = evaluar_visibilidad(
        fragmentos=[frag_norma],
        usuario_id=999,  # cualquier usuario
        obras_por_id={},  # sin obras cargadas
    )

    assert resultado == [frag_norma]


def test_obra_publicada_ajena_pasa() -> None:
    """Obra publicada de otro usuario: el fragmento pasa (visible a todos)."""
    obra_publicada = _make_obra(id=40, propietario_id=2, estado_visibilidad="publicado")
    frag_publicado = make_fragmento(id=400, obra_id=40, norma_id=None)

    resultado = evaluar_visibilidad(
        fragmentos=[frag_publicado],
        usuario_id=1,  # otro usuario distinto al propietario
        obras_por_id={40: obra_publicada},
    )

    assert resultado == [frag_publicado]


def test_obra_privada_ajena_ausente_del_dict_se_poda() -> None:
    """Regla 6 via diseno del batch: si obra_id no esta en obras_por_id,
    el EvaluadorVisibilidad asume que es obra privada ajena (filtrada por
    obtener_por_ids con Regla 5) y poda el fragmento.

    Esta es la proteccion Regla 6 por diseno del adapter (Q3): el batch
    ObraRepo.obtener_por_ids aplica filtro propietario OR publicado, asi
    la ausencia en el dict es la senal suficiente para podar.
    """
    # obra_id=50 NO esta en obras_por_id (simulando filtrado del batch)
    frag_orfano = make_fragmento(id=500, obra_id=50, norma_id=None)

    resultado = evaluar_visibilidad(
        fragmentos=[frag_orfano],
        usuario_id=1,
        obras_por_id={},  # obra 50 fue filtrada por el batch Regla 5
    )

    assert resultado == [], "Regla 6 via diseno: obra_id ausente del dict se asume privada ajena"


def test_lista_mixta_filtra_solo_privadas_ajenas() -> None:
    """Integracion completa: mezcla de escenarios en una sola llamada.

    Entrada: 4 fragmentos (privada propia, privada ajena, publicada ajena, norma).
    Salida esperada: 3 (se poda la privada ajena, las otras 3 pasan).
    """
    obra_privada_propia = _make_obra(id=10, propietario_id=1, estado_visibilidad="privado")
    obra_privada_ajena = _make_obra(id=20, propietario_id=2, estado_visibilidad="privado")
    obra_publicada_ajena = _make_obra(id=30, propietario_id=2, estado_visibilidad="publicado")

    frags = [
        make_fragmento(id=1, obra_id=10, norma_id=None),  # privada propia -> pasa
        make_fragmento(id=2, obra_id=20, norma_id=None),  # privada ajena -> poda
        make_fragmento(id=3, obra_id=30, norma_id=None),  # publicada ajena -> pasa
        make_fragmento(id=4, norma_id=1, obra_id=None),  # corpus normativo -> pasa
    ]

    resultado = evaluar_visibilidad(
        fragmentos=frags,
        usuario_id=1,
        obras_por_id={
            10: obra_privada_propia,
            20: obra_privada_ajena,
            30: obra_publicada_ajena,
        },
    )

    assert {f.id for f in resultado} == {1, 3, 4}, (
        "Solo se poda la obra privada ajena (id=2); las otras 3 pasan"
    )
