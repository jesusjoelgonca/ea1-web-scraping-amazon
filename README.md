# EA1 — Análisis y herramientas de extracción de datos

Evidencia de aprendizaje 1 del curso **Programación para Análisis de Datos**
(PREICA2602B020048). Aplica *web scraping* con **BeautifulSoup**, **Selenium** y **Scrapy**
sobre una ficha de Amazon y construye un catálogo comparable de teléfonos inteligentes.

- **Estudiante:** Jesus Gonzalez
- **Artículo analizado:** Samsung Galaxy A57 5G (128 GB) — ASIN `B0GW9TVHJB`
- **Sitio:** Amazon.com (contexto de entrega: ZIP 10001, Nueva York)
- **Entregables:**
  - `docs/Gonzalez_Jesus_Analizando_EA1.docx` — informe (APA 7.ª edición)
  - `docs/Gonzalez_Jesus_Analizando_EA1.pdf` — mismo informe en PDF
  - `Gonzalez_Jesus_Analizando_EA1.ipynb` — cuaderno ejecutado con el análisis

## Resultado de la ejecución

| Métrica | Valor | Umbral | Estado |
|---|---|---|---|
| Productos en el catálogo | 16 | ≥ 12 | OK |
| Cobertura de campos clave | 98,8 % | ≥ 95 % | OK |
| Concordancia entre métodos | 100,0 % | ≥ 90 % | OK |
| Tasa de éxito HTTP | 100,0 % | ≥ 95 % | OK |
| Duración del pipeline | 72 s | ≤ 600 s | OK |

Veredicto automático: **APROBADO** (`reports/validacion.txt`).

## Problema técnico que resuelve el proyecto

Amazon suprime el *buybox* cuando la ubicación de entrega está fuera de Estados Unidos
(*“This item cannot be shipped to your selected delivery location”*), por lo que el precio no
existe en el HTML. El pipeline resuelve ese contexto con Selenium (widget *Deliver to*),
exporta las cookies resultantes y las reutiliza en BeautifulSoup y en Scrapy, de modo que los
tres métodos observan el mismo estado comercial y sus resultados son comparables.

## Estructura

```
EA1/
├── Gonzalez_Jesus_Analizando_EA1.ipynb   # cuaderno ejecutado (análisis)
├── docs/
│   ├── Gonzalez_Jesus_Analizando_EA1.docx
│   └── Gonzalez_Jesus_Analizando_EA1.pdf
├── data/
│   ├── raw/                              # cookies, semillas y salida de Scrapy
│   └── processed/                        # catálogos en CSV/XLSX
├── reports/
│   ├── metricas.json                     # métricas de éxito
│   ├── validacion.txt                    # veredicto legible
│   └── figuras/                          # gráficas y captura de evidencia
├── scripts/
│   └── verificar_entorno.py              # diagnóstico del entorno
├── src/
│   ├── config.py                         # configuración única
│   ├── normalizers.py                    # funciones puras de normalización
│   ├── models.py                         # contrato de datos (Producto)
│   ├── http_client.py                    # HTTP: caché, reintentos, anti-bot
│   ├── session_bootstrap.py              # Selenium fija el ZIP y exporta cookies
│   ├── scrapers/
│   │   ├── base.py                       # contrato común de los métodos
│   │   ├── bs4_scraper.py                # método 1
│   │   ├── selenium_scraper.py           # método 2
│   │   └── scrapy_project/               # método 3 (spider + pipelines)
│   ├── validation.py                     # métricas y veredicto
│   ├── visualization.py                  # figuras
│   └── pipeline.py                       # orquestador
└── tests/test_normalizers.py             # 20 pruebas unitarias
```

## Instalación

Funciona igual en **Windows, Linux y macOS**.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Requisitos: Python 3.10 o superior. Selenium Manager (incluido en Selenium ≥ 4.6) descarga el
driver del navegador automáticamente; no hay que instalar `chromedriver` ni `msedgedriver`.

## Ejecución

```bash
# Diagnóstico del entorno: dependencias, navegador e insumos disponibles
python scripts/verificar_entorno.py

# Pipeline completo (bootstrap + 3 métodos + validación + figuras)
python -m src.pipeline

# Reutilizando el HTML cacheado (sin golpear el sitio)
python -m src.pipeline --sin-bootstrap --sin-selenium

# Pruebas unitarias
python -m unittest discover -s tests -v
```

Etapas ejecutables por separado:

```bash
python -m src.session_bootstrap                    # fija el ZIP y exporta cookies
python -m src.scrapers.bs4_scraper                 # método 1
python -m src.scrapers.selenium_scraper            # método 2
python -m scrapy crawl productos                   # método 3 (desde src/scrapy_project)
```

### Ejecución en Linux o en la nube (Codespaces, contenedores, VS Code Web)

El código elige el navegador en tiempo de ejecución: **Chrome/Chromium en Linux y macOS**,
**Edge/Chrome en Windows**. Si el entorno no tiene navegador —lo habitual en un contenedor—
`crear_driver()` lanza `NavegadorNoDisponible` y el pipeline **no se cae**: registra el aviso y
continúa con BeautifulSoup y Scrapy, que son los métodos que no necesitan navegador.

```bash
pip install -r requirements.txt
python scripts/verificar_entorno.py     # indica si hay navegador disponible
python -m src.pipeline --sin-selenium   # camino recomendado en contenedores
```

Detalles de portabilidad ya resueltos:

- Rutas construidas con `pathlib` a partir de la ubicación del paquete, sin rutas absolutas.
- Scrapy se invoca con `python -m scrapy`, no con el binario `scrapy`, para que funcione dentro
  de cualquier entorno virtual.
- Archivos de datos abiertos siempre con `encoding="utf-8"` explícito.
- Opciones de navegador `--no-sandbox`, `--disable-dev-shm-usage` y `--disable-gpu`, necesarias
  en contenedores; el modo *headless* se fuerza cuando no hay servidor gráfico (`DISPLAY`).
- `data/raw/cookies.json` se versiona a propósito: sin navegador, ese archivo aporta el
  contexto comercial (ubicación e idioma) que necesitan los otros dos métodos.
- `data/raw/html/` **no** se versiona (42 MB): la primera ejecución lo descarga. Las salidas ya
  procesadas sí vienen en el repositorio, de modo que el cuaderno y el informe se leen sin red.
- Si el crawler de Scrapy falla, la salida anterior de `data/raw/scrapy_productos.json` se
  restaura en lugar de perderse.

## Formato del informe

El informe (`docs/Gonzalez_Jesus_Analizando_EA1.docx` y su PDF) sigue APA 7.ª edición: Times
New Roman 12 pt, interlineado doble, márgenes de 2,54 cm, numeración de página en el
encabezado, portada sencilla de estudiante, tablas sin líneas verticales, figuras en escala de
grises y referencias con sangría francesa. No hay ningún elemento en color: todo el texto es
negro.

## Salidas

| Archivo | Contenido |
|---|---|
| `data/processed/catalogo_consolidado.csv` / `.xlsx` | Catálogo final de 16 productos |
| `data/processed/bs4_productos.csv` | Salida del método 1 |
| `data/processed/selenium_productos.csv` | Salida del método 2 (incluye histograma) |
| `data/raw/scrapy_productos.json` | Salida del método 3 |
| `reports/metricas.json` | Cobertura, concordancia, tiempos y criterios |
| `reports/figuras/*.png` | Figuras del informe y captura de la sesión Selenium |

## Decisiones de diseño

- **Una sola fuente de configuración** (`config.py`): ningún módulo declara URLs, cabeceras ni
  umbrales por su cuenta.
- **Funciones puras y probadas** (`normalizers.py`): las mismas reglas de limpieza alimentan a
  los tres métodos; 20 pruebas unitarias cubren los formatos de precio, calificación y reseñas.
- **Contrato de datos explícito** (`Producto`): un campo mal escrito falla al construir el
  registro, no al analizarlo.
- **Degradación controlada**: si falta el navegador, la etapa Selenium se omite con un aviso y
  el resto del pipeline sigue; el informe declara qué métodos se ejecutaron.
- **Caché de HTML**: el análisis es reproducible sin volver a descargar y cada ficha conserva
  su evidencia.
- **Cortesía con el sitio**: `robots.txt` respetado, dos peticiones concurrentes como máximo,
  espera aleatoria entre solicitudes y reintentos con retroceso exponencial.

## Consideraciones éticas y legales

La extracción se limitó a 16 fichas públicas, con fines académicos, sin autenticación ni
acceso a datos personales. Se respetó `robots.txt`, se identificó un agente de usuario real y
se mantuvo una frecuencia de peticiones baja. Los datos se usan únicamente para el análisis
de la asignatura.
