"""
settings.py
===========
Configuracion del proyecto Scrapy.

Se prioriza la cortesia con el sitio: robots.txt respetado, pocas peticiones
concurrentes, retardo entre peticiones y AutoThrottle adaptativo. Los valores
numericos se importan de `src/config.py` para no duplicar la politica global.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Permite importar el paquete `src` (config, normalizers) desde el subproyecto
RAIZ_PROYECTO = Path(__file__).resolve().parents[3]
if str(RAIZ_PROYECTO) not in sys.path:
    sys.path.insert(0, str(RAIZ_PROYECTO))

from src.config import MAX_RETRIES, RAW_DIR, REQUEST_HEADERS, REQUEST_TIMEOUT_S  # noqa: E402

BOT_NAME = "amazon_scraper"
SPIDER_MODULES = ["amazon_scraper.spiders"]
NEWSPIDER_MODULE = "amazon_scraper.spiders"

# --- Cortesia ---------------------------------------------------------------
ROBOTSTXT_OBEY = True
CONCURRENT_REQUESTS = 2
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 2.0
DOWNLOAD_DELAY_JITTER = 0.5  # variacion aleatoria de +-50 %
DOWNLOAD_TIMEOUT = REQUEST_TIMEOUT_S
RETRY_ENABLED = True
RETRY_TIMES = MAX_RETRIES

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 2.0
AUTOTHROTTLE_MAX_DELAY = 15.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# --- Identidad HTTP ---------------------------------------------------------
USER_AGENT = REQUEST_HEADERS["User-Agent"]
DEFAULT_REQUEST_HEADERS = dict(REQUEST_HEADERS)
COOKIES_ENABLED = True

# --- Pipeline y salida ------------------------------------------------------
ITEM_PIPELINES = {
    "amazon_scraper.pipelines.NormalizacionPipeline": 300,
    "amazon_scraper.pipelines.ValidacionPipeline": 400,
}

FEEDS = {
    str(RAW_DIR / "scrapy_productos.json"): {
        "format": "json",
        "encoding": "utf8",
        "overwrite": True,
        "indent": 2,
    }
}

LOG_LEVEL = "INFO"
TELNETCONSOLE_ENABLED = False
