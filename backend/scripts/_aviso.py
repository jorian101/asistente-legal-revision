"""Aviso comun de los scripts que modifican las bases de datos."""

MENSAJE = "BD modificada: revisá la población de la base antes de continuar."


def aviso_poblar() -> None:
    print(MENSAJE)
