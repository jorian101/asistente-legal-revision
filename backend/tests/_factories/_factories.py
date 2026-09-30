"""Factory helpers de dominio para tests (charla: "domain-specific testing language").

Decision del usuario (ver memoria topic_key
`architecture/plan-red-de-seguridad-calidad-fundamentacional`):
NO usar factory_boy. Helpers simples `make_X(**overrides)`, uno por entidad,
consistentes con la convencion implicita del repo (ver `_DummySegmentador`
en tests/segmentacion/test_registro.py).

Reglas del skill clean-code §5:
- Datos por defecto validos (no hay que pensarlos cada vez).
- Overrides explicitos por test (lo que cambia es lo que se testea).
- Sin estado compartido (cada llamada devuelve una nueva instancia).
- Reset entre tests via autouse fixture en conftest.py.

Estan alineados con dataclasses de src/domain/entities/ (slots, defaults).
No tocan adapters ni ORM — son entidades de dominio puras.
"""

from __future__ import annotations

from src.domain.entities.borrador import Borrador
from src.domain.entities.expediente import Expediente
from src.domain.entities.fragmento import Fragmento
from src.domain.entities.norma import Norma
from src.domain.entities.usuario import Usuario


def make_usuario(**overrides) -> Usuario:
    slug = overrides.pop("carnet", "8012345")
    return Usuario(
        id=overrides.pop("id", None),
        nombre=overrides.pop("nombre", "Operador de Prueba"),
        carnet=slug,
        password_hash=overrides.pop(
            "password_hash", "$2b$12$placeholderbcryptrealhashcon24charsfake"
        ),
        rol=overrides.pop("rol", "operador_juridico"),
        cargo=overrides.pop("cargo", "Fiscal"),
        activo=overrides.pop("activo", True),
        created_at=overrides.pop("created_at", None),
        **overrides,
    )


def make_norma(**overrides) -> Norma:
    abrev = overrides.pop("abreviatura", "CPPM")
    return Norma(
        id=overrides.pop("id", None),
        nombre=overrides.pop("nombre", "Codigo de Procedimiento Penal Militar"),
        abreviatura=abrev,
        tipo=overrides.pop("tipo", "codigo_militar"),
        jerarquia=overrides.pop("jerarquia", "militar"),
        version=overrides.pop("version", "Decreto Ley 13321 de 1976"),
        ruta_archivo=overrides.pop("ruta_archivo", None),
        indexado=overrides.pop("indexado", False),
        indexado_por=overrides.pop("indexado_por", None),
        created_at=overrides.pop("created_at", None),
        **overrides,
    )


def make_expediente(**overrides) -> Expediente:
    return Expediente(
        id=overrides.pop("id", None),
        numero_caso=overrides.pop("numero_caso", "TSJM-C-2024-001"),
        tipo_proceso=overrides.pop("tipo_proceso", "consulta"),
        tribunal_origen=overrides.pop("ribunal_origen", "Tribunal Supremo de Justicia Militar"),
        procesado_nombre=overrides.pop("procesado_nombre", "Juan Perez"),
        procesado_grado=overrides.pop("procesado_grado", "Capitan"),
        delito=overrides.pop("delito", "Desobedencia"),
        sentencia_origen=overrides.pop("sentencia_origen", None),
        fojas_total=overrides.pop("fojas_total", 100),
        estado=overrides.pop("estado", "activo"),
        abierto_por=overrides.pop("abierto_por", 1),
        created_at=overrides.pop("created_at", None),
        **overrides,
    )


def make_fragmento(**overrides) -> Fragmento:
    return Fragmento(
        id=overrides.pop("id", None),
        norma_id=overrides.pop("norma_id", 1),
        obra_id=overrides.pop("obra_id", None),
        expediente_id=overrides.pop("expediente_id", None),
        qdrant_point_id=overrides.pop("qdrant_point_id", "550e8400-e29b-41d4-a716-446655440000"),
        texto=overrides.pop("texto", "Articulo 1. Probando el contenido."),
        padre_ref_id=overrides.pop("padre_ref_id", None),
        padre_ref_key=overrides.pop("padre_ref_key", None),
        nivel_jerarquico=overrides.pop("nivel_jerarquico", 4),
        metadatos=overrides.pop("metadatos", None),
        tipo_chunk=overrides.pop("tipo_chunk", "articulo_simple"),
        **overrides,
    )


def make_borrador(**overrides) -> Borrador:
    return Borrador(
        id=overrides.pop("id", None),
        expediente_id=overrides.pop("expediente_id", 1),
        propietario_id=overrides.pop("propietario_id", 1),
        tipo=overrides.pop("tipo", "proyecto_auto_vista_consulta"),
        contenido=overrides.pop("contenido", "# Auto de Vista\n\nBorrador de prueba..."),
        plantilla_usada=overrides.pop("plantilla_usada", "proyecto_auto_vista_consulta.md"),
        contexto_recuperado=overrides.pop("contexto_recuperado", None),
        estado=overrides.pop("estado", "borrador"),
        created_at=overrides.pop("created_at", None),
        updated_at=overrides.pop("updated_at", None),
        **overrides,
    )


def make_admin(**overrides) -> Usuario:
    """Alias para el caso mas comun: administrador activo."""
    return make_usuario(
        carnet=overrides.pop("carnet", "7000001"),
        nombre=overrides.pop("nombre", "Administrador de Prueba"),
        rol="administrador",
        cargo=overrides.pop("cargo", "Personal Técnico"),
        **overrides,
    )


def make_supervisor(**overrides) -> Usuario:
    """Alias para supervisor activo."""
    return make_usuario(
        carnet=overrides.pop("carnet", "6000002"),
        nombre=overrides.pop("nombre", "Supervisor de Prueba"),
        rol="supervisor",
        cargo=overrides.pop("cargo", "Vocal Presidente"),
        **overrides,
    )
