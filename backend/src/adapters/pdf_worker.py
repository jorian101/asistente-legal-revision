"""Worker de extraccion de PDF nativo en un subproceso aislado (Regla 5 / F-08).

PyMuPDF es una libreria nativa: un PDF malformado o malicioso puede provocar un
fallo de memoria que mate el proceso. Ejecutarla aqui hace que solo muera este
worker; la API recibe un error controlado.

Uso:  python -m src.adapters.pdf_worker <ruta> <max_size_bytes> <paginas_json>

Protocolo (el adapter en file_extractor.py lo interpreta):
- exit 0: stdout = JSON {"escaneo": bool, "resultado": {...} | null}
- exit 2: validacion rechazada (ValueError); el mensaje va a stderr
- exit 3: la extraccion fallo (archivo corrupto, etc.); el mensaje va a stderr
- cualquier otro codigo o una senal: el worker murio (fallo nativo, OOM, kill)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

SALIDA_VALIDACION = 2
SALIDA_EXTRACCION = 3
LIMITE_MEMORIA_BYTES = 4 * 1024**3  # tope de espacio de direcciones del worker


def _limitar_memoria() -> None:
    """Un PDF hostil no debe poder agotar la RAM del servidor (solo Linux/macOS)."""
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (LIMITE_MEMORIA_BYTES, LIMITE_MEMORIA_BYTES))
    except (ImportError, ValueError, OSError):
        pass


def main(argv: list[str]) -> int:
    ruta, max_size, paginas = Path(argv[1]), int(argv[2]), json.loads(argv[3])
    _limitar_memoria()

    from src.adapters.file_extractor import HybridFileExtractor

    try:
        resultado = HybridFileExtractor(max_size_bytes=max_size)._extraer_nativo_sync(ruta, paginas)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return SALIDA_VALIDACION
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de la libreria => error controlado
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return SALIDA_EXTRACCION

    salida = {"escaneo": resultado is None, "resultado": asdict(resultado) if resultado else None}
    sys.stdout.write(json.dumps(salida))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
