from setuptools import find_packages, setup

setup(
    name="ea1-web-scraping",
    version="1.0.0",
    description="Evidencia de aprendizaje 1 - Analisis y herramientas de extraccion de datos",
    author="Jesus Gonzalez",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    python_requires=">=3.10",
    install_requires=[
        "requests>=2.31",
        "beautifulsoup4>=4.12",
        "lxml>=5.0",
        "pandas>=2.0",
        "openpyxl>=3.1",
        "selenium>=4.20",
        "scrapy>=2.13",
        "matplotlib>=3.8",
    ],
)
