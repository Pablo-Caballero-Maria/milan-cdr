"""Apartado 1: carga de los ficheros en ``Milan_CDR_db.Milan_CDR_c``.

La carga se paraleliza con un proceso por fichero: el parseo de texto en
Python es el cuello de botella, así que varios procesos aprovechan todos los
núcleos mientras MongoDB absorbe las inserciones concurrentes.

Las inserciones se hacen con ``insert_many(ordered=False)`` en lotes, que es
la forma más eficiente de carga masiva con PyMongo. Los índices se crean al
final (mantenerlos durante la carga la ralentizaría).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection

from milan_cdr.config import Settings
from milan_cdr.documents import CDRDocument, collections, typed_collection
from milan_cdr.parsing import batched, read_file

log = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 20_000

#: Índices de la colección principal. ``cellid`` + ``time`` acelera las
#: consultas por celda (apartado 8); ``countrycode`` las de países.
INDEXES: tuple[tuple[str, list[tuple[str, int]]], ...] = (
    ("cellid_time", [("cellid", ASCENDING), ("time", ASCENDING)]),
    ("countrycode", [("countrycode", ASCENDING)]),
)


@dataclass(frozen=True, slots=True)
class LoadStats:
    """Resumen de una carga."""

    documents: int
    seconds: float


def insert_documents(
    collection: Collection[CDRDocument],
    documents: Iterable[CDRDocument],
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> int:
    """Inserta documentos por lotes y devuelve cuántos se insertaron."""
    inserted = 0
    for batch in batched(documents, batch_size):
        result = collection.insert_many(batch, ordered=False)
        inserted += len(result.inserted_ids)
    return inserted


def _load_one(path: Path, uri: str, db_name: str, collection_name: str, batch_size: int) -> int:
    """Carga un único fichero (se ejecuta en un proceso hijo)."""
    with MongoClient(uri) as client:
        collection = typed_collection(client[db_name], collection_name, CDRDocument)
        count = insert_documents(collection, read_file(path), batch_size)
    log.info("%s: %d documentos", path.name, count)
    return count


def create_indexes(collection: Collection[CDRDocument]) -> list[str]:
    """Crea los índices de la colección principal (idempotente)."""
    return [collection.create_index(keys, name=name) for name, keys in INDEXES]


def load_files(
    paths: Sequence[Path],
    settings: Settings,
    workers: int = 7,
    drop: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> LoadStats:
    """Carga varios ficheros en paralelo y crea los índices al terminar."""
    start = time.perf_counter()
    with MongoClient(settings.mongo_uri) as client:
        collection = collections(client[settings.db_name], settings).cdr
        if drop:
            collection.drop()

        args = [(p, settings.mongo_uri, settings.db_name, settings.collection, batch_size) for p in paths]
        if workers == 1:
            total = sum(_load_one(*a) for a in args)
        else:
            with ProcessPoolExecutor(max_workers=min(workers, len(paths))) as pool:
                total = sum(pool.map(_load_one, *zip(*args, strict=True)))

        log.info("Creando índices...")
        create_indexes(collection)
    return LoadStats(documents=total, seconds=time.perf_counter() - start)
