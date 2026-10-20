"""
visualization.py
================
Generacion de las figuras del informe.

Se separa del analisis para que el notebook pueda reutilizar las mismas
graficas sin duplicar codigo de matplotlib.

Autor: Jesus Gonzalez
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # backend sin ventana: permite ejecutar en notebook/CI

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .config import FIGURES_DIR  # noqa: E402
from .logger import get_logger  # noqa: E402

log = get_logger("figuras")

# Paleta monocroma: el informe se entrega en blanco y negro (normas APA), de
# modo que las figuras usan una rampa de grises en lugar de colores.
NEGRO = "#000000"
GRIS_OSCURO = "#3d3d3d"
GRIS_MEDIO = "#808080"
GRIS_CLARO = "#b3b3b3"
GRIS_MUY_CLARO = "#d9d9d9"

plt.rcParams.update(
    {
        "figure.dpi": 130,
        "savefig.dpi": 150,
        "font.size": 9,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.edgecolor": NEGRO,
        "axes.labelcolor": NEGRO,
        "text.color": NEGRO,
        "xtick.color": NEGRO,
        "ytick.color": NEGRO,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linestyle": "--",
        "grid.color": GRIS_MEDIO,
    }
)


def _guardar(fig: plt.Figure, nombre: str) -> Path:
    destino = FIGURES_DIR / nombre
    fig.tight_layout()
    fig.savefig(destino, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    log.info("figura guardada: %s", destino.name)
    return destino


def precios_del_catalogo(df: pd.DataFrame, top: int = 12) -> Path:
    """Barras horizontales con los productos mas costosos del catalogo."""
    datos = (
        df.dropna(subset=["precio"])
        .assign(etiqueta=lambda d: d["titulo"].str.slice(0, 38) + "…")
        .nlargest(top, "precio")
        .sort_values("precio")
    )
    fig, ax = plt.subplots(figsize=(6.4, 4.5))
    barras = ax.barh(datos["etiqueta"], datos["precio"], color=GRIS_OSCURO, height=0.65)
    ax.bar_label(barras, fmt="$%.0f", padding=3, fontsize=8, color=NEGRO)
    ax.set_xlabel("Precio (USD)")
    ax.set_title(f"Productos mas costosos del catalogo (n={len(datos)})")
    ax.set_xlim(0, datos["precio"].max() * 1.15)
    return _guardar(fig, "fig_precios_catalogo.png")


def precio_vs_calificacion(df: pd.DataFrame) -> Path:
    """Dispersion precio - calificacion, con tamano proporcional a las resenas."""
    from matplotlib.colors import LogNorm

    datos = df.dropna(subset=["precio", "calificacion", "resenas"])
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    tamanos = (datos["resenas"].clip(upper=8000) / 8000 * 420) + 25
    # Escala logaritmica: el numero de resenas varia en dos ordenes de magnitud
    # y una escala lineal dejaria casi todos los puntos en blanco.
    dispersion = ax.scatter(
        datos["precio"],
        datos["calificacion"],
        s=tamanos,
        c=datos["resenas"].clip(lower=1),
        cmap="Greys",
        norm=LogNorm(vmin=max(datos["resenas"].min(), 1), vmax=datos["resenas"].max()),
        alpha=0.9,
        edgecolors=NEGRO,
        linewidths=0.6,
    )
    ax.set_xlabel("Precio (USD)")
    ax.set_ylabel("Calificacion promedio (0-5)")
    ax.set_title("Precio vs. calificacion (tamano = numero de resenas)")
    fig.colorbar(dispersion, ax=ax, label="Resenas")
    return _guardar(fig, "fig_precio_calificacion.png")


def comparacion_metodos(metricas: list[dict]) -> Path:
    """Barras agrupadas: cobertura de campos y duracion por metodo."""
    tabla = pd.DataFrame(metricas)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(6.6, 3.4))

    colores = [NEGRO, GRIS_MEDIO, GRIS_CLARO][: len(tabla)]
    ax1.bar(tabla["metodo"], tabla["cobertura_campos"] * 100, color=colores, width=0.55)
    ax1.set_ylim(0, 105)
    ax1.set_ylabel("Cobertura de campos clave (%)")
    ax1.set_title("Completitud por metodo")
    for indice, valor in enumerate(tabla["cobertura_campos"] * 100):
        ax1.text(indice, valor + 2, f"{valor:.0f}%", ha="center", fontsize=8)

    ax2.bar(tabla["metodo"], tabla["duracion_seg"], color=colores, width=0.55)
    ax2.set_ylabel("Duracion (s)")
    ax2.set_title("Costo de ejecucion")
    for indice, valor in enumerate(tabla["duracion_seg"]):
        ax2.text(indice, valor + max(tabla["duracion_seg"]) * 0.03, f"{valor:.1f}s", ha="center", fontsize=8)

    return _guardar(fig, "fig_comparacion_metodos.png")


def resumen_por_marca(df: pd.DataFrame, minimo: int = 1) -> Path:
    """Precio promedio por marca, anotado con el numero de productos.

    Se incluyen todas las marcas con al menos un precio publicado: en este
    catalogo Samsung concentra diez fichas y el resto son marcas con una sola,
    de modo que filtrar por "dos o mas productos" dejaria una unica barra.
    """
    datos = (
        df.dropna(subset=["marca", "precio"])
        .groupby("marca")
        .agg(productos=("asin", "count"), precio_promedio=("precio", "mean"))
        .query("productos >= @minimo")
        .sort_values("precio_promedio")
    )
    fig, ax = plt.subplots(figsize=(6.4, 3.7))
    barras = ax.barh(datos.index, datos["precio_promedio"], color=GRIS_MEDIO, height=0.62)
    etiquetas = [f"${valor:,.0f}  (n={cantidad})" for valor, cantidad in zip(datos["precio_promedio"], datos["productos"])]
    ax.bar_label(barras, labels=etiquetas, padding=4, fontsize=8, color=NEGRO)
    ax.set_xlabel("Precio promedio (USD)")
    ax.set_title("Precio promedio por marca (n = productos con precio)")
    ax.set_xlim(0, datos["precio_promedio"].max() * 1.28)
    return _guardar(fig, "fig_precio_por_marca.png")


def generar_todas(df: pd.DataFrame, metricas: list[dict]) -> list[Path]:
    """Genera el juego completo de figuras del informe."""
    return [
        precios_del_catalogo(df),
        precio_vs_calificacion(df),
        resumen_por_marca(df),
        comparacion_metodos(metricas),
    ]
