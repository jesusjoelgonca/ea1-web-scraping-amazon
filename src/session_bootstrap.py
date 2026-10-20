"""
session_bootstrap.py
====================
Arranque de sesion con Selenium (fase 0 del pipeline).

Por que existe
--------------
Amazon personaliza precio, disponibilidad y envio segun la ubicacion de
entrega. Desde Colombia el buybox de la mayoria de los telefonos aparece
suprimido ("This item cannot be shipped to your selected delivery
location") y el precio no existe en el HTML.

Este modulo abre un navegador real, interactua con el widget "Deliver to"
para fijar un codigo postal de EE. UU. y exporta las cookies resultantes.
Esas cookies se reutilizan en BeautifulSoup y en Scrapy, de modo que los tres
metodos observan el mismo contexto comercial y sus resultados son comparables.

Portabilidad
------------
El navegador se elige en tiempo de ejecucion segun el sistema operativo:

* Linux / macOS  -> Chrome y, si no existe, Chromium.
* Windows        -> Edge y, si no existe, Chrome.

El driver lo resuelve Selenium Manager (integrado desde Selenium 4.6), de modo
que no hace falta descargar binarios ni fijar rutas. Si no hay ningun navegador
disponible se lanza ``NavegadorNoDisponible`` y el pipeline continua con las
cookies versionadas en ``data/raw/cookies.json``.

Autor: Jesus Gonzalez
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import time
from pathlib import Path
from typing import Any, Optional

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from .config import (
    DELIVERY_ZIP,
    REQUEST_HEADERS,
    SESSION_CURRENCY,
    SESSION_LOCALE,
    TARGET,
)
from .http_client import COOKIES_PATH
from .logger import get_logger

log = get_logger("bootstrap")

_PAGINA_DE_APOYO = TARGET.product_url("B09B8V1LZ3")  # cualquier ficha sirve para cargar el header

# Orden de preferencia por plataforma. En Linux y macOS el navegador
# mayoritario es Chrome; en Windows el sistema trae Edge preinstalado.
_CANDIDATOS_POR_SO: dict[str, tuple[str, ...]] = {
    "Windows": ("edge", "chrome"),
    "Darwin": ("chrome", "edge"),
}
_CANDIDATOS_POR_DEFECTO: tuple[str, ...] = ("chrome", "chromium", "edge")

# Ejecutables que delatan la presencia de cada navegador en Linux.
_BINARIOS = {
    "chrome": ("google-chrome", "google-chrome-stable", "chrome"),
    "chromium": ("chromium", "chromium-browser"),
    "edge": ("microsoft-edge", "microsoft-edge-stable"),
}


class NavegadorNoDisponible(RuntimeError):
    """No hay navegador ni driver utilizable en este entorno."""


# ---------------------------------------------------------------------------
# Deteccion del entorno
# ---------------------------------------------------------------------------
def _proxy_del_entorno() -> Optional[str]:
    """Detecta un proxy HTTP del sistema (necesario en redes corporativas)."""
    for variable in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if valor := os.environ.get(variable):
            return valor
    return None


def _excluir_localhost_del_proxy() -> None:
    """
    Excluye localhost del proxy del sistema.

    El canal de control de Selenium habla HTTP con el driver en 127.0.0.1: si
    esas peticiones se enrutan por un proxy corporativo, el driver devuelve
    "unhandled request" y la sesion no arranca.
    """
    actuales = {host.strip() for host in os.environ.get("NO_PROXY", "").split(",") if host.strip()}
    actuales.update({"localhost", "127.0.0.1"})
    os.environ["NO_PROXY"] = ",".join(sorted(actuales))
    os.environ["no_proxy"] = os.environ["NO_PROXY"]


def _hay_servidor_grafico() -> bool:
    """Indica si la sesion puede abrir una ventana (falso en contenedores)."""
    sistema = platform.system()
    if sistema in {"Windows", "Darwin"}:
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def navegadores_disponibles() -> list[str]:
    """Lista los navegadores candidatos que parecen estar instalados."""
    sistema = platform.system()
    orden = _CANDIDATOS_POR_SO.get(sistema, _CANDIDATOS_POR_DEFECTO)
    encontrados: list[str] = []
    for navegador in orden:
        if any(shutil.which(binario) for binario in _BINARIOS[navegador]):
            encontrados.append(navegador)
    # En Windows y macOS la ausencia en PATH no descarta el navegador: el
    # instalador no siempre lo expone. Se deja que Selenium Manager lo busque.
    if not encontrados and sistema in {"Windows", "Darwin"}:
        encontrados = list(orden)
    return encontrados


# ---------------------------------------------------------------------------
# Construccion del driver
# ---------------------------------------------------------------------------
def _opciones(navegador: str, headless: bool) -> Any:
    """Devuelve las opciones del navegador con una huella discreta."""
    if navegador == "edge":
        from selenium.webdriver.edge.options import Options

        opciones = Options()
    else:
        from selenium.webdriver.chrome.options import Options

        opciones = Options()
        if navegador == "chromium":
            for binario in _BINARIOS["chromium"]:
                if ruta := shutil.which(binario):
                    opciones.binary_location = ruta
                    break

    if headless:
        opciones.add_argument("--headless=new")
    opciones.add_argument("--window-size=1440,1000")
    opciones.add_argument("--disable-blink-features=AutomationControlled")
    # Necesarias en contenedores y en CI (Codespaces, Docker, GitHub Actions).
    opciones.add_argument("--disable-dev-shm-usage")
    opciones.add_argument("--no-sandbox")
    opciones.add_argument("--disable-gpu")
    opciones.add_argument("--lang=en-US")
    opciones.add_argument(f"--user-agent={REQUEST_HEADERS['User-Agent']}")
    opciones.add_experimental_option("excludeSwitches", ["enable-automation"])
    opciones.add_experimental_option("useAutomationExtension", False)

    if proxy := _proxy_del_entorno():
        opciones.add_argument(f"--proxy-server={proxy}")
    return opciones


def crear_driver(headless: bool = True) -> webdriver.Remote:
    """
    Crea un WebDriver con el primer navegador disponible en el sistema.

    Raises:
        NavegadorNoDisponible: si no hay navegador o el driver no arranca.
    """
    _excluir_localhost_del_proxy()

    # Sin servidor grafico no tiene sentido intentar una ventana.
    headless = headless or not _hay_servidor_grafico()
    errores: list[str] = []

    for navegador in navegadores_disponibles():
        try:
            opciones = _opciones(navegador, headless)
            fabrica = webdriver.Edge if navegador == "edge" else webdriver.Chrome
            driver = fabrica(options=opciones)
            driver.set_page_load_timeout(60)
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
            )
            log.info("navegador iniciado: %s (headless=%s)", navegador, headless)
            return driver
        except (WebDriverException, OSError) as error:
            errores.append(f"{navegador}: {str(error).splitlines()[0][:160]}")
            log.warning("no se pudo iniciar %s", navegador)

    detalle = " | ".join(errores) if errores else "no se detecto ningun navegador"
    raise NavegadorNoDisponible(
        "Selenium no puede ejecutarse en este entorno. "
        f"Detalle: {detalle}. "
        "Instale Google Chrome o ejecute el pipeline con --sin-selenium "
        "(las cookies de data/raw/cookies.json permiten completar el analisis)."
    )


# ---------------------------------------------------------------------------
# Flujo de arranque
# ---------------------------------------------------------------------------
def fijar_ubicacion(driver: webdriver.Remote, zip_code: str = DELIVERY_ZIP) -> str:
    """Fija la ubicacion de entrega con el widget 'Deliver to' y devuelve su etiqueta."""
    driver.get(_PAGINA_DE_APOYO)
    WebDriverWait(driver, 25).until(
        EC.presence_of_element_located((By.ID, "nav-global-location-popover-link"))
    )

    driver.find_element(By.ID, "nav-global-location-popover-link").click()
    campo = WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.ID, "GLUXZipUpdateInput"))
    )
    campo.clear()
    campo.send_keys(zip_code)
    driver.find_element(By.ID, "GLUXZipUpdate").click()
    time.sleep(4)

    for selector in ("#GLUXConfirmClose", "button[name='glowDoneButton']"):
        try:
            driver.find_element(By.CSS_SELECTOR, selector).click()
            break
        except WebDriverException:
            continue
    time.sleep(3)

    try:
        return driver.find_element(By.ID, "glow-ingress-line2").text.strip()
    except WebDriverException:
        return zip_code


def exportar_cookies(driver: webdriver.Remote, ruta: Path = COOKIES_PATH) -> dict[str, str]:
    """Guarda las cookies de la sesion en JSON para reutilizarlas."""
    cookies = {cookie["name"]: cookie["value"] for cookie in driver.get_cookies()}
    # Homologa idioma y divisa: sin esto cada metodo recibe la ficha en un
    # idioma distinto segun el Accept-Language y la comparacion falla.
    cookies["lc-main"] = SESSION_LOCALE
    cookies["i18n-prefs"] = SESSION_CURRENCY
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    return cookies


def bootstrap(headless: bool = True, zip_code: str = DELIVERY_ZIP) -> dict[str, str]:
    """Ejecuta el arranque de sesion completo y devuelve las cookies."""
    driver = crear_driver(headless=headless)
    try:
        etiqueta = fijar_ubicacion(driver, zip_code)
        cookies = exportar_cookies(driver)
        log.info("ubicacion de entrega fijada: %s (%s)", zip_code, etiqueta)
        log.info("cookies exportadas: %s -> %s", len(cookies), COOKIES_PATH.name)
        return cookies
    finally:
        driver.quit()


if __name__ == "__main__":
    bootstrap()
