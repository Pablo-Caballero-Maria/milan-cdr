"""Datos sintéticos y agregaciones de referencia para los tests."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from milan_cdr.config import ACTIVITY_FIELDS

TEST_URI = os.environ.get("MILAN_CDR_TEST_URI", "mongodb://localhost:27017")

#: Lunes 2-dic-2013 00:00 en Milán (CET = UTC+1).
WEEK_START_UTC = datetime(2013, 12, 1, 23, 0, tzinfo=UTC)
CELLS = {1: "Esquina SO", 102: "Interior", 4259: "Bocconi"}


def _value(cell: int, code: int, t: datetime, field: str) -> float | None:
    """Valores deterministas con patrón diario/semanal y países distintos por celda."""
    local = t + timedelta(hours=1)
    weekend = local.isoweekday() >= 6
    hour_factor = 1 + local.hour  # crece a lo largo del día
    base = {1: 1.0, 102: 2.0, 4259: 3.0}[cell] * (0.5 if weekend else 1.0)
    if code == 39:
        return {
            "smsin": base * 0.1,
            "smsout": base * 0.2,
            "callin": base * 0.3,
            "callout": base * 0.4,
            "internet": base * hour_factor,
        }[field]
    if code == 33:  # Francia en todas las celdas, solo SMS e internet
        return {"smsin": 0.05 * base, "internet": 0.5 * base}.get(field)
    if code == 44 and cell == 4259:  # Reino Unido solo en Bocconi, mucho internet
        return {"internet": 2.0, "callout": 0.01}.get(field)
    if code == 0:
        return {"smsin": 0.01}.get(field)
    return None


def synthetic_documents() -> list[dict[str, Any]]:
    """Una semana completa (1008 intervalos) para 3 celdas y 4 códigos."""
    docs: list[dict[str, Any]] = []
    for step in range(7 * 24 * 6):
        t = WEEK_START_UTC + timedelta(minutes=10 * step)
        for cell in CELLS:
            for code in (0, 33, 39, 44):
                values = {f: v for f in ACTIVITY_FIELDS if (v := _value(cell, code, t, f)) is not None}
                if values:
                    docs.append({"cellid": cell, "time": t, "countrycode": code, **values})
    return docs


def to_line(doc: dict[str, Any]) -> str:
    ms = int(doc["time"].timestamp() * 1000)
    fields = [repr(doc[f]) if f in doc else "" for f in ACTIVITY_FIELDS]
    return "\t".join([str(doc["cellid"]), str(ms), str(doc["countrycode"]), *fields]) + "\n"


def expected_sums(docs: list[dict[str, Any]], key) -> dict[Any, dict[str, float]]:
    """Agregación de referencia hecha en Python puro."""
    acc: dict[Any, dict[str, float]] = defaultdict(lambda: dict.fromkeys((*ACTIVITY_FIELDS, "registros"), 0.0))
    for doc in docs:
        k = key(doc)
        for f in ACTIVITY_FIELDS:
            acc[k][f] += doc.get(f, 0.0)
        acc[k]["registros"] += 1
    for v in acc.values():
        v["total"] = sum(v[f] for f in ACTIVITY_FIELDS)
        v["sms_llamadas"] = v["smsin"] + v["smsout"] + v["callin"] + v["callout"]
    return dict(acc)
