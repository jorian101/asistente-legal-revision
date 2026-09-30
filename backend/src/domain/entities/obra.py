"""Entidad de dominio Obra (Pieza Procesal).

Regla Clean Architecture: dataclass pura, sin SQLAlchemy ni Pydantic.
El ORM vive en adapters/postgres/models/obra.py y mapea esta entidad
a la tabla `obra`.

Una obra es cada pieza procesal cargada al expediente: sentencias,
memoriales de apelacion, autos interlocutorios, dictamenes, etc.

Regla de dominio (arquitectura.md seccion 2.2): solo el propietario ve
obras privadas. El servicio EvaluadorVisibilidad (domain/services/)
centraliza esta regla; no vive aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TipoDocumento = Literal[
    "sentencia",
    "memorial_apelacion",
    "auto_interlocutorio",
    "oficio_elevacion",
    "acta_audiencia",
    "requerimiento_fiscal",
    "dictamen_radicatoria",
    "dictamen_fondo",
    "relacion_obrados",
    "proyecto_auto_vista",
    "auto_vista",
    "doctrina",
    "criterio",
    "otro",
    # Punteros a corpus (F3.2, niveles-corpus): referencian sin duplicar.
    "doctrina_libro",
    "jurisprudencia",
    "ejemplo",
    # Rename de "doctrina" (uploads sueltos): alias deprecado, se sigue
    # leyendo; lo nuevo usa material_caso.
    "material_caso",
    # Puntero a una norma del corpus (leyes): se fija en el chat sin duplicar contenido.
    "norma_corpus",
]
EstadoVisibilidad = Literal["privado", "publicado", "global", "rechazado"]
FuenteObra = Literal["carga_usuario", "generado_sistema"]
EstadoProcesamiento = Literal["pendiente", "procesando", "completado", "fallido"]


@dataclass
class Obra:
    """Obra (pieza procesal) del expediente.

    Atributos:
        id: Identificador interno. None si la entidad no fue persistida aun.
        expediente_id: ID del expediente al que pertenece (FK a expediente.id).
            El dominio guarda el int; el adapter resuelve la FK y el
            ON DELETE CASCADE.
        propietario_id: ID del usuario propietario (FK a usuario.id).
            Solo el propietario ve obras privadas (ver EvaluadorVisibilidad).
        tipo_documento: Tipo de pieza procesal. Ver TipoDocumento (18 valores).
        nombre_archivo: Nombre del archivo cargado.
        contenido_texto: Texto extraido del archivo.
        ruta_archivo: Ruta al archivo fisico en storage. None si solo texto.
        fojas_inicio: Foja inicial dentro del expediente. None si no aplica.
        fojas_fin: Foja final dentro del expediente. None si no aplica.
        estado_visibilidad: Estado de visibilidad. Por defecto 'privado'.
        fuente: Origen de la obra. Por defecto 'carga_usuario'.
        created_at: Fecha/hora de carga. None antes de persistir.
    """

    id: int | None
    expediente_id: int | None
    propietario_id: int
    tipo_documento: TipoDocumento
    nombre_archivo: str
    contenido_texto: str
    ruta_archivo: str | None = None
    fojas_inicio: int | None = None
    fojas_fin: int | None = None
    estado_visibilidad: EstadoVisibilidad = "privado"
    fuente: FuenteObra = "carga_usuario"
    # ponytail: añadidos al final para no romper orden posicional existente.
    # El ORM ObraModel ya tenía tamano_archivo + estado_procesamiento (Sprint 0);
    # la entity estaba desactualizada — Sprint 4 Fase 1.3b corrigió.
    tamano_archivo: int | None = None
    estado_procesamiento: EstadoProcesamiento = "completado"
    # Autor institucional (instancia inferior, ej. 'Tribunal Permanente de
    # Justicia Militar') para obras subidas al abrir el expediente. Si es None,
    # el autor es el usuario propietario (nombre + cargo).
    autor_instancia: str | None = None
    created_at: datetime | None = None
    # --- Campos de doctrina (Plan A) ---
    autor: str | None = None
    fecha_documento: str | None = None
    procedencia: str | None = None
    estado_validacion: str | None = None
    motivo_rechazo: str | None = None
    recomendada: bool = False
    # --- Puntero a corpus N2/N3 (F3.2) ---
    # corpus+corpus_ref no nulos = referencia a norma global (abreviatura),
    # sin duplicar contenido (contenido_texto=''). None = pieza propia.
    corpus: str | None = None
    corpus_ref: str | None = None
    # --- Soft delete (Plan A4) ---
    activo: bool = True
