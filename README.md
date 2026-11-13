# milan-cdr

Carga y análisis con **MongoDB** de los CDR (Call Detail Records) de Milán
publicados por Telecom Italia en el *Big Data Challenge* (dataset
[doi:10.7910/DVN/EGZHFV](https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/EGZHFV)).

Semana analizada: **lunes 2 a domingo 8 de diciembre de 2013** (36.362.524 registros).

## Requisitos

- Python 3.14 y [uv](https://docs.astral.sh/uv/)
- Google Chrome o Chromium, que kaleido usa para exportar las figuras de plotly a PNG
  (si no hay ninguno, `uv run plotly_get_chrome` descarga uno)
- Un servidor MongoDB ≥ 7.0 en `localhost:27017` (se usan `$median`, `$topN`,
  `$dateTrunc` y `$setWindowFields`). Probado con MongoDB 8.3.

```bash
uv sync                    # crea el entorno e instala dependencias
```

## Uso

```bash
# Apartado 1: descarga (Dataverse exige un email en su "guestbook") y carga
uv run milan-cdr download --email tu@correo.es
uv run milan-cdr load                   # 7 procesos en paralelo, ~3 min

# Apartados 2-8 por separado
uv run milan-cdr run 2

# Todo: resultados en results/ (JSON + Markdown + figuras)
uv run milan-cdr report

# Solo las figuras (PNG para la memoria + HTML interactivo)
uv run milan-cdr figures
```

La configuración se puede cambiar con variables de entorno `MILAN_CDR_*`
(`MONGO_URI`, `DB`, `COLLECTION`, `WEEK_START`, `DATA_DIR`, `RESULTS_DIR`...),
ver `src/milan_cdr/config.py`.

## Estructura

```
src/milan_cdr/
  config.py      constantes del dominio y Settings
  dataverse.py   descarga desde Harvard Dataverse (guestbook + URL firmada)
  parsing.py     línea .txt -> documento (time como Date, campos vacíos omitidos)
  loader.py      carga masiva en paralelo + índices          (apartado 1)
  pipelines.py   pipelines de agregación, funciones puras     (apartados 2-8)
  analysis.py    ejecución de los apartados 2-7
  study.py       estudio de las 8 celdas                      (apartado 8)
  countries.py   prefijo telefónico -> país (phonenumbers + CLDR)
  plots.py       figuras (plotly; PNG con kaleido + HTML)
  report.py      salida por consola, JSON y Markdown
  cli.py         CLI `milan-cdr` (typer)
tests/           tests unitarios + integración contra MongoDB real
```

Colecciones que se crean en `Milan_CDR_db`:

| Colección | Contenido |
|---|---|
| `Milan_CDR_c` | un documento por línea de los ficheros (apartado 1) |
| `Milan_CDR_celdas` | un documento por celda con los acumulados (apartado 6) |
| `Milan_CDR_celda_hora` | un documento por celda y hora con los acumulados (apartado 7) |

## Calidad

```bash
uv run ruff check . && uv run ruff format --check .   # lint + formato
uv run ty check                                        # tipos
uv run pytest --cov                                    # tests (+ doctests)
```

Los tests de integración (`-m mongo`) crean una base de datos temporal con una
semana sintética, ejecutan cada pipeline y comparan el resultado con la misma
agregación hecha en Python. Si no hay servidor MongoDB se saltan.

## Licencia de los datos

Datos bajo [ODbL 1.0](http://opendatacommons.org/licenses/odbl/1-0/),
"from BigDataChallenge contest" (Telecom Italia).
