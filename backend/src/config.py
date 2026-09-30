"""Configuracion central de la aplicacion.

Lee variables de entorno desde el .env del raiz del proyecto y las expone
como constantes tipadas. Unico lugar del codigo que conoce `os.environ` y
`python-dotenv` — el resto de modulos debe importar de aca.

Regla Clean Architecture: la configuracion es infraestructura. Vive en src/
como modulo comun consumido por application/ y adapters/, nunca por domain/.

Sprint 0 — Modulos LLM/Embedding/Ollama:
- LLM_MODEL_NAME: nombre del modelo LLM (default 'llama3:8b' para Ollama).
- EMBEDDING_MODEL_NAME: nombre del modelo de embeddings (default 'nomic-embed-text').
- EMBEDDING_DIM: dimension del vector de embedding (depende del modelo;
  nomic-embed-text=768, bge-m3=1024, qwen3-embedding-0.6b=1024).
- EMBEDDING_TEXT_BATCH_SIZE: tamano del batch que se envia a Ollama /api/embed.

Sprint 2 — Endpoints de embeddings (multi-proveedor):
- EMBEDDING_ENDPOINTS: JSON con lista de endpoints disponibles para el selector
  de la vista admin. Cada entrada: {id, provider, base_url, model, dim,
  api_key_env|null}. provider: ollama (local).
  Si no se define, se deriva un endpoint unico 'ollama_default' de
  OLLAMA_HOST + EMBEDDING_MODEL_NAME + EMBEDDING_DIM (backward-compatible).

Sprint 3 — Endpoints de reranker (multi-proveedor, decision D10):
- RERANKER_ENDPOINTS: JSON con lista de endpoints del cross-encoder, mismo
  formato que EMBEDDING_ENDPOINTS ({id, provider, base_url, model, api_key_env|null}).
  Si no se define, se deriva un endpoint unico 'reranker_default' de
  RERANKER_BASE_URL + RERANKER_MODEL (backward-compatible). Default del model:
  'bge-reranker-v2-m3' (568M, MIT).

Sprint 0 — Upload de corpus (Trail of Bits Regla 3):
- MAX_PDF_SIZE_MB: limite en MB para PDFs del corpus juridico (default 500, Regla 3).

Refactor Sprint 0 higiene:
- QDRANT_UPSERT_BATCH_SIZE: cuantos puntos por request HTTP a Qdrant (256 empirico).
- OLLAMA_TIMEOUT_SECONDS: timeout del cliente HTTP a Ollama /api/embed (300 empirico).
- SAFETY_ALLOW_COLLECTION_RECREATE: (Sprint 0=false) bloquea recreate destructivo
  de la coleccion Qdrant si hay mismatch de dimension. Setear a 1 solo para
  migrar el modelo de embedding.

Instalacion de usuario (sin APIs):
- MODO_LOCAL: (default false) si es 1, el arranque falla si algun endpoint de LLM,
  embeddings o reranker apunta fuera de la maquina/red local, y el login no usa
  2FA por email.

Nota: `embedding_model_name` y `embedding_dim` son operativas (pre-seleccion
antes del despliegue), no ajustables en runtime. Cambiarlas invalidaria los 3109
vectores ya almacenados. Umbrales de busqueda (score_threshold, top_k_*) viven
en la tabla `configuracion_rag` (BD), no aca.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ENV_PATH = _PROJECT_ROOT / ".env"

if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)


def _required(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise RuntimeError(f"Variable de entorno requerida faltante: {key}")
    return value


def _optional(key: str, default: str) -> str:
    value = os.environ.get(key)
    return value if value is not None else default


def _int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{key} debe ser un entero, se recibio {raw!r}.") from exc


def _float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise RuntimeError(f"{key} debe ser un numero, se recibio {raw!r}.") from exc


def _endpoints_json(
    key: str, raw: str, claves: tuple[str, ...], enteros: tuple[str, ...] = ()
) -> list[dict]:
    """Parsea y valida el JSON de endpoints: lista de objetos con `claves` no vacias.

    Falla al arrancar nombrando la variable y la entrada, en vez de un KeyError
    en el primer uso del endpoint.
    """
    try:
        endpoints = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{key} debe ser JSON valido. Ver .env.example.") from exc
    if not isinstance(endpoints, list):
        raise RuntimeError(f"{key} debe ser una lista JSON de endpoints.")
    for i, ep in enumerate(endpoints):
        if not isinstance(ep, dict):
            raise RuntimeError(f"{key}[{i}] debe ser un objeto JSON.")
        for clave in claves:
            if ep.get(clave) in (None, ""):
                raise RuntimeError(f"{key}[{i}] no define la clave obligatoria '{clave}'.")
        for clave in enteros:
            valor = ep[clave]
            if not isinstance(valor, int) or isinstance(valor, bool):
                raise RuntimeError(f"{key}[{i}]: '{clave}' debe ser un entero, es {valor!r}.")
    return endpoints


def _bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


log = logging.getLogger(__name__)

# Longitud minima recomendada para firmar JWT HS256 (RFC 7518 §3.2: >= 256 bits).
_SECRET_KEY_MIN_LEN = 32


def _es_host_local(base_url: str) -> bool:
    """Loopback, IP privada o nombre sin dominio (servicio de docker o de la LAN)."""
    host = urlsplit(base_url).hostname or ""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return bool(host) and (host == "localhost" or "." not in host)
    return ip.is_loopback or ip.is_private


def _exigir_endpoints_locales(**endpoints_por_variable: list[dict]) -> None:
    """MODO_LOCAL: ningun expediente puede salir de la maquina (borde de confianza)."""
    for variable, endpoints in endpoints_por_variable.items():
        for ep in endpoints:
            if not _es_host_local(str(ep.get("base_url", ""))):
                raise RuntimeError(
                    f"MODO_LOCAL=1 pero {variable} tiene el endpoint externo "
                    f"'{ep.get('id')}' ({ep.get('base_url')}). En modo local solo se "
                    "admiten servicios de esta maquina o de la red local (ej. Ollama)."
                )


@lru_cache
class Settings:
    """Settings inmutables cargados una sola vez por proceso."""

    # Postgres / Qdrant / Auth / Ollama host
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int
    qdrant_host: str
    qdrant_port: int
    qdrant_grpc_port: int
    qdrant_api_key: str | None
    secret_key: str
    llm_provider: str
    ollama_host: str

    # Pool de conexiones Postgres (SQLAlchemy QueuePool). Cada request que hace
    # streaming LLM retiene su conexion mientras se consume el body (los
    # endpoints /consultas/responder pueden tardar decenas de segundos), y el
    # frontend hace polling concurrente; con el default (5+10) se agota y
    # aparecen 'connection is closed' en otros endpoints. Ajustable por env.
    pg_pool_size: int
    pg_max_overflow: int
    pg_pool_recycle: int

    # Modelos IA (Sprint 0+)
    llm_model_name: str
    embedding_model_name: str
    embedding_dim: int
    embedding_text_batch_size: int

    # Endpoints de embeddings (Sprint 2 — multi-proveedor)
    embedding_endpoints: list[dict]

    # Endpoints de reranker (Sprint 3 — multi-proveedor, decision D10)
    reranker_endpoints: list[dict]

    # Variables legacy single-provider del reranker (backward-compat)
    reranker_base_url: str
    reranker_model: str

    # Upload (Sprint 0 — Trail of Bits Regla 3)
    max_pdf_size_mb: int

    # Operativas del refactor Sprint 0 higiene (no ajustables via BD).
    qdrant_upsert_batch_size: int
    ollama_timeout_seconds: float
    safety_allow_collection_recreate: bool
    email_2fa_code_ttl_minutes: int
    email_2fa_max_intentos_codigo: int

    # P5.2 — Protección de recursos del reranker (laptop CPU/RAM).
    reranker_max_candidates: int
    reranker_timeout_seconds: float
    reranker_fallos_consecutivos: int
    reranker_cooldown_seconds: float

    # F1 — Presupuesto de tokens del bloque de contexto (ProcesadorContexto).
    llm_presupuesto_tokens: int

    # Instalacion de usuario: todo local, sin APIs externas.
    modo_local: bool

    def __init__(self) -> None:
        self.postgres_user = _required("POSTGRES_USER")
        self.postgres_password = _required("POSTGRES_PASSWORD")
        self.postgres_db = _required("POSTGRES_DB")
        self.postgres_port = _int("POSTGRES_PORT", 5432)
        self.postgres_host = _optional("POSTGRES_HOST", "127.0.0.1")
        self.qdrant_port = _int("QDRANT_PORT", 6333)
        self.qdrant_host = _optional("QDRANT_HOST", "127.0.0.1")
        self.qdrant_grpc_port = _int("QDRANT_GRPC_PORT", 6334)
        # Opcional: solo si el Qdrant exige API key. Vacia = sin autenticacion (como antes).
        self.qdrant_api_key = _optional("QDRANT_API_KEY", "").strip() or None
        self.secret_key = _required("SECRET_KEY")
        if len(self.secret_key) < _SECRET_KEY_MIN_LEN:
            log.warning(
                "SECRET_KEY tiene %d caracteres; HS256 recomienda al menos %d. "
                "Genera una con: python -c 'import secrets; print(secrets.token_urlsafe(48))'",
                len(self.secret_key),
                _SECRET_KEY_MIN_LEN,
            )
        self.llm_provider = _required("LLM_PROVIDER")
        self.ollama_host = _required("OLLAMA_HOST")

        # Pool Postgres: default holgado para streaming + polling concurrente.
        self.pg_pool_size = _int("PG_POOL_SIZE", 10)
        self.pg_max_overflow = _int("PG_MAX_OVERFLOW", 20)
        self.pg_pool_recycle = _int("PG_POOL_RECYCLE", 1800)

        # Modelos — defaults conservadormente seguros para Ollama on-premise.
        # Para migrar a Qwen3-Embedding-0.6B o bge-m3: editar el .env.
        self.llm_model_name = _optional("LLM_MODEL_NAME", "llama3:8b")
        self.embedding_model_name = _optional("EMBEDDING_MODEL_NAME", "nomic-embed-text")
        self.embedding_dim = _int("EMBEDDING_DIM", 768)
        self.embedding_text_batch_size = _int("EMBEDDING_TEXT_BATCH_SIZE", 64)

        # Endpoints de embeddings — multi-proveedor (Sprint 2). Si no se define
        # EMBEDDING_ENDPOINTS, se deriva un endpoint unico 'ollama_default' de
        # las variables legacy (backward-compatible con el .env de Sprint 0).
        endpoints_raw = os.environ.get("EMBEDDING_ENDPOINTS")
        if endpoints_raw:
            self.embedding_endpoints = _endpoints_json(
                "EMBEDDING_ENDPOINTS",
                endpoints_raw,
                ("id", "provider", "base_url", "model", "dim"),
                enteros=("dim",),
            )
        else:
            self.embedding_endpoints = [
                {
                    "id": "ollama_default",
                    "provider": "ollama",
                    "base_url": self.ollama_host,
                    "model": self.embedding_model_name,
                    "dim": self.embedding_dim,
                    "api_key_env": None,
                }
            ]

        # Upload — limite de 500 MB (Regla 3 Trail of Bits), consistente
        # con ValidadorUpload.MAX_BYTES (500MB) y .env.example.
        self.max_pdf_size_mb = _int("MAX_PDF_SIZE_MB", 500)

        # Endpoints de reranker — multi-proveedor (Sprint 3, decision D10).
        # Backward-compatible: si no se define RERANKER_ENDPOINTS, se deriva
        # un endpoint unico 'reranker_default' de RERANKER_BASE_URL +
        # RERANKER_MODEL (default 'bge-reranker-v2-m3').
        # El boot NO depende de servicios externos: si no hay config, lista
        # vacia y el error se emite en el punto de uso (reranker_endpoint()
        # o build_reranker()) — no bloquea /auth/login ni /admin/*.
        self.reranker_base_url = _optional("RERANKER_BASE_URL", "")
        self.reranker_model = _optional("RERANKER_MODEL", "bge-reranker-v2-m3")
        reranker_raw = os.environ.get("RERANKER_ENDPOINTS")
        if reranker_raw:
            self.reranker_endpoints = _endpoints_json(
                "RERANKER_ENDPOINTS", reranker_raw, ("id", "provider", "base_url", "model")
            )
        elif self.reranker_base_url:
            self.reranker_endpoints = [
                {
                    "id": "reranker_default",
                    "provider": "http",
                    "base_url": self.reranker_base_url,
                    "model": self.reranker_model,
                    "api_key_env": None,
                }
            ]
        else:
            # Sin config: lista vacia. PipelineRAG degrada sin reranker.
            self.reranker_endpoints = []

        # Endpoints de LLM — multi-proveedor (Sprint 6, extension). Si no se
        # define LLM_ENDPOINTS, se deriva un endpoint unico 'ollama_default'
        # de las variables legacy LLM_PROVIDER / OLLAMA_HOST / LLM_MODEL_NAME.
        # Backward-compatible: .env sin LLM_ENDPOINTS sigue funcionando.
        # Campos opcionales por endpoint (F2): context_window_tokens (acota
        # el presupuesto de contexto a la mitad de la ventana) y
        # soporta_system (default True; False pliega el system al user).
        llm_raw = os.environ.get("LLM_ENDPOINTS")
        if llm_raw:
            self.llm_endpoints: list[dict] = _endpoints_json(
                "LLM_ENDPOINTS", llm_raw, ("id", "provider", "base_url", "model")
            )
        else:
            self.llm_endpoints = [
                {
                    "id": "ollama_default",
                    "provider": "ollama",
                    "base_url": self.ollama_host,
                    "model": self.llm_model_name,
                    "api_key_env": None,
                }
            ]

        # Operativas (256 y 300 son empiricos del Sprint 0 — ver commits 915289a
        # y docs de _upsert_corpus_sync y OllamaEmbedder).
        self.qdrant_upsert_batch_size = _int("QDRANT_UPSERT_BATCH_SIZE", 256)
        self.ollama_timeout_seconds = _float("OLLAMA_TIMEOUT_SECONDS", 300.0)

        # Seguridad: bloquea recreate destructivo de coleccion Qdrant por defecto.
        # Setear SAFETY_ALLOW_COLLECTION_RECREATE=1 solo durante migracion de
        # modelo de embedding (requiere reindexar 3109 fragmentos).
        self.safety_allow_collection_recreate = _bool("SAFETY_ALLOW_COLLECTION_RECREATE", False)
        self.email_2fa_code_ttl_minutes = _int("EMAIL_2FA_CODE_TTL_MINUTES", 5)
        self.email_2fa_max_intentos_codigo = _int("EMAIL_2FA_MAX_INTENTOS_CODIGO", 3)

        # P5.2 — Protección de recursos del reranker. Defaults conservadores para
        # laptop CPU: 15 candidatos máximo, timeout 45s, breaker tras 2 fallos.
        self.reranker_max_candidates = _int("RERANKER_MAX_CANDIDATES", 15)
        self.reranker_timeout_seconds = _float("RERANKER_TIMEOUT_SECONDS", 45.0)
        self.reranker_fallos_consecutivos = _int("RERANKER_FALLOS_CONSECUTIVOS", 2)
        self.reranker_cooldown_seconds = _float("RERANKER_COOLDOWN_SECONDS", 60.0)

        # F1: presupuesto de tokens del bloque de contexto (ProcesadorContexto).
        # Aproximacion chars/4; F2 lo afina por endpoint con context_window_tokens.
        self.llm_presupuesto_tokens = _int("LLM_PRESUPUESTO_TOKENS", 4096)

        self.modo_local = _bool("MODO_LOCAL", False)
        if self.modo_local:
            _exigir_endpoints_locales(
                LLM_ENDPOINTS=self.llm_endpoints,
                EMBEDDING_ENDPOINTS=self.embedding_endpoints,
                RERANKER_ENDPOINTS=self.reranker_endpoints,
            )

    @property
    def postgres_url(self) -> str:
        """URL SQLAlchemy para PostgreSQL usando psycopg (sync, para Alembic)."""
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_url_async(self) -> str:
        """URL SQLAlchemy async (para el backend FastAPI en runtime)."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def upload_dir(self) -> str:
        """Directorio donde se persisten obras cargadas (Sprint 4 Regla 5).

        Default <tempdir>/asistente-legal/uploads — para prod requiere
        storage con cuotas + ACLs + UUID naming (upgrade path StoragePort).
        Usa tempfile.gettempdir() en runtime (no hardcoded /tmp) para
        satisfacer bandit B108.
        """
        import os
        import tempfile

        default = os.path.join(tempfile.gettempdir(), "asistente-legal", "uploads")
        return os.environ.get("UPLOAD_DIR", default)

    @property
    def qdrant_url(self) -> str:
        """Trail of Bits Regla 1: 127.0.0.1 only (no 0.0.0.0, no LAN)."""
        return f"http://{self.qdrant_host}:{self.qdrant_port}"

    @property
    def max_pdf_size_bytes(self) -> int:
        """Limite de tamano de PDF para indexacion (Trail of Bits Regla 3)."""
        return self.max_pdf_size_mb * 1024 * 1024

    def embedding_endpoint(self, endpoint_id: str | None) -> dict:
        """Devuelve un endpoint de embedding por id, o el primero como default."""
        if not self.embedding_endpoints:
            raise RuntimeError("No hay endpoints de embeddings configurados.")
        if endpoint_id is None:
            return self.embedding_endpoints[0]
        for ep in self.embedding_endpoints:
            if ep["id"] == endpoint_id:
                return ep
        raise KeyError(
            f"Endpoint de embeddings '{endpoint_id}' no configurado. "
            f"Disponibles: {[e['id'] for e in self.embedding_endpoints]}"
        )

    def reranker_endpoint(self, endpoint_id: str | None) -> dict:
        """Devuelve un endpoint de reranker por id, o el primero como default."""
        if not self.reranker_endpoints:
            raise RuntimeError("No hay endpoints de reranker configurados.")
        if endpoint_id is None:
            return self.reranker_endpoints[0]
        for ep in self.reranker_endpoints:
            if ep["id"] == endpoint_id:
                return ep
        raise KeyError(
            f"Endpoint de reranker '{endpoint_id}' no configurado. "
            f"Disponibles: {[e['id'] for e in self.reranker_endpoints]}"
        )

    def llm_endpoint(self, endpoint_id: str | None) -> dict:
        """Devuelve un endpoint de LLM por id, o el primero como default."""
        if not self.llm_endpoints:
            raise RuntimeError("No hay endpoints de LLM configurados.")
        if endpoint_id is None:
            return self.llm_endpoints[0]
        for ep in self.llm_endpoints:
            if ep["id"] == endpoint_id:
                return ep
        raise KeyError(
            f"Endpoint de LLM '{endpoint_id}' no configurado. "
            f"Disponibles: {[e['id'] for e in self.llm_endpoints]}"
        )


def get_settings() -> Settings:
    """Factory para obtener settings. lru_cache garantiza una sola instancia."""
    return Settings()
