"""
selenium_scraper.py
===================
METODO 2 - Extraccion dinamica con Selenium WebDriver.

Rol: controlar un navegador real para (a) fijar el contexto de entrega que
condiciona el precio, (b) esperar a que el DOM este listo, (c) desplazar la
pagina para forzar la carga perezosa de bloques que no vienen en el HTML
inicial (resenas, resumen de opiniones) y (d) capturar evidencia visual.

A diferencia del metodo 1, aqui la extraccion se hace con la API del
WebDriver (`find_element`, `get_attribute`, `execute_script`), no con
BeautifulSoup.

Uso:
    python -m src.scrapers.selenium_scraper

Autor: Jesus Gonzalez
"""

from __future__ import annotations

import argparse
import time
from dataclasses import replace
from typing import Any, Optional

from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from ..config import FIGURES_DIR, TARGET, ScrapingTarget
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
from ..session_bootstrap import crear_driver, fijar_ubicacion

log = get_logger("selenium")

METODO = "selenium"
ESPERA_MAX_S = 25


class SeleniumScraper(BaseScraper):
    """Extrae la ficha del articulo principal con un navegador automatizado."""

    metodo = METODO

    def __init__(self, target: ScrapingTarget = TARGET, headless: bool = True) -> None:
        super().__init__(target)
        self.headless = headless

    # ------------------------------------------------------------------
    # Navegacion
    # ------------------------------------------------------------------
    @staticmethod
    def _desplazar(driver, pasos: int = 8, pausa: float = 0.5) -> None:
        """
        Desplazamiento progresivo hasta el bloque de resenas.

        Amazon construye el histograma de calificaciones y otros bloques por
        JavaScript: sin desplazarse hasta `#customer-reviews_feature_div` el
        contenido no existe en el DOM.
        """
        for _ in range(pasos):
            driver.execute_script("window.scrollBy(0, document.body.scrollHeight / 8);")
            time.sleep(pausa)

        driver.execute_script(
            "const seccion = document.querySelector('#customer-reviews_feature_div');"
            "if (seccion) { seccion.scrollIntoView({block: 'center'}); }"
        )
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.ID, "histogramTable"))
            )
        except TimeoutException:
            log.warning("el histograma de calificaciones no se renderizo en el tiempo de espera")

    @staticmethod
    def _texto_seguro(driver, selector: str) -> Optional[str]:
        """Texto del primer elemento que coincida con `selector` (o None)."""
        try:
            elemento = driver.find_element(By.CSS_SELECTOR, selector)
            return limpiar_texto(elemento.text) or limpiar_texto(elemento.get_attribute("textContent"))
        except (NoSuchElementException, WebDriverException):
            return None

    @staticmethod
    def _atributo_seguro(driver, selector: str, atributo: str) -> Optional[str]:
        try:
            return limpiar_texto(driver.find_element(By.CSS_SELECTOR, selector).get_attribute(atributo))
        except (NoSuchElementException, WebDriverException):
            return None

    # ------------------------------------------------------------------
    # Extraccion
    # ------------------------------------------------------------------
    def _extraer_especificaciones(self, driver) -> dict[str, Any]:
        """Lee la tabla 'Product information' con JavaScript y la vuelve dict."""
        filas = driver.execute_script(
            """
            const filas = [...document.querySelectorAll('#productOverview_feature_div tr, #prodDetails tr')];
            return filas.map(f => {
                const c = f.querySelectorAll('th, td');
                return c.length >= 2 ? [c[0].innerText.trim(), c[1].innerText.trim()] : null;
            }).filter(Boolean);
            """
        )
        return {clave: valor for clave, valor in filas}

    def _extraer_histograma(self, driver) -> dict[str, int]:
        """
        Distribucion de calificaciones (`#histogramTable`).

        Este bloque se construye con JavaScript: en el HTML estatico el
        contenedor existe pero esta vacio, por lo que BeautifulSoup no puede
        leerlo. Es el aporte diferencial del metodo dinamico.
        """
        pares = driver.execute_script(
            """
            const tabla = document.querySelector('#histogramTable');
            if (!tabla) { return []; }
            const texto = tabla.innerText || '';
            return [...texto.matchAll(/(\\d)\\s*star\\s*[|\\n]?\\s*(\\d+)\\s*%/g)]
                .map(m => [parseInt(m[1], 10), parseInt(m[2], 10)]);
            """
        )
        return {f"{estrella}_estrella_pct": porcentaje for estrella, porcentaje in pares or []}

    # ------------------------------------------------------------------
    def ejecutar(self) -> list[Producto]:
        asin = self.target.article_asin
        driver = crear_driver(headless=self.headless)
        try:
            fijar_ubicacion(driver, self.target.delivery_zip)
            driver.get(self.target.product_url(asin))
            WebDriverWait(driver, ESPERA_MAX_S).until(
                EC.presence_of_element_located((By.ID, "productTitle"))
            )
            self._desplazar(driver)

            especificaciones = self._extraer_especificaciones(driver)
            precio, moneda = parse_precio(
                self._texto_seguro(driver, "#corePrice_feature_div span.a-price span.a-offscreen")
                or self._texto_seguro(driver, "#corePrice_desktop span.a-price span.a-offscreen")
            )
            precio_lista, _ = parse_precio(self._texto_seguro(driver, "span.basisPrice span.a-offscreen"))

            titulo = self._texto_seguro(driver, "#productTitle")
            histograma = self._extraer_histograma(driver)

            producto = Producto(
                asin=asin,
                url=self.target.product_url(asin),
                titulo=titulo,
                marca=limpiar_marca(especificaciones.get("Brand")) or inferir_marca_desde_titulo(titulo),
                precio=precio,
                moneda=moneda,
                precio_lista=precio_lista,
                descuento_pct=calcular_descuento(precio, precio_lista),
                calificacion=parse_calificacion(
                    self._atributo_seguro(driver, "#acrPopover", "title")
                    or self._texto_seguro(driver, "#acrPopover")
                ),
                resenas=parse_resenas(self._texto_seguro(driver, "#acrCustomerReviewText")),
                disponibilidad=self._texto_seguro(driver, "#availability span"),
                envio=self._texto_seguro(driver, "#mir-layout-DELIVERY_BLOCK span.a-text-bold"),
                vendedor=self._texto_seguro(driver, "#sellerProfileTriggerId"),
                sistema_operativo=especificaciones.get("Operating System"),
                ram_gb=parse_entero(especificaciones.get("Ram Memory Installed Size")),
                almacenamiento_gb=parse_entero(especificaciones.get("Memory Storage Capacity")),
                pantalla_pulgadas=parse_decimal(especificaciones.get("Screen Size")),
                modelo=especificaciones.get("Model Name"),
                num_bullets=len(driver.find_elements(By.CSS_SELECTOR, "#feature-bullets li")),
                histograma=histograma,
                metodo=self.metodo,
            )

            self._guardar_evidencias(driver, asin)
            log.info(
                "articulo %s | %s %s | %.1f estrellas | %s resenas | histograma: %s barras",
                asin,
                producto.precio,
                producto.moneda or "",
                producto.calificacion or 0.0,
                producto.resenas or 0,
                len(histograma),
            )
            return [producto]
        finally:
            driver.quit()

    # ------------------------------------------------------------------
    @staticmethod
    def _guardar_evidencias(driver, asin: str) -> None:
        """Captura de pantalla como evidencia de la sesion automatizada."""
        captura = FIGURES_DIR / f"evidencia_selenium_{asin}.png"
        try:
            driver.save_screenshot(str(captura))
            log.info("captura de pantalla guardada en %s", captura.name)
        except WebDriverException:
            log.warning("no se pudo guardar la captura de pantalla")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extraccion dinamica con Selenium")
    parser.add_argument("--visible", action="store_true", help="Muestra el navegador")
    args = parser.parse_args()

    scraper = SeleniumScraper(target=replace(TARGET, max_products=1), headless=not args.visible)
    with scraper.cronometrar() as reloj:
        productos = scraper.ejecutar()

    scraper.guardar(productos, "selenium_productos.csv")
    resumen = scraper.resumen(productos, reloj.duracion)
    log.info("metodo=%s productos=%s duracion=%ss", resumen.metodo, resumen.productos, resumen.duracion_seg)


if __name__ == "__main__":
    main()
