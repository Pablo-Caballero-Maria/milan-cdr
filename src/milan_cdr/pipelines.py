"""Pipelines de agregación de MongoDB para cada apartado.

Todas las funciones son **puras**: solo construyen y devuelven la lista de
etapas (``list[dict]``) sin tocar la base de datos. Esto permite:

* reutilizar bloques comunes (sumas por campo, total, filtros de país...),
* testear la estructura de los pipelines sin servidor,
* imprimirlos tal cual en la memoria (la sintaxis es la misma que en
  ``mongosh``: ``db.Milan_CDR_c.aggregate(<pipeline>)``).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from milan_cdr.config import ACTIVITY_FIELDS, ACTIVITY_GROUPS, GRID_SIZE, ITALY_CODE, TIMEZONE, UNKNOWN_CODE

type Stage = dict[str, Any]
type Pipeline = list[Stage]

#: Códigos que no se consideran "extranjero": Italia y desconocido.
NOT_FOREIGN: tuple[int, ...] = (ITALY_CODE, UNKNOWN_CODE)


# --------------------------------------------------------------------------
# Bloques reutilizables
# --------------------------------------------------------------------------
def sum_fields(fields: Sequence[str] = ACTIVITY_FIELDS) -> dict[str, Any]:
    """Acumuladores ``$sum`` de cada campo, para usar dentro de ``$group``."""
    return {f: {"$sum": f"${f}"} for f in fields}


def add_fields(fields: Sequence[str] = ACTIVITY_FIELDS) -> dict[str, Any]:
    """Expresión que suma varios campos ya agregados (``$add``)."""
    return {"$add": [f"${f}" for f in fields]}


def record_total(fields: Sequence[str] = ACTIVITY_FIELDS) -> dict[str, Any]:
    """Actividad total de un registro sin agrupar (campos ausentes = 0)."""
    return {"$add": [{"$ifNull": [f"${f}", 0]} for f in fields]}


def group_totals() -> dict[str, Any]:
    """Campos agregados a partir de las sumas por campo.

    ``sms``, ``llamadas`` e ``internet`` agrupan por tipo; ``sms_llamadas`` es
    la comunicación "persona a persona" (sin internet) y ``total`` la suma de
    los cinco campos.
    """
    exprs: dict[str, Any] = {name: add_fields(fields) for name, fields in ACTIVITY_GROUPS.items()}
    exprs["sms_llamadas"] = add_fields((*ACTIVITY_GROUPS["sms"], *ACTIVITY_GROUPS["llamadas"]))
    exprs["total"] = add_fields()
    return exprs


def foreign_match(exclude: Iterable[int] = NOT_FOREIGN) -> Stage:
    """``$match`` que se queda con los registros de países extranjeros."""
    return {"$match": {"countrycode": {"$nin": list(exclude)}}}


def ranking(
    key: str,
    *,
    match: Stage | None = None,
    sort_by: str = "total",
    limit: int | None = None,
    count_records: bool = True,
) -> Pipeline:
    """Agrupa por ``key``, acumula todos los campos y ordena descendentemente.

    Es la base de los apartados 2, 3 y 4: solo cambian la clave de agrupación
    (país o celda), el filtro previo y el criterio de orden.
    """
    group: Stage = {"_id": f"${key}", **sum_fields()}
    if count_records:
        group["registros"] = {"$sum": 1}
    pipeline: Pipeline = [match] if match else []
    pipeline += [
        {"$group": group},
        {"$addFields": group_totals()},
        {"$sort": {sort_by: -1, "_id": 1}},
    ]
    if limit is not None:
        pipeline.append({"$limit": limit})
    return pipeline


# --------------------------------------------------------------------------
# Apartados 2-5: consultas sobre la colección principal
# --------------------------------------------------------------------------
def countries() -> Pipeline:
    """Apartado 2: actividad acumulada por país (``countrycode``)."""
    return ranking("countrycode")


def top_foreign_countries(limit: int = 10, sort_by: str = "total") -> Pipeline:
    """Apartado 3: países con más interacción excluyendo Italia (y el código 0)."""
    return ranking("countrycode", match=foreign_match(), sort_by=sort_by, limit=limit)


def top_foreign_cells(limit: int = 10, sort_by: str = "total") -> Pipeline:
    """Apartado 4: celdas con más actividad con el extranjero."""
    return ranking("cellid", match=foreign_match(), sort_by=sort_by, limit=limit)


def top_cell_per_field(fields: Sequence[str] = (*ACTIVITY_FIELDS, "total"), top: int = 5) -> Pipeline:
    """Apartado 5: celda(s) con más actividad en cada campo y en el total.

    Se agrupa una sola vez por celda y después ``$facet`` calcula en paralelo
    un ranking por cada campo sobre los 10.000 documentos resultantes.
    """
    facets = {
        f: [
            {"$sort": {f: -1, "_id": 1}},
            {"$limit": top},
            {"$project": {"_id": 0, "cellid": "$_id", "valor": f"${f}"}},
        ]
        for f in fields
    }
    return [
        {"$group": {"_id": "$cellid", **sum_fields()}},
        {"$addFields": {"total": add_fields()}},
        {"$facet": facets},
    ]


# --------------------------------------------------------------------------
# Apartados 6 y 7: colecciones derivadas ($out)
# --------------------------------------------------------------------------
def cell_totals(out: str) -> Pipeline:
    """Apartado 6: un documento por celda con los acumulados de cada campo.

    Además de las sumas se guardan métricas útiles para el apartado 8:
    número de registros, número de países distintos, actividad con el
    extranjero y la posición (fila, columna) en la cuadrícula de 100x100.
    """
    foreign_total = {
        "$cond": [{"$in": ["$countrycode", list(NOT_FOREIGN)]}, 0, record_total()],
    }
    return [
        {
            "$group": {
                "_id": "$cellid",
                **sum_fields(),
                "registros": {"$sum": 1},
                "paises": {"$addToSet": "$countrycode"},
                "total_extranjero": {"$sum": foreign_total},
            }
        },
        {
            "$addFields": {
                **group_totals(),
                "n_paises": {"$size": {"$setDifference": ["$paises", [UNKNOWN_CODE]]}},
                "fila": {"$toInt": {"$floor": {"$divide": [{"$subtract": ["$_id", 1]}, GRID_SIZE]}}},
                "columna": {"$toInt": {"$mod": [{"$subtract": ["$_id", 1]}, GRID_SIZE]}},
            }
        },
        {"$project": {"paises": 0}},
        {"$sort": {"_id": 1}},
        {"$out": out},
    ]


def cell_hour_totals(out: str, timezone: str = TIMEZONE) -> Pipeline:
    """Apartado 7: un documento por celda y hora con los acumulados.

    La hora se obtiene truncando ``time`` a la hora en la zona horaria de
    Milán, de modo que cada documento agrega los 6 intervalos de 10 minutos
    (y todos los países) de esa hora. Se añaden campos derivados
    (fecha, día de la semana ISO y hora del día) para facilitar el apartado 8.
    """
    hour = {"$dateTrunc": {"date": "$time", "unit": "hour", "timezone": timezone}}
    return [
        {"$group": {"_id": {"cellid": "$cellid", "hora": hour}, **sum_fields()}},
        {
            "$addFields": {
                **group_totals(),
                "cellid": "$_id.cellid",
                "hora": "$_id.hora",
                "fecha": {"$dateToString": {"date": "$_id.hora", "format": "%Y-%m-%d", "timezone": timezone}},
                "dia_semana": {"$isoDayOfWeek": {"date": "$_id.hora", "timezone": timezone}},
                "hora_dia": {"$hour": {"date": "$_id.hora", "timezone": timezone}},
            }
        },
        {"$out": out},
    ]


# --------------------------------------------------------------------------
# Apartado 8: estudio de celdas concretas
# --------------------------------------------------------------------------
def cell_ranks() -> Pipeline:
    """Posición de cada celda en el ranking de actividad total (sobre ``celdas``).

    Usa ``$setWindowFields`` para calcular el puesto de cada celda entre las
    10.000 en cada métrica.
    """
    metrics = ("total", "sms", "llamadas", "internet", "total_extranjero")
    return [
        {
            "$setWindowFields": {
                "sortBy": {m: -1},
                "output": {f"puesto_{m}": {"$rank": {}}},
            }
        }
        for m in metrics
    ]


def study_cells_summary(cells: Iterable[int]) -> Pipeline:
    """Acumulados y puestos en el ranking de las celdas de estudio."""
    return [*cell_ranks(), {"$match": {"_id": {"$in": list(cells)}}}, {"$sort": {"_id": 1}}]


def city_average() -> Pipeline:
    """Media y mediana por celda de cada métrica (referencia para comparar)."""
    metrics = (*ACTIVITY_FIELDS, "sms", "llamadas", "total", "total_extranjero")
    group: Stage = {"_id": None}
    for m in metrics:
        group[f"media_{m}"] = {"$avg": f"${m}"}
        group[f"mediana_{m}"] = {"$median": {"input": f"${m}", "method": "approximate"}}
    return [{"$group": group}, {"$project": {"_id": 0}}]


def hourly_profile(cells: Iterable[int]) -> Pipeline:
    """Perfil horario medio (laborables vs. fin de semana) de cada celda.

    Opera sobre la colección del apartado 7: cada documento es una hora real
    de la semana, así que la media por ``hora_dia`` es la actividad media en
    esa hora del día.
    """
    metrics = ("sms", "llamadas", "internet", "total")
    return [
        {"$match": {"cellid": {"$in": list(cells)}}},
        {
            "$group": {
                "_id": {
                    "cellid": "$cellid",
                    "fin_de_semana": {"$gte": ["$dia_semana", 6]},
                    "hora_dia": "$hora_dia",
                },
                **{m: {"$avg": f"${m}"} for m in metrics},
            }
        },
        {"$sort": {"_id.cellid": 1, "_id.fin_de_semana": 1, "_id.hora_dia": 1}},
    ]


def weekly_series(cells: Iterable[int]) -> Pipeline:
    """Serie horaria completa (168 horas) de cada celda de estudio."""
    return [
        {"$match": {"cellid": {"$in": list(cells)}}},
        {"$project": {"_id": 0, "cellid": 1, "hora": 1, "sms": 1, "llamadas": 1, "internet": 1, "total": 1}},
        {"$sort": {"cellid": 1, "hora": 1}},
    ]


def daily_totals(cells: Iterable[int]) -> Pipeline:
    """Actividad total por día de la semana de cada celda de estudio."""
    return [
        {"$match": {"cellid": {"$in": list(cells)}}},
        {
            "$group": {
                "_id": {"cellid": "$cellid", "fecha": "$fecha", "dia_semana": "$dia_semana"},
                "sms": {"$sum": "$sms"},
                "llamadas": {"$sum": "$llamadas"},
                "internet": {"$sum": "$internet"},
                "total": {"$sum": "$total"},
            }
        },
        {"$sort": {"_id.cellid": 1, "_id.fecha": 1}},
    ]


def top_foreign_countries_per_cell(cells: Iterable[int], n: int = 3) -> Pipeline:
    """Los ``n`` países extranjeros con más actividad en cada celda (``$topN``)."""
    return [
        {"$match": {"cellid": {"$in": list(cells)}, "countrycode": {"$nin": list(NOT_FOREIGN)}}},
        {"$group": {"_id": {"cellid": "$cellid", "countrycode": "$countrycode"}, "total": {"$sum": record_total()}}},
        {
            "$group": {
                "_id": "$_id.cellid",
                "top": {
                    "$topN": {
                        "n": n,
                        "sortBy": {"total": -1},
                        "output": {"countrycode": "$_id.countrycode", "total": "$total"},
                    }
                },
            }
        },
        {"$sort": {"_id": 1}},
    ]


def city_hourly_profile() -> Pipeline:
    """Perfil horario medio de una celda "promedio" de la ciudad.

    Se suma toda la ciudad por hora real y luego se promedia por hora del día
    y tipo de día; dividiendo entre el número de celdas se obtiene la celda
    media (se hace en Python para no depender del número de celdas).
    """
    return [
        {
            "$group": {
                "_id": "$hora",
                "dia_semana": {"$first": "$dia_semana"},
                "hora_dia": {"$first": "$hora_dia"},
                "total": {"$sum": "$total"},
                "internet": {"$sum": "$internet"},
                "llamadas": {"$sum": "$llamadas"},
                "sms": {"$sum": "$sms"},
            }
        },
        {
            "$group": {
                "_id": {"fin_de_semana": {"$gte": ["$dia_semana", 6]}, "hora_dia": "$hora_dia"},
                "total": {"$avg": "$total"},
                "internet": {"$avg": "$internet"},
                "llamadas": {"$avg": "$llamadas"},
                "sms": {"$avg": "$sms"},
            }
        },
        {"$sort": {"_id.fin_de_semana": 1, "_id.hora_dia": 1}},
    ]


def city_series() -> Pipeline:
    """Actividad total de toda la ciudad hora a hora (168 puntos)."""
    return [
        {
            "$group": {
                "_id": "$hora",
                "sms": {"$sum": "$sms"},
                "llamadas": {"$sum": "$llamadas"},
                "internet": {"$sum": "$internet"},
                "total": {"$sum": "$total"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
