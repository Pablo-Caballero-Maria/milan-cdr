from datetime import date

import pytest

from milan_cdr.config import STUDY_CELLS, Settings


def test_default_week_is_monday_to_sunday():
    days = Settings().week_days
    assert days[0] == date(2013, 12, 2)
    assert days[-1] == date(2013, 12, 8)
    assert [d.weekday() for d in days] == list(range(7))


def test_week_must_start_on_monday():
    with pytest.raises(ValueError, match="lunes"):
        Settings(week_start=date(2013, 12, 3))


def test_env_override(monkeypatch):
    monkeypatch.setenv("MILAN_CDR_DB", "otra_db")
    monkeypatch.setenv("MILAN_CDR_WEEK_START", "2013-11-04")
    settings = Settings()
    assert settings.db_name == "otra_db"
    assert settings.week_start == date(2013, 11, 4)


def test_study_cells_are_the_eight_of_the_statement():
    assert set(STUDY_CELLS) == {4259, 4456, 5060, 1419, 2436, 4990, 945, 5048}
