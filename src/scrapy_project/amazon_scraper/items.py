"""
items.py
========
Item de Scrapy: transporte de datos CRUDOS entre el spider y el pipeline.

El spider no normaliza nada; solo selecciona texto. La conversion a tipos
(precio float, resenas int, etc.) ocurre en `pipelines.NormalizacionPipeline`,
que reutiliza las funciones puras de `src/normalizers.py`.
"""

from __future__ import annotations

import scrapy


class ProductoItem(scrapy.Item):
    """Campos crudos extraidos de una ficha de producto."""

    asin = scrapy.Field()
    url = scrapy.Field()
    titulo = scrapy.Field()
    marca = scrapy.Field()
    precio_texto = scrapy.Field()
    precio_lista_texto = scrapy.Field()
    calificacion_texto = scrapy.Field()
    resenas_texto = scrapy.Field()
    disponibilidad = scrapy.Field()
    envio = scrapy.Field()
    sistema_operativo = scrapy.Field()
    almacenamiento_texto = scrapy.Field()
    ram_texto = scrapy.Field()
