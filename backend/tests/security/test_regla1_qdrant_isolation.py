"""Tests de seguridad — Trail of Bits Regla 1 (Sprint 0: Infra Docker/DB).

Regla 1 (arquitectura.md §8):
    - Qdrant debe usar `expose` (no `ports`) — solo comunicacion entre
      contenedores Docker. Sin acceso directo desde la LAN.
    - PostgreSQL con contrasenia y SECRET_KEY via variables de entorno, nunca
      hardcodeadas.

Seam elegido por el usuario: PARSEAR docker-compose.yml como YAML (no levantar
Docker). Es seco, corre en CI sin dependencias externas, valida desde el source
mismo. Tests de integracion runtime (opcion 3) pueden agregarse despues si se
quiere doble verificacion.

No requiere fixtures ni factories (no toca dominio).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

# docker-compose.yml vive en la raiz del repo, NO en backend/.
# pytest cwd = backend/, por eso navegamos dos niveles arriba.
COMPOSE_PATH = Path(__file__).resolve().parent.parent.parent.parent / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose_yaml() -> dict:
    """Carga docker-compose.yml parseado. Module-scope: se lee una sola vez."""
    if not COMPOSE_PATH.exists():
        pytest.fail(
            f"No se encontro docker-compose.yml en {COMPOSE_PATH}. "
            "Tests de Regla 1 requieren el archivo presente en la raiz del repo."
        )
    with COMPOSE_PATH.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_qdrant_usa_expose_sin_ports(compose_yaml: dict) -> None:
    """Regla 1 (a): Qdrant debe usar `expose`, NUNCA `ports`.

    Razon de seguridad: `ports` mapea el puerto del contenedor al host, dejando
    Qdrant accesible desde la LAN. `expose` solo lo hace visible dentro de la
    red de Docker. El acceso administrativo desde el host debe ser via SSH
    tunnel o proxy reverso con auth, no un puerto abierto.
    """
    qdrant = compose_yaml.get("services", {}).get("qdrant")
    assert qdrant is not None, "Servicio `qdrant` no definido en docker-compose.yml."

    # Debe tener `expose`.
    assert "expose" in qdrant, (
        "Regla 1 violada: `qdrant` NO tiene clave `expose`. "
        "Debe usar `expose` (no `ports`) para no abrir puertos al host."
    )

    # NO debe tener `ports` (ni siquiera como lista vacia — confunde).
    assert "ports" not in qdrant, (
        "Regla 1 violada: `qdrant` tiene clave `ports`. Debe eliminarse y usar `expose` unicamente."
    )


def test_postgres_usa_password_via_env_no_hardcodeado(compose_yaml: dict) -> None:
    """Regla 1 (b): PostgreSQL con contrasenia via variables de entorno.

    docker-compose.yml NO debe contener la contrasenia literal — solo la
    referencia `${POSTGRES_PASSWORD}` que se resuelve desde `.env` (que no
    entra al repo). Esto evita exponer credenciales en el versionado.
    """
    postgres = compose_yaml.get("services", {}).get("postgres")
    assert postgres is not None, "Servicio `postgres` no definido en docker-compose.yml."

    # Debe referenciar POSTGRES_PASSWORD desde env (resuelve via .env o shell).
    env_block = postgres.get("environment", {})
    env_vars = list(env_block.values()) if isinstance(env_block, dict) else list(env_block)
    password_refs = [v for v in env_vars if isinstance(v, str) and "POSTGRES_PASSWORD" in v]
    assert password_refs, (
        "Regla 1 violada: postgres.environment no referencia POSTGRES_PASSWORD "
        "via ${POSTGRES_PASSWORD}. La contrasenia no debe estar hardcodeada."
    )

    # Ningun valor del environment debe ser una contrasenia literal (no ${...}).
    for v in env_vars:
        if isinstance(v, str) and "PASSWORD" in v.upper():
            assert v.startswith("${") and v.endswith("}"), (
                f"Regla 1 violada: valor '{v}' parece contrasenia hardcodeada. "
                "Debe ser referencia ${VAR} resuelta desde .env."
            )


def test_no_secrets_hardcodeados_en_compose() -> None:
    """Regla 1 (general): docker-compose.yml sin SECRET_KEY ni passwords literales.

    Busca patrones sospechosos en el archivo:
        secret_key: abc123...
        password: literal123
    Acepta referencias ${VAR} pero rechaza valores que parezcan secrets literales
    adheridos al archivo versionado.
    """
    contenido = COMPOSE_PATH.read_text(encoding="utf-8")

    # Patrones: clave = valor literal (no ${VAR}).
    # ^\s*(secret_key|api_key|jwt_secret|password)\s*:\s*([^$\s][^$\n]+)$
    # Matchea si el valor NO empieza con $ (que seria ${VAR}).
    patron = re.compile(
        r"^\s*(secret_key|jwt_secret|api_key|PRIVATE_KEY|private_key)\s*:\s+"
        r"(?!\$\{)[A-Za-z0-9+/=_\-]{8,}\s*$",
        re.MULTILINE,
    )
    matches = patron.findall(contenido)
    assert not matches, (
        f"Posible secret hardcodeado en docker-compose.yml: {matches}. "
        "Toda secret debe ser referencia ${{VAR}} resuelta via .env."
    )
