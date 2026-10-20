"""
normalizers.py
==============
Funciones PURAS de normalizacion de texto y numeros.

No dependen de requests, BeautifulSoup, Selenium ni Scrapy: reciben texto y
devuelven tipos de Python. Esto permite reutilizarlas en los tres metodos de
extraccion y probarlas con tests unitarios (ver tests/test_normalizers.py).

Autor: Jesus Gonzalez
"""

from __future__ import annotations

import re
from typing import Optional

_MONEDA_POR_SIMBOLO = {"$": "USD", "€": "EUR", "£": "GBP"}
_PATRON_NUMERO = re.compile(r"\d[\d.,]*")
_PATRON_ESTRELLAS = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:out of|de)\s*5", re.IGNORECASE)
_PATRON_RESENAS = re.compile(r"([\d.,]+)\s*([KkMm])?")


def limpiar_texto(valor: Optional[str]) -> Optional[str]:
    """Colapsa espacios, quita NBSP y recorta. Devuelve None si queda vacio."""
    if valor is None:
        return None
    limpio = re.sub(r"\s+", " ", valor.replace("\u00a0", " ")).strip()
    return limpio or None


def parse_precio(texto: Optional[str]) -> tuple[Optional[float], Optional[str]]:
    """
    Convierte un texto de precio en ``(valor, moneda)``.

    Ejemplos
    --------
    >>> parse_precio("$499.99")
    (499.99, 'USD')
    >>> parse_precio("COP1.809.393")
    (1809393.0, 'COP')
    >>> parse_precio("$79.99 - $99.99")
    (79.99, 'USD')
    >>> parse_precio("No disponible")
    (None, None)
    """
    limpio = limpiar_texto(texto)
    if not limpio:
        return None, None

    mayusculas = limpio.upper()
    if "COP" in mayusculas:
        moneda = "COP"
    elif "US$" in mayusculas or "$" in limpio:
        moneda = "USD"
    else:
        moneda = next(
            (iso for simbolo, iso in _MONEDA_POR_SIMBOLO.items() if simbolo in limpio),
            None,
        )

    coincidencia = _PATRON_NUMERO.search(limpio)
    if not coincidencia:
        return None, moneda
    crudo = coincidencia.group(0)

    if moneda == "COP":
        crudo = crudo.replace(".", "").replace(",", ".")
    elif "," in crudo and "." in crudo:
        crudo = crudo.replace(",", "")
    elif crudo.count(",") == 1 and len(crudo.split(",")[-1]) == 2:
        crudo = crudo.replace(",", ".")
    else:
        crudo = crudo.replace(",", "")

    try:
        return round(float(crudo), 2), moneda
    except ValueError:
        return None, moneda


def parse_calificacion(texto: Optional[str]) -> Optional[float]:
    """
    Extrae la calificacion en escala 0-5.

    >>> parse_calificacion("4.4 out of 5 stars")
    4.4
    >>> parse_calificacion("4,4 de 5 estrellas")
    4.4
    """
    limpio = limpiar_texto(texto)
    if not limpio:
        return None
    coincidencia = _PATRON_ESTRELLAS.search(limpio) or re.search(r"(\d+[.,]\d+)", limpio)
    if not coincidencia:
        return None
    return float(coincidencia.group(1).replace(",", "."))


def parse_resenas(texto: Optional[str]) -> Optional[int]:
    """
    Convierte el conteo de resenas a entero, expandiendo sufijos K/M.

    >>> parse_resenas("(2.1K)")
    2100
    >>> parse_resenas("6,135 ratings")
    6135
    """
    limpio = limpiar_texto(texto)
    if not limpio:
        return None
    coincidencia = _PATRON_RESENAS.search(limpio.replace(",", ""))
    if not coincidencia:
        return None
    valor = float(coincidencia.group(1))
    sufijo = (coincidencia.group(2) or "").upper()
    factor = {"K": 1_000, "M": 1_000_000}.get(sufijo, 1)
    return int(round(valor * factor))


def parse_entero(texto: Optional[str]) -> Optional[int]:
    """
    Extrae el primer entero de un texto de especificacion.

    >>> parse_entero("128 GB")
    128
    """
    limpio = limpiar_texto(texto)
    if not limpio:
        return None
    coincidencia = re.search(r"\d+", limpio)
    return int(coincidencia.group(0)) if coincidencia else None


def parse_decimal(texto: Optional[str]) -> Optional[float]:
    """
    Extrae el primer decimal de un texto de especificacion.

    >>> parse_decimal("6.7 inches")
    6.7
    """
    limpio = limpiar_texto(texto)
    if not limpio:
        return None
    coincidencia = re.search(r"\d+(?:[.,]\d+)?", limpio)
    return float(coincidencia.group(0).replace(",", ".")) if coincidencia else None


def calcular_descuento(precio: Optional[float], precio_lista: Optional[float]) -> Optional[float]:
    """
    Descuento porcentual respecto al precio de lista.

    >>> calcular_descuento(80.0, 100.0)
    20.0
    """
    if not precio or not precio_lista or precio_lista <= precio:
        return None
    return round((1 - precio / precio_lista) * 100, 1)


def limpiar_marca(valor: Optional[str]) -> Optional[str]:
    """
    Normaliza la marca a partir de textos como 'Visit the Samsung Store'.

    >>> limpiar_marca("Visit the Samsung Store")
    'Samsung'
    >>> limpiar_marca("Brand: Samsung")
    'Samsung'
    """
    limpio = limpiar_texto(valor)
    if not limpio:
        return None
    limpio = re.sub(r"^(Brand|Marca)\s*:\s*", "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"^Visit the\s+", "", limpio, flags=re.IGNORECASE)
    limpio = re.sub(r"\s+Store$", "", limpio, flags=re.IGNORECASE)
    return limpio or None


def inferir_marca_desde_titulo(titulo: Optional[str]) -> Optional[str]:
    """Usa la primera palabra del titulo como aproximacion de la marca."""
    limpio = limpiar_texto(titulo)
    return limpio.split()[0] if limpio else None
