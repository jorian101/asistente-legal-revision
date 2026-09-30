"""Smoke E2E reanudable: Fase 0 (infra + regresión del blocker) y Fase 1 (backend).

Reemplaza el smoke manual con curl que abortó el plan E2E de 2026-08-12. El
plan vive en `docs/planes/verificacion-e2e-plan-v1.md` y cada paso de aquí
corresponde a un paso de ese documento.

Requiere el stack arriba:
    pnpm dev:db && pnpm db:migrate && pnpm seed && pnpm dev:api

Uso:
    cd backend && uv run python scripts/smoke_e2e.py
    cd backend && uv run python scripts/smoke_e2e.py --sin-llm
    cd backend && uv run python scripts/smoke_e2e.py --consultas 10

Exit code: 0 = todos los pasos OK (los SKIP no cuentan como fallo); 1 = al
menos un FAIL.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import asyncpg  # noqa: E402
import httpx  # noqa: E402

from src.config import get_settings  # noqa: E402

# Cuentas QA del seed (email=None -> login legacy, sin 2FA).
QA = {
    "admin": ("qaadmin", "qasecret123"),
    "operador": ("qaop", "qasecret123"),
    "supervisor": ("qasup", "qasecret123"),
}
PASSWORD_QA = "qasecret123"


@dataclass
class Resultado:
    """Resultado de un paso del smoke (OK / FAIL / SKIP + evidencia)."""

    paso: str
    nombre: str
    estado: str = "OK"
    detalle: str = ""
    extra: dict = field(default_factory=dict)


class Smoke:
    """Ejecuta el smoke contra un backend vivo y acumula resultados."""

    def __init__(self, base_url: str, consultas: int, sin_llm: bool) -> None:
        self.base_url = base_url.rstrip("/")
        self.consultas = consultas
        self.sin_llm = sin_llm
        self.resultados: list[Resultado] = []
        self.tokens: dict[str, str] = {}
        self.expediente_id: int | None = None
        self.historial_id: int | None = None
        # Paso en curso: si algo explota fuera de lo previsto, el reporte dice dónde.
        self.paso_actual = "inicio"

    # ----- infra de reporte -----

    def ok(self, paso: str, nombre: str, detalle: str = "", **extra) -> None:
        self.resultados.append(Resultado(paso, nombre, "OK", detalle, extra))

    def fail(self, paso: str, nombre: str, detalle: str, **extra) -> None:
        self.resultados.append(Resultado(paso, nombre, "FAIL", detalle, extra))

    def skip(self, paso: str, nombre: str, detalle: str) -> None:
        self.resultados.append(Resultado(paso, nombre, "SKIP", detalle, {}))

    def hdr(self, rol: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.tokens[rol]}"}

    # ----- helpers HTTP -----

    async def login(self, client: httpx.AsyncClient, rol: str) -> None:
        carnet, password = QA[rol]
        r = await client.post("/auth/login", json={"carnet": carnet, "password": password})
        if r.status_code != 200:
            raise RuntimeError(f"login {carnet} -> {r.status_code} {r.text[:200]}")
        body = r.json()
        if "access_token" not in body:
            # 2FA activo: las cuentas QA no deberían tener email.
            raise RuntimeError(f"login {carnet} no devolvió token: {body}")
        self.tokens[rol] = body["access_token"]

    async def idle_in_transaction(self) -> int:
        """Conexiones PG en `idle in transaction` (el bug del reporte v1)."""
        settings = get_settings()
        dsn = settings.postgres_url_async.replace("postgresql+asyncpg://", "postgresql://")
        conn = await asyncpg.connect(dsn)
        try:
            return int(
                await conn.fetchval(
                    "SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction'"
                )
            )
        finally:
            await conn.close()

    # ----- Fase 0 -----

    async def fase_0(self, client: httpx.AsyncClient) -> None:
        self.paso_actual = "0.1 Backend vivo"
        r = await client.get("/openapi.json")
        if r.status_code == 200:
            self.ok("0.1", "Backend vivo (openapi)", "GET /openapi.json = 200")
        else:
            self.fail("0.1", "Backend vivo (openapi)", f"HTTP {r.status_code}")
            raise RuntimeError("backend no responde: se cancela el smoke")

        self.paso_actual = "0.2 Login QA"
        for rol in QA:
            try:
                await self.login(client, rol)
                self.ok("0.2", f"Login {rol}", f"carnet={QA[rol][0]}")
            except Exception as exc:  # noqa: BLE001 - reporte, no control de flujo
                self.fail("0.2", f"Login {rol}", str(exc))

        if "admin" not in self.tokens:
            raise RuntimeError("sin token admin no se pueden verificar conteos")

        self.paso_actual = "0.3 Conteos base"
        r = await client.get("/admin/corpus/normas", headers=self.hdr("admin"))
        if r.status_code == 200 and len(r.json()) > 0:
            self.ok(
                "0.3",
                "Conteos base (normas)",
                f"{len(r.json())} normas activas",
            )
        else:
            self.fail(
                "0.3",
                "Conteos base (normas)",
                f"HTTP {r.status_code}, body={r.text[:120]}",
            )

        r = await client.get("/admin/metricas/salud", headers=self.hdr("admin"))
        if r.status_code == 200:
            salud = r.json()
            if salud.get("qdrant_ok"):
                self.ok(
                    "0.3",
                    "Conteos base (Qdrant)",
                    f"qdrant_ok, {salud.get('qdrant_puntos')} puntos, "
                    f"postgres_ok={salud.get('postgres_ok')}",
                )
            else:
                self.fail("0.3", "Conteos base (Qdrant)", f"salud={salud}")
        else:
            self.fail("0.3", "Conteos base (Qdrant)", f"HTTP {r.status_code}")

        # 0.5 Config RAG activa: sin esto la corrida no es reproducible.
        self.paso_actual = "0.5 Config RAG activa"
        rr = await client.get(
            "/admin/corpus/configuracion-rag/reranker-endpoint",
            headers=self.hdr("admin"),
        )
        ll = await client.get(
            "/admin/corpus/configuracion-rag/llm-endpoint",
            headers=self.hdr("admin"),
        )
        if ll.status_code != 200:
            self.fail(
                "0.5",
                "Config RAG activa",
                f"llm HTTP {ll.status_code}, reranker HTTP {rr.status_code}",
            )
        elif rr.status_code == 200:
            self.ok(
                "0.5",
                "Config RAG activa",
                f"reranker={rr.json().get('id')}, llm={ll.json().get('id')}",
            )
        elif rr.status_code == 400:
            # Sin RERANKER_ENDPOINTS en el .env: el pipeline degrada sin fase 3.
            # Es una configuración válida (y la recomendada en CPU), no un fallo.
            self.ok(
                "0.5",
                "Config RAG activa",
                f"sin reranker (degradado a fases 1-2-4), llm={ll.json().get('id')}",
            )
        else:
            self.fail(
                "0.5",
                "Config RAG activa",
                f"reranker HTTP {rr.status_code}, llm HTTP {ll.status_code}",
            )

        # 0.4 Regresión del blocker: N consultas y cero transacciones colgadas.
        self.paso_actual = "0.4 idle-in-transaction"
        rol_rw = "supervisor" if "supervisor" in self.tokens else "admin"
        errores: list[str] = []
        for i in range(self.consultas):
            r = await client.post(
                "/consultas/",
                json={"consulta": f"plazo de radicatoria (smoke {i})", "alcance": "todo"},
                headers=self.hdr(rol_rw),
            )
            if r.status_code != 200:
                errores.append(f"#{i} -> HTTP {r.status_code}")
                if len(errores) >= 3:
                    break
        colgadas = await self.idle_in_transaction()
        detalle = f"{self.consultas} POST /consultas/; idle in transaction = {colgadas}"
        if not errores and colgadas == 0:
            self.ok("0.4", "Regresión idle-in-transaction", detalle)
        else:
            self.fail(
                "0.4",
                "Regresión idle-in-transaction",
                f"{detalle}; errores={errores[:3]}",
            )

    # ----- Fase 1 -----

    async def fase_1(self, client: httpx.AsyncClient) -> None:
        # 1.3 Corpus
        self.paso_actual = "1.3 Corpus"
        r = await client.get(
            "/admin/corpus/fragmentos",
            params={"pagina": 1, "por_pagina": 5},
            headers=self.hdr("admin"),
        )
        if r.status_code == 200:
            total = r.json().get("total", 0)
            self.ok("1.3", "Corpus: normas + fragmentos", f"{total} segmentos en PG")
        else:
            self.fail("1.3", "Corpus: normas + fragmentos", f"HTTP {r.status_code}")

        # 1.6 Expedientes (antes de 1.4: da el expediente_id)
        self.paso_actual = "1.6 Expedientes"
        rol_consulta = "supervisor"
        r = await client.get("/expedientes/", headers=self.hdr(rol_consulta))
        expedientes = r.json().get("items", []) if r.status_code == 200 else []
        if r.status_code == 200 and expedientes:
            self.expediente_id = int(expedientes[0]["id"])
            self.ok(
                "1.6",
                "Expedientes: listar",
                f"{len(expedientes)} expedientes; se usa id={self.expediente_id}",
            )
            r2 = await client.get(
                f"/expedientes/{self.expediente_id}/historial",
                headers=self.hdr(rol_consulta),
            )
            if r2.status_code == 200:
                obras = len(r2.json().get("obras", []))
                self.ok("1.6", "Expedientes: historial de obras", f"{obras} obras")
            else:
                self.fail("1.6", "Expedientes: historial de obras", f"HTTP {r2.status_code}")
        else:
            self.fail(
                "1.6",
                "Expedientes: listar",
                f"HTTP {r.status_code}, body={r.text[:120]}",
            )

        # 1.4 Consulta RAG con expediente -> fuentes > 0
        self.paso_actual = "1.4 Consulta RAG"
        if self.expediente_id is None:
            self.fail("1.4", "Consulta RAG con expediente", "sin expediente_id (1.6 falló)")
        else:
            r = await client.post(
                "/consultas/",
                json={
                    "consulta": "cuales son los hechos y normas aplicables",
                    "expediente_id": self.expediente_id,
                    "alcance": "todo",
                },
                headers=self.hdr(rol_consulta),
            )
            if r.status_code != 200:
                self.fail(
                    "1.4",
                    "Consulta RAG con expediente",
                    f"HTTP {r.status_code}, body={r.text[:200]}",
                )
            else:
                body = r.json()
                fuentes = len(body.get("fragmentos", []))
                detalle = (
                    f"{fuentes} fuentes, tipo={body.get('tipo_respuesta')}, "
                    f"latencia={body.get('latencia_ms')}ms"
                )
                if fuentes > 0:
                    self.ok("1.4", "Consulta RAG con expediente", detalle)
                else:
                    self.fail(
                        "1.4",
                        "Consulta RAG con expediente",
                        f"0 fuentes ({detalle})",
                    )
                self.historial_id = body.get("historial_id")

        # 1.5 LLM streaming
        self.paso_actual = "1.5 LLM streaming"
        if self.sin_llm:
            self.skip("1.5", "LLM streaming", "--sin-llm (no se gasta tokens)")
        elif self.expediente_id is None:
            self.fail("1.5", "LLM streaming", "sin expediente_id (1.6 falló)")
        else:
            await self._paso_llm(client, rol_consulta)

        # 1.7 Borradores
        self.paso_actual = "1.7 Borradores"
        r = await client.get("/borradores/mios", headers=self.hdr("operador"))
        if r.status_code == 200:
            self.ok(
                "1.7",
                "Borradores: listar",
                f"{len(r.json())} borradores del operador QA",
            )
        else:
            self.fail(
                "1.7",
                "Borradores: listar",
                f"HTTP {r.status_code}, body={r.text[:120]}",
            )

        # 1.8 Métricas
        self.paso_actual = "1.8 Métricas"
        r = await client.get("/admin/metricas/contexto", headers=self.hdr("admin"))
        if r.status_code == 200:
            self.ok("1.8", "Métricas de contexto", "GET /admin/metricas/contexto = 200")
        else:
            self.fail("1.8", "Métricas de contexto", f"HTTP {r.status_code}")

        # 1.9 Seguridad
        self.paso_actual = "1.9 Seguridad"
        r = await client.get("/admin/corpus/normas", headers=self.hdr("operador"))
        if r.status_code == 403:
            self.ok("1.9", "Seguridad: operador no entra al admin de corpus", "403")
        else:
            self.fail(
                "1.9",
                "Seguridad: operador no entra al admin de corpus",
                f"HTTP {r.status_code} (se esperaba 403)",
            )
        await self._paso_regla_1()

    async def _paso_llm(self, client: httpx.AsyncClient, rol: str) -> None:
        """Streaming real del LLM: al menos un token + modelo persistido."""
        chunks = 0
        caracteres = 0
        try:
            async with client.stream(
                "POST",
                "/consultas/responder",
                json={
                    "consulta": "resumí en una frase el estado del proceso",
                    "expediente_id": self.expediente_id,
                    "alcance": "todo",
                },
                headers=self.hdr(rol),
                timeout=180.0,
            ) as r:
                if r.status_code != 201:
                    cuerpo = (await r.aread()).decode("utf-8", "replace")[:200]
                    self.fail(
                        "1.5",
                        "LLM streaming",
                        f"HTTP {r.status_code}, body={cuerpo}",
                    )
                    return
                historial_hdr = r.headers.get("X-Historial-Id")
                if historial_hdr:
                    self.historial_id = int(historial_hdr)
                async for chunk in r.aiter_text():
                    chunks += 1
                    caracteres += len(chunk)
        except Exception as exc:  # noqa: BLE001 - reporte
            self.fail("1.5", "LLM streaming", f"excepción: {exc}")
            return

        if chunks == 0:
            self.fail("1.5", "LLM streaming", "stream vacío (0 chunks)")
            return
        self.ok(
            "1.5",
            "LLM streaming",
            f"{chunks} chunks / {caracteres} chars (historial={self.historial_id})",
        )

        if self.historial_id is None:
            return
        r = await client.get(f"/consultas/historial/{self.historial_id}", headers=self.hdr(rol))
        if r.status_code != 200:
            self.fail(
                "1.5",
                "LLM: modelo persistido",
                f"HTTP {r.status_code} al leer el historial",
            )
            return
        modelo = r.json().get("modelo_llm")
        if modelo:
            self.ok("1.5", "LLM: modelo persistido", f"modelo_llm={modelo}")
        else:
            self.fail("1.5", "LLM: modelo persistido", "modelo_llm vacío")

    async def _paso_regla_1(self) -> None:
        """Regla 1 (Trail of Bits): aislamiento de Qdrant en docker-compose."""
        test = (
            Path(__file__).resolve().parents[1] / "tests/security/test_regla1_qdrant_isolation.py"
        )
        if not test.exists():
            self.skip("1.9", "Regla 1 (Qdrant aislado)", "test no encontrado")
            return
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pytest",
            str(test),
            "-q",
            "--no-cov",
            cwd=str(test.parents[2]),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await proc.communicate()
        salida = out.decode("utf-8", "replace").strip().splitlines()
        ultimo = salida[-1] if salida else ""
        if proc.returncode == 0:
            self.ok("1.9", "Regla 1 (Qdrant aislado)", ultimo[:120])
        else:
            self.fail("1.9", "Regla 1 (Qdrant aislado)", ultimo[:200])

    # ----- reporte -----

    def imprimir(self) -> int:
        ancho = max((len(r.nombre) for r in self.resultados), default=10)
        print("\n=== Smoke E2E (Fase 0 + Fase 1) ===")
        for r in self.resultados:
            print(f"[{r.estado:4}] {r.paso} {r.nombre.ljust(ancho)}  {r.detalle}")
        fail = [r for r in self.resultados if r.estado == "FAIL"]
        skip = [r for r in self.resultados if r.estado == "SKIP"]
        print(
            f"\nTotal: {len(self.resultados)} pasos | "
            f"OK {len(self.resultados) - len(fail) - len(skip)} | "
            f"FAIL {len(fail)} | SKIP {len(skip)}"
        )
        if fail:
            print("\nFallos:")
            for r in fail:
                print(f"  - {r.paso} {r.nombre}: {r.detalle}")
        return 1 if fail else 0


async def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke E2E (Fase 0 + Fase 1)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--consultas",
        type=int,
        default=5,
        help="POST /consultas/ de la regresión 0.4 (cada uno cuesta ~45s de pipeline)",
    )
    parser.add_argument("--sin-llm", action="store_true")
    args = parser.parse_args()

    smoke = Smoke(args.base_url, args.consultas, args.sin_llm)
    async with httpx.AsyncClient(base_url=smoke.base_url, timeout=60.0) as client:
        try:
            await smoke.fase_0(client)
            await smoke.fase_1(client)
        except Exception as exc:  # noqa: BLE001 - abortar con reporte parcial
            smoke.fail(
                "0.0",
                "Aborto del smoke",
                f"en {smoke.paso_actual}: {type(exc).__name__}: {exc}",
            )
    return smoke.imprimir()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
