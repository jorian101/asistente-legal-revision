"""Adapter: PlantillaMarkdownAdapter — Resuelve plantillas .md desde docs/plantillas/.

Implementa el puerto application.ports.resolvedor_plantilla.ResolvedorPlantilla.

Lee plantillas como archivos Markdown, resuelve variables del expediente
via ExpedienteRepo, y deja slots {{contexto_expandido}} y
{{consulta_usuario}} para que el use case GenerarBorrador los llene.

Cache: lru_cache en lectura de archivo (las plantillas no cambian en
runtime). NO Jinja2 — solo str.replace() para {{variables}} simples y
condicionales {{CONDICIONAL_*}} con lógica if/else.

Fase 3 (G1): el metodo resolver() acepta un kwarg opcional `vicios`
(ResultadoVicios, ver domain.value_objects.resultado_vicios) generado por
AnalizadorVicios (domain.services.analizador_vicios). Cuando el condicional
{{CONDICIONAL_LOGICA_SANEAMIENTO: SI_EXISTE_VICIO_DE_NULIDAD}} aparece,
el adapter inyecta los vicios detectados en vez del placeholder
hardcodeado "[No se detectó vicio...]". Si vicios=None o
vicios.hay_vicios=False, se conserva el fallback conservador.

U6 (alineación vocal, "fácil de modificar" — ver docs/plantillas/README.md):
- Variable con fallback inline: una plantilla puede escribir
  {{NOMBRE_VAR|texto de fallback}} para una variable SIN mapear en
  `vars_map`, sin tocar este archivo. Se resuelve siempre al texto de
  fallback (no hay fuente de datos real para ella, igual que
  RESOLUCION_RECURRIDA o DICTAMEN_NUMERO hoy en `vars_map`) — nunca es
  "vivo": no reintroduce {{, "}}" ni "|" del propio fallback.
- Aviso de tokens sin resolver: si tras resolver variables, fallbacks
  inline y condicionales queda algún {{...}} que no sea uno de los slots
  que llena GenerarBorrador después (contexto_expandido,
  sugerencia_argumentacion, criterio_vocal, consulta_usuario), se loguea
  un warning — antes viajaba literal al prompt en silencio.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from src.application.ports.expediente_repo import ExpedienteRepo
from src.application.services.constructor_mensajes import neutralizar_tokens_plantilla
from src.domain.exceptions import PlantillaNoImplementadaError
from src.domain.value_objects.contexto_recuperado import TipoRespuesta

if TYPE_CHECKING:
    from src.domain.entities.expediente import Expediente
    from src.domain.value_objects.resultado_vicios import ResultadoVicios

logger = logging.getLogger(__name__)

# U6(a): {{NOMBRE_VAR|texto de fallback}} — variable nueva sin tocar Python.
_RE_VAR_CON_FALLBACK_INLINE = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\|([^{}]*)\}\}")

# U6(b): slots que GenerarBorrador llena después de resolver() — no son un
# token huérfano, aunque queden como {{...}} al salir de este adapter.
_SLOTS_DIFERIDOS = frozenset(
    {
        "{{contexto_expandido}}",
        "{{sugerencia_argumentacion}}",
        "{{criterio_vocal}}",
        "{{consulta_usuario}}",
    }
)
_RE_TOKEN_LLAVES = re.compile(r"\{\{[^{}]*\}\}")


def _avisar_tokens_sin_resolver(prompt: str, tipo_respuesta: str) -> None:
    """U6(b): loguea las {{VAR}} que quedaron sin resolver (antes, silencio)."""
    huerfanos = sorted({m for m in _RE_TOKEN_LLAVES.findall(prompt) if m not in _SLOTS_DIFERIDOS})
    if huerfanos:
        logger.warning(
            "PlantillaMarkdownAdapter: '%s' dejó variables sin resolver "
            "(viajan literales al prompt del LLM): %s",
            tipo_respuesta,
            huerfanos,
        )


def _render_vicios_nulidad(vicios: ResultadoVicios | None) -> str:
    """Renderiza el condicional SI_EXISTE_VICIO_DE_NULIDAD (Fase 3 G1).

    - Sin vicios (None o vacio): fallback conservador actual, para mantener
      el comportamiento previo en tests y callers que no cablean vicios.
    - Con vicios: lista textual de los vicios detectados con tipo, foja
      (si se pudo extraer) y norma vulnerada, para que el LLM los considere
      al redactar el Auto de Vista.

    ponytail: string formatting simple, sin Jinja. El LLM recibira este
    bloque como parte del prompt y decidira como integrarlo al texto final.
    """
    if vicios is None or not vicios.hay_vicios:
        return (
            "Que, del análisis automático efectuado sobre el contexto recuperado "
            "no se advierten vicios de nulidad que ameriten declaratoria de oficio."
        )

    lineas: list[str] = [
        "Que, se advierten los siguientes vicios procesales detectados sobre el "
        "contexto recuperado:",
    ]
    for i, v in enumerate(vicios.vicios, start=1):
        foja = f", foja {v.foja_referida}" if v.foja_referida else ""
        lineas.append(
            f"  {i}. Vicio de {v.tipo} (norma sugerida: {v.norma_vulnerada}{foja}). "
            f"Contexto: {v.snippet}"
        )
    return neutralizar_tokens_plantilla("\n".join(lineas))


# F1: extraccion de numero y fecha desde sentencia_origen. Formatos de
# origen (seed y formulario): 'SENTENCIA Nº 24/2025 (15/10/2025)
# ABSOLUTORIA' y 'RESOLUCION Nº 17/2025 (12/11/2025) Auto Interlocutorio'.
_RE_NUMERO_SENTENCIA = re.compile(r"\b(\d{1,4}/\d{4})\b")
_RE_FECHA_SENTENCIA = re.compile(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b")


def _extraer_numero_sentencia(sentencia_origen: str | None) -> str:
    """Extrae 'N/AAAA' de sentencia_origen (ej. -> '24/2025').

    Fallback conservador: texto completo (comportamiento anterior) si no
    hay match — nunca inventa datos.
    """
    if not sentencia_origen:
        return ""
    m = _RE_NUMERO_SENTENCIA.search(sentencia_origen)
    return m.group(1) if m else sentencia_origen


def _extraer_fecha_sentencia(sentencia_origen: str | None) -> str:
    """Extrae la fecha dd/mm/aaaa (o con guiones) de sentencia_origen.

    Si no hay match devuelve 'FECHA_NO_DISPONIBLE' (placeholder explicito,
    preferible a que el LLM invente una fecha en el documento legal).
    """
    if not sentencia_origen:
        return "FECHA_NO_DISPONIBLE"
    m = _RE_FECHA_SENTENCIA.search(sentencia_origen)
    return m.group(1) if m else "FECHA_NO_DISPONIBLE"


# U5 (alineación vocal): rótulos de los firmantes de la Sala. Único lugar
# para actualizar cuando rote su composición. Los nombres reales se cargan
# por configuración, no se versionan en el código.
_FIRMAS_SALA_ACTUAL: dict[str, str] = {
    "vocal_presidente": "<NOMBRE DEL PRESIDENTE>",
    "vocal_relator": "<NOMBRE DEL VOCAL RELATOR>",
    "vocal_propietario": "<NOMBRE DEL VOCAL PROPIETARIO>",
    "secretario_camara": "<NOMBRE DEL SECRETARIO DE CÁMARA>",
    # U-D: mismo criterio para el Auditor que firma los dictámenes.
    "auditor": "<NOMBRE DEL AUDITOR>",
}

# U-D: rótulo de la resolución recurrida/consultada según la vía procesal —
# "SENTENCIA" en consulta y apelación restringida (se apela/consulta una
# sentencia); "Resolución Incidental" en apelación incidental (se apela un
# auto interlocutorio), mismo criterio que ya usa proyecto_auto_vista_apelacion.md.
_ETIQUETA_RESOLUCION_PRINCIPAL: dict[str, str] = {
    "consulta": "SENTENCIA",
    "apelacion_restringida": "SENTENCIA",
    "apelacion_incidental": "Resolución Incidental",
}

# U-D: nombre legible de la vía procesal para prosa (dictámenes/relación de
# obrados) — TipoProceso del dominio es snake_case, no para citar tal cual.
_VIA_PROCESAL_LEGIBLE: dict[str, str] = {
    "consulta": "Consulta",
    "apelacion_incidental": "Apelación Incidental",
    "apelacion_restringida": "Apelación Restringida",
}


class PlantillaMarkdownAdapter:
    """Implementa ResolvedorPlantilla leyendo .md desde docs/plantillas/."""

    def __init__(
        self,
        plantillas_dir: Path,
        expediente_repo: ExpedienteRepo,
        obra_repo=None,
    ) -> None:
        self._dir = plantillas_dir
        self._expediente_repo = expediente_repo
        # Opcional: si se inyecta, las variables FOJA_* se resuelven desde
        # las obras del expediente (por tipo_documento) en vez del fallback
        # conservador "FOJA_NO_DISPONIBLE".
        self._obra_repo = obra_repo

    @lru_cache(maxsize=8)  # noqa: B019
    def _leer_plantilla(self, nombre: str) -> str:
        """Lee plantilla desde disco con cache LRU.

        Args:
            nombre: Nombre base sin extension (ej. 'consulta_simple',
            'proyecto_auto_vista_consulta', 'proyecto_auto_vista_apelacion').

        Returns:
            Contenido crudo del archivo .md con variables {{...}} intactas.

        Raises:
            PlantillaNoImplementadaError: Si el archivo no existe.
        """
        path = self._dir / f"{nombre}.md"
        if not path.exists():
            raise PlantillaNoImplementadaError(
                f"Plantilla '{nombre}' no implementada. Archivo esperado: {path}"
            )
        return path.read_text(encoding="utf-8")

    async def resolver(
        self,
        tipo_respuesta: TipoRespuesta,
        expediente_id: int | None,
        *,
        vicios: ResultadoVicios | None = None,
        usuario_id: int | None = None,
    ) -> str:
        """Resuelve la plantilla segun el tipo de respuesta.

        Args:
            tipo_respuesta: Tipo de respuesta (determina que plantilla usar).
            expediente_id: ID del expediente (para resolver variables).
                None si es consulta_simple.
            vicios: ResultadoVicios de AnalizadorVicios sobre los fragmentos
                del contexto (Fase 3 G1). None si el caller no corre
                analisis de vicios. Se inyecta en el condicional
                {{CONDICIONAL_LOGICA_SANEAMIENTO: SI_EXISTE_VICIO_DE_NULIDAD}}
                cuando hay vicios reales; si no hay, se conserva el
                fallback conservador.

        Returns:
            String del prompt con variables de expediente resueltas.
            Los slots {{contexto_expandido}} y {{consulta_usuario}} quedan
            sin resolver para que el caller (GenerarBorrador) las llene.

        Raises:
            PlantillaNoImplementadaError: Si el tipo no tiene plantilla.
            ValueError: Si tipo_respuesta requiere expediente y no se provee.
        """
        # Mapeo TipoRespuesta -> archivo plantilla (sin .md)
        mapping: dict[TipoRespuesta, str] = {
            "consulta_simple": "consulta_simple",
            "auto_vista_consulta": "proyecto_auto_vista_consulta",
            "auto_vista_apelacion_incidental": "proyecto_auto_vista_apelacion",
            "dictamen_radicatoria_consulta": "dictamen_radicatoria_consulta",
            "dictamen_radicatoria_apelacion": "dictamen_radicatoria_apelacion",
            # Plan D (D3): plantillas nuevas, fuera del flujo de borrador.
            "dictamen_fondo": "dictamen_fondo",
            "relacion_obrados": "relacion_obrados",
        }

        nombre = mapping.get(tipo_respuesta)
        if nombre is None:
            raise PlantillaNoImplementadaError(f"Tipo '{tipo_respuesta}' sin plantilla mapeada")

        plantilla = self._leer_plantilla(nombre)

        # consultation_simple no requiere expediente
        if tipo_respuesta != "consulta_simple":
            if expediente_id is None:
                raise ValueError(f"Tipo '{tipo_respuesta}' requiere expediente_id")
            plantilla = await self._resolver_variables_expediente(
                plantilla,
                expediente_id,
                vicios=vicios,
                usuario_id=usuario_id,
            )

        _avisar_tokens_sin_resolver(plantilla, tipo_respuesta)
        return plantilla

    async def _resolver_variables_expediente(
        self,
        plantilla: str,
        expediente_id: int,
        *,
        vicios: ResultadoVicios | None = None,
        usuario_id: int | None = None,
    ) -> str:
        """Resuelve variables {{...}} del expediente en la plantilla.

        Soporta:
        - Variables simples: {{VAR_NOMBRE}} -> valor
        - Condicionales: {{CONDICIONAL_*: SI_...}} -> bloque correspondiente
        - FOJA_*: si hay obra_repo inyectado, se resuelven desde las obras
          del expediente (tipo_documento -> rango de fojas). Fallback
          conservador "FOJA_NO_DISPONIBLE" si la obra no tiene fojas.
        """

        expediente = await self._expediente_repo.obtener(expediente_id)
        if expediente is None:
            raise ValueError(f"Expediente {expediente_id} no encontrado")

        fojas = await self._fojas_por_tipo(expediente_id, usuario_id)
        if fojas is None:
            fojas = {}

        # Mapping de variables disponibles
        vars_map = {
            "EXPEDIENTE_ID": str(expediente.id),
            "NUMERO_CASO": expediente.numero_caso,
            "TIPO_PROCESO": expediente.tipo_proceso,
            "TRIBUNAL_ORIGEN": expediente.tribunal_origen or "",
            "PROCESADO_GRADO_Y_NOMBRE": (
                f"{expediente.procesado_grado or ''} {expediente.procesado_nombre or ''}".strip()
            ),
            "DELITO_CONCRETO": expediente.delito or "",
            # F1: extraer 'N/AAAA' de sentencia_origen (ej. 'SENTENCIA Nº
            # 24/2025 (15/10/2025) ABSOLUTORIA' -> '24/2025'). Antes se
            # inyectaba el texto completo y la plantilla leia
            # 'N° SENTENCIA Nº 24/2025 (...) ABSOLUTORIA'. Fallback: texto
            # completo (comportamiento anterior).
            "SENTENCIA_NUMERO": _extraer_numero_sentencia(expediente.sentencia_origen),
            "SENTIDO_SENTENCIA_INFERIOR": "CONDENATORIA"
            if expediente.sentencia_origen and "condena" in expediente.sentencia_origen.lower()
            else "ABSOLUTORIA",
            # F1: fecha entre parentesis de sentencia_origen. Antes era
            # 'FECHA_NO_DISPONIBLE' hardcodeado y el LLM inventaba la fecha.
            "SENTENCIA_FECHA": _extraer_fecha_sentencia(expediente.sentencia_origen),
            "TRIBUNAL_PERMANENTE_ORIGEN": expediente.tribunal_origen or "",
            "FOJA_INICIO": fojas.get("relacion_obrados", "FOJA_NO_DISPONIBLE"),
            "FECHA_SIM": "FECHA_NO_DISPONIBLE",
            "FOJA_ACUSACION": fojas.get("pliego_cargo", "FOJA_NO_DISPONIBLE"),
            "FECHA_ACUSACION": "FECHA_NO_DISPONIBLE",
            "FOJA_SENTENCIA": fojas.get("sentencia", "FOJA_NO_DISPONIBLE"),
            "FOJA_RADICATORIA": fojas.get("radicatoria", "FOJA_NO_DISPONIBLE"),
            "FOJA_AUDITORIA": fojas.get("dictamen_fondo", "FOJA_NO_DISPONIBLE"),
            "DICTAMEN_NUMERO": "DICTAMEN_NO_DISPONIBLE",
            "DICTAMEN_FECHA": "FECHA_NO_DISPONIBLE",
            "CONCLUSION_LITERAL_AUDITOR": "CONCLUSION_NO_DISPONIBLE",
            "FOJA_PRUEBA": fojas.get("prueba", "FOJA_NO_DISPONIBLE"),
            "FOJA_PRUEBA_FINAL": fojas.get("prueba_final", "FOJA_NO_DISPONIBLE"),
            "SI_O_NO": "SI",
            "FOJA_DEL_VICIO": "FOJA_NO_DISPONIBLE",
            "NUEVA_SITUACION_JURIDICA": "SITUACION_NO_DISPONIBLE",
            "FIRMA_VOCAL_PRESIDENTE": _FIRMAS_SALA_ACTUAL["vocal_presidente"],
            "FIRMA_VOCAL_RELATOR": _FIRMAS_SALA_ACTUAL["vocal_relator"],
            "FECHA_ACTUAL": self._fecha_actual_bolivia(),
            "AUTO_DE_VISTA_CORRELATIVO": "CORRELATIVO_NO_DISPONIBLE",
            "RECURRENTE": (
                f"{expediente.procesado_grado or ''} {expediente.procesado_nombre or ''}".strip()
            ),
            "DELITOS": expediente.delito or "",
            "RESOLUCION_RECURRIDA": "RESOLUCION_NO_DISPONIBLE",
            # Apelación incidental: el dominio no modela acumulación de
            # expedientes (Expediente tiene un solo numero_caso), asi que
            # este campo siempre queda en el fallback — nunca se inventa
            # un segundo numero de expediente.
            "NUMERO_CASO_SECUNDARIO": "EXPEDIENTE_SECUNDARIO_NO_DISPONIBLE",
            "FOJA_MEMORIAL_APELACION": fojas.get("memorial_apelacion", "FOJA_NO_DISPONIBLE"),
            "ANIO_PRIMERA_ACTUACION": "ANIO_NO_DISPONIBLE",
            "FIRMA_VOCAL_PROPIETARIO": _FIRMAS_SALA_ACTUAL["vocal_propietario"],
            "FIRMA_SECRETARIO_CAMARA": _FIRMAS_SALA_ACTUAL["secretario_camara"],
            # U1 (alineación vocal): el año del auto es un dato cierto (hoy),
            # separado del correlativo (que sí depende de la Secretaría y no
            # tiene fuente en el dominio, por eso sigue en fallback).
            "ANIO": str(self._fecha_actual_bolivia_hoy().year),
            # Vocal Relator del encabezado: misma persona que
            # FIRMA_VOCAL_RELATOR (U5) — mismo default, un solo lugar.
            "VOCAL_RELATOR": _FIRMAS_SALA_ACTUAL["vocal_relator"],
            # U-D (dictámenes): firma del Auditor, mismo criterio que las
            # firmas de los autos (U5) — nombre real, un solo lugar.
            "FIRMA_AUDITOR": _FIRMAS_SALA_ACTUAL["auditor"],
            # U-D: rótulo + número de la resolución recurrida/consultada
            # (ej. "SENTENCIA N° 24/2025" o "Resolución Incidental N°
            # 17/2025"), calculados a partir de datos ya extraídos — no es
            # un dato nuevo, es la etiqueta correcta de un dato existente.
            "RESOLUCION_PRINCIPAL": (
                f"{_ETIQUETA_RESOLUCION_PRINCIPAL.get(expediente.tipo_proceso, 'RESOLUCIÓN')} "
                f"N° {_extraer_numero_sentencia(expediente.sentencia_origen)}"
            ),
            # U-D: vía procesal en prosa (relación de obrados, dictámenes).
            "VIA_PROCESAL": _VIA_PROCESAL_LEGIBLE.get(
                expediente.tipo_proceso, expediente.tipo_proceso
            ),
        }

        # Resolver variables simples (valores neutralizados: metadata editable
        # por usuarios no debe crear slots ni marcadores vivos en el prompt)
        result = plantilla
        for key, value in vars_map.items():
            result = result.replace(f"{{{{{key}}}}}", neutralizar_tokens_plantilla(value))

        # U6(a): {{VAR_SIN_MAPEAR|fallback}} — variable nueva declarada en el
        # propio markdown, sin tocar vars_map. Siempre resuelve al fallback
        # (no hay fuente de dato real para ella).
        result = _RE_VAR_CON_FALLBACK_INLINE.sub(
            lambda m: neutralizar_tokens_plantilla(m.group(2)), result
        )

        # Resolver condicionales {{CONDICIONAL_*: SI_...}}
        result = await self._resolver_condicionales(result, expediente, vicios=vicios)

        return result

    async def _fojas_por_tipo(
        self,
        expediente_id: int,
        usuario_id: int | None,
    ) -> dict[str, str] | None:
        """Mapea tipo_documento -> rango de fojas de las obras del expediente.

        Usa ObraRepo.listar_por_expediente (Regla 5: solo obras del usuario
        o publicadas). Devuelve None si no hay obra_repo inyectado (fallback
        conservador). El rango se formatea como "inicio-fin" o "inicio"
        cuando solo hay un extremo.
        """
        if self._obra_repo is None or usuario_id is None:
            return None
        try:
            obras = await self._obra_repo.listar_por_expediente(expediente_id, usuario_id)
        except Exception:  # noqa: BLE001 — no bloquear la generacion de plantilla
            return None

        fojas: dict[str, str] = {}
        for obra in obras:
            inicio = obra.fojas_inicio
            fin = obra.fojas_fin
            if inicio is None and fin is None:
                continue
            if inicio is not None and fin is not None:
                valor = f"{inicio}-{fin}"
            elif inicio is not None:
                valor = str(inicio)
            else:
                valor = str(fin)
            tipo = obra.tipo_documento
            fojas.setdefault(tipo, valor)
        return fojas

    async def _resolver_condicionales(
        self,
        plantilla: str,
        expediente: Expediente,
        *,
        vicios: ResultadoVicios | None = None,
    ) -> str:
        """Resuelve condicionales {{CONDICIONAL_*: SI_...}} con lógica simple.

        Args:
            vicios: ResultadoVicios de AnalizadorVicios (Fase 3 G1). Si None
                o vacio, el condicional SI_EXISTE_VICIO_DE_NULIDAD conserva
                el fallback conservador "[No se detectó vicio...]".
                Si hay vicios, se renderiza un listado textual de los
                vicios detectados para que el LLM los considere al redactar.
        """

        # CONDICIONAL_LOGICA_SANEAMIENTO
        # Si hay sentencia_origen -> asumimos procedimiento correcto (fallback simple)
        if "CONDICIONAL_LOGICA_SANEAMIENTO: SI_EL_PROCEDIMIENTO_ES_CORRECTO" in plantilla:
            plantilla = plantilla.replace(
                "{{CONDICIONAL_LOGICA_SANEAMIENTO: SI_EL_PROCEDIMIENTO_ES_CORRECTO}}",
                "Que, no se advierten defectos procedimentales ni vulneraciones a las "
                "formas esenciales del proceso que ameriten una declaración de nulidad "
                "de oficio, estando expedita la vía para resolver el fondo.",
            )
        if "CONDICIONAL_LOGICA_SANEAMIENTO: SI_EXISTE_VICIO_DE_NULIDAD" in plantilla:
            plantilla = plantilla.replace(
                "{{CONDICIONAL_LOGICA_SANEAMIENTO: SI_EXISTE_VICIO_DE_NULIDAD}}",
                _render_vicios_nulidad(vicios),
            )

        # CONDICIONAL_LOGICA_VIAS (fundamento, no resolucion: la remision a la
        # via disciplinaria se ventila ante la instancia competente segun la ley
        # ya establecida — Art. 182 CPPM, LOFA, Reglamento N° 23 — sin que el
        # Auto de Vista lo ordene en su parte resolutiva).
        if 'CONDICIONAL_LOGICA_VIAS: SI_SENTIDO_SENTENCIA_INFERIOR == "ABSOLUTORIA"' in plantilla:
            plantilla = plantilla.replace(
                '{{CONDICIONAL_LOGICA_VIAS: SI_SENTIDO_SENTENCIA_INFERIOR == "ABSOLUTORIA"}}',
                "Que, si bien del análisis fáctico se concluye que los elementos "
                "probatorios acumulados no alcanzan el estándar de certeza punitiva "
                "para mantener una condena en la esfera penal militar, la absolución "
                "penal no implica impunidad administrativa; la eventual falta contra "
                "el servicio se ventila ante la instancia disciplinaria competente "
                "conforme al Art. 182 del CPPM, la LOFA y el Reglamento de Faltas "
                "N° 23, en aplicación de la doctrina de la independencia de vías y "
                "el principio de non bis in ídem relativo.",
            )
        if 'CONDICIONAL_LOGICA_VIAS: SI_SENTIDO_SENTENCIA_INFERIOR == "CONDENATORIA"' in plantilla:
            plantilla = plantilla.replace(
                '{{CONDICIONAL_LOGICA_VIAS: SI_SENTIDO_SENTENCIA_INFERIOR == "CONDENATORIA"}}',
                "Que, se ratifica la sanción penal impuesta en base al análisis de "
                "proporcionalidad de la pena conforme a los Artículos 38 y 40 del "
                "Código Penal Militar.",
            )

        # AGENTE_SELECCIONAR_Y_RENDERIZAR_UNA_SOLA_OPCION -> renderiza las 4 opciones
        # (U4: se agrega Aprobación/Improbación, específica de consulta según
        # el Gem del vocal — antes solo A/B/C).
        # El mapeo A/B/C/D vive SOLO acá: los 4 bullets de la plantilla ya no
        # llevan el rótulo "[OPCIÓN X: ...]" (un modelo local lo copiaba
        # literal al documento — no es texto resolutivo, es instrucción de
        # elección). La instrucción aclara explícitamente que se emite solo
        # el texto resolutivo puro del bullet elegido, sin rótulo.
        if "AGENTE_SELECCIONAR_Y_RENDERIZAR_UNA_SOLA_OPCION" in plantilla:
            plantilla = plantilla.replace(
                "{{AGENTE_SELECCIONAR_Y_RENDERIZAR_UNA_SOLA_OPCION}}",
                "[El agente debe seleccionar UNA SOLA de las 4 opciones "
                "siguientes según corresponda — A (Confirmación, primer "
                "bullet), B (Aprobación/Improbación, segundo bullet), "
                "C (Revocación, tercer bullet) o D (Anulación, cuarto "
                "bullet) — y emitir ÚNICAMENTE el texto resolutivo puro de "
                "ese bullet, tal cual está redactado: sin rótulos, sin "
                "letras (A/B/C/D) ni corchetes; los rótulos son "
                "instrucción de elección, no texto del documento.]",
            )

        return plantilla

    @staticmethod
    def _fecha_actual_bolivia_hoy():
        """`date.today()` — extraído para reusar el mismo "hoy" en ANIO y fecha."""
        from datetime import date

        return date.today()

    def _fecha_actual_bolivia(self) -> str:
        """Fecha actual en formato Bolivia (ej. 09 de agosto de 2026).

        U1 (alineación vocal): día con cero a la izquierda — los autos reales
        usan "01 de julio de 2026", "03 de julio de 2026", nunca "1 de julio".
        """
        meses = [
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ]
        hoy = self._fecha_actual_bolivia_hoy()
        return f"{hoy.day:02d} de {meses[hoy.month - 1]} de {hoy.year}"
