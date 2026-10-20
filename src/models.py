"""
models.py
=========
Contratos de datos del pipeline.

`Producto` define, en un solo lugar, la estructura del registro extraido y
sirve como validador ligero: cualquier scraper construye un `Producto`, de
modo que un campo mal escrito falla de inmediato en lugar de propagarse
silenciosamente al dataset.

Autor: Jesus Gonzalez
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Any, Optional

from .config import KEY_FIELDS


@dataclass
class Producto:
    """Registro normalizado de una ficha de producto de Amazon."""

    asin: str
    titulo: Optional[str] = None
    marca: Optional[str] = None
    precio: Optional[float] = None
    moneda: Optional[str] = None
    precio_lista: Optional[float] = None
    descuento_pct: Optional[float] = None
    calificacion: Optional[float] = None
    resenas: Optional[int] = None
    disponibilidad: Optional[str] = None
    envio: Optional[str] = None
    vendedor: Optional[str] = None
    sistema_operativo: Optional[str] = None
    ram_gb: Optional[int] = None
    almacenamiento_gb: Optional[int] = None
    pantalla_pulgadas: Optional[float] = None
    modelo: Optional[str] = None
    bsr_rank: Optional[int] = None
    bsr_categoria: Optional[str] = None
    num_bullets: Optional[int] = None
    bullet_1: Optional[str] = None
    histograma: dict[str, int] = field(default_factory=dict)

    # Trazabilidad
    url: Optional[str] = None
    metodo: str = "desconocido"
    fecha_extraccion: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )

    # ------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Serializa el registro a un diccionario plano (apto para CSV)."""
        datos = asdict(self)
        datos["histograma"] = str(self.histograma) if self.histograma else None
        return datos

    def cobertura_campos_clave(self) -> float:
        """Proporcion de campos clave diligenciados (0-1)."""
        valores = [getattr(self, campo) for campo in KEY_FIELDS]
        return sum(valor not in (None, "", {}) for valor in valores) / len(KEY_FIELDS)

    @classmethod
    def nombres_de_campo(cls) -> list[str]:
        return [campo.name for campo in fields(cls)]


@dataclass
class MetricasMetodo:
    """Resultado de evaluar un metodo de extraccion contra las metricas de exito."""

    metodo: str
    productos: int
    duracion_seg: float
    cobertura_campos: float
    tasa_exito_http: float
    peticiones: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResultadoValidacion:
    """Veredicto global de la evidencia."""

    cobertura_campos: float
    concordancia_metodos: float
    productos: int
    tasa_exito_http: float
    duracion_seg: float
    criterios: dict[str, bool] = field(default_factory=dict)

    @property
    def aprobado(self) -> bool:
        return all(self.criterios.values())

    def to_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos["aprobado"] = self.aprobado
        return datos
