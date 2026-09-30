"""Tests unitarios del flujo 2FA email (Fase 2 plan jurado).

Use cases puros — no DB, no HTTP. Fakes que cumplen AuthRepository, JwtService
y EmailService (structural typing).

Cobertura:
- login: usuario con email_verificado -> Requiere2FaError + codigo guardado + email enviado
- login: usuario sin email_verificado -> login legacy directo
- verificar_2fa: codigo valido -> tokens + refresh guardado
- verificar_2fa: codigo invalido -> incrementa intentos; 3 fallos -> lockout
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import override

import pytest

from src.application.auth import login, verificar_2fa
from src.application.ports.auth_repository import RefreshTokenData
from src.domain.entities.usuario import Usuario
from tests._factories import make_usuario


class Fake2FaAuthRepo:
    """AuthRepository in-memory con soporte 2FA para tests."""

    def __init__(self, usuario: Usuario) -> None:
        self.usuario = usuario
        self.usuarios: dict[str, Usuario] = {usuario.carnet: usuario}
        self.refresh_tokens: dict[str, RefreshTokenData] = {}
        self.intentos: list[tuple[str, str, bool]] = []
        self.intentos_por_ip = 0
        self.codigo_guardado: tuple[str, datetime] | None = None
        self.codigo_limpiado = False
        self.desbloqueado = False
        self.email_verificado_llamada = False

    @override
    async def get_by_carnet(self, carnet: str) -> Usuario | None:
        return self.usuarios.get(carnet)

    @override
    async def registrar_intento(self, carnet: str, ip: str, exitoso: bool) -> None:
        self.intentos.append((carnet, ip, exitoso))

    @override
    async def contar_intentos_fallidos(self, carnet: str, desde: datetime) -> int:
        return 0

    @override
    async def contar_intentos_por_ip(self, ip: str, desde: datetime) -> int:
        return self.intentos_por_ip

    @override
    async def guardar_codigo_2fa(self, carnet: str, codigo_hash: str, expira: datetime) -> None:
        self.codigo_guardado = (codigo_hash, expira)

    @override
    async def verificar_codigo_2fa(self, carnet: str, codigo_hash: str) -> bool:
        if self.codigo_guardado is None:
            return False
        guardado_hash, expira = self.codigo_guardado
        return guardado_hash == codigo_hash and expira > datetime.now(UTC)

    @override
    async def limpiar_codigo_2fa(self, carnet: str) -> None:
        self.codigo_limpiado = True

    @override
    async def incrementar_intentos_2fa(self, carnet: str) -> int:
        self.usuario.intentos_codigo += 1
        if self.usuario.intentos_codigo >= 3:
            self.usuario.bloqueado_hasta = datetime.now(UTC) + timedelta(hours=1)
        return self.usuario.intentos_codigo

    @override
    async def desbloquear_2fa(self, carnet: str) -> None:
        self.desbloqueado = True
        self.usuario.bloqueado_hasta = None
        self.usuario.intentos_codigo = 0

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


class FakeJwtService:
    """JwtService fake — tokens deterministicos."""

    def __init__(self) -> None:
        self.counter = 0

    @override
    def crear_access_token(self, usuario_id: int, rol: str) -> str:
        return f"access-{usuario_id}-{rol}"

    @override
    def crear_refresh_token(self) -> str:
        self.counter += 1
        return f"refresh-{self.counter}"

    @override
    def verificar_access_token(self, token: str) -> dict:
        return {"sub": "1", "rol": "operador_juridico"}


class FakeEmailService:
    """EmailService fake — captura codigo enviado."""

    def __init__(self) -> None:
        self.enviados: list[tuple[str, str, int]] = []

    @override
    async def enviar_codigo_2fa(
        self, email: str, codigo: str, ttl_minutes: int | None = None
    ) -> None:
        self.enviados.append((email, codigo, ttl_minutes or 5))

    @override
    async def enviar_email_generico(
        self, to: str, subject: str, html: str, text: str | None = None
    ) -> None:
        self.enviados.append((to, subject, 0))


def _usuario_con_email() -> Usuario:
    return make_usuario(
        email="operador@tsjm.edu.bo",
        email_verificado=True,
        password_hash=_hash("secret123"),
    )


def _usuario_sin_email() -> Usuario:
    return make_usuario(
        password_hash=_hash("secret123"),
    )


def _hash(plain: str) -> str:
    import bcrypt

    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=4)).decode()


# ---------------------------------------------------------------------------
# login (paso 1 2FA)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_con_email_verificado_lanza_requiere_2fa_y_envia_codigo() -> None:
    repo = Fake2FaAuthRepo(_usuario_con_email())
    email = FakeEmailService()
    jwt = FakeJwtService()

    with pytest.raises(login.Requiere2FaError):
        await login.execute("8012345", "secret123", "1.2.3.4", repo, jwt, email)

    # Codigo guardado (hash) + enviado por email
    assert repo.codigo_guardado is not None
    assert len(email.enviados) == 1
    destinatario, codigo, ttl = email.enviados[0]
    assert destinatario == "operador@tsjm.edu.bo"
    assert len(codigo) == 6
    assert ttl == 5
    # El hash guardado corresponde al codigo enviado
    assert repo.codigo_guardado[0] == hashlib.sha256(codigo.encode()).hexdigest()


@pytest.mark.asyncio
async def test_login_sin_email_verificado_emite_tokens_legacy() -> None:
    repo = Fake2FaAuthRepo(_usuario_sin_email())
    email = FakeEmailService()
    jwt = FakeJwtService()

    result = await login.execute("8012345", "secret123", "1.2.3.4", repo, jwt, email)

    assert result.access_token.startswith("access-")
    assert result.rol == "operador_juridico"
    assert len(email.enviados) == 0


@pytest.mark.asyncio
async def test_login_verifica_bcrypt_fuera_del_event_loop(monkeypatch) -> None:
    """bcrypt.checkpw (~250 ms) no debe bloquear el event loop (F-13)."""
    import threading

    hilos: list[int] = []
    real = login.bcrypt.checkpw

    def _espia(*args, **kwargs):
        hilos.append(threading.get_ident())
        return real(*args, **kwargs)

    monkeypatch.setattr(login.bcrypt, "checkpw", _espia)
    repo = Fake2FaAuthRepo(_usuario_sin_email())

    await login.execute(
        "8012345", "secret123", "1.2.3.4", repo, FakeJwtService(), FakeEmailService()
    )

    assert hilos and hilos[0] != threading.get_ident()


@pytest.mark.asyncio
@pytest.mark.parametrize("caso", ["inexistente", "inactivo"])
async def test_login_usuario_invalido_gasta_el_mismo_bcrypt(monkeypatch, caso: str) -> None:
    """Sin bcrypt para usuarios inexistentes/inactivos se enumeran carnets por tiempo (F-28)."""
    llamadas: list[bytes] = []
    real = login.bcrypt.checkpw

    def _espia(password: bytes, hashed: bytes) -> bool:
        llamadas.append(hashed)
        return real(password, hashed)

    monkeypatch.setattr(login.bcrypt, "checkpw", _espia)
    usuario = _usuario_sin_email()
    if caso == "inactivo":
        usuario.activo = False
    repo = Fake2FaAuthRepo(usuario)
    carnet = usuario.carnet if caso == "inactivo" else "0000000"

    with pytest.raises(login.LoginError):
        await login.execute(
            carnet, "cualquiera", "1.2.3.4", repo, FakeJwtService(), FakeEmailService()
        )

    assert len(llamadas) == 1
    # El intento fallido se sigue registrando y no se filtra el motivo.
    assert repo.intentos == [(carnet, "1.2.3.4", False)]


@pytest.mark.asyncio
async def test_login_credenciales_invalidas_no_envia_codigo() -> None:
    repo = Fake2FaAuthRepo(_usuario_con_email())
    email = FakeEmailService()
    jwt = FakeJwtService()

    with pytest.raises(login.LoginError):
        await login.execute("8012345", "wrongpass", "1.2.3.4", repo, jwt, email)

    assert len(email.enviados) == 0


# ---------------------------------------------------------------------------
# verificar_2fa (paso 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verificar_2fa_codigo_valido_emite_tokens() -> None:
    repo = Fake2FaAuthRepo(_usuario_con_email())
    jwt = FakeJwtService()
    codigo = "123456"
    repo.codigo_guardado = (
        hashlib.sha256(codigo.encode()).hexdigest(),
        datetime.now(UTC) + timedelta(minutes=5),
    )

    result = await verificar_2fa.execute("8012345", codigo, "1.2.3.4", repo, jwt)

    assert result.access_token.startswith("access-")
    assert result.rol == "operador_juridico"
    assert len(repo.refresh_tokens) == 1
    assert repo.codigo_limpiado is True


@pytest.mark.asyncio
async def test_verificar_2fa_codigo_invalido_incrementa_intentos() -> None:
    repo = Fake2FaAuthRepo(_usuario_con_email())
    jwt = FakeJwtService()
    repo.codigo_guardado = (
        hashlib.sha256(b"000000").hexdigest(),
        datetime.now(UTC) + timedelta(minutes=5),
    )

    with pytest.raises(verificar_2fa.Verificar2FaError):
        await verificar_2fa.execute("8012345", "999999", "1.2.3.4", repo, jwt)

    assert repo.usuario.intentos_codigo == 1


@pytest.mark.asyncio
async def test_verificar_2fa_3_fallos_bloquea() -> None:
    repo = Fake2FaAuthRepo(_usuario_con_email())
    jwt = FakeJwtService()
    repo.codigo_guardado = (
        hashlib.sha256(b"000000").hexdigest(),
        datetime.now(UTC) + timedelta(minutes=5),
    )

    for _ in range(3):
        with pytest.raises(verificar_2fa.Verificar2FaError):
            await verificar_2fa.execute("8012345", "999999", "1.2.3.4", repo, jwt)

    assert repo.usuario.intentos_codigo == 3
    assert repo.usuario.bloqueado_hasta is not None


@pytest.mark.asyncio
async def test_verificar_2fa_usuario_bloqueado_rechaza() -> None:
    repo = Fake2FaAuthRepo(_usuario_con_email())
    jwt = FakeJwtService()
    repo.usuario.intentos_codigo = 3
    repo.usuario.bloqueado_hasta = datetime.now(UTC) + timedelta(hours=1)
    repo.codigo_guardado = (
        hashlib.sha256(b"123456").hexdigest(),
        datetime.now(UTC) + timedelta(minutes=5),
    )

    with pytest.raises(verificar_2fa.Verificar2FaError):
        await verificar_2fa.execute("8012345", "123456", "1.2.3.4", repo, jwt)

    assert len(repo.refresh_tokens) == 0
