"""
config.py
=========
Unica fuente de verdad de la configuracion del proyecto.

Ningun modulo define rutas, cabeceras ni umbrales por su cuenta: todos leen
de aqui. Esto evita la dispersion de "valores magicos" y permite cambiar el
objetivo del scraping (sitio, termino de busqueda, articulo) en un solo lugar.

Autor: Jesus Gonzalez
Curso: Programacion para Analisis de Datos - PREICA2602B020048
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
HTML_CACHE_DIR = RAW_DIR / "html"
PROCESSED_DIR = DATA_DIR / "processed"
REPORTS_DIR = ROOT_DIR / "reports"
FIGURES_DIR = REPORTS_DIR / "figuras"

for _directorio in (RAW_DIR, HTML_CACHE_DIR, PROCESSED_DIR, REPORTS_DIR, FIGURES_DIR):
    _directorio.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Objetivo del scraping
# ---------------------------------------------------------------------------
SITE_NAME = "Amazon"
BASE_URL = "https://www.amazon.com"

# Termino de busqueda que define el catalogo de comparacion
SEARCH_TERM = "unlocked android smartphone 128gb"
SEARCH_URL = f"{BASE_URL}/s?k={SEARCH_TERM.replace(' ', '+')}"

# Articulo principal de la evidencia: Samsung Galaxy A57 5G (128 GB)
ARTICLE_ASIN = "B0GW9TVHJB"
ARTICLE_URL = f"{BASE_URL}/dp/{ARTICLE_ASIN}"

# Tamano maximo del catalogo (articulo principal + competidores)
MAX_PRODUCTS = 16

# Contexto comercial: sin una ubicacion de entrega valida Amazon no publica
# el precio del buybox, por lo que se fija un ZIP de referencia.
DELIVERY_ZIP = "10001"
DELIVERY_CITY = "New York, NY"

# Idioma y moneda de la sesion: se fijan para que los tres metodos devuelvan
# los titulos en el mismo idioma y los importes en la misma divisa.
SESSION_LOCALE = "en_US"
SESSION_CURRENCY = "USD"

# ---------------------------------------------------------------------------
# Cabeceras HTTP
# ---------------------------------------------------------------------------
# Amazon devuelve la pagina anti-robot cuando faltan las cabeceras
# Sec-Fetch-* / sec-ch-ua propias de un navegador moderno.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

REQUEST_HEADERS: dict[str, str] = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="126", "Google Chrome";v="126", "Not.A/Brand";v="24"',
    "sec-ch-ua-platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

# ---------------------------------------------------------------------------
# Politica de cortesia y robustez
# ---------------------------------------------------------------------------
REQUEST_DELAY_RANGE = (2.5, 5.0)  # espera aleatoria entre peticiones (s)
MAX_RETRIES = 3
BACKOFF_BASE_S = 4
REQUEST_TIMEOUT_S = 30
MIN_HTML_BYTES = 5_000            # por debajo de esto se asume bloqueo

# ---------------------------------------------------------------------------
# Metricas de exito de la solucion
# ---------------------------------------------------------------------------
MIN_FIELD_COVERAGE = 0.95        # >= 95 % de campos clave diligenciados
MIN_METHOD_AGREEMENT = 0.90      # >= 90 % de coincidencia entre metodos
MIN_CATALOG_SIZE = 12            # productos minimos del catalogo
MIN_HTTP_SUCCESS_RATE = 0.95     # peticiones exitosas / totales
MAX_PIPELINE_SECONDS = 600       # duracion maxima aceptable del pipeline

KEY_FIELDS: tuple[str, ...] = ("asin", "titulo", "precio", "calificacion", "resenas")


@dataclass(frozen=True)
class ScrapingTarget:
    """Describe el objeto de estudio y el contexto de extraccion."""

    site: str = SITE_NAME
    search_term: str = SEARCH_TERM
    article_asin: str = ARTICLE_ASIN
    delivery_zip: str = DELIVERY_ZIP
    max_products: int = MAX_PRODUCTS
    headers: dict[str, str] = field(default_factory=lambda: dict(REQUEST_HEADERS))

    @property
    def article_url(self) -> str:
        return f"{BASE_URL}/dp/{self.article_asin}"

    @property
    def search_url(self) -> str:
        return f"{BASE_URL}/s?k={self.search_term.replace(' ', '+')}"

    def product_url(self, asin: str) -> str:
        return f"{BASE_URL}/dp/{asin}"


TARGET = ScrapingTarget()
