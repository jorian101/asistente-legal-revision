"""Interactor: IndexarNorma — Caso de uso principal de indexación de corpus.

Orquesta la extracción, segmentación, vectorización y persistencia de una norma
completa (PDF/DOCX) en PostgreSQL (metadatos) + Qdrant (vectores).

Flujo:
1. El router valida el upload (Regla 3) y guarda el temporal en disco
2. Extraer texto completo (RAW mode PyMuPDF)
3. Limpiar texto OCR (limpiar_texto_ocr)
4. Segmentar con SegmentadorNorma específico de la abreviatura
5. Persistir Norma + Fragmentos en PostgreSQL (transacción)
6. Generar embeddings (Ollama /api/embed) en lotes
7. Upsert en Qdrant (collection 'corpus_juridico')
8. Marcar Norma.indexado = True + indexado_por = usuario

Clean Architecture: Dominio puro, sin I/O directo. Puertos inyectados.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.application.ports.corpus_vectorial import CorpusRepoVectorial
from src.application.ports.embedder import Embedder
from src.application.ports.fragmento_repo import FragmentoRepo
from src.application.ports.norma_repo import NormaRepo
from src.application.ports.text_extractor import TextExtractor
from src.application.services.trabajos_indexado import TokenCancelacion
from src.domain.entities.fragmento import Fragmento
from src.domain.entities.norma import JerarquiaNorma, Norma, TipoNorma
from src.domain.services.categoria_fuente import categoria_de_jerarquia
from src.domain.services.segmentacion.base import (
    limpiar_texto_ocr,
    tipo_chunk_estructural,
)
from src.domain.services.segmentacion.registro import SegmentadorRegistry

# Mapeo abreviatura -> (tipo, jerarquia) segun esquema DB
TIPO_JERARQUIA_POR_ABREVIATURA: dict[str, tuple[TipoNorma, JerarquiaNorma]] = {
    "CPPM": ("codigo_militar", "militar"),
    "CPM": ("codigo_militar", "militar"),
    "LOJM": ("ley_organica", "militar"),
    "LOFA": ("ley_organica", "militar"),
    "CPE": ("constitucion", "suprema"),
    "CP": ("codigo_ordinario", "supletoria"),
    "CPP": ("codigo_ordinario", "supletoria"),
    # Alias histórico deprecado (mismo mapeo) hasta retirar el registro alias.
    "LEY1970_CP": ("codigo_ordinario", "supletoria"),
    "LEY1970_CPP": ("codigo_ordinario", "supletoria"),
}


def tipo_jerarquia_para(abreviatura: str) -> tuple[TipoNorma, JerarquiaNorma]:
    """Resuelve (tipo, jerarquia) con regla por prefijo para jurisprudencia.

    Cada sentencia tiene abreviatura propia (UNIQUE en norma.abreviatura):
    'SCP-0623-2024-S4' -> (scp_tcp, jurisprudencia),
    'CIDH-TC-PERU-2001' -> (sentencia_cidh, jurisprudencia).
    """
    if abreviatura in TIPO_JERARQUIA_POR_ABREVIATURA:
        return TIPO_JERARQUIA_POR_ABREVIATURA[abreviatura]
    if abreviatura.startswith("SCP-") or abreviatura.startswith("SC-"):
        # SC = Sentencia Constitucional (era pre-plurinacional del TCP);
        # mismo tipo que SCP. Ojo: chequear "SCP-" antes no hace falta
        # ("SCP-...".startswith("SC-") es False por la P), pero se deja
        # explícito por legibilidad.
        return ("scp_tcp", "jurisprudencia")
    if abreviatura.startswith("CIDH-"):
        return ("sentencia_cidh", "jurisprudencia")
    if abreviatura.startswith("LIB-"):
        return ("doctrina_libro", "doctrina")
    raise ValueError(
        f"Abreviatura sin categoría conocida: {abreviatura!r}. Usa el prefijo SCP-/SC- "
        "(jurisprudencia TCP), CIDH- (Corte IDH) o LIB- (doctrina), o registra la norma "
        "en TIPO_JERARQUIA_POR_ABREVIATURA."
    )


_TIPOS_JURISPRUDENCIA = ("scp_tcp", "sentencia_cidh")
_JERARQUIAS_NORMA = ("suprema", "militar", "supletoria")


def tipo_jerarquia_de_categoria(
    categoria: str, tipo: str | None, jerarquia: str | None
) -> tuple[TipoNorma, JerarquiaNorma]:
    """(tipo, jerarquia) de una fuente de usuario segun su categoria explicita."""
    if categoria == "doctrina":
        return ("doctrina_libro", "doctrina")
    if categoria == "jurisprudencia":
        if tipo not in (None, *_TIPOS_JURISPRUDENCIA):
            raise ValueError(f"Tipo de jurisprudencia invalido: {tipo!r}")
        return (tipo or "scp_tcp", "jurisprudencia")  # type: ignore[return-value]
    if categoria == "norma":
        jerarquia = jerarquia or "supletoria"
        if jerarquia not in _JERARQUIAS_NORMA:
            raise ValueError(
                f"Jerarquía invalida para una norma: {jerarquia!r} "
                f"(usa {', '.join(_JERARQUIAS_NORMA)})"
            )
        return (tipo or "reglamento", jerarquia)  # type: ignore[return-value]
    raise ValueError(f"Categoría de fuente desconocida: {categoria!r}")


@dataclass(slots=True)
class IndexarNormaRequest:
    """Entrada del caso de uso IndexarNorma."""

    abreviatura: str  # ej: 'CPPM', 'CPE', 'SCP-0623-2024-S4'
    ruta_pdf: Path
    version: str | None = None
    indexado_por: int | None = None  # usuario ID
    # Texto ya extraído (p.ej. raws .txt de jurisprudencia): si viene,
    # se salta el extractor (PDF/DOCX) y se segmenta directo.
    texto_directo: str | None = None
    # Fuentes que suben los usuarios (sin segmentador propio): la categoria
    # (norma | jurisprudencia | doctrina) elige el segmentador generico y, con
    # `tipo`/`jerarquia`, decide donde se guarda. Sin categoria, todo se deduce
    # de la abreviatura (corpus institucional).
    categoria: str | None = None
    nombre: str | None = None
    tipo: str | None = None
    jerarquia: str | None = None
    propietario_id: int | None = None
    estado_visibilidad: str = "global"  # privado | pendiente | global
    origen_obra_id: int | None = None  # obrado desde el que se promovio


@dataclass(slots=True)
class IndexarNormaResponse:
    """Salida del caso de uso IndexarNorma."""

    norma_id: int
    fragmentos_creados: int
    vectores_indexados: int
    qdrant_collection: str


class IndexarNorma:
    """Caso de uso: Indexar una norma completa en corpus juridico."""

    #: Colecciones por jerarquía (N1 leyes -> corpus_juridico).
    COLECCION_JURISPRUDENCIA = "jurisprudencia"
    COLECCION_DOCTRINA = "doctrina"

    def __init__(
        self,
        text_extractor: TextExtractor,
        embedder: Embedder,
        vector_repo: CorpusRepoVectorial,
        norma_repo: NormaRepo,
        fragmento_repo: FragmentoRepo,
        vector_repo_jurisprudencia: CorpusRepoVectorial | None = None,
        vector_repo_doctrina: CorpusRepoVectorial | None = None,
    ) -> None:
        self._extractor = text_extractor
        self._embedder = embedder
        self._vector_repo = vector_repo
        self._vector_repo_jurisprudencia = vector_repo_jurisprudencia
        self._vector_repo_doctrina = vector_repo_doctrina
        self._norma_repo = norma_repo
        self._fragmento_repo = fragmento_repo

    @staticmethod
    def _organo_para(abreviatura: str) -> str:
        """Órgano/autor por prefijo de abreviatura N2/N3."""
        if abreviatura.startswith("SCP-"):
            return "TCP"
        if abreviatura.startswith("CIDH-"):
            return "Corte IDH"
        return ""

    def _sparse_vector(
        self, texto: str, vector_repo: CorpusRepoVectorial | None = None
    ) -> dict | None:
        """Vector disperso BM25 del fragmento (D-S2C-02, mismo patrón que obras).

        Solo se incluye si el vector repo soporta el named vector 'text-sparse'
        (búsqueda híbrida real). Si no, None (el upsert no lo usa) y la norma
        queda solo densa, como antes.
        """
        repo = vector_repo if vector_repo is not None else self._vector_repo
        has_sparse = getattr(repo, "_collection_has_sparse", None)
        if has_sparse is None or not has_sparse():
            return None
        from src.application.services.hybrid_searcher import compute_bm25_sparse

        sp = compute_bm25_sparse(texto)
        return {
            "indices": list(sp.indices),
            "values": list(sp.values),
        }

    async def _enlazar_padres(
        self,
        estructurales: list[Fragmento],
        indexables: list[Fragmento],
    ) -> None:
        """Enlaza padre_ref_id por clave semantica (D-S5K-01, Regla 6).

        Convencion de claves: los fragmentos indexables guardan en
        `padre_ref_key` SU propia clave semantica (maestro 'X_MASTER',
        numeral 'X_MASTER_1'); los nodos estructurales guardan la del
        PADRE y la propia en `metadatos['clave_estructural']`.
        maestro -> estructura es el nivel 2 (follow-up D-S5K-02): no se
        enlaza aqui.
        """
        clave_a_id: dict[str, int] = {}
        for fila in [*estructurales, *indexables]:
            if fila.id is None:
                continue
            if fila.qdrant_point_id == "" and fila.metadatos:
                propia = fila.metadatos.get("clave_estructural")
                if isinstance(propia, str):
                    clave_a_id[propia] = fila.id
            elif fila.padre_ref_key:
                clave_a_id.setdefault(fila.padre_ref_key, fila.id)

        pares: list[tuple[int, int]] = []
        for fila in [*estructurales, *indexables]:
            if fila.id is None or not fila.padre_ref_key:
                continue
            if fila.qdrant_point_id == "":
                padre = clave_a_id.get(fila.padre_ref_key)
            elif fila.padre_ref_key.endswith("_MASTER"):
                continue
            else:
                padre = clave_a_id.get(fila.padre_ref_key.rsplit("_", 1)[0])
            if padre is not None and padre != fila.id:
                pares.append((fila.id, padre))
        if pares:
            await self._fragmento_repo.asignar_padres_por_ids(pares)

    async def _limpiar_norma_cancelada(self, norma_id: int) -> None:
        """Deshace una indexacion cancelada: borra la norma y sus fragmentos.

        La norma la creo este trabajo (`save` es un INSERT), asi que darla de
        baja no toca nada que existiera antes.
        """
        await self._fragmento_repo.delete_by_norma(norma_id)
        await self._norma_repo.eliminar_soft(norma_id)

    async def ejecutar(
        self,
        request: IndexarNormaRequest,
        *,
        token: TokenCancelacion | None = None,
    ) -> IndexarNormaResponse:
        """Ejecuta la indexación completa de una norma.

        `token` permite cancelar el trabajo: se verifica entre fases y, si
        cancelan despues de escribir algo, se deshace antes de salir.
        """
        token = token or TokenCancelacion()
        # 1. Extraer texto completo (RAW mode) o usar texto directo (.txt).
        if request.texto_directo is not None:
            texto_raw = request.texto_directo
        else:
            result = await self._extractor.extract(request.ruta_pdf)
            texto_raw = result.full_text

        token.verificar()  # cancelado durante la extraccion

        # 2. Obtener segmentador especifico (antes de limpiar: los de
        # limpieza propia necesitan el texto crudo con marcadores).
        try:
            segmentador = (
                SegmentadorRegistry.obtener(request.abreviatura, request.categoria)
                if request.categoria
                else SegmentadorRegistry.obtener(request.abreviatura)
            )
        except KeyError as exc:
            raise ValueError(
                f"No hay segmentador para abreviatura '{request.abreviatura}'. "
                f"Disponibles: {SegmentadorRegistry.disponibles()}"
            ) from exc

        # 3. Limpiar artefactos OCR (salvo segmentador con limpieza propia).
        if getattr(segmentador, "LIMPIEZA_PROPIA", False):
            texto_limpio = texto_raw
        else:
            texto_limpio = limpiar_texto_ocr(texto_raw)

        # 4. Segmentar
        arbol = segmentador.segmentar(texto_limpio)

        # Nada escrito todavia: cancelar aca no deja residuos.
        token.verificar()

        # 5. Persistir Norma en PostgreSQL (obtener ID)
        tipo, jerarquia = (
            tipo_jerarquia_de_categoria(request.categoria, request.tipo, request.jerarquia)
            if request.categoria
            else tipo_jerarquia_para(request.abreviatura)
        )
        es_jurisprudencia = jerarquia == "jurisprudencia"
        es_doctrina = jerarquia == "doctrina"
        repo_destino = {
            "jurisprudencia": self._vector_repo_jurisprudencia,
            "doctrina": self._vector_repo_doctrina,
        }.get(jerarquia)
        if repo_destino is None:
            vector_repo = self._vector_repo
            coleccion_destino = "corpus_juridico"
        else:
            vector_repo = repo_destino
            coleccion_destino = (
                self.COLECCION_JURISPRUDENCIA if es_jurisprudencia else self.COLECCION_DOCTRINA
            )
        norma = Norma(
            id=None,
            nombre=(
                request.nombre
                or getattr(segmentador, "NOMBRE", "")
                or segmentador.__class__.__name__.replace("Segmentador", "").upper()
            ),
            abreviatura=request.abreviatura,
            tipo=tipo,
            jerarquia=jerarquia,
            version=request.version,
            ruta_archivo=str(request.ruta_pdf),
            indexado=False,
            indexado_por=request.indexado_por,
            created_at=datetime.now(UTC),
            propietario_id=request.propietario_id,
            estado_visibilidad=request.estado_visibilidad,
            origen_obra_id=request.origen_obra_id,
        )
        norma_guardada = await self._norma_repo.save(norma)
        norma_id = norma_guardada.id
        # De aca en adelante hay escritura: si cancelan, borramos la norma
        # (la crea este trabajo: `save` es un INSERT) y sus fragmentos.
        token.al_cancelar(lambda: self._limpiar_norma_cancelada(norma_id))

        # 5b. Nodos estructurales (D-S2C-06 split): existen en PG como
        # contexto no indexable (qdrant_point_id vacío). Sin wiring de
        # padre_ref_id — va en el ciclo s5.
        padre_de: dict[str, str] = {}
        for clave_nodo, nodo in arbol.nodos.items():
            for hijo in nodo.hijos:
                padre_de.setdefault(hijo, clave_nodo)
        estructurales = [
            Fragmento(
                id=None,
                norma_id=norma_id,
                obra_id=None,
                expediente_id=None,
                qdrant_point_id="",
                texto=nodo.titulo,
                padre_ref_id=None,
                padre_ref_key=padre_de.get(clave_nodo),
                nivel_jerarquico=nodo.nivel,
                metadatos={
                    **nodo.metadatos,
                    "clave_estructural": clave_nodo,
                },
                tipo_chunk=tipo_chunk_estructural(nodo.metadatos.get("tipo_estructura", "")),
            )
            for clave_nodo, nodo in arbol.nodos.items()
        ]

        # 6. Persistir Fragmentos en PostgreSQL + generar embeddings
        fragmentos_guardados = []
        textos_para_embedding = []
        qdrant_points = []

        for pos, frag in enumerate(arbol.fragmentos):
            if not frag.es_indexable:
                continue
            if pos % 200 == 0:
                token.verificar()  # cancelado armando fragmentos

            qdrant_id = str(uuid.uuid4())
            fragmento = Fragmento(
                id=None,
                norma_id=norma_id,
                obra_id=None,
                expediente_id=None,
                qdrant_point_id=qdrant_id,
                texto=frag.texto,
                padre_ref_id=None,  # se resuelve después si hay padre
                padre_ref_key=frag.padre_ref_key,
                nivel_jerarquico=frag.nivel_jerarquico,
                metadatos={**frag.metadatos, "tipo_chunk": frag.tipo_chunk},
                tipo_chunk=frag.tipo_chunk,
            )
            fragmentos_guardados.append(fragmento)
            textos_para_embedding.append(frag.texto)

            # Preparar punto Qdrant (payload N2/N3 según jerarquía).
            tipo_fuente = categoria_de_jerarquia(jerarquia)
            payload: dict[str, object] = {
                "tipo_fuente": tipo_fuente,
                "norma_id": norma_id,
                "abreviatura": request.abreviatura,
                "numero_articulo": frag.metadatos.get("numero_articulo"),
                "texto": frag.texto,
                "tipo_chunk": frag.tipo_chunk,
                "nivel_jerarquico": frag.nivel_jerarquico,
                "padre_ref_key": frag.padre_ref_key,
                "metadatos": frag.metadatos,
            }
            if request.estado_visibilidad != "global":
                # Fuente privada o pendiente: el filtro de privacidad la limita al dueno.
                payload["visibilidad"] = request.estado_visibilidad
                payload["propietario_id"] = request.propietario_id
            if es_jurisprudencia:
                payload.update(
                    {
                        "numero_sentencia": frag.metadatos.get(
                            "numero_sentencia", request.abreviatura
                        ),
                        "organo": self._organo_para(request.abreviatura),
                        "bloque": frag.metadatos.get("bloque"),
                        "nivel_autoridad": "vinculante",
                    }
                )
            if es_doctrina:
                payload.update(
                    {
                        "autor": frag.metadatos.get("autor", ""),
                        "obra": frag.metadatos.get("obra", request.abreviatura),
                        "pagina": frag.metadatos.get("pagina"),
                        "bloque": "doctrina",
                        "nivel_autoridad": "orientativa",
                    }
                )
            qdrant_points.append(
                {
                    "id": qdrant_id,
                    "vector": None,  # se llena después
                    "vector_sparse": self._sparse_vector(frag.texto, vector_repo),
                    "payload": payload,
                }
            )

        # Guardar fragmentos en PostgreSQL (batch): estructurales (contexto,
        # no indexable) + indexables. Solo los indexables van a embeddings.
        token.verificar()
        await self._fragmento_repo.save_many([*estructurales, *fragmentos_guardados])

        # 6.5 D-S5K-01: enlazar padre_ref_id (Regla 6 asciende por PG).
        # numeral/parrafo -> maestro; estructural -> su padre. maestro->
        # estructura es el nivel 2 (follow-up D-S5K-02): aqui no se enlacea.
        await self._enlazar_padres(estructurales, fragmentos_guardados)

        # 7. Generar embeddings (un solo await opaco: no se puede cortar en
        # medio de forma cooperativa, por eso se chequea justo antes).
        token.verificar()
        embeddings = await self._embedder.embed(textos_para_embedding)

        # 8. Rellenar vectores y upsert en Qdrant
        for i, emb in enumerate(embeddings):
            qdrant_points[i]["vector"] = emb

        # Ultimo punto de control: despues del upsert el trabajo ya escribe
        # en Qdrant, asi que llega hasta el final.
        token.verificar()
        await vector_repo.upsert_corpus(qdrant_points)

        # 9. Marcar Norma como indexada
        await self._norma_repo.marcar_indexada(norma_id, request.indexado_por)

        return IndexarNormaResponse(
            norma_id=norma_id,
            fragmentos_creados=len(fragmentos_guardados),
            vectores_indexados=len(qdrant_points),
            qdrant_collection=coleccion_destino,
        )
