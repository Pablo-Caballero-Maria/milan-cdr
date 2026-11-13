"""Apartado 8: estudio de las celdas de interés.

Combina varias consultas sobre las colecciones de los apartados 6 y 7 y
calcula en Python métricas que caracterizan el comportamiento de cada zona:

* volumen total y puesto en el ranking de las 10.000 celdas,
* mezcla de actividad (SMS / llamadas / internet),
* peso de la actividad con el extranjero y principales países,
* forma del perfil horario: hora pico, hora valle, peso de la noche,
* relación fin de semana / laborables.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from milan_cdr import pipelines as pl
from milan_cdr.analysis import DB, QueryResult, Row, run_pipeline
from milan_cdr.config import STUDY_CELLS, Settings
from milan_cdr.countries import lookup

#: Horas consideradas "noche" (hora local, intervalo [0, 6)).
NIGHT_HOURS = range(6)
#: Horas consideradas "tarde-noche / ocio" (intervalo [20, 24)).
EVENING_HOURS = range(20, 24)

type Profile = dict[str, list[float]]  # métrica -> 24 valores


@dataclass(slots=True)
class CellStudy:
    """Métricas de una celda de estudio."""

    cellid: int
    nombre: str
    totales: Row
    puestos: dict[str, int]
    perfil_laborable: Profile
    perfil_finde: Profile
    diario: list[Row]
    serie: list[Row]
    top_paises: list[Row]
    metricas: dict[str, float] = field(default_factory=dict)


def _profile(rows: list[Row], metrics: tuple[str, ...]) -> Profile:
    profile: Profile = {m: [0.0] * 24 for m in metrics}
    for row in rows:
        for m in metrics:
            profile[m][row["_id"]["hora_dia"]] = row[m]
    return profile


def split_profiles(
    rows: list[Row], metrics: tuple[str, ...] = ("sms", "llamadas", "internet", "total")
) -> dict[tuple[int | None, bool], Profile]:
    """Agrupa filas de :func:`pipelines.hourly_profile` por (celda, finde)."""
    grouped: dict[tuple[int | None, bool], list[Row]] = defaultdict(list)
    for row in rows:
        key = (row["_id"].get("cellid"), bool(row["_id"]["fin_de_semana"]))
        grouped[key].append(row)
    return {k: _profile(v, metrics) for k, v in grouped.items()}


def profile_metrics(weekday: list[float], weekend: list[float], daily: list[Row]) -> dict[str, float]:
    """Métricas de forma a partir de los perfiles horarios (de ``total``).

    El perfil "semanal" se pondera 5/7 laborable y 2/7 fin de semana.
    """
    week = [(5 * a + 2 * b) / 7 for a, b in zip(weekday, weekend, strict=True)]
    day_total = sum(week)
    peak = max(range(24), key=week.__getitem__)
    valley = min(range(24), key=week.__getitem__)
    workdays = [d["total"] for d in daily if d["_id"]["dia_semana"] <= 5]
    weekend_days = [d["total"] for d in daily if d["_id"]["dia_semana"] >= 6]
    mean_workday = sum(workdays) / len(workdays) if workdays else 0.0
    mean_weekend = sum(weekend_days) / len(weekend_days) if weekend_days else 0.0
    return {
        "hora_pico": float(peak),
        "hora_valle": float(valley),
        "pico_valle": week[peak] / week[valley] if week[valley] else float("inf"),
        "pct_noche": 100 * sum(week[h] for h in NIGHT_HOURS) / day_total if day_total else 0.0,
        "pct_tarde_noche": 100 * sum(week[h] for h in EVENING_HOURS) / day_total if day_total else 0.0,
        "finde_vs_laborable": mean_weekend / mean_workday if mean_workday else 0.0,
        "hora_pico_laborable": float(max(range(24), key=weekday.__getitem__)),
        "hora_pico_finde": float(max(range(24), key=weekend.__getitem__)),
    }


def mix_metrics(totals: Mapping[str, Any]) -> dict[str, float]:
    """Porcentaje de cada tipo de actividad y peso del extranjero."""
    total = totals["total"] or 1.0
    return {
        "pct_sms": 100 * totals["sms"] / total,
        "pct_llamadas": 100 * totals["llamadas"] / total,
        "pct_internet": 100 * totals["internet"] / total,
        "pct_extranjero": 100 * totals["total_extranjero"] / total,
        "internet_por_llamada": totals["internet"] / totals["llamadas"] if totals["llamadas"] else 0.0,
    }


@dataclass(slots=True)
class StudyResult:
    """Resultado completo del apartado 8."""

    cells: list[CellStudy]
    media_ciudad: Row
    perfil_ciudad: dict[bool, Profile]
    serie_ciudad: list[Row]
    metricas_ciudad: dict[str, float]
    queries: list[QueryResult]


def city_daily(series: list[Row], n_cells: int) -> list[Row]:
    """Actividad diaria de la celda media a partir de la serie horaria de la ciudad."""
    days: dict[int, float] = defaultdict(float)
    for row in series:
        days[row["_id"].isoweekday()] += row["total"] / n_cells
    return [{"_id": {"dia_semana": d}, "total": t} for d, t in sorted(days.items())]


def city_metrics(average: Row, profiles: dict[bool, Profile], daily: list[Row]) -> dict[str, float]:
    """Las mismas métricas de :class:`CellStudy` para la celda media de la ciudad."""
    totals = {m: average[f"media_{m}"] for m in ("total", "sms", "llamadas", "internet", "total_extranjero")}
    return {
        **mix_metrics(totals),
        **profile_metrics(profiles[False]["total"], profiles[True]["total"], daily),
        "veces_media": 1.0,
    }


def run_study(db: DB, settings: Settings, cells: Mapping[int, str] = STUDY_CELLS) -> StudyResult:
    """Ejecuta todas las consultas del apartado 8 y calcula las métricas."""
    ids = list(cells)
    cell_coll, hour_coll = settings.cell_collection, settings.cell_hour_collection

    q_summary = run_pipeline(db, cell_coll, pl.study_cells_summary(ids), "Resumen y ranking de las celdas")
    q_city = run_pipeline(db, cell_coll, pl.city_average(), "Media de la ciudad por celda")
    q_profile = run_pipeline(db, hour_coll, pl.hourly_profile(ids), "Perfil horario medio")
    q_daily = run_pipeline(db, hour_coll, pl.daily_totals(ids), "Totales diarios")
    q_series = run_pipeline(db, hour_coll, pl.weekly_series(ids), "Serie horaria semanal")
    q_foreign = run_pipeline(
        db, settings.collection, pl.top_foreign_countries_per_cell(ids), "Principales países extranjeros por celda"
    )
    q_city_profile = run_pipeline(db, hour_coll, pl.city_hourly_profile(), "Perfil horario de la ciudad")
    q_city_series = run_pipeline(db, hour_coll, pl.city_series(), "Serie horaria de la ciudad")

    n_cells = max(db[cell_coll].estimated_document_count(), 1)
    profiles = split_profiles(q_profile.rows)
    city_profiles_raw = split_profiles(q_city_profile.rows)
    city_profiles = {
        weekend: {m: [v / n_cells for v in vals] for m, vals in prof.items()}
        for (_, weekend), prof in city_profiles_raw.items()
    }

    summary = {row["_id"]: row for row in q_summary.rows}
    daily: dict[int, list[Row]] = defaultdict(list)
    for row in q_daily.rows:
        daily[row["_id"]["cellid"]].append(row)
    series: dict[int, list[Row]] = defaultdict(list)
    for row in q_series.rows:
        series[row["cellid"]].append(row)
    foreign = {row["_id"]: row["top"] for row in q_foreign.rows}

    studies: list[CellStudy] = []
    for cellid, name in cells.items():
        totals = summary[cellid]
        weekday = profiles[(cellid, False)]
        weekend = profiles[(cellid, True)]
        top = [{**t, "pais": lookup(int(t["countrycode"])).name} for t in foreign.get(cellid, [])]
        study = CellStudy(
            cellid=cellid,
            nombre=name,
            totales=totals,
            puestos={k.removeprefix("puesto_"): int(v) for k, v in totals.items() if k.startswith("puesto_")},
            perfil_laborable=weekday,
            perfil_finde=weekend,
            diario=daily[cellid],
            serie=series[cellid],
            top_paises=top,
        )
        study.metricas = {
            **mix_metrics(totals),
            **profile_metrics(weekday["total"], weekend["total"], daily[cellid]),
            "veces_media": totals["total"] / q_city.rows[0]["media_total"],
        }
        studies.append(study)

    return StudyResult(
        cells=studies,
        media_ciudad=q_city.rows[0],
        perfil_ciudad=city_profiles,
        serie_ciudad=q_city_series.rows,
        metricas_ciudad=city_metrics(q_city.rows[0], city_profiles, city_daily(q_city_series.rows, n_cells)),
        queries=[q_summary, q_city, q_profile, q_daily, q_series, q_foreign, q_city_profile, q_city_series],
    )


def series_hours(rows: list[Row], key: str = "hora") -> list[datetime]:
    """Extrae los instantes de una serie horaria."""
    return [row[key] for row in rows]
