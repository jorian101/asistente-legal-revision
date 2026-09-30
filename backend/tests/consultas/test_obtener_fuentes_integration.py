"""Integracion (BD real): enriquecimiento de /fuentes + Regla 5 sobre Postgres.

Corre SOLO con `make test-integration` (Docker arriba); excluido de
`make test-cov` por el marker. Es autocontenido: crea su propio expediente,
norma, dos obras (una publicada propia, una privada de OTRO usuario) y un
historial que las cita; ejerce el use case con los REPOS REALES y luego borra
todo. Verifica lo que los fakes del unit test no pueden:

  1. Que el JOIN resuelve de verdad tipo/fecha/expediente/nombre.
  2. Regla 5: una obra PRIVADA de otro usuario NO se enriquece (no se filtra).

Aislamiento: resuelve settings via `tests._bd_real.bd_real_asegurada`
(BD real con datos sembrados, nunca la BD `test` de conftest).
"""

from __future__ import annotations

import secrets

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.adapters.postgres.repos.consulta_historial_repo import (
    get_consulta_historial_repo,
)
from src.adapters.postgres.repos.expediente_repo import get_expediente_repo
from src.adapters.postgres.repos.norma_repo import get_norma_repo
from src.adapters.postgres.repos.obra_repo import get_obra_repo
from src.application.consultas.obtener_fuentes_historial import ejecutar
from src.domain.entities.consulta_historial import ConsultaHistorial
from src.domain.entities.expediente import Expediente
from src.domain.entities.norma import Norma
from src.domain.entities.obra import Obra

pytestmark = pytest.mark.integration


async def _dos_usuarios(session) -> tuple[int, int]:
    rows = (await session.execute(text("SELECT id FROM usuario ORDER BY id LIMIT 2"))).all()
    if len(rows) < 2:
        pytest.skip("se necesitan >=2 usuarios seedeados")
    return int(rows[0][0]), int(rows[1][0])


@pytest.mark.asyncio
async def test_obtener_fuentes_enriquece_y_respeta_regla5() -> None:
    from tests._bd_real import bd_real_asegurada

    with bd_real_asegurada() as settings:
        engine = create_async_engine(settings.postgres_url_async, poolclass=NullPool)
    sfactory = async_sessionmaker(engine, expire_on_commit=False)

    tag = secrets.token_hex(3).upper()  # id unico para no pisar ni chocar uniques
    ids: dict[str, int] = {}
    try:
        async with sfactory() as s:
            owner_u, other_u = await _dos_usuarios(s)

            norma = await get_norma_repo(s).save(
                Norma(
                    id=None,
                    nombre=f"Ley Probe {tag}",
                    abreviatura=f"ZPR{tag}",
                    tipo="ley_organica",
                    jerarquia="militar",
                )
            )
            exp = await get_expediente_repo(s).guardar(
                Expediente(
                    id=None,
                    numero_caso=f"Z-PROBE-{tag}",
                    tipo_proceso="consulta",
                    tribunal_origen="TPM",
                    procesado_nombre="Probe",
                    delito="d",
                    abierto_por=owner_u,
                )
            )
            # Obra PUBLICADA del dueño -> visible -> debe enriquecerse.
            obra_pub = await get_obra_repo(s).guardar(
                Obra(
                    id=None,
                    expediente_id=exp.id,
                    propietario_id=owner_u,
                    tipo_documento="auto_vista",
                    nombre_archivo="p.txt",
                    contenido_texto="VISTOS",
                    estado_visibilidad="publicado",
                    fecha_documento="2024",
                )
            )
            # Obra PRIVADA de OTRO usuario -> no visible para owner_u -> Regla 5.
            obra_priv = await get_obra_repo(s).guardar(
                Obra(
                    id=None,
                    expediente_id=exp.id,
                    propietario_id=other_u,
                    tipo_documento="sentencia",
                    nombre_archivo="q.txt",
                    contenido_texto="FALLO",
                    estado_visibilidad="privado",
                )
            )
            ids = {
                "norma": norma.id,
                "exp": exp.id,
                "obra_pub": obra_pub.id,
                "obra_priv": obra_priv.id,
            }

            fuentes = {
                "fragmentos": [
                    {
                        "id": obra_pub.id,
                        "norma_id": None,
                        "obra_id": obra_pub.id,
                        "expediente_id": exp.id,
                        "texto": "VISTOS",
                        "padre_ref_key": None,
                        "nivel_jerarquico": None,
                    },
                    {
                        "id": obra_priv.id,
                        "norma_id": None,
                        "obra_id": obra_priv.id,
                        "expediente_id": exp.id,
                        "texto": "FALLO",
                        "padre_ref_key": None,
                        "nivel_jerarquico": None,
                    },
                    {
                        "id": norma.id,
                        "norma_id": norma.id,
                        "obra_id": None,
                        "expediente_id": None,
                        "texto": "Art. 1",
                        "padre_ref_key": f"ZPR{tag}_1_MASTER",
                        "nivel_jerarquico": 4,
                    },
                ],
                "scores": [0.9, 0.8, 0.7],
            }
            hist = await get_consulta_historial_repo(s).guardar(
                ConsultaHistorial(
                    id=None,
                    expediente_id=exp.id,
                    usuario_id=owner_u,
                    pregunta=f"probe {tag}",
                    respuesta=None,
                    tipo_respuesta="consulta_simple",
                    fuentes_recuperadas=fuentes,
                    latencia_ms=10,
                    modelo_llm=None,
                )
            )
            ids["hist"] = hist.id

            resultado = await ejecutar(
                get_consulta_historial_repo(s),
                get_norma_repo(s),
                get_obra_repo(s),
                get_expediente_repo(s),
                historial_id=hist.id,
                usuario_id=owner_u,
            )

        assert resultado is not None
        por_obra = {f.obra_id: f for f in resultado.fragmentos if f.obra_id}
        norma_cita = next(f for f in resultado.fragmentos if f.norma_id)

        # 1) obrado publicado propio: enriquecido completo.
        pub = por_obra[obra_pub.id]
        assert pub.obra_tipo == "auto_vista"
        assert pub.expediente_numero == f"Z-PROBE-{tag}"
        assert pub.obra_fecha_documento == "2024"

        # 2) Regla 5: obrado privado ajeno NO se filtra (campos enriquecidos null).
        priv = por_obra[obra_priv.id]
        assert priv.obra_tipo is None
        assert priv.expediente_numero is None
        assert priv.obra_fecha_documento is None

        # 3) norma publica: nombre + abreviatura resueltos.
        assert norma_cita.norma_nombre == f"Ley Probe {tag}"
        assert norma_cita.norma_abreviatura == f"ZPR{tag}"
    finally:
        async with sfactory() as s:
            if ids.get("hist"):
                await s.execute(
                    text("DELETE FROM consulta_historial WHERE id=:i"), {"i": ids["hist"]}
                )
            for k in ("obra_pub", "obra_priv"):
                if ids.get(k):
                    await s.execute(text("DELETE FROM obra WHERE id=:i"), {"i": ids[k]})
            if ids.get("exp"):
                await s.execute(text("DELETE FROM expediente WHERE id=:i"), {"i": ids["exp"]})
            if ids.get("norma"):
                await s.execute(text("DELETE FROM norma WHERE id=:i"), {"i": ids["norma"]})
            await s.commit()
        await engine.dispose()
