"""
pipelines.py
============
Pipelines de Scrapy: normalizacion y validacion.

`NormalizacionPipeline` convierte los textos crudos del Item en el mismo
esquema `Producto` que usan los otros dos metodos, reutilizando las funciones
puras de `src/normalizers.py` (una sola implementacion de las reglas de
limpieza para todo el proyecto).

`ValidacionPipeline` descarta registros sin identificador o sin titulo y deja
traza en el log.
"""

from __future__ import annotations

from itemadapter import ItemAdapter
from scrapy.exceptions import DropItem

from src.logger import get_logger
from src.models import Producto
from src.normalizers import (
    calcular_descuento,
    inferir_marca_desde_titulo,
    limpiar_marca,
    parse_calificacion,
    parse_entero,
    parse_precio,
    parse_resenas,
)

log = get_logger("scrapy.pipeline")


class NormalizacionPipeline:
    """Convierte el Item crudo en un diccionario normalizado."""

    def process_item(self, item):
        datos = ItemAdapter(item)
        precio, moneda = parse_precio(datos.get("precio_texto"))
        precio_lista, _ = parse_precio(datos.get("precio_lista_texto"))
        titulo = datos.get("titulo")

        producto = Producto(
            asin=datos.get("asin", ""),
            url=datos.get("url"),
            titulo=titulo,
            marca=limpiar_marca(datos.get("marca")) or inferir_marca_desde_titulo(titulo),
            precio=precio,
            moneda=moneda,
            precio_lista=precio_lista,
            descuento_pct=calcular_descuento(precio, precio_lista),
            calificacion=parse_calificacion(datos.get("calificacion_texto")),
            resenas=parse_resenas(datos.get("resenas_texto")),
            disponibilidad=datos.get("disponibilidad"),
            envio=datos.get("envio"),
            sistema_operativo=datos.get("sistema_operativo"),
            ram_gb=parse_entero(datos.get("ram_texto")),
            almacenamiento_gb=parse_entero(datos.get("almacenamiento_texto")),
            metodo="scrapy",
        )
        return producto.to_dict()


class ValidacionPipeline:
    """Descarta registros incompletos y contabiliza el descarte."""

    def __init__(self) -> None:
        self.validos = 0
        self.descartados = 0

    def process_item(self, item):
        if not item.get("asin") or not item.get("titulo"):
            self.descartados += 1
            raise DropItem(f"registro sin asin/titulo: {item.get('url')}")
        self.validos += 1
        return item

    def close_spider(self) -> None:
        log.info("scrapy: %s validos, %s descartados", self.validos, self.descartados)
