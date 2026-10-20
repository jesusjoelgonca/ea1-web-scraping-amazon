"""
http_client.py
==============
Capa HTTP unica del proyecto (requests + cache en disco + reintentos).

Se aísla aqui todo lo que no es "parseo": cabeceras, cookies, espera entre
peticiones, reintentos con retroceso exponencial, deteccion de la pagina
anti-robot y persistencia del HTML. Los scrapers solo piden HTML y reciben
un `FetchResult` con su traza de ejecucion.

Autor: Jesus Gonzalez
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests

from .config import (
    BACKOFF_BASE_S,
    HTML_CACHE_DIR,
    MAX_RETRIES,
    MIN_HTML_BYTES,
    RAW_DIR,
    REQUEST_DELAY_RANGE,
    REQUEST_HEADERS,
    REQUEST_TIMEOUT_S,
)
from .logger import get_logger

log = get_logger("http")

COOKIES_PATH = RAW_DIR / "cookies.json"

# Marcadores de la pagina de verificacion de Amazon
_BOT_MARKERS = (
    "api-services-support@amazon.com",
    "Enter the characters you see below",
    "To discuss automated access to Amazon data",
    "/errors/validateCaptcha",
)


@dataclass
class FetchResult:
    """HTML obtenido y traza de la peticion."""

    url: str
    html: str = ""
    status_code: int = 0
    elapsed_s: float = 0.0
    attempts: int = 0
    from_cache: bool = False
    blocked: bool = False
    error: Optional[str] = None
    meta: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status_code == 200 and bool(self.html) and not self.blocked


def load_cookies(ruta: Path = COOKIES_PATH) -> dict[str, str]:
    """Carga las cookies exportadas por `session_bootstrap` (si existen)."""
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8"))


def is_blocked(html: str) -> bool:
    """True si el HTML corresponde a la pagina anti-robot o viene vacio."""
    if not html or len(html.encode("utf-8", errors="ignore")) < MIN_HTML_BYTES:
        return True
    encabezado = html[:400_000]
    return any(marcador in encabezado for marcador in _BOT_MARKERS)


def _cache_file(cache_key: str) -> Path:
    seguro = "".join(c for c in cache_key if c.isalnum() or c in "-_") or "page"
    return HTML_CACHE_DIR / f"{seguro}.html"


class PoliteSession:
    """
    Sesion HTTP con cache, cortesia y reintentos.

    Parameters
    ----------
    cookies : cookies de sesion (contexto de entrega fijado por Selenium).
    delay   : rango de espera aleatoria entre peticiones, en segundos.
    """

    def __init__(
        self,
        cookies: Optional[dict[str, str]] = None,
        headers: Optional[dict[str, str]] = None,
        delay: tuple[float, float] = REQUEST_DELAY_RANGE,
    ) -> None:
        self.session = requests.Session()
        self.session.headers.update(headers or REQUEST_HEADERS)
        if cookies:
            self.session.cookies.update(cookies)
        self.delay = delay
        self.stats = {"requests": 0, "ok": 0, "blocked": 0, "errors": 0, "cache_hits": 0}

    # ------------------------------------------------------------------
    def get(
        self,
        url: str,
        cache_key: Optional[str] = None,
        use_cache: bool = True,
        force: bool = False,
    ) -> FetchResult:
        """Descarga `url` aplicando cache, espera y reintentos."""
        archivo = _cache_file(cache_key or url)

        if use_cache and not force and archivo.exists() and archivo.stat().st_size > MIN_HTML_BYTES:
            self.stats["cache_hits"] += 1
            log.debug("cache HIT %s", archivo.name)
            return FetchResult(
                url=url,
                html=archivo.read_text(encoding="utf-8", errors="ignore"),
                status_code=200,
                from_cache=True,
            )

        inicio = time.perf_counter()
        ultimo_error: Optional[str] = None

        for intento in range(1, MAX_RETRIES + 1):
            self.stats["requests"] += 1
            try:
                respuesta = self.session.get(url, timeout=REQUEST_TIMEOUT_S, allow_redirects=True)
                html = respuesta.text

                if respuesta.status_code == 200 and not is_blocked(html):
                    archivo.write_text(html, encoding="utf-8")
                    self.stats["ok"] += 1
                    return FetchResult(
                        url=respuesta.url,
                        html=html,
                        status_code=200,
                        elapsed_s=round(time.perf_counter() - inicio, 2),
                        attempts=intento,
                        meta={"bytes": len(html)},
                    )

                if respuesta.status_code == 200:
                    self.stats["blocked"] += 1
                    ultimo_error = "pagina anti-robot"
                else:
                    self.stats["errors"] += 1
                    ultimo_error = f"HTTP {respuesta.status_code}"

            except requests.RequestException as exc:
                self.stats["errors"] += 1
                ultimo_error = f"{type(exc).__name__}: {exc}"

            log.warning("intento %s/%s fallido en %s (%s)", intento, MAX_RETRIES, url, ultimo_error)
            if intento < MAX_RETRIES:
                time.sleep(BACKOFF_BASE_S * intento + random.uniform(0, 2))

        return FetchResult(
            url=url,
            status_code=0,
            elapsed_s=round(time.perf_counter() - inicio, 2),
            attempts=MAX_RETRIES,
            blocked=True,
            error=ultimo_error,
        )

    def get_many(self, urls: list[tuple[str, str]], use_cache: bool = True) -> list[FetchResult]:
        """
        Descarga una lista de ``(cache_key, url)`` respetando la espera entre
        peticiones. Solo se espera cuando la peticion no vino de cache.
        """
        resultados: list[FetchResult] = []
        for indice, (cache_key, url) in enumerate(urls):
            resultado = self.get(url, cache_key=cache_key, use_cache=use_cache)
            resultados.append(resultado)
            if indice < len(urls) - 1 and not resultado.from_cache:
                time.sleep(random.uniform(*self.delay))
        return resultados

    @property
    def success_rate(self) -> float:
        """
        Peticiones exitosas / peticiones realizadas.

        Si toda la ejecucion se resolvio con la cache en disco no hubo
        peticiones: se informa 1.0 (no hubo fallos) y el numero de aciertos de
        cache queda registrado en `stats` para no perder trazabilidad.
        """
        total = self.stats["requests"]
        return round(self.stats["ok"] / total, 4) if total else 1.0
