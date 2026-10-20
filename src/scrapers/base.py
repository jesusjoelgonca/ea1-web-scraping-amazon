"""
base.py
=======
Contrato comun de los tres metodos de extraccion.

Cada scraper implementa `ejecutar()` y hereda la persistencia y el calculo de
metricas. Asi se evita repetir en cada metodo el guardado de CSV, el conteo de
cobertura de campos y el registro de la duracion.

Autor: Jesus Gonzalez
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from ..config import PROCESSED_DIR, TARGET, ScrapingTarget
from ..logger import get_logger
from ..models import MetricasMetodo, Producto

log = get_logger("scraper")


class BaseScraper(ABC):
    """Esqueleto de un metodo de web scraping."""

    metodo: str = "base"

    def __init__(self, target: ScrapingTarget = TARGET) -> None:
        self.target = target

    # ------------------------------------------------------------------
    @abstractmethod
    def ejecutar(self) -> list[Producto]:
        """Extrae los productos y devuelve registros normalizados."""

    # ------------------------------------------------------------------
    def guardar(self, productos: list[Producto], nombre_archivo: str) -> Path:
        """Persiste los registros en CSV dentro de data/processed/."""
        destino = PROCESSED_DIR / nombre_archivo
        pd.DataFrame([producto.to_dict() for producto in productos]).to_csv(
            destino, index=False, encoding="utf-8-sig"
        )
        log.info("%s registros guardados en %s", len(productos), destino.name)
        return destino

    def resumen(
        self,
        productos: list[Producto],
        duracion_seg: float,
        tasa_exito_http: float = 1.0,
        peticiones: dict[str, int] | None = None,
    ) -> MetricasMetodo:
        """Calcula las metricas del metodo para la validacion posterior."""
        cobertura = (
            sum(producto.cobertura_campos_clave() for producto in productos) / len(productos)
            if productos
            else 0.0
        )
        return MetricasMetodo(
            metodo=self.metodo,
            productos=len(productos),
            duracion_seg=round(duracion_seg, 2),
            cobertura_campos=round(cobertura, 4),
            tasa_exito_http=tasa_exito_http,
            peticiones=peticiones or {},
        )

    # ------------------------------------------------------------------
    def cronometrar(self):
        """Context manager simple para medir la duracion de una etapa."""

        class _Cronometro:
            def __enter__(self_inner):
                self_inner.inicio = time.perf_counter()
                return self_inner

            def __exit__(self_inner, *_):
                self_inner.duracion = round(time.perf_counter() - self_inner.inicio, 2)
                return False

        return _Cronometro()
