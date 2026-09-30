"""Use case: ObtenerFuentesConsulta — citas RAG de una consulta (HU-18 UI).

Retorna los fragmentos recuperados + scores persistidos en
`consulta_historial.fuentes_recuperadas` para mostrarlos como citas bajo el
mensaje del asistente en el chat.

Regla 4: el repo solo retorna la entrada si pertenece al usuario; None
encubierto (no se revela si el id existe de otro).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.domain.services.categoria_fuente import categoria_de_jerarquia, categoria_de_obra
from src.domain.services.referencias import etiqueta_legible


@dataclass(frozen=True, slots=True)
class FragmentoCita:
    """Fragmento citable, sanitizado y enriquecido para display.

    Los campos de enriquecimiento (`norma_*`, `obra_*`, `expediente_numero`)
    se resuelven en lectura contra Postgres; quedan None si no se pasan los
    repos o la entidad no aplica a este fragmento.
    """

    id: int | None
    norma_id: int | None
    obra_id: int | None
    texto: str
    referencia: str | None
    nivel_jerarquico: int | None
    norma_nombre: str | None = None
    norma_abreviatura: str | None = None
    obra_tipo: str | None = None
    obra_fecha_documento: str | None = None
    expediente_numero: str | None = None
    # norma | jurisprudencia | doctrina | obrado (None si no hay norma ni obra).
    categoria: str | None = None


@dataclass(frozen=True, slots=True)
class FuentesConsulta:
    fragmentos: tuple[FragmentoCita, ...]
    scores: tuple[float, ...]


async def _resolver_normas(crudos: list[dict], norma_repo) -> dict[int, object]:
    """Batch-fetch de normas citadas (corpus publico). {} si no hay repo."""
    if norma_repo is None:
        return {}
    result: dict[int, object] = {}
    for nid in {f["norma_id"] for f in crudos if f.get("norma_id")}:
        norma = await norma_repo.get_by_id(nid)
        if norma is not None:
            result[nid] = norma
    return result


async def _resolver_obras_y_expedientes(
    crudos: list[dict],
    obra_repo,
    expediente_repo,
    usuario_id: int,
) -> tuple[dict[int, object], dict[int, object]]:
    """Batch-fetch de obras (Regla 5) + expedientes de las visibles.

    Una obra privada de otro usuario no aparece en `obras` (obtener_por_ids la
    filtra), de modo que sus expedientes tampoco se resuelven -> no se filtra.
    """
    if obra_repo is None:
        return {}, {}
    obra_ids = {f["obra_id"] for f in crudos if f.get("obra_id")}
    if not obra_ids:
        return {}, {}
    obras = await obra_repo.obtener_por_ids(list(obra_ids), usuario_id=usuario_id)
    expedientes: dict[int, object] = {}
    if expediente_repo is not None:
        for eid in {o.expediente_id for o in obras.values() if o.expediente_id}:
            expediente = await expediente_repo.obtener(eid)
            if expediente is not None:
                expedientes[eid] = expediente
    return obras, expedientes


def _campos_enriquecidos(
    f: dict,
    normas: dict[int, object],
    obras: dict[int, object],
    expedientes: dict[int, object],
) -> dict[str, str | None]:
    """Valores legibles del fragmento. getattr sobre None -> None (sin ramas)."""
    norma = normas.get(f["norma_id"]) if f.get("norma_id") else None
    obra = obras.get(f["obra_id"]) if f.get("obra_id") else None
    expediente = expedientes.get(getattr(obra, "expediente_id", None))
    categoria = None
    if norma is not None:
        categoria = categoria_de_jerarquia(norma.jerarquia)
    elif obra is not None:
        categoria = categoria_de_obra(obra.tipo_documento)
    return {
        "categoria": categoria,
        "norma_nombre": getattr(norma, "nombre", None),
        "norma_abreviatura": getattr(norma, "abreviatura", None),
        "obra_tipo": getattr(obra, "tipo_documento", None),
        "obra_fecha_documento": getattr(obra, "fecha_documento", None),
        "expediente_numero": getattr(expediente, "numero_caso", None),
    }


def _construir_cita(
    f: dict,
    normas: dict[int, object],
    obras: dict[int, object],
    expedientes: dict[int, object],
) -> FragmentoCita:
    padre_ref = f.get("padre_ref_key")
    return FragmentoCita(
        id=f.get("id"),
        norma_id=f.get("norma_id"),
        obra_id=f.get("obra_id"),
        texto=f.get("texto", ""),
        referencia=etiqueta_legible(padre_ref) if padre_ref else None,
        nivel_jerarquico=f.get("nivel_jerarquico"),
        **_campos_enriquecidos(f, normas, obras, expedientes),
    )


async def ejecutar(
    repo,
    norma_repo=None,
    obra_repo=None,
    expediente_repo=None,
    *,
    historial_id: int,
    usuario_id: int,
) -> FuentesConsulta | None:
    """Extrae citas del JSONB de la entrada propia, enriquecidas con etiquetas.

    Enriquece en LECTURA (cero cambios al pipeline ni a la escritura del JSONB):
    resuelve `norma_id`/`obra_id`/`expediente_id` ya presentes en el snapshot a
    nombre de norma, tipo/fecha de documento y numero de caso, para que la UI
    diga QUE es cada fuente (no solo "OBRADO").

    Los repos son opcionales: si no se pasan, el resultado es identico al
    comportamiento anterior (sin enriquecer). Regla 4/5: `repo.obtener_por_id`
    acota al dueno y `obra_repo.obtener_por_ids` aplica visibilidad, de modo
    que una obra privada ajena simplemente no aparece (queda None).

    Returns:
        FuentesConsulta con fragmentos+scores, o None si la entrada no
        existe / es de otro usuario (Regla 4 encubierto).
    """
    historial = await repo.obtener_por_id(historial_id, usuario_id)
    if historial is None:
        return None

    fuentes = historial.fuentes_recuperadas or {}
    crudos = [f for f in (fuentes.get("fragmentos") or []) if isinstance(f, dict)]
    scores = tuple(float(s) for s in (fuentes.get("scores") or []))

    normas = await _resolver_normas(crudos, norma_repo)
    obras, expedientes = await _resolver_obras_y_expedientes(
        crudos, obra_repo, expediente_repo, usuario_id
    )
    citas = tuple(_construir_cita(f, normas, obras, expedientes) for f in crudos)
    return FuentesConsulta(fragmentos=citas, scores=scores)
