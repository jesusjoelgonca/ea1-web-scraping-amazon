"""
bs4_scraper.py
==============
METODO 1 - Extraccion estatica con requests + BeautifulSoup.

Rol: descargar el HTML del buscador y de las fichas, y extraer los campos con
selectores CSS. Es el metodo mas rapido y ligero; su limite es que no ejecuta
JavaScript, por lo que depende de que el HTML llegue completo del servidor
(Amazon lo hace para las fichas de producto).

Los selectores estan aislados en `SELECTORES` y cada bloque de campos tiene su
propia funcion extractora, de modo que un cambio de maquetado se corrige en un
solo punto.

Uso:
    python -m src.scrapers.bs4_scraper
    python -m src.scrapers.bs4_scraper --solo-articulo

Autor: Jesus Gonzalez
"""

from __future__ import annotations

import argparse
import re
from dataclasses import replace
from typing import Any, Optional

from bs4 import BeautifulSoup, Tag

from ..config import TARGET, ScrapingTarget
from ..http_client import PoliteSession, load_cookies
from ..logger import get_logger
from ..models import Producto
from ..normalizers import (
    calcular_descuento,
    inferir_marca_desde_titulo,
    limpiar_marca,
    limpiar_texto,
    parse_calificacion,
    parse_decimal,
    parse_entero,
    parse_precio,
    parse_resenas,
)
from .base import BaseScraper

log = get_logger("bs4")

METODO = "beautifulsoup"

SELECTORES: dict[str, list[str]] = {
    "titulo": ["#productTitle"],
    "precio": [
        "#corePrice_feature_div span.a-price span.a-offscreen",
        "#corePrice_desktop span.a-price span.a-offscreen",
        "#apex_desktop span.a-price span.a-offscreen",
        "#price_inside_buybox",
        "#priceblock_ourprice",
        "#priceblock_dealprice",
    ],
    "precio_lista": [
        "span.basisPrice span.a-offscreen",
        "#corePrice_feature_div span.a-price.a-text-price span.a-offscreen",
        "#listPrice",
    ],
    "calificacion": ["#acrPopover"],
    "resenas": ["#acrCustomerReviewText"],
    "disponibilidad": ["#availability span", "#availability", "#outOfStock"],
    "envio": [
        "#mir-layout-DELIVERY_BLOCK span.a-text-bold",
        "#deliveryBlockMessage",
        "#priceBadging_feature_div",
    ],
    "vendedor": ["#sellerProfileTriggerId", "#merchant-info", "#tabular-buybox .a-col-right"],
    "bullets": ["#feature-bullets li"],
    "overview": ["#productOverview_feature_div tr"],
    "detalles": ["#prodDetails tr"],
}


# ---------------------------------------------------------------------------
# Utilidades de seleccion
# ---------------------------------------------------------------------------
def _texto(nodo: Optional[Tag]) -> Optional[str]:
    return limpiar_texto(nodo.get_text(" ", strip=True)) if nodo else None


def _primer_texto(soup: BeautifulSoup, selectores: list[str]) -> Optional[str]:
    """Devuelve el texto del primer selector con contenido."""
    for selector in selectores:
        if texto := _texto(soup.select_one(selector)):
            return texto
    return None


def _tabla_clave_valor(soup: BeautifulSoup, selector: str) -> dict[str, str]:
    """Convierte una tabla de especificaciones (th/td o td/td) en diccionario."""
    datos: dict[str, str] = {}
    for fila in soup.select(selector):
        celdas = fila.select("th, td")
        if len(celdas) < 2:
            continue
        clave = limpiar_texto(celdas[0].get_text(" ", strip=True))
        valor = limpiar_texto(celdas[1].get_text(" ", strip=True))
        if clave and valor:
            datos[clave] = valor
    return datos


# ---------------------------------------------------------------------------
# Extractores por bloque de la ficha
# ---------------------------------------------------------------------------
def _extraer_identidad(soup: BeautifulSoup, asin: str, overview: dict[str, str]) -> dict[str, Any]:
    titulo = _primer_texto(soup, SELECTORES["titulo"])
    marca = limpiar_marca(overview.get("Brand")) or limpiar_marca(
        _primer_texto(soup, ["#bylineInfo"])
    )
    return {
        "asin": asin,
        "url": TARGET.product_url(asin),
        "titulo": titulo,
        "marca": marca or inferir_marca_desde_titulo(titulo),
    }


def _extraer_precio(soup: BeautifulSoup) -> dict[str, Any]:
    precio, moneda = parse_precio(_primer_texto(soup, SELECTORES["precio"]))
    precio_lista, _ = parse_precio(_primer_texto(soup, SELECTORES["precio_lista"]))
    return {
        "precio": precio,
        "moneda": moneda,
        "precio_lista": precio_lista,
        "descuento_pct": calcular_descuento(precio, precio_lista),
    }


def _extraer_reputacion(soup: BeautifulSoup) -> dict[str, Any]:
    histograma: dict[str, int] = {}
    for fila in soup.select("#histogramTable tr"):
        etiqueta = fila.get("aria-label") or fila.get_text(" ", strip=True)
        estrella = re.search(r"(\d)\s*(?:star|estrella)", etiqueta, re.IGNORECASE)
        porcentaje = re.search(r"(\d+)\s*%", etiqueta)
        if estrella and porcentaje:
            histograma[f"{estrella.group(1)}_estrella_pct"] = int(porcentaje.group(1))

    return {
        "calificacion": parse_calificacion(_primer_texto(soup, SELECTORES["calificacion"])),
        "resenas": parse_resenas(_primer_texto(soup, SELECTORES["resenas"])),
        "histograma": histograma,
    }


def _extraer_logistica(soup: BeautifulSoup) -> dict[str, Any]:
    return {
        "disponibilidad": _primer_texto(soup, SELECTORES["disponibilidad"]),
        "envio": _primer_texto(soup, SELECTORES["envio"]),
        "vendedor": _primer_texto(soup, SELECTORES["vendedor"]),
    }


def _extraer_especificaciones(
    soup: BeautifulSoup, overview: dict[str, str], detalles: dict[str, str]
) -> dict[str, Any]:
    return {
        "sistema_operativo": overview.get("Operating System") or detalles.get("Operating System"),
        "ram_gb": parse_entero(overview.get("Ram Memory Installed Size")),
        "almacenamiento_gb": parse_entero(
            overview.get("Memory Storage Capacity") or detalles.get("Memory Storage Capacity")
        ),
        "pantalla_pulgadas": parse_decimal(overview.get("Screen Size")),
        "modelo": overview.get("Model Name"),
    }


def _extraer_rankings(soup: BeautifulSoup, detalles: dict[str, str]) -> dict[str, Any]:
    texto_bsr = next(
        (valor for clave, valor in detalles.items() if "Best Sellers Rank" in clave),
        None,
    )
    if not texto_bsr:
        texto_bsr = next(
            (
                fila.get_text(" ", strip=True)
                for fila in soup.select("#detailBullets_feature_div li")
                if "Best Sellers Rank" in fila.get_text()
            ),
            None,
        )

    rank, categoria = None, None
    if texto_bsr and (coincidencia := re.search(r"#([\d,]+)\s+in\s+([^(#]+)", texto_bsr)):
        rank = int(coincidencia.group(1).replace(",", ""))
        categoria = coincidencia.group(2).strip()

    bullets = [
        limpiar_texto(li.get_text(" ", strip=True))
        for li in soup.select(SELECTORES["bullets"][0])
        if li.get_text(strip=True)
    ]
    return {
        "bsr_rank": rank,
        "bsr_categoria": categoria,
        "num_bullets": len(bullets),
        "bullet_1": bullets[0][:180] if bullets else None,
    }


# ---------------------------------------------------------------------------
# Parsers publicos
# ---------------------------------------------------------------------------
def parse_busqueda(html: str) -> list[dict[str, Any]]:
    """Extrae las tarjetas del listado de resultados de busqueda."""
    soup = BeautifulSoup(html, "lxml")
    resultados: list[dict[str, Any]] = []
    vistos: set[str] = set()

    for tarjeta in soup.select('div[data-component-type="s-search-result"]'):
        asin = (tarjeta.get("data-asin") or "").strip()
        if not asin or asin in vistos:
            continue
        vistos.add(asin)

        titulo = _texto(tarjeta.select_one("h2")) or ""
        if enlace := tarjeta.select_one("a.a-link-normal[href*='/dp/']"):
            titulo = (enlace.get("aria-label") or titulo).strip()

        precio, moneda = parse_precio(_texto(tarjeta.select_one("span.a-price span.a-offscreen")))
        resultados.append(
            {
                "asin": asin,
                "titulo_listado": titulo,
                "precio_listado": precio,
                "moneda_listado": moneda,
                "calificacion_listado": parse_calificacion(
                    _texto(tarjeta.select_one("span.a-icon-alt"))
                ),
                "resenas_listado": parse_resenas(
                    _texto(tarjeta.select_one("span.a-size-base.s-underline-text"))
                ),
                "patrocinado": bool(tarjeta.select_one("span.puis-sponsored-label-text")),
                "url": TARGET.product_url(asin),
            }
        )
    return resultados


def parse_producto(html: str, asin: str, metodo: str = METODO) -> Producto:
    """Convierte el HTML de una ficha de producto en un `Producto`."""
    soup = BeautifulSoup(html, "lxml")
    overview = _tabla_clave_valor(soup, SELECTORES["overview"][0])
    detalles = _tabla_clave_valor(soup, SELECTORES["detalles"][0])

    campos: dict[str, Any] = {
        **_extraer_identidad(soup, asin, overview),
        **_extraer_precio(soup),
        **_extraer_reputacion(soup),
        **_extraer_logistica(soup),
        **_extraer_especificaciones(soup, overview, detalles),
        **_extraer_rankings(soup, detalles),
        "metodo": metodo,
    }
    return Producto(**campos)


# ---------------------------------------------------------------------------
# Scraper
# ---------------------------------------------------------------------------
class BS4Scraper(BaseScraper):
    """Descarga el catalogo y el articulo principal y los parsea con BeautifulSoup."""

    metodo = METODO

    def __init__(self, target: ScrapingTarget = TARGET, usar_cache: bool = True) -> None:
        super().__init__(target)
        self.sesion = PoliteSession(cookies=load_cookies())
        self.usar_cache = usar_cache

    # ------------------------------------------------------------------
    def _asins_objetivo(self) -> list[str]:
        respuesta = self.sesion.get(
            self.target.search_url, cache_key="search", use_cache=self.usar_cache
        )
        if not respuesta.ok:
            log.error("no se pudo leer el buscador: %s", respuesta.error)
            return [self.target.article_asin]

        listado = parse_busqueda(respuesta.html)
        log.info("resultados en el buscador: %s", len(listado))

        asins = [self.target.article_asin]
        asins.extend(item["asin"] for item in listado if item["asin"] not in asins)
        return asins[: self.target.max_products]

    def ejecutar(self) -> list[Producto]:
        productos: list[Producto] = []
        for indice, asin in enumerate(self._asins_objetivo(), start=1):
            respuesta = self.sesion.get(
                self.target.product_url(asin), cache_key=asin, use_cache=self.usar_cache
            )
            if not respuesta.ok:
                log.warning("%s/%s %s sin datos (%s)", indice, self.target.max_products, asin, respuesta.error)
                continue

            producto = parse_producto(respuesta.html, asin, metodo=self.metodo)
            productos.append(producto)
            log.info(
                "%s/%s %s | %s %s | %.1f estrellas | %s resenas",
                indice,
                self.target.max_products,
                asin,
                producto.precio,
                producto.moneda or "",
                producto.calificacion or 0.0,
                producto.resenas or 0,
            )
        return productos


def main() -> None:
    parser = argparse.ArgumentParser(description="Extraccion estatica con BeautifulSoup")
    parser.add_argument("--max", type=int, default=TARGET.max_products)
    parser.add_argument("--solo-articulo", action="store_true", help="Extrae solo el articulo principal")
    parser.add_argument("--sin-cache", action="store_true", help="Ignora el HTML cacheado")
    args = parser.parse_args()

    target = replace(TARGET, max_products=1) if args.solo_articulo else TARGET
    scraper = BS4Scraper(target=target, usar_cache=not args.sin_cache)

    with scraper.cronometrar() as reloj:
        productos = scraper.ejecutar()

    scraper.guardar(productos, "bs4_productos.csv")
    resumen = scraper.resumen(productos, reloj.duracion, scraper.sesion.success_rate, scraper.sesion.stats)
    log.info("metodo=%s productos=%s duracion=%ss", resumen.metodo, resumen.productos, resumen.duracion_seg)


if __name__ == "__main__":
    main()
