"""Tests F3: ConstructorMemoriaConversacional.

Cobertura:
- Ventana verbatim de turnos recientes, orden cronologico, presupuesto
- Privacidad: solo mensajes del propietario (Regla 4/5) y solo del chat activo
- Borradores: contenido ACTUAL de BD solo si la consulta menciona "borrador"
"""

from __future__ import annotations

from src.application.services.memoria_conversacional import (
    ConstructorMemoriaConversacional,
    truncar_por_oracion,
)
from src.domain.entities.borrador import Borrador
from src.domain.entities.mensaje_chat import MensajeChat


def _mensaje(pos: int, tipo: str, contenido: str, usuario_id: int = 3) -> MensajeChat:
    return MensajeChat(
        id=pos,
        chat_id=1,
        usuario_id=usuario_id,
        tipo=tipo,
        contenido=contenido,
        razonamiento="",
        estado="activo",
        posicion=pos,
        metadatos={},
    )


class _FakeMensajeRepo:
    def __init__(self, chats: dict[int, list[MensajeChat]]) -> None:
        self._chats = chats

    async def listar_por_chat(
        self,
        chat_id: int,
        usuario_id: int,
        pagina: int = 1,
        por_pagina: int = 50,
    ) -> tuple[list[MensajeChat], int]:
        items = [m for m in self._chats.get(chat_id, []) if m.usuario_id == usuario_id]
        items.sort(key=lambda m: m.posicion or 0)
        return items, len(items)


class _FakeBorradorRepo:
    def __init__(self, por_chat: dict[tuple[int, int], Borrador]) -> None:
        self._por_chat = por_chat

    async def obtener_por_chat(self, chat_id: int, propietario_id: int) -> Borrador | None:
        return self._por_chat.get((chat_id, propietario_id))


def _constructor(chats, borradores=None, max_chars=6000):
    return ConstructorMemoriaConversacional(
        mensaje_repo=_FakeMensajeRepo(chats),
        borrador_repo=_FakeBorradorRepo(borradores or {}),
        max_chars=max_chars,
    )


async def test_sin_mensajes_devuelve_vacio() -> None:
    memoria = _constructor({})
    assert await memoria.construir(1, 3, "hola") == ""


async def test_orden_cronologico_y_roles() -> None:
    chats = {
        1: [
            _mensaje(1, "user", "Cual es la norma de competencia?"),
            _mensaje(2, "bot", "El CPPM art 184."),
        ]
    }
    texto = await _constructor(chats).construir(1, 3, "gracias")
    assert texto.index("Usuario:") < texto.index("Asistente:")
    assert "norma de competencia" in texto


async def test_privacidad_usuario_ajeno_no_ve_nada() -> None:
    chats = {1: [_mensaje(1, "user", "secreto del vocal")]}

    texto = await _constructor(chats).construir(1, usuario_id=999, consulta_actual="x")

    assert texto == ""


async def test_contaminacion_cruzada_entre_chats() -> None:
    chats = {
        1: [_mensaje(1, "user", "contexto del chat A")],
        2: [_mensaje(1, "user", "contexto del chat B")],
    }

    texto_b = await _constructor(chats).construir(2, 3, "seguimos")

    assert "chat A" not in texto_b
    assert "chat B" in texto_b


async def test_presupuesto_deja_fuera_turnos_viejos() -> None:
    viejos = [_mensaje(i, "user", f"turno viejo numero {i}") for i in range(2, 20)]
    viejos.insert(0, _mensaje(1, "user", "PRIMER MENSAJE HISTORICO"))
    recientes = [_mensaje(20, "user", "turno reciente"), _mensaje(21, "bot", "respuesta final")]
    chats = {1: viejos + recientes}

    texto = await _constructor(chats, max_chars=120).construir(1, 3, "y ahora?")

    assert "turno reciente" in texto
    assert "PRIMER MENSAJE HISTORICO" not in texto
    assert "respuesta final" in texto


async def test_mencion_borrador_inyecta_contenido_actual_editado() -> None:
    chats = {
        1: [_mensaje(1, "user", "genera el auto"), _mensaje(2, "bot", "[borrador v1 obsoleto]")]
    }
    borrador = Borrador(
        id=7,
        expediente_id=1,
        propietario_id=3,
        tipo="proyecto_auto_vista_consulta",
        contenido="CONSIDERANDO version editada y vigente",
        estado="borrador",
        chat_id=1,
        mensaje_id=2,
    )
    memoria = _constructor(chats, {(1, 3): borrador})

    texto = await memoria.construir(1, 3, "mejora el borrador")

    assert "version editada y vigente" in texto
    assert "[BORRADOR ACTUAL DE ESTE CHAT]" in texto


async def test_mensaje_largo_se_corta_en_frontera_de_oracion() -> None:
    """Truncado por oracion: nunca deja texto roto a mitad de frase en memoria.

    Regresion anti-poisoning: un corte ciego ('...or el accionante') el LLM
    lo lee como si fuera real.
    """
    relleno = "palabra de relleno sin valor. " * 40  # >800 chars
    chats = {
        1: [
            _mensaje(
                1,
                "bot",
                "Primera oracion completa. "
                + relleno
                + "Cola que se corta a la mitad y jamas debe aparecer.",
            )
        ]
    }
    texto = await _constructor(chats, max_chars=6000).construir(1, 3, "x")
    assert "Primera oracion completa." in texto
    assert "mitad" not in texto  # la cola cortada no entra a memoria

    # Sin frontera dentro del limite: corte duro marcado con "…".
    assert truncar_por_oracion("a" * 900, 800) == "a" * 800 + "…"
    # Texto corto: intacto.
    assert truncar_por_oracion("hola.", 800) == "hola."


async def test_sin_mencion_no_trae_borrador() -> None:
    chats = {1: [_mensaje(1, "user", "hola")]}
    borrador = Borrador(
        id=7,
        expediente_id=1,
        propietario_id=3,
        tipo="sugerencia_argumentacion",
        contenido="contenido privado",
        estado="borrador",
        chat_id=1,
        mensaje_id=None,
    )
    memoria = _constructor(chats, {(1, 3): borrador})

    texto = await memoria.construir(1, 3, "que tal")

    assert "contenido privado" not in texto
