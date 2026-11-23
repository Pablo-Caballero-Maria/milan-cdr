"""El esquema tipado (documents.py) y las etapas tipadas de los pipelines."""

from typing import get_type_hints

import pytest
from pymongo import MongoClient

from milan_cdr import pipelines as pl
from milan_cdr.config import ACTIVITY_FIELDS, Settings
from milan_cdr.documents import CDRDocument, CellDocument, CellHourDocument, collections
from milan_cdr.parsing import parse_line

STAGE_OPERATORS = {
    "$match",
    "$group",
    "$addFields",
    "$project",
    "$sort",
    "$limit",
    "$facet",
    "$setWindowFields",
    "$out",
}


def test_cdr_documents_have_the_declared_fields():
    doc = parse_line("1\t1385938800000\t39\t0.5\t\t1\t\t12.3")
    hints = get_type_hints(CDRDocument)
    assert set(doc) <= set(hints)
    assert set(ACTIVITY_FIELDS) <= set(hints)
    assert CDRDocument.__required_keys__ == {"cellid", "time", "countrycode"}  # the rest only if present


def test_derived_documents_have_every_total():
    for doc_type in (CellDocument, CellHourDocument):
        assert {*ACTIVITY_FIELDS, "sms", "llamadas", "sms_llamadas", "total"} <= set(get_type_hints(doc_type))


def test_collections_are_the_configured_ones(tmp_path):
    settings = Settings(results_dir=tmp_path)
    client: MongoClient = MongoClient(connect=False)
    try:
        c = collections(client[settings.db_name], settings)
        assert (c.cdr.name, c.cells.name, c.cell_hours.name) == (
            settings.collection,
            settings.cell_collection,
            settings.cell_hour_collection,
        )
    finally:
        client.close()


@pytest.mark.parametrize(
    "pipeline",
    [
        pl.countries(),
        pl.top_foreign_cells(),
        pl.top_cell_per_field(),
        pl.cell_totals("out"),
        pl.cell_hour_totals("out"),
        pl.study_cells_summary([1]),
        pl.city_average(),
        pl.hourly_profile([1]),
        pl.top_foreign_countries_per_cell([1]),
        pl.city_series(),
    ],
)
def test_every_stage_is_one_known_operator(pipeline):
    for stage in pipeline:
        assert len(stage) == 1
        assert next(iter(stage)) in STAGE_OPERATORS
