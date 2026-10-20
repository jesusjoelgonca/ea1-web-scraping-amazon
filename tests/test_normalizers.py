"""
test_normalizers.py
===================
Pruebas unitarias de las funciones puras de normalizacion.

Se ejecutan sin red y sin navegador, lo que las hace aptas para integracion
continua:

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.normalizers import (  # noqa: E402
    calcular_descuento,
    limpiar_marca,
    parse_calificacion,
    parse_decimal,
    parse_entero,
    parse_precio,
    parse_resenas,
)


class TestParsePrecio(unittest.TestCase):
    def test_dolares_simple(self):
        self.assertEqual(parse_precio("$499.99"), (499.99, "USD"))

    def test_miles_con_coma(self):
        self.assertEqual(parse_precio("$1,299.00"), (1299.0, "USD"))

    def test_pesos_colombianos(self):
        self.assertEqual(parse_precio("COP1.809.393"), (1809393.0, "COP"))

    def test_rango_toma_limite_inferior(self):
        self.assertEqual(parse_precio("$79.99 - $99.99"), (79.99, "USD"))

    def test_texto_sin_precio(self):
        self.assertEqual(parse_precio("No disponible"), (None, None))

    def test_none(self):
        self.assertEqual(parse_precio(None), (None, None))


class TestParseCalificacion(unittest.TestCase):
    def test_ingles(self):
        self.assertEqual(parse_calificacion("4.4 out of 5 stars"), 4.4)

    def test_espanol(self):
        self.assertEqual(parse_calificacion("4,4 de 5 estrellas"), 4.4)

    def test_sin_datos(self):
        self.assertIsNone(parse_calificacion(None))


class TestParseResenas(unittest.TestCase):
    def test_miles_con_k(self):
        self.assertEqual(parse_resenas("(2.1K)"), 2100)

    def test_millones(self):
        self.assertEqual(parse_resenas("1.5M ratings"), 1500000)

    def test_entero_con_separador(self):
        self.assertEqual(parse_resenas("6,135 ratings"), 6135)

    def test_parentesis_simple(self):
        self.assertEqual(parse_resenas("(209)"), 209)


class TestEspecificaciones(unittest.TestCase):
    def test_entero_desde_gb(self):
        self.assertEqual(parse_entero("128 GB"), 128)

    def test_decimal_desde_pulgadas(self):
        self.assertEqual(parse_decimal("6.7 inches"), 6.7)

    def test_sin_numero(self):
        self.assertIsNone(parse_entero("No aplica"))


class TestReglasDeNegocio(unittest.TestCase):
    def test_descuento(self):
        self.assertEqual(calcular_descuento(80.0, 100.0), 20.0)

    def test_sin_descuento_cuando_precio_lista_es_menor(self):
        self.assertIsNone(calcular_descuento(120.0, 100.0))

    def test_marca_desde_byline(self):
        self.assertEqual(limpiar_marca("Visit the Samsung Store"), "Samsung")

    def test_marca_con_prefijo(self):
        self.assertEqual(limpiar_marca("Brand: Samsung"), "Samsung")


if __name__ == "__main__":
    unittest.main()
