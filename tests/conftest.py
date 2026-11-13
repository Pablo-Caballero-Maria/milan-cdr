"""Fixtures compartidas.

Los tests marcados con ``mongo`` usan un servidor real (``MILAN_CDR_TEST_URI``,
por defecto ``mongodb://localhost:27017``) y una base de datos temporal que se
borra al terminar. Si no hay servidor, se saltan.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from milan_cdr.config import Settings
from synthetic import TEST_URI, synthetic_documents, to_line


@pytest.fixture(scope="session")
def mongo_client() -> Iterator[MongoClient]:
    client: MongoClient = MongoClient(TEST_URI, serverSelectionTimeoutMS=1500)
    try:
        client.admin.command("ping")
    except PyMongoError:
        pytest.skip(f"No hay servidor MongoDB en {TEST_URI}")
    yield client
    client.close()


@pytest.fixture(scope="session")
def documents() -> list[dict[str, Any]]:
    return synthetic_documents()


@pytest.fixture(scope="session")
def data_file(tmp_path_factory: pytest.TempPathFactory, documents) -> Path:
    path = tmp_path_factory.mktemp("raw") / "sms-call-internet-mi-2013-12-02.txt"
    path.write_text("".join(to_line(d) for d in documents), encoding="ascii")
    return path


@pytest.fixture(scope="session")
def settings(mongo_client: MongoClient, tmp_path_factory: pytest.TempPathFactory) -> Iterator[Settings]:
    db_name = f"Milan_CDR_test_{uuid.uuid4().hex[:8]}"
    yield Settings(
        mongo_uri=TEST_URI,
        db_name=db_name,
        data_dir=tmp_path_factory.mktemp("data"),
        results_dir=tmp_path_factory.mktemp("results"),
    )
    mongo_client.drop_database(db_name)


@pytest.fixture(scope="session")
def loaded_db(settings: Settings, data_file: Path, mongo_client: MongoClient):
    """Base de datos temporal con los datos sintéticos cargados con el loader real."""
    from milan_cdr.loader import load_files

    load_files([data_file], settings, workers=1)
    return mongo_client[settings.db_name]
