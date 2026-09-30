"""Tests unitarios de use cases de auth (Sprint 1, F1.3).

Use cases puros — no DB, no HTTP. Fakes que cumplen los Protocol
AuthRepository y JwtService (structural typing).

Cobertura:
- login: exito, credenciales invalidas, rate limit, lockout
- refresh_token: rotacion, replay detection, expirado
- logout: revoca por hash
- crear_usuario: carnet duplicado
- modificar_usuario: no encontrado
- reset_password: no encontrado
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import override

import bcrypt
import pytest

from src.application.auth import (
    actualizar_perfil,
    crear_usuario,
    listar_usuarios,
    login,
    logout,
    modificar_usuario,
    refresh_token,
    reset_password,
)
from src.application.ports.auth_repository import RefreshTokenData
from src.domain.entities.usuario import CargoInvalidoParaRolError, Usuario
from tests._factories import make_admin, make_supervisor, make_usuario


class FakeAuthRepo:
    """AuthRepository in-memory para tests. Configurable por test."""

    def __init__(
        self,
        usuarios: list[Usuario] | None = None,
        refresh_tokens: list[RefreshTokenData] | None = None,
        usuarios_by_carnet: dict[str, Usuario] | None = None,
    ) -> None:
        self.usuarios: dict[str, Usuario] = dict(usuarios_by_carnet or {})
        self.refresh_tokens: dict[str, RefreshTokenData] = {
            r.token_hash: r for r in (refresh_tokens or [])
        }
        self.intentos: list[tuple[str, str, bool]] = []
        self.intentos_fallidos_carnet = 0
        self.intentos_por_ip = 0
        self.revoked_tokens: list[str] = []
        self.revoked_all: list[int] = []
        self.next_id = 1

    @override
    async def get_by_carnet(self, carnet: str) -> Usuario | None:
        return self.usuarios.get(carnet)

    @override
    async def get_by_id(self, usuario_id: int) -> Usuario | None:
        for usuario in self.usuarios.values():
            if usuario.id == usuario_id:
                return usuario
        return None

    @override
    async def crear_usuario(self, usuario: Usuario) -> Usuario:
        if usuario.carnet in self.usuarios:
            raise crear_usuario.CarnetDuplicadoError
        usuario.id = self.next_id
        self.next_id += 1
        self.usuarios[usuario.carnet] = usuario
        return usuario

    @override
    async def actualizar_usuario(
        self, usuario: Usuario, carnet_original: str | None = None
    ) -> Usuario:
        identificador = carnet_original or usuario.carnet
        del self.usuarios[identificador]
        if usuario.carnet in self.usuarios:
            raise crear_usuario.CarnetDuplicadoError
        self.usuarios[usuario.carnet] = usuario
        return usuario

    @override
    async def listar_usuarios(self) -> list[Usuario]:
        return sorted(self.usuarios.values(), key=lambda u: u.carnet)

    @override
    async def guardar_refresh_token(
        self, usuario_id: int, token_hash: str, expires_at: datetime
    ) -> None:
        self.refresh_tokens[token_hash] = RefreshTokenData(
            id=f"rt-{len(self.refresh_tokens)}",
            usuario_id=usuario_id,
            token_hash=token_hash,
            expires_at=expires_at,
            revocado=False,
            created_at=datetime.now(UTC),
        )

    @override
    async def revocar_refresh_token(self, token_hash: str) -> None:
        self.revoked_tokens.append(token_hash)
        if token_hash in self.refresh_tokens:
            self.refresh_tokens[token_hash].revocado = True

    @override
    async def revocar_todos_refresh_tokens(self, usuario_id: int) -> None:
        self.revoked_all.append(usuario_id)
        for r in self.refresh_tokens.values():
            if r.usuario_id == usuario_id:
                r.revocado = True

    @override
    async def get_refresh_token(self, token_hash: str) -> RefreshTokenData | None:
        return self.refresh_tokens.get(token_hash)

    @override
    async def registrar_intento(self, carnet: str, ip: str, exitoso: bool) -> None:
        self.intentos.append((carnet, ip, exitoso))

    @override
    async def contar_intentos_fallidos(self, carnet: str, desde: datetime) -> int:
        return self.intentos_fallidos_carnet

    @override
    async def contar_intentos_por_ip(self, ip: str, desde: datetime) -> int:
        return self.intentos_por_ip


class FakeJwtService:
    """JwtService fake — genera tokens deterministicos."""

    def __init__(self) -> None:
        self.counter = 0
        self.access_tokens: list[tuple[int, str]] = []

    @override
    def crear_access_token(self, usuario_id: int, rol: str) -> str:
        self.access_tokens.append((usuario_id, rol))
        return f"access-{usuario_id}-{rol}"

    @override
    def crear_refresh_token(self) -> str:
        self.counter += 1
        return f"refresh-{self.counter}"

    @override
    def verificar_access_token(self, token: str) -> dict:
        return {"sub": "1", "rol": "operador_juridico"}


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_ok() -> None:
    pwd = "S3cure!"
    usuario = make_usuario(carnet="8012345", password_hash=_hash_password(pwd))
    usuario.id = 1
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})
    jwt = FakeJwtService()

    resp = await login.execute("8012345", pwd, "10.0.0.1", repo, jwt)

    assert resp.rol == "operador_juridico"
    assert resp.access_token.startswith("access-1-")
    assert resp.refresh_token.startswith("refresh-")
    assert (usuario.carnet, "10.0.0.1", True) in repo.intentos
    assert len(repo.refresh_tokens) == 1


@pytest.mark.asyncio
async def test_login_credenciales_invalidas() -> None:
    usuario = make_usuario(carnet="8012345", password_hash=_hash_password("correct"))
    usuario.id = 1
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})
    jwt = FakeJwtService()

    with pytest.raises(login.LoginError):
        await login.execute("8012345", "wrong", "10.0.0.1", repo, jwt)

    assert (usuario.carnet, "10.0.0.1", False) in repo.intentos


@pytest.mark.asyncio
async def test_login_rate_limit_ip() -> None:
    pwd = "S3cure!"
    usuario = make_usuario(carnet="8012345", password_hash=_hash_password(pwd))
    usuario.id = 1
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})
    repo.intentos_por_ip = 6
    jwt = FakeJwtService()

    with pytest.raises(login.RateLimitError):
        await login.execute("8012345", pwd, "10.0.0.1", repo, jwt)


@pytest.mark.asyncio
async def test_login_lockout_carnet() -> None:
    pwd = "S3cure!"
    usuario = make_usuario(carnet="8012345", password_hash=_hash_password(pwd))
    usuario.id = 1
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})
    repo.intentos_fallidos_carnet = 10
    jwt = FakeJwtService()

    with pytest.raises(login.LockoutError):
        await login.execute("8012345", pwd, "10.0.0.1", repo, jwt)


# ---------------------------------------------------------------------------
# refresh_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_rotacion_ok() -> None:
    usuario = make_usuario(carnet="8012345")
    usuario.id = 7
    raw = "raw-token-abc"
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    record = RefreshTokenData(
        id="rt-1",
        usuario_id=7,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=5),
        revocado=False,
        created_at=datetime.now(UTC),
    )
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario}, refresh_tokens=[record])
    jwt = FakeJwtService()

    resp = await refresh_token.execute(raw, repo, jwt)

    assert resp.refresh_token != raw
    assert jwt.access_tokens[-1] == (7, "operador_juridico")
    assert token_hash in repo.revoked_tokens
    assert token_hash in repo.refresh_tokens
    assert any(r.usuario_id == 7 and not r.revocado for r in repo.refresh_tokens.values())


@pytest.mark.asyncio
async def test_refresh_replay_detection() -> None:
    usuario_id = 7
    raw = "raw-token-replay"
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    record = RefreshTokenData(
        id="rt-1",
        usuario_id=usuario_id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=5),
        revocado=True,  # ya revocado -> replay
        created_at=datetime.now(UTC),
    )
    repo = FakeAuthRepo(refresh_tokens=[record])
    jwt = FakeJwtService()

    with pytest.raises(refresh_token.ReplayError):
        await refresh_token.execute(raw, repo, jwt)

    assert usuario_id in repo.revoked_all


@pytest.mark.asyncio
async def test_refresh_expirado() -> None:
    raw = "raw-token-expired"
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    record = RefreshTokenData(
        id="rt-1",
        usuario_id=7,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) - timedelta(days=1),  # pasado
        revocado=False,
        created_at=datetime.now(UTC) - timedelta(days=8),
    )
    repo = FakeAuthRepo(refresh_tokens=[record])
    jwt = FakeJwtService()

    with pytest.raises(refresh_token.RefreshTokenError):
        await refresh_token.execute(raw, repo, jwt)


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_revoca_por_hash() -> None:
    raw = "raw-logout"
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    repo = FakeAuthRepo()

    await logout.execute(raw, repo)

    assert token_hash in repo.revoked_tokens


# ---------------------------------------------------------------------------
# crear_usuario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crear_usuario_ok() -> None:
    repo = FakeAuthRepo()
    pwd_plain = "S3cure!"

    usuario = await crear_usuario.execute(
        carnet="9012345",
        nombre="Nuevo Operador",
        password=pwd_plain,
        rol="operador_juridico",
        cargo="Fiscal",
        auth_repo=repo,
    )

    assert usuario.id is not None
    assert usuario.carnet == "9012345"
    assert bcrypt.checkpw(pwd_plain.encode(), usuario.password_hash.encode())


@pytest.mark.asyncio
async def test_crear_usuario_duplicado() -> None:
    usuario = make_usuario(carnet="8012345")
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})

    with pytest.raises(crear_usuario.CarnetDuplicadoError):
        await crear_usuario.execute(
            carnet="8012345",
            nombre="Dup",
            password="x",
            rol="operador_juridico",
            cargo="Fiscal",
            auth_repo=repo,
        )


@pytest.mark.asyncio
async def test_crear_usuario_cargo_invalido_para_rol() -> None:
    """Tabla 18: operador_juridico no puede tener cargo de supervisor."""
    repo = FakeAuthRepo()

    with pytest.raises(CargoInvalidoParaRolError):
        await crear_usuario.execute(
            carnet="9012346",
            nombre="Mal Cargo",
            password="x",
            rol="operador_juridico",
            cargo="Vocal Presidente",
            auth_repo=repo,
        )


@pytest.mark.asyncio
async def test_crear_usuario_admin_solo_cargo_tecnico() -> None:
    """Tabla 18: administrador solo admite Personal Técnico."""
    repo = FakeAuthRepo()

    with pytest.raises(CargoInvalidoParaRolError):
        await crear_usuario.execute(
            carnet="9012347",
            nombre="Admin con cargo SAC",
            password="x",
            rol="administrador",
            cargo="Fiscal",
            auth_repo=repo,
        )


# ---------------------------------------------------------------------------
# listar_usuarios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_listar_usuarios_devuelve_todos_ordenados() -> None:
    u1 = make_usuario(carnet="8012345")
    u1.id = 1
    u2 = make_supervisor(carnet="7012345")
    u2.id = 2
    u3 = make_admin(carnet="9012345")
    u3.id = 3
    repo = FakeAuthRepo(usuarios_by_carnet={u1.carnet: u1, u2.carnet: u2, u3.carnet: u3})

    usuarios = await listar_usuarios.execute(repo)

    assert [u.carnet for u in usuarios] == ["7012345", "8012345", "9012345"]


@pytest.mark.asyncio
async def test_listar_usuarios_vacio() -> None:
    repo = FakeAuthRepo()
    assert await listar_usuarios.execute(repo) == []


# ---------------------------------------------------------------------------
# modificar_usuario
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_modificar_usuario_ok() -> None:
    usuario = make_supervisor(carnet="8012345")
    usuario.id = 2
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})

    actualizado = await modificar_usuario.execute(
        "8012345", repo, activo=False, cargo="Vocal Presidente"
    )

    assert actualizado.activo is False
    assert actualizado.cargo == "Vocal Presidente"


@pytest.mark.asyncio
async def test_modificar_usuario_rol_invalido_con_cargo_actual() -> None:
    """Cambiar rol a uno cuyo cargo actual no es valido -> CargoInvalidoParaRolError."""
    usuario = make_usuario(carnet="8012345")  # operador/Fiscal
    usuario.id = 2
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})

    with pytest.raises(CargoInvalidoParaRolError):
        # operador(Fiscal) -> supervisor: Fiscal no es cargo de supervisor.
        await modificar_usuario.execute("8012345", repo, rol="supervisor")


@pytest.mark.asyncio
async def test_modificar_usuario_no_encontrado() -> None:
    repo = FakeAuthRepo()

    with pytest.raises(modificar_usuario.UsuarioNoEncontradoError):
        await modificar_usuario.execute("4040404", repo, activo=False)


@pytest.mark.asyncio
async def test_modificar_usuario_nombre_y_carnet() -> None:
    usuario = make_usuario(carnet="8012345")
    usuario.id = 2
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})

    actualizado = await modificar_usuario.execute(
        "8012345", repo, nombre="Ana Lopez", carnet_nuevo="8019999"
    )

    assert actualizado.nombre == "Ana Lopez"
    assert actualizado.carnet == "8019999"
    assert repo.usuarios.get("8012345") is None
    assert repo.usuarios.get("8019999") is actualizado


@pytest.mark.asyncio
async def test_modificar_usuario_carnet_duplicado() -> None:
    a = make_usuario(carnet="8012345")
    b = make_usuario(carnet="8099999")
    repo = FakeAuthRepo(usuarios_by_carnet={a.carnet: a, b.carnet: b})

    with pytest.raises(crear_usuario.CarnetDuplicadoError):
        await modificar_usuario.execute("8012345", repo, carnet_nuevo="8099999")


# ---------------------------------------------------------------------------
# reset_password
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_password_ok() -> None:
    usuario = make_admin(carnet="1234567")
    usuario.id = 3
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})

    nueva = "NewS3cure!"
    actualizado = await reset_password.execute("1234567", nueva, repo)

    assert bcrypt.checkpw(nueva.encode(), actualizado.password_hash.encode())


@pytest.mark.asyncio
async def test_reset_password_no_encontrado() -> None:
    repo = FakeAuthRepo()

    with pytest.raises(reset_password.UsuarioNoEncontradoError):
        await reset_password.execute("4040404", "x", repo)


# ---------------------------------------------------------------------------
# actualizar_perfil
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_actualizar_perfil_email_none_no_borra_email() -> None:
    """PATCH /auth/me sin email (None) = sin cambio, no data loss."""
    usuario = make_usuario(carnet="8012345")
    usuario.id = 2
    usuario.email = "op@sac.gob.bo"
    usuario.email_verificado = True
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})

    actualizado = await actualizar_perfil.execute(
        auth_repo=repo,
        usuario_id=2,
        nombre="Nombre Nuevo",
        email=None,
        password_actual=None,
        password_nueva=None,
    )

    assert actualizado.nombre == "Nombre Nuevo"
    assert actualizado.email == "op@sac.gob.bo"
    assert actualizado.email_verificado is True


@pytest.mark.asyncio
async def test_actualizar_perfil_email_nuevo_resetea_verificacion() -> None:
    """Cambiar el email si actualiza y email_verificado vuelve a False."""
    usuario = make_usuario(carnet="8012345")
    usuario.id = 2
    usuario.email = "viejo@sac.gob.bo"
    usuario.email_verificado = True
    repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})

    actualizado = await actualizar_perfil.execute(
        auth_repo=repo,
        usuario_id=2,
        nombre="Operador de Prueba",
        email="nuevo@sac.gob.bo",
        password_actual=None,
        password_nueva=None,
    )

    assert actualizado.email == "nuevo@sac.gob.bo"
    assert actualizado.email_verificado is False


# ---------------------------------------------------------------------------
# bcrypt fuera del event loop (F-24)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("caso", ["crear_usuario", "reset_password", "actualizar_perfil"])
async def test_bcrypt_corre_fuera_del_event_loop(monkeypatch, caso: str) -> None:
    """hashpw/checkpw (~250 ms) no deben bloquear el event loop."""
    import threading

    principal = threading.get_ident()
    hilos: list[int] = []

    def _espia(real):
        def _f(*args, **kwargs):
            hilos.append(threading.get_ident())
            return real(*args, **kwargs)

        return _f

    monkeypatch.setattr(bcrypt, "hashpw", _espia(bcrypt.hashpw))
    monkeypatch.setattr(bcrypt, "checkpw", _espia(bcrypt.checkpw))

    if caso == "crear_usuario":
        await crear_usuario.execute(
            carnet="9012345",
            nombre="Nuevo",
            password="S3cure!",
            rol="operador_juridico",
            cargo="Fiscal",
            auth_repo=FakeAuthRepo(),
        )
    elif caso == "reset_password":
        usuario = make_admin(carnet="1234567")
        usuario.id = 3
        repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})
        await reset_password.execute("1234567", "NewS3cure!", repo)
    else:
        usuario = make_usuario(carnet="8012345")
        usuario.id = 2
        usuario.password_hash = _hash_password("actual123")
        repo = FakeAuthRepo(usuarios_by_carnet={usuario.carnet: usuario})
        hilos.clear()  # descarta el hash de preparacion, hecho en el hilo principal
        await actualizar_perfil.execute(
            auth_repo=repo,
            usuario_id=2,
            nombre="Nombre",
            email=None,
            password_actual="actual123",
            password_nueva="nueva1234",
        )

    assert hilos, "bcrypt no fue invocado"
    assert principal not in hilos
