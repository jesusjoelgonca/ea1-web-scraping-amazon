"""
productos.py
============
METODO 3 - Crawler asincrono con Scrapy.

Rol: recorrer el catalogo de ASIN como un crawler de produccion, con
peticiones concurrentes limitadas, AutoThrottle, reintentos y pipelines de
normalizacion/validacion. Es el metodo que escala a cientos de fichas.

El spider no conoce selectores de normalizacion: solo selecciona texto con
CSS/XPath y delega la conversion de tipos en el pipeline.

Semillas: `data/raw/seeds.json` (lista de ASIN generada por la etapa 1).
Cookies: `data/raw/cookies.json` (contexto de entrega fijado por Selenium).

Uso:
    cd src/scrapy_project
    scrapy crawl productos
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, AsyncIterator

import scrapy
from scrapy.http import Response

from src.config import ARTICLE_ASIN, RAW_DIR, TARGET

from ..items import ProductoItem


class ProductosSpider(scrapy.Spider):
    """Recorre las fichas de producto del catalogo y emite un Item por ficha."""

    name = "productos"
    allowed_domains = ["amazon.com"]

    def __init__(self, seeds_file: str | None = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.seeds_file = Path(seeds_file) if seeds_file else RAW_DIR / "seeds.json"
        self.cookies = self._cargar_json(RAW_DIR / "cookies.json")

    # ------------------------------------------------------------------
    @staticmethod
    def _cargar_json(ruta: Path) -> Any:
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}

    def _asins(self) -> list[str]:
        semillas = self._cargar_json(self.seeds_file)
        asins = semillas.get("asins", []) if isinstance(semillas, dict) else semillas
        if not asins:
            self.logger.warning("sin semillas en %s; se usa el articulo principal", self.seeds_file)
            return [ARTICLE_ASIN]
        return asins

    # ------------------------------------------------------------------
    async def start(self) -> AsyncIterator[scrapy.Request]:
        """
        Punto de entrada del crawler (API asincrona de Scrapy >= 2.13).

        Emite una peticion por ASIN con las cookies de sesion, de modo que el
        crawler observe el mismo contexto de entrega que los otros metodos.
        """
        for asin in self._asins():
            yield scrapy.Request(
                url=TARGET.product_url(asin),
                callback=self.parse_producto,
                cb_kwargs={"asin": asin},
                cookies=self.cookies,
                dont_filter=True,
            )

    # ------------------------------------------------------------------
    @staticmethod
    def _texto(response: Response, selector: str) -> str | None:
        valores = response.css(f"{selector}::text").getall()
        if not valores:
            valores = response.css(f"{selector} *::text").getall()
        texto = " ".join(v.strip() for v in valores if v and v.strip())
        return texto or None

    def parse_producto(self, response: Response, asin: str) -> Iterator[ProductoItem]:
        if response.status != 200 or not response.css("#productTitle"):
            self.logger.warning("ficha %s descartada (HTTP %s)", asin, response.status)
            return

        especificaciones = self._especificaciones(response)
        yield ProductoItem(
            asin=asin,
            url=response.url,
            titulo=self._texto(response, "#productTitle"),
            marca=especificaciones.get("Brand"),
            precio_texto=response.css(
                "#corePrice_feature_div span.a-price span.a-offscreen::text"
            ).get(),
            precio_lista_texto=response.css("span.basisPrice span.a-offscreen::text").get(),
            calificacion_texto=response.css("#acrPopover::attr(title)").get(),
            resenas_texto=response.css("#acrCustomerReviewText::text").get(),
            disponibilidad=self._texto(response, "#availability span"),
            envio=self._texto(response, "#mir-layout-DELIVERY_BLOCK span.a-text-bold"),
            sistema_operativo=especificaciones.get("Operating System"),
            almacenamiento_texto=especificaciones.get("Memory Storage Capacity"),
            ram_texto=especificaciones.get("Ram Memory Installed Size"),
        )

    @staticmethod
    def _especificaciones(response: Response) -> dict[str, str]:
        """Convierte la tabla 'Product information' en diccionario clave-valor."""
        datos: dict[str, str] = {}
        for fila in response.css("#productOverview_feature_div tr, #prodDetails tr"):
            celdas = fila.css("th::text, td::text").getall()
            celdas = [c.strip() for c in celdas if c and c.strip()]
            if len(celdas) >= 2:
                datos[celdas[0]] = celdas[1]
        return datos
