"""Tests de la interfaz de línea de comandos."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from milan_cdr import dataverse
from milan_cdr.cli import app

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("download", "load", "run", "report", "figures"):
        assert command in result.output


def test_load_fails_on_missing_files(tmp_path: Path):
    result = runner.invoke(app, ["load", str(tmp_path / "no-existe.txt")])
    assert result.exit_code != 0
    assert "No existen" in result.output


def test_run_rejects_unknown_section():
    assert runner.invoke(app, ["run", "9"]).exit_code != 0


def test_download_selects_the_week(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    downloaded: list[date] = []

    class FakeClient:
        def __init__(self, email: str) -> None:
            assert email == "alumno@example.org"

        def list_files(self):
            return [
                dataverse.DataFile(i, f"sms-call-internet-mi-2013-12-{i:02d}.txt", 1, date(2013, 12, i))
                for i in range(1, 15)
            ]

        def download(self, data_file, dest_dir):
            downloaded.append(data_file.day)
            return dest_dir / data_file.filename

    monkeypatch.setattr(dataverse, "DataverseClient", FakeClient)
    monkeypatch.setenv("MILAN_CDR_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["download", "--email", "alumno@example.org"])
    assert result.exit_code == 0, result.output
    assert sorted(downloaded) == [date(2013, 12, d) for d in range(2, 9)]


@pytest.mark.mongo
def test_load_command(monkeypatch: pytest.MonkeyPatch, mongo_client, settings, data_file, documents):
    db_name = settings.db_name + "_cli"
    monkeypatch.setenv("MILAN_CDR_MONGO_URI", settings.mongo_uri)
    monkeypatch.setenv("MILAN_CDR_DB", db_name)
    try:
        result = runner.invoke(app, ["load", str(data_file), "--workers", "1"])
        assert result.exit_code == 0, result.output
        assert mongo_client[db_name][settings.collection].count_documents({}) == len(documents)
    finally:
        mongo_client.drop_database(db_name)


@pytest.mark.mongo
@pytest.mark.parametrize("section", [2, 3, 4, 5, 6, 7])
def test_run_section(monkeypatch: pytest.MonkeyPatch, loaded_db, settings, section):
    monkeypatch.setenv("MILAN_CDR_MONGO_URI", settings.mongo_uri)
    monkeypatch.setenv("MILAN_CDR_DB", settings.db_name)
    result = runner.invoke(app, ["run", str(section)])
    assert result.exit_code == 0, result.output
    assert f"Apartado {section}" in result.output
