"""
test_artefactos.py
==================
Verifica que los artefactos versionados de la entrega sean coherentes entre sí.

A diferencia de ``test_normalizers``, que prueba funciones puras, estas pruebas
revisan los productos del pipeline: el catálogo consolidado, el reporte de
métricas, el cuaderno ejecutado y los entregables en Word y PDF. Sirven como
red de seguridad en integración continua: si un commit deja el catálogo sin
filas, borra las métricas o sube un cuaderno con celdas en error, la corrida
falla antes de que el cambio llegue al docente.
"""

from __future__ import annotations

import csv
import json
import unittest
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

CATALOGO = RAIZ / "data" / "processed" / "catalogo_consolidado.csv"
METRICAS = RAIZ / "reports" / "metricas.json"
CUADERNO = RAIZ / "Gonzalez_Jesus_Analizando_EA1.ipynb"
DOCX = RAIZ / "docs" / "Gonzalez_Jesus_Analizando_EA1.docx"
PDF = RAIZ / "docs" / "Gonzalez_Jesus_Analizando_EA1.pdf"

ARTICULO = "B0GW9TVHJB"
COLUMNAS_CLAVE = {
    "asin",
    "titulo",
    "marca",
    "precio",
    "calificacion",
    "resenas",
    "metodo",
    "histograma",
}
CRITERIOS = {
    "cobertura_campos",
    "concordancia_metodos",
    "tamano_catalogo",
    "tasa_exito_http",
    "tiempo_ejecucion",
}


class TestCatalogo(unittest.TestCase):
    """El catálogo consolidado debe conservar su esquema y su tamaño mínimo."""

    @classmethod
    def setUpClass(cls) -> None:
        with CATALOGO.open(encoding="utf-8-sig", newline="") as archivo:
            cls.filas = list(csv.DictReader(archivo))

    def test_catalogo_tiene_productos_suficientes(self) -> None:
        self.assertGreaterEqual(len(self.filas), 12, "el catálogo perdió registros")

    def test_columnas_clave_presentes(self) -> None:
        faltantes = COLUMNAS_CLAVE - set(self.filas[0])
        self.assertFalse(faltantes, f"faltan columnas: {sorted(faltantes)}")

    def test_asin_sin_duplicados(self) -> None:
        asins = [fila["asin"] for fila in self.filas]
        self.assertEqual(len(asins), len(set(asins)), "hay ASIN repetidos")

    def test_articulo_principal_identificado(self) -> None:
        principales = [fila for fila in self.filas if fila["es_articulo_principal"] == "True"]
        self.assertEqual(len(principales), 1, "debe haber un único artículo principal")
        self.assertEqual(principales[0]["asin"], ARTICULO)


class TestMetricas(unittest.TestCase):
    """El reporte de validación debe declarar los cinco criterios y su veredicto."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.metricas = json.loads(METRICAS.read_text(encoding="utf-8"))

    def test_estructura_del_reporte(self) -> None:
        for clave in ("fecha_ejecucion", "objetivo", "umbrales", "validacion", "metodos"):
            self.assertIn(clave, self.metricas)

    def test_cinco_criterios_evaluados(self) -> None:
        criterios = set(self.metricas["validacion"]["criterios"])
        self.assertEqual(criterios, CRITERIOS)

    def test_veredicto_aprobado(self) -> None:
        self.assertTrue(self.metricas["validacion"]["aprobado"])

    def test_tres_metodos_registrados(self) -> None:
        metodos = {metrica["metodo"] for metrica in self.metricas["metodos"]}
        self.assertEqual(metodos, {"beautifulsoup", "selenium", "scrapy"})


class TestCuaderno(unittest.TestCase):
    """El cuaderno debe ser JSON válido y no contener celdas con error."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.cuaderno = json.loads(CUADERNO.read_text(encoding="utf-8"))

    def test_tiene_celdas(self) -> None:
        self.assertGreater(len(self.cuaderno["cells"]), 10)

    def test_sin_errores_de_ejecucion(self) -> None:
        errores = [
            salida
            for celda in self.cuaderno["cells"]
            for salida in celda.get("outputs", [])
            if salida.get("output_type") == "error"
        ]
        self.assertEqual(errores, [], "el cuaderno tiene celdas con error")

    def test_esta_ejecutado(self) -> None:
        codigo = [c for c in self.cuaderno["cells"] if c["cell_type"] == "code"]
        con_salida = [c for c in codigo if c.get("outputs")]
        self.assertGreaterEqual(len(con_salida), len(codigo) - 1, "el cuaderno no está ejecutado")


class TestEntregables(unittest.TestCase):
    """Word y PDF deben existir, ser legibles y conservar las figuras."""

    def test_docx_es_un_paquete_valido(self) -> None:
        with zipfile.ZipFile(DOCX) as paquete:
            nombres = paquete.namelist()
        self.assertIn("word/document.xml", nombres)
        self.assertIn("word/styles.xml", nombres)

    def test_docx_conserva_las_cuatro_figuras(self) -> None:
        with zipfile.ZipFile(DOCX) as paquete:
            imagenes = [n for n in paquete.namelist() if n.startswith("word/media/")]
        self.assertEqual(len(imagenes), 4, f"se esperaban 4 figuras, hay {len(imagenes)}")

    def test_pdf_tiene_firma_y_peso(self) -> None:
        self.assertTrue(PDF.exists(), "falta el PDF")
        self.assertGreater(PDF.stat().st_size, 100_000, "el PDF parece incompleto")
        self.assertTrue(PDF.read_bytes()[:5].startswith(b"%PDF-"), "el archivo no es un PDF")


if __name__ == "__main__":
    unittest.main(verbosity=2)
