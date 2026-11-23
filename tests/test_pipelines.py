"""Tests de estructura de los pipelines (no necesitan servidor)."""

from typing import Any, cast

from milan_cdr import pipelines as pl
from milan_cdr.config import ACTIVITY_FIELDS


def _op(stage: pl.Stage, operator: str) -> Any:
    """El valor de una etapa (``{"$group": …}`` → ``…``): las etapas son TypedDicts distintos según su operador."""
    return cast("dict[str, Any]", stage)[operator]


def _stage_names(pipeline):
    return [next(iter(stage)) for stage in pipeline]


def test_sum_fields_covers_all_activity_fields():
    assert pl.sum_fields() == {f: {"$sum": f"${f}"} for f in ACTIVITY_FIELDS}


def test_record_total_treats_missing_as_zero():
    expr = pl.record_total()
    assert expr["$add"][0] == {"$ifNull": ["$smsin", 0]}
    assert len(expr["$add"]) == len(ACTIVITY_FIELDS)


def test_group_totals_fields():
    totals = pl.group_totals()
    assert set(totals) == {"sms", "llamadas", "internet", "sms_llamadas", "total"}
    assert totals["sms_llamadas"] == {"$add": ["$smsin", "$smsout", "$callin", "$callout"]}


def test_countries_groups_by_countrycode_without_filter():
    pipeline = pl.countries()
    assert _stage_names(pipeline) == ["$group", "$addFields", "$sort"]
    assert _op(pipeline[0], "$group")["_id"] == "$countrycode"
    assert _op(pipeline[0], "$group")["registros"] == {"$sum": 1}


def test_top_foreign_countries_excludes_italy_and_unknown():
    pipeline = pl.top_foreign_countries(limit=3, sort_by="sms_llamadas")
    assert pipeline[0] == {"$match": {"countrycode": {"$nin": [39, 0]}}}
    assert _op(pipeline[-2], "$sort") == {"sms_llamadas": -1, "_id": 1}
    assert pipeline[-1] == {"$limit": 3}


def test_top_foreign_cells_groups_by_cell():
    pipeline = pl.top_foreign_cells()
    assert _op(pipeline[1], "$group")["_id"] == "$cellid"


def test_top_cell_per_field_has_one_facet_per_field():
    pipeline = pl.top_cell_per_field(top=2)
    facets = _op(pipeline[-1], "$facet")
    assert set(facets) == {*ACTIVITY_FIELDS, "total"}
    assert facets["internet"][1] == {"$limit": 2}


def test_cell_totals_ends_with_out():
    pipeline = pl.cell_totals("salida")
    assert pipeline[-1] == {"$out": "salida"}
    added = _op(pipeline[1], "$addFields")
    assert {"fila", "columna", "n_paises", "total"} <= set(added)


def test_cell_hour_totals_truncates_in_milan_timezone():
    pipeline = pl.cell_hour_totals("salida", timezone="Europe/Rome")
    hour = _op(pipeline[0], "$group")["_id"]["hora"]["$dateTrunc"]
    assert hour == {"date": "$time", "unit": "hour", "timezone": "Europe/Rome"}
    assert pipeline[-1] == {"$out": "salida"}


def test_study_pipelines_filter_by_cells():
    cells = [1, 2]
    for builder in (pl.hourly_profile, pl.weekly_series, pl.daily_totals):
        assert builder(cells)[0] == {"$match": {"cellid": {"$in": cells}}}
    assert pl.study_cells_summary(cells)[-2] == {"$match": {"_id": {"$in": cells}}}
    assert _op(pl.top_foreign_countries_per_cell(cells)[0], "$match")["countrycode"] == {"$nin": [39, 0]}


def test_pipelines_are_new_objects_each_call():
    a, b = pl.countries(), pl.countries()
    assert a == b
    assert a is not b
    _op(a[0], "$group")["_id"] = "x"
    assert _op(pl.countries()[0], "$group")["_id"] == "$countrycode"
