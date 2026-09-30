"""Entidad de dominio FormatoDocumento.

Regla Clean Architecture: dataclass pura, sin SQLAlchemy ni Pydantic.
El ORM vive en adapters/postgres/models/formato_documento.py y mapea
esta entidad a la tabla `formato_documento`.

Un FormatoDocumento es la definición curada de un tipo de obrado del
TSJM (SAC/SCUI) — su layout canónico más los ejemplos crudos de los que
deriva. Se alimenta del pipeline `tools/formatos` (layout.json) y se
cura vía el módulo de administración (corrección de bloques + guardado).

Tipos: ver TipoDocumento en domain/entities/obra.py (14 valores).
Autor: aliaga | tsjm-otro | instancia-inferior | parte | desconocido.
Estado: borrador (en edición) | canonico (semilla del tipo, usado por
    docxtpl/plantillas).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from src.domain.entities.obra import TipoDocumento

AutorFormato = Literal["aliaga", "tsjm-otro", "instancia-inferior", "parte", "desconocido"]
EstadoFormato = Literal["borrador", "canonico"]


@dataclass(slots=True)
class FormatoDocumento:
    """Formato canónico/crudo de un tipo de obrado TSJM.

    Atributos:
        id: PK interno. None si no persistida.
        tipo_documento: TipoDocumento de obra.py.
        slug: Identificador legible único (ej. auto_vista-aliaga-12-2026).
        autor: AutorFormato. Prioriza 'aliaga' como semilla.
        engine: Motor que generó el layout (python-docx, pymupdf,
            docling+tess-cli-spa, etc.).
        estado: borrador | canonico.
        version: Contador de ediciones (incrementa en cada actualización).
        meta: Metadatos del layout (página, márgenes, tamaño de hoja, fuente, etc.).
        bloques: Lista de bloques del layout (estructura layout.json).
        esqueleto: Lista de bloques con marca de plantilla (template/texto_plantilla)
            y placeholders {{VAR}} — es el formato que alimenta la vista y el export.
        hash_fuente: Hash16 del archivo fuente (detección de cambios).
        created_at / updated_at: Timestamps.
    """

    id: int | None
    tipo_documento: TipoDocumento
    slug: str
    autor: AutorFormato
    engine: str
    meta: dict[str, Any]
    bloques: list[dict[str, Any]]
    esqueleto: list[dict[str, Any]] | None = None
    estado: EstadoFormato = "borrador"
    version: int = 1
    hash_fuente: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
