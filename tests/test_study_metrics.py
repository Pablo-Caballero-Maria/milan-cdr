"""Tests de las métricas del apartado 8 (cálculo puro en Python)."""

import pytest

from milan_cdr.study import mix_metrics, profile_metrics, split_profiles


def _daily(values):
    return [{"_id": {"dia_semana": i + 1}, "total": v} for i, v in enumerate(values)]


def test_profile_metrics_peak_valley_and_weekend_ratio():
    weekday = [1.0] * 24
    weekday[18] = 10.0
    weekday[4] = 0.5
    weekend = [1.0] * 24
    weekend[22] = 8.0
    metrics = profile_metrics(weekday, weekend, _daily([10, 10, 10, 10, 10, 5, 5]))
    assert metrics["hora_pico"] == 18
    assert metrics["hora_valle"] == 4
    assert metrics["hora_pico_laborable"] == 18
    assert metrics["hora_pico_finde"] == 22
    assert metrics["finde_vs_laborable"] == pytest.approx(0.5)
    assert 0 < metrics["pct_noche"] < 100


def test_profile_metrics_flat_day():
    flat = [2.0] * 24
    metrics = profile_metrics(flat, flat, _daily([1] * 7))
    assert metrics["pct_noche"] == pytest.approx(100 * 6 / 24)
    assert metrics["pico_valle"] == pytest.approx(1.0)


def test_mix_metrics():
    totals = {"total": 200.0, "sms": 20.0, "llamadas": 30.0, "internet": 150.0, "total_extranjero": 10.0}
    mix = mix_metrics(totals)
    assert mix == {
        "pct_sms": 10.0,
        "pct_llamadas": 15.0,
        "pct_internet": 75.0,
        "pct_extranjero": 5.0,
        "internet_por_llamada": 5.0,
    }


def test_split_profiles():
    def row(weekend, hour, value):
        key = {"cellid": 1, "fin_de_semana": weekend, "hora_dia": hour}
        return {"_id": key, "total": value, "sms": 0, "llamadas": 0, "internet": value}

    rows = [row(False, h, h) for h in range(24)] + [row(True, 3, 7)]
    profiles = split_profiles(rows)
    assert profiles[(1, False)]["total"] == [float(h) for h in range(24)]
    assert profiles[(1, True)]["total"][3] == 7
    assert profiles[(1, True)]["total"][4] == 0.0


def test_city_daily_divides_by_cells_and_groups_by_weekday():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from milan_cdr.study import city_daily

    tz = ZoneInfo("Europe/Rome")
    series = [
        {"_id": datetime(2013, 12, 2, 10, tzinfo=tz), "total": 10.0},
        {"_id": datetime(2013, 12, 2, 11, tzinfo=tz), "total": 30.0},
        {"_id": datetime(2013, 12, 8, 11, tzinfo=tz), "total": 4.0},
    ]
    assert city_daily(series, n_cells=2) == [
        {"_id": {"dia_semana": 1}, "total": 20.0},
        {"_id": {"dia_semana": 7}, "total": 2.0},
    ]
