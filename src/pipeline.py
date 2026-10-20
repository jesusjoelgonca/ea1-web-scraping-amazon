"""
pipeline.py
===========
Orquestador del pipeline de extraccion (EA1).

Etapas
------
0. bootstrap   : Selenium fija el ZIP de entrega y exporta cookies.
1. beautifulsoup: catalogo completo (buscador + 16 fichas).
2. semillas    : guarda los ASIN en data/raw/seeds.json para el crawler.
3. selenium    : ficha del articulo principal + resenas destacadas.
4. scrapy      : crawleo asincrono del mismo catalogo.
5. consolidacion: dataset unico en CSV/XLSX.
6. validacion  : metricas de exito y veredicto.
7. figuras     : graficas del informe.

Cada etapa es idempotente y puede saltarse con banderas CLI, lo que permite
re-ejecutar solo la parte necesaria (por ejemplo, reparsear el HTML cacheado
sin volver a golpear el sitio).

Uso:
    python -m src.pipeline
    python -m src.pipeline --sin-scrapy --sin-selenium
    python -m src.pipeline --solo-validacion

Autor: Jesus Gonzalez
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .config import (
    ARTICLE_ASIN,
    PROCESSED_DIR,
    RAW_DIR,
    REPORTS_DIR,
    ROOT_DIR,
    TARGET,
)
from .logger import configurar_logging, get_logger
from .models import MetricasMetodo, ResultadoValidacion
from .scrapers.bs4_scraper import BS4Scraper
from .scrapers.selenium_scraper import SeleniumScraper
from .validation import evaluar, guardar_metricas
from .visualization import generar_todas

log = get_logger("pipeline")

SCRAPY_DIR = ROOT_DIR / "src" / "scrapy_project"
SEEDS_PATH = RAW_DIR / "seeds.json"
SCRAPY_JSON = RAW_DIR / "scrapy_productos.json"


@dataclass
class PipelineResult:
    """Salida consolidada de una ejecucion completa."""

    catalogo: pd.DataFrame
    metodos: list[MetricasMetodo] = field(default_factory=list)
    validacion: ResultadoValidacion | None = None
    figuras: list[Path] = field(default_factory=list)

    def resumen(self) -> str:
        valido = self.validacion
        return (
            f"catalogo={len(self.catalogo)} productos | "
            f"metodos={len(self.metodos)} | "
            f"cobertura={valido.cobertura_campos:.1%} | "
            f"concordancia={valido.concordancia_metodos:.1%} | "
            f"veredicto={'APROBADO' if valido and valido.aprobado else 'REVISAR'}"
        )


class ScrapingPipeline:
    """Coordina las etapas de extraccion, consolidacion y validacion."""

    def __init__(
        self,
        headless: bool = True,
        usar_cache: bool = True,
        con_bootstrap: bool = True,
        con_selenium: bool = True,
        con_scrapy: bool = True,
    ) -> None:
        self.headless = headless
        self.usar_cache = usar_cache
        self.con_bootstrap = con_bootstrap
        self.con_selenium = con_selenium
        self.con_scrapy = con_scrapy
        self.metricas: list[MetricasMetodo] = []
        self.inicio = time.perf_counter()

    # ------------------------------------------------------------------
    # Etapas
    # ------------------------------------------------------------------
    def _bootstrap(self) -> None:
        from .http_client import COOKIES_PATH

        if COOKIES_PATH.exists() and self.usar_cache:
            log.info("etapa 0: cookies existentes reutilizadas (%s)", COOKIES_PATH.name)
            return
        from .session_bootstrap import NavegadorNoDisponible, bootstrap

        try:
            bootstrap(headless=self.headless)
        except NavegadorNoDisponible as error:
            # Sin navegador el pipeline sigue: las cookies versionadas cubren el
            # contexto comercial y las etapas 1 y 3 no dependen del driver.
            log.warning("bootstrap omitido: %s", error)

    def _extraer_bs4(self) -> pd.DataFrame:
        log.info("etapa 1: extraccion estatica con BeautifulSoup")
        scraper = BS4Scraper(usar_cache=self.usar_cache)
        with scraper.cronometrar() as reloj:
            productos = scraper.ejecutar()

        ruta = scraper.guardar(productos, "bs4_productos.csv")
        self.metricas.append(
            scraper.resumen(productos, reloj.duracion, scraper.sesion.success_rate, scraper.sesion.stats)
        )
        self._guardar_semillas([producto.asin for producto in productos])
        return pd.read_csv(ruta)

    def _guardar_semillas(self, asins: list[str]) -> None:
        semillas = {
            "generado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "article_asin": ARTICLE_ASIN,
            "asins": asins,
        }
        SEEDS_PATH.write_text(json.dumps(semillas, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("semillas para Scrapy: %s ASIN -> %s", len(asins), SEEDS_PATH.name)

    def _extraer_selenium(self) -> pd.DataFrame:
        log.info("etapa 2: extraccion dinamica con Selenium")
        from .session_bootstrap import NavegadorNoDisponible

        try:
            scraper = SeleniumScraper(headless=self.headless)
        except NavegadorNoDisponible as error:
            log.warning("etapa 2 omitida: %s", error)
            return pd.DataFrame()

        with scraper.cronometrar() as reloj:
            try:
                productos = scraper.ejecutar()
            except NavegadorNoDisponible as error:
                log.warning("etapa 2 interrumpida: %s", error)
                return pd.DataFrame()

        ruta = scraper.guardar(productos, "selenium_productos.csv")
        self.metricas.append(scraper.resumen(productos, reloj.duracion))
        return pd.read_csv(ruta)

    def _extraer_scrapy(self) -> pd.DataFrame:
        log.info("etapa 3: crawleo asincrono con Scrapy")
        # La salida anterior se mueve a un respaldo en lugar de borrarse: si el
        # crawler falla (por ejemplo, sin red en un contenedor), el repositorio
        # conserva la evidencia de la corrida previa.
        respaldo = SCRAPY_JSON.with_name(SCRAPY_JSON.name + ".prev")
        if SCRAPY_JSON.exists():
            os.replace(SCRAPY_JSON, respaldo)

        inicio = time.perf_counter()
        try:
            proceso = subprocess.run(
                [sys.executable, "-m", "scrapy", "crawl", "productos", "-L", "INFO"],
                cwd=SCRAPY_DIR,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
            )
        except OSError as error:  # intérprete o paquete no disponible
            log.error("no se pudo lanzar Scrapy: %s", error)
            proceso = None
        duracion = time.perf_counter() - inicio

        if proceso is not None and proceso.returncode != 0:
            log.error("Scrapy finalizo con codigo %s\n%s", proceso.returncode, proceso.stderr[-1500:])

        if not SCRAPY_JSON.exists() or SCRAPY_JSON.stat().st_size == 0:
            if respaldo.exists():
                os.replace(respaldo, SCRAPY_JSON)
                log.warning("Scrapy no genero salida; se restauro la extraccion previa y la etapa se omite")
            else:
                log.warning("Scrapy no genero salida; se omite del analisis")
            return pd.DataFrame()

        registros = json.loads(SCRAPY_JSON.read_text(encoding="utf-8"))
        df = pd.DataFrame(registros)
        semillas = len(json.loads(SEEDS_PATH.read_text(encoding="utf-8")).get("asins", [])) or len(df)
        self.metricas.append(
            MetricasMetodo(
                metodo="scrapy",
                productos=len(df),
                duracion_seg=round(duracion, 2),
                cobertura_campos=round(float(df[["asin", "titulo", "precio", "calificacion", "resenas"]].notna().mean().mean()), 4)
                if not df.empty
                else 0.0,
                # El crawler no expone su contador de respuestas al orquestador:
                # se usa la proporcion de fichas recuperadas sobre las semillas.
                tasa_exito_http=round(len(df) / semillas, 4) if semillas else 0.0,
            )
        )
        return df

    # ------------------------------------------------------------------
    def _consolidar(self, df_bs4: pd.DataFrame, df_selenium: pd.DataFrame) -> pd.DataFrame:
        """
        Unifica el catalogo y completa el articulo principal con Selenium.

        Solo se rellenan celdas vacias: el dato estatico (BeautifulSoup) se
        conserva y Selenium aporta lo que el HTML inicial no traia.
        """
        base = df_bs4.copy()
        # Columnas con estructura propia que no se mezclan entre metodos
        excluidas = {"asin", "histograma", "metodo", "fecha_extraccion", "url"}

        if not df_selenium.empty:
            articulo = df_selenium.iloc[0]
            es_articulo = base["asin"] == articulo["asin"]

            for columna in (c for c in df_selenium.columns if c not in excluidas and c in base.columns):
                faltantes = base[columna].isna() & es_articulo
                if faltantes.any():
                    base[columna] = base[columna].astype(object)
                    base.loc[faltantes, columna] = articulo[columna]

        base["es_articulo_principal"] = base["asin"] == ARTICLE_ASIN
        destino_csv = PROCESSED_DIR / "catalogo_consolidado.csv"
        destino_xlsx = PROCESSED_DIR / "catalogo_consolidado.xlsx"
        base.to_csv(destino_csv, index=False, encoding="utf-8-sig")
        base.to_excel(destino_xlsx, index=False, sheet_name="catalogo")
        log.info("catalogo consolidado: %s registros -> %s", len(base), destino_csv.name)
        return base

    def _validar(self, datasets: dict[str, pd.DataFrame]) -> ResultadoValidacion:
        duracion = time.perf_counter() - self.inicio
        tasa_http = (
            sum(m.tasa_exito_http for m in self.metricas) / len(self.metricas) if self.metricas else 0.0
        )
        resultado, detalle = evaluar(datasets, duracion, tasa_http)
        detalle["metodos"] = [metrica.to_dict() for metrica in self.metricas]
        guardar_metricas(detalle)
        return resultado

    # ------------------------------------------------------------------
    def ejecutar(self) -> PipelineResult:
        """Ejecuta el pipeline completo."""
        if self.con_bootstrap:
            self._bootstrap()

        df_bs4 = self._extraer_bs4()
        df_selenium = self._extraer_selenium() if self.con_selenium else pd.DataFrame()
        df_scrapy = self._extraer_scrapy() if self.con_scrapy else pd.DataFrame()

        catalogo = self._consolidar(df_bs4, df_selenium)

        datasets = {"beautifulsoup": df_bs4}
        if not df_selenium.empty:
            datasets["selenium"] = df_selenium
        if not df_scrapy.empty:
            datasets["scrapy"] = df_scrapy

        validacion = self._validar(datasets)
        figuras = generar_todas(catalogo, [m.to_dict() for m in self.metricas])

        resultado = PipelineResult(catalogo=catalogo, metodos=self.metricas, validacion=validacion, figuras=figuras)
        log.info("pipeline finalizado: %s", resultado.resumen())
        return resultado


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline de web scraping - EA1")
    parser.add_argument("--sin-bootstrap", action="store_true", help="No reabre el navegador para cookies")
    parser.add_argument("--sin-selenium", action="store_true", help="Omite la etapa Selenium")
    parser.add_argument("--sin-scrapy", action="store_true", help="Omite la etapa Scrapy")
    parser.add_argument("--sin-cache", action="store_true", help="Fuerza la descarga del HTML")
    parser.add_argument("--visible", action="store_true", help="Navegador visible (Selenium)")
    args = parser.parse_args()

    configurar_logging(archivo=REPORTS_DIR / "ejecucion.log")
    pipeline = ScrapingPipeline(
        headless=not args.visible,
        usar_cache=not args.sin_cache,
        con_bootstrap=not args.sin_bootstrap,
        con_selenium=not args.sin_selenium,
        con_scrapy=not args.sin_scrapy,
    )
    pipeline.ejecutar()


if __name__ == "__main__":
    main()
