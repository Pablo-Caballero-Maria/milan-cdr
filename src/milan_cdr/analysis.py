"""Ejecución de los apartados 2 a 7 contra MongoDB.

Cada función recibe la base de datos y la configuración, ejecuta el pipeline
correspondiente de :mod:`milan_cdr.pipelines` y devuelve un
:class:`QueryResult` con el pipeline usado, las filas obtenidas y el tiempo
de ejecución, de forma que el informe pueda mostrar *código + salida*.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from zoneinfo import ZoneInfo

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database

from milan_cdr import pipelines as pl
from milan_cdr.config import TIMEZONE, Settings
from milan_cdr.countries import NON_GEOGRAPHIC, lookup

type Row = dict[str, Any]
type DB = Database[dict[str, Any]]


@dataclass(slots=True)
class QueryResult:
    """Resultado de un apartado: qué se ejecutó y qué devolvió."""

    title: str
    collection: str
    pipeline: pl.Pipeline
    rows: list[Row]
    seconds: float
    extra: dict[str, Any] = field(default_factory=dict)


def connect(settings: Settings, timeout_ms: int = 5000) -> MongoClient[dict[str, Any]]:
    """Crea un cliente y comprueba que el servidor responde.

    Las fechas se devuelven con zona horaria, convertidas a la hora de Milán.
    """
    client: MongoClient[dict[str, Any]] = MongoClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=timeout_ms,
        tz_aware=True,
        tzinfo=ZoneInfo(TIMEZONE),
    )
    client.admin.command("ping")
    return client


def run_pipeline(db: DB, collection: str, pipeline: pl.Pipeline, title: str = "") -> QueryResult:
    """Ejecuta un pipeline (con ``allowDiskUse``) midiendo el tiempo."""
    start = time.perf_counter()
    rows = list(db[collection].aggregate(pipeline, allowDiskUse=True))
    return QueryResult(title, collection, pipeline, rows, time.perf_counter() - start)


def with_country_names(rows: list[Row]) -> list[Row]:
    """Añade ``pais`` y ``region`` a filas cuyo ``_id`` es un ``countrycode``."""
    for row in rows:
        country = lookup(int(row["_id"]))
        row["pais"] = country.name
        row["region"] = country.region
    return rows


# --------------------------------------------------------------------------
# Apartados
# --------------------------------------------------------------------------
def section2_countries(db: DB, settings: Settings) -> QueryResult:
    """Países con los que se interactúa."""
    coll = settings.collection
    start = time.perf_counter()
    codes = sorted(db[coll].distinct("countrycode"))
    distinct_seconds = time.perf_counter() - start

    result = run_pipeline(db, coll, pl.countries(), "Actividad por país")
    with_country_names(result.rows)
    # Países = regiones geográficas identificadas (se excluyen el código 0,
    # los códigos no asignados y los servicios no geográficos "001").
    regions = {lookup(int(row["_id"])).region for row in result.rows}
    countries = regions - {None, NON_GEOGRAPHIC}
    result.extra = {
        "codigos": codes,
        "n_codigos": len(codes),
        "n_paises": len(countries),
        "n_paises_extranjeros": len(countries - {"IT"}),
        "distinct_seconds": distinct_seconds,
    }
    return result


def section3_top_country(db: DB, settings: Settings, limit: int = 10) -> QueryResult:
    """País extranjero con más interacción (total y solo SMS+llamadas)."""
    result = run_pipeline(db, settings.collection, pl.top_foreign_countries(limit), "Top países (total)")
    with_country_names(result.rows)
    by_comm = run_pipeline(
        db, settings.collection, pl.top_foreign_countries(limit, sort_by="sms_llamadas"), "Top países (SMS+llamadas)"
    )
    with_country_names(by_comm.rows)
    result.extra = {"por_sms_llamadas": by_comm.rows, "pipeline_sms_llamadas": by_comm.pipeline}
    result.seconds += by_comm.seconds
    return result


def section4_top_foreign_cell(db: DB, settings: Settings, limit: int = 10) -> QueryResult:
    """Celda que más se comunica con el extranjero."""
    result = run_pipeline(db, settings.collection, pl.top_foreign_cells(limit), "Top celdas extranjero (total)")
    by_comm = run_pipeline(
        db, settings.collection, pl.top_foreign_cells(limit, sort_by="sms_llamadas"), "Top celdas (SMS+llamadas)"
    )
    result.extra = {"por_sms_llamadas": by_comm.rows, "pipeline_sms_llamadas": by_comm.pipeline}
    result.seconds += by_comm.seconds
    return result


def section5_top_cells(db: DB, settings: Settings, top: int = 5) -> QueryResult:
    """Celda con más actividad en cada campo y en total."""
    return run_pipeline(db, settings.collection, pl.top_cell_per_field(top=top), "Top celdas por campo")


def _materialize(
    db: DB,
    settings: Settings,
    *,
    builder: Callable[[str], pl.Pipeline],
    out: str,
    title: str,
    indexes: list[list[tuple[str, int]]],
) -> QueryResult:
    result = run_pipeline(db, settings.collection, builder(out), title)
    for keys in indexes:
        db[out].create_index(keys)
    result.extra = {
        "salida": out,
        "documentos": db[out].estimated_document_count(),
        "ejemplo": db[out].find_one(sort=[("_id", ASCENDING)]),
    }
    return result


def section6_cell_collection(db: DB, settings: Settings) -> QueryResult:
    """Crea la colección con un documento por celda."""
    return _materialize(
        db,
        settings,
        builder=pl.cell_totals,
        out=settings.cell_collection,
        title="Colección por celda",
        indexes=[[("total", -1)]],
    )


def section7_cell_hour_collection(db: DB, settings: Settings) -> QueryResult:
    """Crea la colección con un documento por celda y hora."""
    return _materialize(
        db,
        settings,
        builder=pl.cell_hour_totals,
        out=settings.cell_hour_collection,
        title="Colección por celda y hora",
        indexes=[[("cellid", ASCENDING), ("hora", ASCENDING)], [("hora", ASCENDING)]],
    )


SECTIONS: dict[int, Callable[[DB, Settings], QueryResult]] = {
    2: section2_countries,
    3: section3_top_country,
    4: section4_top_foreign_cell,
    5: section5_top_cells,
    6: section6_cell_collection,
    7: section7_cell_hour_collection,
}
