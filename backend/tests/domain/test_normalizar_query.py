"""Tests: NormalizarQuery — limpieza de ruido en el prefijo de la consulta.

Fase 1 (bug sala): el saludo/muletilla inicial degradaba la búsqueda densa
y dejaba fragmentos relevantes (Art. 115 CPE) fuera del top-k final.
Capa A (anti-overfit): corrección de typos por edit-distance contra el
vocabulario del corpus en vez de un diccionario fijo.
"""

from __future__ import annotations

import pytest

from src.domain.services.normalizar_query import (
    _distancia_levenshtein,
    normalizar_query,
)

_VOCAB = frozenset(
    {
        "principio",
        "proceso",
        "procesal",
        "penal",
        "militar",
        "sentencia",
        "apelacion",
        "debido",
        "prescripcion",
        "juzgado",
        "recurso",
        "competencia",
        "expediente",
        "consulta",
    }
)


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        # Saludos iniciales
        (
            "hola cual es el prinincipio del debido proceso y de qué trata",  # noqa: E501
            "principio del debido proceso y de qué trata",
        ),
        ("ola cual es el principio del debido proceso", "principio del debido proceso"),
        ("buenos días, que es el debido proceso", "debido proceso"),
        ("holaa quiero saber que dice el articulo 115", "que dice el articulo 115"),
        ("saludos, me podrias decir que es la prescripcion", "prescripcion"),
        # Muletillas
        ("por favor, cuando prescribe la accion penal", "prescribe la accion penal"),
        ("me podrias decir que dice el cpm", "que dice el cpm"),
        ("quisiera saber si el auto de vista es apelable", "si el auto de vista es apelable"),
        # Interrogativas vacías que dejan el sustantivo
        ("cual es el principio del debido proceso", "principio del debido proceso"),
        ("que es el debido proceso", "debido proceso"),
        ("de que trata el codigo penal militar", "codigo penal militar"),
        ("en que consiste la consulta de oficio", "consulta de oficio"),
        # Múltiples capas
        ("hola cual es el principio del debido proceso", "principio del debido proceso"),
        # Typos de términos jurídicos frecuentes
        ("hola cual es el prinincipio del debido proceso", "principio del debido proceso"),
        ("cual es el proseso penal militar", "proceso penal militar"),
        ("sentensia absolutoria en apelacion", "sentencia absolutoria en apelacion"),
        # Caso de la sala (query real: saludo + muletilla + typo + sufijo)
        (
            "hola cual es el prinincipio del debido proceso y de qué trata",  # noqa: E501
            "principio del debido proceso y de qué trata",
        ),
    ],
)
def test_normalizar_query_quita_prefijo_ruidoso(entrada: str, esperado: str) -> None:
    assert normalizar_query(entrada) == esperado


def test_normalizar_query_conserva_original_si_nucleo_es_corto() -> None:
    assert normalizar_query("hola") == "hola"
    assert normalizar_query("buenos dias") == "buenos dias"


def test_normalizar_query_no_toca_query_sin_ruido() -> None:
    q = "auto de vista consulta de oficio"
    assert normalizar_query(q) == q


def test_normalizar_query_cadena_vacia() -> None:
    assert normalizar_query("") == ""
    assert normalizar_query("   ") == "   "


# ---------- Capa A: edit-distance contra el vocabulario ----------


@pytest.mark.parametrize(
    ("a", "b", "max_dist", "esperado"),
    [
        ("principio", "principio", 2, 0),
        ("prinincipio", "principio", 2, 2),
        ("proseso", "proceso", 2, 1),
        ("sentensia", "sentencia", 2, 1),
        ("xyz", "principio", 2, 3),  # muy distinto -> corta con max_dist+1
        ("pepe", "principio", 1, 2),  # longitudes difieren > max_dist -> corta
    ],
)
def test_distancia_levenshtein_banda(a: str, b: str, max_dist: int, esperado: int) -> None:
    assert _distancia_levenshtein(a, b, max_dist) == esperado


def test_edit_distance_corrige_typo_con_vocabulario() -> None:
    assert normalizar_query("prinincipio del debido proceso", _VOCAB) == (
        "principio del debido proceso"
    )
    assert normalizar_query("cual es el proseso penal militar", _VOCAB) == ("proceso penal militar")
    assert normalizar_query("sentensia absolutoria en apelacion", _VOCAB) == (
        "sentencia absolutoria en apelacion"
    )


def test_edit_distance_no_corrige_palabra_desconocida_legitima() -> None:
    """Un apellido o término ajeno al corpus NO se corrige (no hay match claro)."""
    assert normalizar_query("el apellido Contreras en el expediente", _VOCAB) == (
        "el apellido Contreras en el expediente"
    )


def test_edit_distance_no_corrige_token_corto() -> None:
    """Tokens de <4 chars no se corrigen (falsos positivos)."""
    assert normalizar_query("que es dp", _VOCAB) == "que es dp"


def test_edit_distance_caso_sala_real() -> None:
    """Query real de la sala: saludo + muletilla + typo + sufijo."""
    resultado = normalizar_query(
        "hola cual es el prinincipio del debido proceso y de qué trata", _VOCAB
    )
    assert resultado == "principio del debido proceso y de qué trata"


def test_edit_distance_sin_vocabulario_usa_dict_fallback() -> None:
    """Sin vocabulario, el dict minimo sigue cubriendo los typos conocidos."""
    assert normalizar_query("prinincipio del debido proceso") == ("principio del debido proceso")


@pytest.mark.parametrize(
    "consulta,esperado",
    [
        ("dime sobre el articulo del debido proceso explicalo", "debido proceso"),
        ("Explícame el artículo del debido proceso", "debido proceso"),
        ("cuéntame sobre la presunción de inocencia", "presunción de inocencia"),
        (
            "háblame de la prescripción de la acción penal, explícalo",
            "prescripción de la acción penal",
        ),
    ],
)
def test_quita_imperativos_y_articulo_generico(consulta, esperado):
    assert normalizar_query(consulta) == esperado


def test_conserva_articulo_con_numero():
    """«artículo 115» es dato de búsqueda: no se debe quitar."""
    assert "115" in normalizar_query("dime que dice el articulo 115 de la CPE")


def test_las_tildes_no_parten_palabras_con_vocabulario():
    """`[a-zA-Z0-9]+` partía 'presunción' en 'presunci'+'n' y corregía el trozo."""
    vocab = frozenset({"presuncion", "inocencia"})
    assert "presunción" in normalizar_query("presunción de inocencia", vocab)
