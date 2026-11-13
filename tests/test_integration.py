"""Tests de integración: pipelines reales contra MongoDB con datos sintéticos.

Cada resultado de MongoDB se compara con la misma agregación hecha en Python.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from milan_cdr import analysis
from milan_cdr.config import ACTIVITY_FIELDS
from synthetic import CELLS, expected_sums

pytestmark = pytest.mark.mongo
TZ = ZoneInfo("Europe/Rome")


def _assert_sums(row, expected, fields=(*ACTIVITY_FIELDS, "total", "sms_llamadas")):
    for f in fields:
        assert row[f] == pytest.approx(expected[f], rel=1e-9), f


def test_load_inserts_every_line_and_creates_indexes(loaded_db, settings, documents):
    coll = loaded_db[settings.collection]
    assert coll.count_documents({}) == len(documents)
    assert {"cellid_time", "countrycode"} <= set(coll.index_information())
    sample = coll.find_one({"countrycode": 0})
    assert set(sample) == {"_id", "cellid", "time", "countrycode", "smsin"}


def test_section2_countries(loaded_db, settings, documents):
    result = analysis.section2_countries(loaded_db, settings)
    expected = expected_sums(documents, lambda d: d["countrycode"])
    assert result.extra["codigos"] == [0, 33, 39, 44]
    assert result.extra["n_paises"] == 3
    assert result.extra["n_paises_extranjeros"] == 2
    assert [r["_id"] for r in result.rows] == sorted(expected, key=lambda k: -expected[k]["total"])
    for row in result.rows:
        _assert_sums(row, expected[row["_id"]])
        assert row["registros"] == expected[row["_id"]]["registros"]
    assert {r["pais"] for r in result.rows} >= {"Italia", "Francia", "Reino Unido"}


def test_section3_top_country_excludes_italy(loaded_db, settings):
    result = analysis.section3_top_country(loaded_db, settings)
    assert [r["_id"] for r in result.rows] == [33, 44]  # Francia: más total
    assert [r["_id"] for r in result.extra["por_sms_llamadas"]] == [33, 44]
    assert result.rows[0]["pais"] == "Francia"


def test_section4_top_foreign_cell(loaded_db, settings, documents):
    result = analysis.section4_top_foreign_cell(loaded_db, settings)
    foreign = [d for d in documents if d["countrycode"] not in (0, 39)]
    expected = expected_sums(foreign, lambda d: d["cellid"])
    assert result.rows[0]["_id"] == 4259
    for row in result.rows:
        _assert_sums(row, expected[row["_id"]])


def test_section5_top_cell_per_field(loaded_db, settings, documents):
    result = analysis.section5_top_cells(loaded_db, settings)
    expected = expected_sums(documents, lambda d: d["cellid"])
    facets = result.rows[0]
    for field in (*ACTIVITY_FIELDS, "total"):
        best = max(expected, key=lambda c, f=field: expected[c][f])
        assert facets[field][0]["cellid"] == best, field
        assert facets[field][0]["valor"] == pytest.approx(expected[best][field])


def test_section6_cell_collection(loaded_db, settings, documents):
    result = analysis.section6_cell_collection(loaded_db, settings)
    coll = loaded_db[settings.cell_collection]
    assert result.extra["documentos"] == len(CELLS)
    expected = expected_sums(documents, lambda d: d["cellid"])
    foreign = expected_sums([d for d in documents if d["countrycode"] not in (0, 39)], lambda d: d["cellid"])
    for doc in coll.find():
        _assert_sums(doc, expected[doc["_id"]])
        assert doc["registros"] == expected[doc["_id"]]["registros"]
        assert doc["total_extranjero"] == pytest.approx(foreign[doc["_id"]]["total"])
    bocconi = coll.find_one({"_id": 4259})
    assert (bocconi["fila"], bocconi["columna"]) == (42, 58)
    assert bocconi["n_paises"] == 3  # 33, 39, 44 (0 no cuenta)
    assert coll.find_one({"_id": 1})["n_paises"] == 2


def test_section7_cell_hour_collection(loaded_db, settings, documents):
    result = analysis.section7_cell_hour_collection(loaded_db, settings)
    coll = loaded_db[settings.cell_hour_collection]
    assert result.extra["documentos"] == len(CELLS) * 7 * 24

    def local_hour(d):
        t = d["time"].astimezone(TZ)
        return d["cellid"], t.replace(minute=0)

    expected = expected_sums(documents, local_hour)
    doc = coll.find_one({"cellid": 102, "fecha": "2013-12-07", "hora_dia": 21})
    assert doc["dia_semana"] == 6  # sábado
    key = (102, datetime(2013, 12, 7, 21, tzinfo=TZ))
    _assert_sums(doc, expected[key])
    first = coll.find_one(sort=[("hora", 1)])
    assert first["fecha"] == "2013-12-02"
    assert first["hora_dia"] == 0
    assert first["dia_semana"] == 1


def test_section8_study(loaded_db, settings):
    from milan_cdr.study import run_study

    analysis.section6_cell_collection(loaded_db, settings)
    analysis.section7_cell_hour_collection(loaded_db, settings)
    result = run_study(loaded_db, settings, cells=CELLS)
    assert [c.cellid for c in result.cells] == list(CELLS)
    bocconi = result.cells[-1]
    assert bocconi.puestos["total"] == 1
    assert len(bocconi.diario) == 7
    assert len(bocconi.serie) == 7 * 24
    assert len(bocconi.perfil_laborable["total"]) == 24
    assert bocconi.top_paises[0]["pais"] == "Reino Unido"
    # Datos sintéticos: el finde tiene la mitad de actividad italiana/francesa.
    assert 0.5 < bocconi.metricas["finde_vs_laborable"] < 1
    assert bocconi.metricas["hora_pico"] == 23  # internet crece con la hora
    assert sum(c.metricas["veces_media"] for c in result.cells) == pytest.approx(len(CELLS))
    assert result.metricas_ciudad["veces_media"] == 1.0
    assert result.metricas_ciudad["finde_vs_laborable"] < 1


def test_build_report_writes_outputs(loaded_db, settings):
    from milan_cdr import report
    from milan_cdr.config import STUDY_CELLS

    # El informe usa las 8 celdas del enunciado; con datos sintéticos solo
    # existen 3, así que se ejecuta con esas.
    original = dict(STUDY_CELLS)
    STUDY_CELLS.clear()
    STUDY_CELLS.update(CELLS)
    try:
        out = report.build_report(settings)
    finally:
        STUDY_CELLS.clear()
        STUDY_CELLS.update(original)
    assert (out / "resultados.json").stat().st_size > 0
    assert (out / "informe.md").read_text(encoding="utf-8").startswith("# Resultados")
    assert len(list((out / "figuras").glob("*.png"))) == 7
