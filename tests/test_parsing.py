from datetime import UTC, datetime
from pathlib import Path

import pytest

from milan_cdr.parsing import ParseError, batched, iter_documents, ms_to_datetime, parse_line, read_file

FULL = "4259\t1385938800000\t39\t0.19\t0.16\t0.026\t0.029\t10.4\n"
SPARSE = "1\t1385939400000\t0\t0.10687577828294556\t\t\t\t\n"


def test_ms_to_datetime_is_utc_and_exact():
    assert ms_to_datetime(1385938800000) == datetime(2013, 12, 1, 23, 0, tzinfo=UTC)
    assert ms_to_datetime(1385938800123).microsecond == 123_000


def test_parse_full_line():
    doc = parse_line(FULL)
    assert doc == {
        "cellid": 4259,
        "time": datetime(2013, 12, 1, 23, 0, tzinfo=UTC),
        "countrycode": 39,
        "smsin": 0.19,
        "smsout": 0.16,
        "callin": 0.026,
        "callout": 0.029,
        "internet": 10.4,
    }


def test_parse_omits_empty_fields():
    doc = parse_line(SPARSE)
    assert set(doc) == {"cellid", "time", "countrycode", "smsin"}
    assert doc["smsin"] == pytest.approx(0.10687577828294556)


def test_parse_handles_crlf():
    assert parse_line(FULL.replace("\n", "\r\n"))["internet"] == 10.4


@pytest.mark.parametrize(
    "line",
    [
        "1\t2\t3\n",  # pocas columnas
        "1\t1385938800000\t39\t0.1\t\t\t\t\t\t\n",  # demasiadas columnas
        "x\t1385938800000\t39\t\t\t\t\t\n",  # cellid no numérico
        "1\t1\t39\ta\t\t\t\t\n",  # actividad no numérica
    ],
)
def test_parse_rejects_malformed(line):
    with pytest.raises(ParseError):
        parse_line(line)


def test_iter_documents_skips_blank_lines():
    docs = list(iter_documents([FULL, "\n", "   \n", SPARSE]))
    assert [d["cellid"] for d in docs] == [4259, 1]


def test_read_file(tmp_path: Path):
    path = tmp_path / "sample.txt"
    path.write_text(FULL + SPARSE, encoding="ascii")
    assert len(list(read_file(path))) == 2


def test_batched():
    assert [len(b) for b in batched(iter(range(7)), 3)] == [3, 3, 1]
    assert list(batched([], 3)) == []
    with pytest.raises(ValueError, match="size"):
        list(batched([1], 0))
