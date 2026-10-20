"""
verificar_entorno.py
====================
Diagnostico rapido del entorno de ejecucion.

Comprueba version de Python, dependencias, navegador disponible y presencia de
los insumos versionados (cookies, HTML en cache, salidas del pipeline). Sirve
para saber de antemano que etapas pueden ejecutarse en la maquina donde se
abre el repositorio, por ejemplo un contenedor de Codespaces sin navegador.

Uso:
    python scripts/verificar_entorno.py
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DEPENDENCIAS = (
    "requests",
    "bs4",
    "lxml",
    "pandas",
    "openpyxl",
    "selenium",
    "scrapy",
    "matplotlib",
)


def _marcar(ok: bool) -> str:
    return "OK  " if ok else "FALTA"


def main() -> int:
    print(f"Python      : {platform.python_version()} ({platform.system()} {platform.machine()})")
    print(f"Ejecutable  : {sys.executable}")
    print(f"Raiz        : {RAIZ}")

    print("\nDependencias")
    faltantes: list[str] = []
    for paquete in DEPENDENCIAS:
        try:
            modulo = __import__(paquete)
            version = getattr(modulo, "__version__", "?")
            print(f"  [{_marcar(True)}] {paquete:12s} {version}")
        except ImportError:
            faltantes.append(paquete)
            print(f"  [{_marcar(False)}] {paquete:12s}")

    print("\nNavegador (solo etapa Selenium)")
    try:
        from src.session_bootstrap import NavegadorNoDisponible, crear_driver, navegadores_disponibles

        candidatos = navegadores_disponibles()
        print(f"  detectados: {', '.join(candidatos) if candidatos else 'ninguno'}")
        try:
            driver = crear_driver(headless=True)
            print(f"  [{_marcar(True)}] sesion WebDriver iniciada ({driver.name})")
            driver.quit()
            selenium_ok = True
        except NavegadorNoDisponible as error:
            print(f"  [{_marcar(False)}] {error}")
            selenium_ok = False
    except ImportError:
        print("  [FALTA] selenium no instalado")
        selenium_ok = False

    print("\nInsumos versionados")
    insumos = {
        "cookies de sesion": RAIZ / "data" / "raw" / "cookies.json",
        "semillas Scrapy": RAIZ / "data" / "raw" / "seeds.json",
        "HTML en cache": RAIZ / "data" / "raw" / "html",
        "catalogo consolidado": RAIZ / "data" / "processed" / "catalogo_consolidado.csv",
        "metricas": RAIZ / "reports" / "metricas.json",
    }
    for etiqueta, ruta in insumos.items():
        existe = ruta.exists()
        detalle = ""
        if ruta.is_dir():
            detalle = f" ({len(list(ruta.glob('*.html')))} archivos)"
        print(f"  [{_marcar(existe)}] {etiqueta}{detalle}")

    print("\nRecomendacion de ejecucion")
    if faltantes:
        print(f"  pip install -r requirements.txt  (faltan: {', '.join(faltantes)})")
    if selenium_ok:
        print("  python -m src.pipeline")
    else:
        print("  python -m src.pipeline --sin-selenium")
        print("  El pipeline usa data/raw/cookies.json y completa las etapas 1 y 3.")

    print("\nPruebas unitarias: python -m unittest discover -s tests -v")
    return 0


if __name__ == "__main__":
    sys.exit(main())
