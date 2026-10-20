"""
validation.py
=============
Evaluacion de la calidad de la extraccion.

Responde a la pregunta de la rubrica "metricas de exito": no basta con que el
scraper corra, hay que demostrar que los datos son completos, consistentes
entre metodos y trazables.

Metricas calculadas
-------------------
1. Cobertura de campos clave: proporcion de valores no nulos.
2. Concordancia entre metodos: para los ASIN extraidos por mas de un metodo,
   se compara precio, calificacion y numero de resenas con tolerancias
   explicitas (el conteo de resenas cambia entre peticiones).
3. Tasa de exito HTTP: peticiones exitosas / peticiones realizadas.
4. Tamano del catalogo y duracion total.

Autor: Jesus Gonzalez
"""

from __future__ import annotations

import difflib
import json
from datetime import datetime, timezone
from itertools import combinations
from typing import Any

import pandas as pd

from .config import (
    KEY_FIELDS,
    MAX_PIPELINE_SECONDS,
    MIN_CATALOG_SIZE,
    MIN_FIELD_COVERAGE,
    MIN_HTTP_SUCCESS_RATE,
    MIN_METHOD_AGREEMENT,
    REPORTS_DIR,
    TARGET,
)
from .logger import get_logger
from .models import ResultadoValidacion

log = get_logger("validacion")

# Tolerancias para considerar que dos metodos observaron el mismo dato
TOLERANCIA_PRECIO_REL = 0.01     # 1 %
TOLERANCIA_CALIFICACION = 0.1    # 0.1 estrellas
TOLERANCIA_RESENAS_REL = 0.02    # 2 % (el contador cambia entre peticiones)
UMBRAL_SIMILITUD_TITULO = 0.90


# ---------------------------------------------------------------------------
# Metricas por metodo
# ---------------------------------------------------------------------------
def cobertura_campos(df: pd.DataFrame, campos: tuple[str, ...] = KEY_FIELDS) -> float:
    """Proporcion de celdas diligenciadas sobre los campos clave presentes."""
    presentes = [campo for campo in campos if campo in df.columns]
    if df.empty or not presentes:
        return 0.0
    return round(float(df[presentes].notna().mean().mean()), 4)


def cobertura_por_campo(df: pd.DataFrame) -> dict[str, float]:
    """Cobertura individual por campo clave (para el informe)."""
    return {
        campo: round(float(df[campo].notna().mean()), 4)
        for campo in KEY_FIELDS
        if campo in df.columns
    }


# ---------------------------------------------------------------------------
# Concordancia entre metodos
# ---------------------------------------------------------------------------
def _precios_coinciden(a: float, b: float) -> bool:
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(a - b) <= max(a, b) * TOLERANCIA_PRECIO_REL


def _calificaciones_coinciden(a: float, b: float) -> bool:
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(a - b) <= TOLERANCIA_CALIFICACION


def _resenas_coinciden(a: float, b: float) -> bool:
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(a - b) <= max(a, b, 1) * TOLERANCIA_RESENAS_REL


def _titulos_coinciden(a: str, b: str) -> bool:
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return difflib.SequenceMatcher(None, a.strip(), b.strip()).ratio() >= UMBRAL_SIMILITUD_TITULO


def concordancia_entre_metodos(datasets: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """
    Compara los registros que comparten ASIN entre pares de metodos.

    Devuelve el acuerdo por campo y el detalle de los ASIN comparados.
    """
    campos = {
        "precio": _precios_coinciden,
        "calificacion": _calificaciones_coinciden,
        "resenas": _resenas_coinciden,
        "titulo": _titulos_coinciden,
    }
    aciertos = {campo: [0, 0] for campo in campos}  # [acuerdos, comparaciones]
    detalle: list[dict[str, Any]] = []

    for (nombre_a, df_a), (nombre_b, df_b) in combinations(datasets.items(), 2):
        comunes = set(df_a["asin"]) & set(df_b["asin"])
        for asin in comunes:
            fila_a = df_a.loc[df_a["asin"] == asin].iloc[0]
            fila_b = df_b.loc[df_b["asin"] == asin].iloc[0]
            resultados = {}
            for campo, comparador in campos.items():
                if campo not in fila_a or campo not in fila_b:
                    continue
                valor_a, valor_b = fila_a[campo], fila_b[campo]
                # Solo se comparan valores observados por ambos metodos: un
                # dato ausente penaliza la cobertura, no la concordancia.
                if pd.isna(valor_a) or pd.isna(valor_b):
                    continue
                coincide = comparador(valor_a, valor_b)
                aciertos[campo][1] += 1
                aciertos[campo][0] += int(coincide)
                resultados[campo] = bool(coincide)
            if resultados:
                detalle.append({"asin": asin, "metodos": f"{nombre_a} vs {nombre_b}", **resultados})

    por_campo = {
        campo: round(conteo[0] / conteo[1], 4) if conteo[1] else None
        for campo, conteo in aciertos.items()
    }
    valores = [valor for valor in por_campo.values() if valor is not None]
    global_ = round(sum(valores) / len(valores), 4) if valores else 0.0
    return {"global": global_, "por_campo": por_campo, "detalle": detalle}


# ---------------------------------------------------------------------------
# Veredicto
# ---------------------------------------------------------------------------
def evaluar(
    datasets: dict[str, pd.DataFrame],
    duracion_seg: float,
    tasa_exito_http: float,
) -> tuple[ResultadoValidacion, dict[str, Any]]:
    """Calcula el veredicto global y el detalle de la validacion."""
    catalogo = max(datasets.values(), key=len) if datasets else pd.DataFrame()
    cobertura = cobertura_campos(catalogo)
    concordancia = concordancia_entre_metodos(datasets)

    resultado = ResultadoValidacion(
        cobertura_campos=cobertura,
        concordancia_metodos=concordancia["global"],
        productos=int(len(catalogo)),
        tasa_exito_http=round(tasa_exito_http, 4),
        duracion_seg=round(duracion_seg, 2),
        criterios={
            "cobertura_campos": cobertura >= MIN_FIELD_COVERAGE,
            "concordancia_metodos": concordancia["global"] >= MIN_METHOD_AGREEMENT,
            "tamano_catalogo": len(catalogo) >= MIN_CATALOG_SIZE,
            "tasa_exito_http": tasa_exito_http >= MIN_HTTP_SUCCESS_RATE,
            "tiempo_ejecucion": duracion_seg <= MAX_PIPELINE_SECONDS,
        },
    )

    detalle = {
        "fecha_ejecucion": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "objetivo": {
            "sitio": TARGET.site,
            "termino_busqueda": TARGET.search_term,
            "articulo_asin": TARGET.article_asin,
            "zip_entrega": TARGET.delivery_zip,
        },
        "cobertura_por_campo": cobertura_por_campo(catalogo),
        "concordancia": concordancia,
        "umbrales": {
            "cobertura_campos": MIN_FIELD_COVERAGE,
            "concordancia_metodos": MIN_METHOD_AGREEMENT,
            "tamano_catalogo": MIN_CATALOG_SIZE,
            "tasa_exito_http": MIN_HTTP_SUCCESS_RATE,
            "tiempo_ejecucion_seg": MAX_PIPELINE_SECONDS,
        },
        "validacion": resultado.to_dict(),
    }
    return resultado, detalle


def _serializable(valor: Any) -> Any:
    """Convierte escalares de numpy (bool_, int64, float64) a tipos nativos."""
    if hasattr(valor, "item"):
        return valor.item()
    raise TypeError(f"tipo no serializable: {type(valor)!r}")


def guardar_metricas(detalle: dict[str, Any], ruta=None) -> None:
    """Persiste las metricas en JSON y un resumen legible en TXT."""
    destino_json = ruta or REPORTS_DIR / "metricas.json"
    destino_json.write_text(
        json.dumps(detalle, ensure_ascii=False, indent=2, default=_serializable),
        encoding="utf-8",
    )

    validacion = detalle["validacion"]
    lineas = [
        "REPORTE DE VALIDACION - EA1 WEB SCRAPING",
        "=" * 46,
        f"Fecha: {detalle['fecha_ejecucion']}",
        f"Articulo: {detalle['objetivo']['articulo_asin']} ({detalle['objetivo']['sitio']})",
        "",
        "Metricas",
        "-" * 46,
        f"Productos en el catalogo : {validacion['productos']}",
        f"Cobertura de campos      : {validacion['cobertura_campos']:.1%}",
        f"Concordancia entre metodos: {validacion['concordancia_metodos']:.1%}",
        f"Tasa de exito HTTP       : {validacion['tasa_exito_http']:.1%}",
        f"Duracion total           : {validacion['duracion_seg']} s",
        "",
        "Criterios",
        "-" * 46,
        *[f"{'OK ' if ok else 'FALLA'}  {criterio}" for criterio, ok in validacion["criterios"].items()],
        "",
        f"VEREDICTO: {'APROBADO' if validacion['aprobado'] else 'REVISAR'}",
    ]
    (REPORTS_DIR / "validacion.txt").write_text("\n".join(lineas), encoding="utf-8")
    log.info("metricas guardadas en %s y validacion.txt", destino_json.name)
