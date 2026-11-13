"""Generación de resultados: salida por consola, JSON, Markdown y figuras.

``build_report`` ejecuta todos los apartados en orden (6 y 7 crean las
colecciones que usa el 8) y deja en ``results/``:

* ``resultados.json``: pipelines, filas devueltas y tiempos de cada consulta,
* ``informe.md``: tablas resumen listas para la memoria,
* ``figuras/*.png`` y ``figuras/*.html``: gráficas del apartado 8 (plotly).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from bson import json_util
from rich.console import Console
from rich.table import Table

from milan_cdr.analysis import DB, SECTIONS, QueryResult, Row, connect
from milan_cdr.config import ACTIVITY_FIELDS, Settings
from milan_cdr.plots import all_study_figures
from milan_cdr.study import StudyResult, run_study

console = Console()

COUNTRY_COLUMNS = ("_id", "pais", "registros", *ACTIVITY_FIELDS, "sms_llamadas", "total")
CELL_COLUMNS = ("_id", "registros", *ACTIVITY_FIELDS, "sms_llamadas", "total")


# --------------------------------------------------------------------------
# Formato
# --------------------------------------------------------------------------
#: Columnas que son identificadores (se muestran sin separador de miles).
ID_COLUMNS = frozenset({"_id", "cellid", "celda", "countrycode", "puesto", "pico_lab", "pico_fds"})


def fmt(value: Any, column: str | None = None) -> str:
    """Formatea números con separador de miles y 2 decimales a la española."""
    if isinstance(value, bool) or value is None or column in ID_COLUMNS:
        return str(value)
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    if isinstance(value, float):
        text = f"{value:,.2f}"
        return text.replace(",", "_").replace(".", ",").replace("_", ".")
    return str(value)


def markdown_table(rows: Iterable[Row], columns: Sequence[str], headers: Sequence[str] | None = None) -> str:
    """Tabla Markdown con las columnas pedidas."""
    headers = headers or columns
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(fmt(row.get(c), c) for c in columns) + " |" for row in rows]
    return "\n".join(lines)


def rich_table(title: str, rows: Iterable[Row], columns: Sequence[str]) -> Table:
    """Tabla de ``rich`` para mostrar por consola."""
    table = Table(title=title)
    for col in columns:
        table.add_column(col, justify="right" if col != "pais" else "left")
    for row in rows:
        table.add_row(*(fmt(row.get(c), c) for c in columns))
    return table


def facet_rows(result: QueryResult) -> list[Row]:
    """Aplana la salida del ``$facet`` del apartado 5 (una fila por campo)."""
    facets = result.rows[0]
    return [
        {"campo": name, "puesto": i + 1, "cellid": item["cellid"], "valor": item["valor"]}
        for name, items in facets.items()
        for i, item in enumerate(items)
    ]


def _study_row(cellid: int | str, name: str, total: float, puesto: int | str, m: dict[str, float]) -> Row:
    return {
        "celda": cellid,
        "zona": name,
        "total": total,
        "puesto": puesto,
        "x_media": m["veces_media"],
        "%sms": m["pct_sms"],
        "%llam": m["pct_llamadas"],
        "%inet": m["pct_internet"],
        "%extr": m["pct_extranjero"],
        "pico_lab": int(m["hora_pico_laborable"]),
        "pico_fds": int(m["hora_pico_finde"]),
        "%noche": m["pct_noche"],
        "%20-24h": m["pct_tarde_noche"],
        "fds/lab": m["finde_vs_laborable"],
        "pico/valle": m["pico_valle"],
    }


def study_rows(result: StudyResult, with_city: bool = True) -> list[Row]:
    """Filas resumen del apartado 8 (una por celda y, opcionalmente, la media)."""
    rows = [
        {
            **_study_row(c.cellid, c.nombre, c.totales["total"], c.puestos["total"], c.metricas),
            "top_paises": ", ".join(t["pais"] for t in c.top_paises),
        }
        for c in result.cells
    ]
    if with_city:
        city = result.metricas_ciudad
        rows.append(_study_row("-", "Media ciudad", result.media_ciudad["media_total"], "-", city))
    return rows


STUDY_COLUMNS = (
    "celda",
    "zona",
    "total",
    "puesto",
    "x_media",
    "%sms",
    "%llam",
    "%inet",
    "%extr",
    "pico_lab",
    "pico_fds",
    "%noche",
    "%20-24h",
    "fds/lab",
    "pico/valle",
)


# --------------------------------------------------------------------------
# Consola
# --------------------------------------------------------------------------
def _print_result(section: int, result: QueryResult) -> None:
    console.print(f"[bold]Apartado {section}[/] · {result.title} · {result.seconds:.2f} s")
    match section:
        case 2:
            console.print(f"countrycode distintos: {result.extra['n_codigos']}  ·  países: {result.extra['n_paises']}")
            console.print(rich_table("Actividad por país", result.rows, COUNTRY_COLUMNS))
        case 3:
            console.print(rich_table("Top países (total)", result.rows, COUNTRY_COLUMNS))
            console.print(rich_table("Top países (SMS + llamadas)", result.extra["por_sms_llamadas"], COUNTRY_COLUMNS))
        case 4:
            console.print(rich_table("Top celdas extranjero (total)", result.rows, CELL_COLUMNS))
            console.print(rich_table("Top celdas (SMS + llamadas)", result.extra["por_sms_llamadas"], CELL_COLUMNS))
        case 5:
            console.print(
                rich_table("Celdas top por campo", facet_rows(result), ("campo", "puesto", "cellid", "valor"))
            )
        case _:
            console.print(f"Colección {result.extra['salida']}: {result.extra['documentos']:,} documentos")
            console.print(result.extra["ejemplo"])


def print_section(section: int, settings: Settings) -> None:
    """Ejecuta un apartado y muestra su resultado."""
    with connect(settings) as client:
        db: DB = client[settings.db_name]
        if section == 8:
            study = run_study(db, settings)
            console.print(rich_table("Apartado 8", study_rows(study), STUDY_COLUMNS))
            return
        _print_result(section, SECTIONS[section](db, settings))


# --------------------------------------------------------------------------
# Informe completo
# --------------------------------------------------------------------------
def _result_json(result: QueryResult) -> dict[str, Any]:
    return {
        "titulo": result.title,
        "coleccion": result.collection,
        "pipeline": result.pipeline,
        "segundos": round(result.seconds, 3),
        "filas": result.rows,
        "extra": result.extra,
    }


def _markdown(results: dict[int, QueryResult], study: StudyResult, figures: dict[str, Path]) -> str:
    r2, r3, r4, r5, r6, r7 = (results[i] for i in range(2, 8))
    parts = [
        "# Resultados CDR Milán (2–8 dic 2013)",
        "## Apartado 2",
        f"{r2.extra['n_codigos']} códigos distintos, {r2.extra['n_paises']} países.",
        markdown_table(r2.rows, COUNTRY_COLUMNS),
        "## Apartado 3",
        markdown_table(r3.rows, COUNTRY_COLUMNS),
        "### Por SMS + llamadas",
        markdown_table(r3.extra["por_sms_llamadas"], COUNTRY_COLUMNS),
        "## Apartado 4",
        markdown_table(r4.rows, CELL_COLUMNS),
        "### Por SMS + llamadas",
        markdown_table(r4.extra["por_sms_llamadas"], CELL_COLUMNS),
        "## Apartado 5",
        markdown_table(facet_rows(r5), ("campo", "puesto", "cellid", "valor")),
        "## Apartado 6",
        f"{r6.extra['documentos']} documentos en {r6.extra['salida']} ({r6.seconds:.1f} s)",
        "## Apartado 7",
        f"{r7.extra['documentos']} documentos en {r7.extra['salida']} ({r7.seconds:.1f} s)",
        "## Apartado 8",
        markdown_table(study_rows(study), STUDY_COLUMNS),
        "### Países extranjeros principales",
        markdown_table(study_rows(study, with_city=False), ("celda", "zona", "top_paises")),
        "### Figuras",
        *(f"![{name}](figuras/{path.name})" for name, path in figures.items()),
    ]
    return "\n\n".join(parts) + "\n"


def build_figures(settings: Settings) -> dict[str, Path]:
    """Regenera solo las figuras del apartado 8 (usa las colecciones de 6 y 7)."""
    with connect(settings) as client:
        db: DB = client[settings.db_name]
        study = run_study(db, settings)
        cell_docs = list(db[settings.cell_collection].find({}, {"total": 1}))
    return all_study_figures(study, cell_docs, settings.results_dir / "figuras")


def build_report(settings: Settings) -> Path:
    """Ejecuta los apartados 2-8 y guarda todos los resultados en disco."""
    out = settings.results_dir
    fig_dir = out / "figuras"
    fig_dir.mkdir(parents=True, exist_ok=True)

    with connect(settings) as client:
        db: DB = client[settings.db_name]
        results: dict[int, QueryResult] = {}
        for section, func in SECTIONS.items():
            console.print(f"Ejecutando apartado {section}...")
            results[section] = func(db, settings)
            _print_result(section, results[section])

        console.print("Ejecutando apartado 8...")
        study = run_study(db, settings)
        console.print(rich_table("Apartado 8", study_rows(study), STUDY_COLUMNS))
        cell_docs = list(db[settings.cell_collection].find({}, {"total": 1}))

    figures = all_study_figures(study, cell_docs, fig_dir)

    payload = {
        "semana": [d.isoformat() for d in settings.week_days],
        "apartados": {str(k): _result_json(v) for k, v in results.items()},
        "apartado_8": {
            "consultas": [_result_json(q) for q in study.queries],
            "resumen": study_rows(study),
            "media_ciudad": study.media_ciudad,
            "metricas_ciudad": study.metricas_ciudad,
            "perfil_ciudad": {"laborable": study.perfil_ciudad[False], "fin_de_semana": study.perfil_ciudad[True]},
            "serie_ciudad": study.serie_ciudad,
            "celdas": [
                {
                    "cellid": c.cellid,
                    "nombre": c.nombre,
                    "totales": c.totales,
                    "puestos": c.puestos,
                    "metricas": c.metricas,
                    "top_paises": c.top_paises,
                    "diario": c.diario,
                    "serie": c.serie,
                    "perfil_laborable": c.perfil_laborable,
                    "perfil_finde": c.perfil_finde,
                }
                for c in study.cells
            ],
        },
    }
    (out / "resultados.json").write_text(
        json.dumps(payload, default=json_util.default, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "informe.md").write_text(_markdown(results, study, figures), encoding="utf-8")
    return out
