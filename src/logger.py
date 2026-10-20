"""
logger.py
=========
Configuracion unica de logging.

Se usa logging (y no print) para que cada etapa registre hora, modulo y
nivel, y para poder redirigir la traza a un archivo de auditoria sin tocar
el codigo de los scrapers.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_FORMATO = "%(asctime)s | %(levelname)-7s | %(name)-22s | %(message)s"
_FECHA = "%H:%M:%S"
_configurado = False


def configurar_logging(nivel: int = logging.INFO, archivo: Path | None = None) -> None:
    """Inicializa el logging global una sola vez (idempotente)."""
    global _configurado
    if _configurado:
        return

    manejadores: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if archivo is not None:
        archivo.parent.mkdir(parents=True, exist_ok=True)
        manejadores.append(logging.FileHandler(archivo, encoding="utf-8"))

    logging.basicConfig(level=nivel, format=_FORMATO, datefmt=_FECHA, handlers=manejadores)
    for ruidoso in ("urllib3", "selenium", "scrapy", "asyncio"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)
    _configurado = True


def get_logger(nombre: str) -> logging.Logger:
    """
    Devuelve un logger del proyecto.

    Todos los loggers llevan el prefijo ``ea1.`` para no colisionar con los
    loggers de librerias de terceros que se silencian en `configurar_logging`
    (por ejemplo, el paquete `selenium`).
    """
    configurar_logging()
    return logging.getLogger(f"ea1.{nombre}")
