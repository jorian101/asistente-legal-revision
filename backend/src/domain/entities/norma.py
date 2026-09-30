"""Entidad de dominio Norma.

Codigo de la norma juridica al que pertenecen los Fragmentos almacenados en
la tabla `fragmento`. Una Norma representa un cuerpo normativo completo
(CPPM, CPM, CPE, LOJM, LOFA, Ley 1970, etc.), no un articulo individual.

Regla Clean Architecture: dataclass pura (3.13 `slots=True` opcionalmente).
El ORM vive en adapters/postgres/models/norma.py.

Esquema (arquitectura.md seccion 3.1, tabla `norma`):
- id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
- nombre TEXT NOT NULL
- abreviatura TEXT NOT NULL UNIQUE              (ej: 'CPPM', 'CPE')
- tipo TEXT NOT NULL CHECK (...)                (7 valores, ver abajo)
- jerarquia TEXT NOT NULL CHECK (...)           (5 valores, ver abajo)
- version TEXT NULL
- ruta_archivo TEXT NULL
- indexado BOOLEAN NOT NULL DEFAULT false
- indexado_por BIGINT NULL REFERENCES usuario(id)
- created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

TipoNorma = Literal[
    "constitucion",
    "codigo_militar",
    "codigo_ordinario",
    "ley_organica",
    "reglamento",
    "scp_tcp",
    "sentencia_cidh",
    "doctrina_libro",
]

JerarquiaNorma = Literal[
    "suprema",
    "militar",
    "supletoria",
    "jurisprudencia",
    "doctrina",
]


@dataclass(slots=True)
class Norma:
    """Cuerpo normativo indexable en el corpus juridico.

    Atributos:
        id: Identificador interno. None si la entidad no fue persistida aun.
        nombre: Nombre completo del cuerpo normativo. Ej: 'Codigo de
            Procedimiento Penal Militar'.
        abreviatura: Abreviatura canonica UNIQUE. Ej: 'CPPM'.
        tipo: Clasificacion tematica. Ver TipoNorma.
        jerarquia: Posicion jerarquica en el ordenamiento. Ver JerarquiaNorma.
        version: Version del texto (ej: 'Decreto Ley 13321 de 1976').
            None si no aplica.
        ruta_archivo: Ruta del PDF original en disco. Se guarda como
            referencia para re-indexacion, nunca para servir el archivo.
        indexado: False hasta que `IndexarNorma` complete la fase de
            insercion + embeddings + Qdrant upsert. En caso de fallo debe
            volver a False.
        indexado_por: ID del usuario que disparo la indexacion (FK a
            usuario.id). El dominio guarda el int; el adapter resuelve la FK.
        activo: Soft delete (False = norma eliminada por admin). Default True.
        created_at: Fecha/hora de creacion del registro. None antes de persistir.
    """

    id: int | None
    nombre: str
    abreviatura: str
    tipo: TipoNorma
    jerarquia: JerarquiaNorma
    version: str | None = None
    ruta_archivo: str | None = None
    indexado: bool = False
    indexado_por: int | None = None
    activo: bool = True
    created_at: datetime | None = None
    # Flujo privada -> global con aprobacion (mismo que las obras de doctrina).
    propietario_id: int | None = None
    estado_visibilidad: str = "global"  # privado | pendiente | global | rechazado
    motivo_rechazo: str | None = None
    origen_obra_id: int | None = None  # obrado desde el que se promovio
