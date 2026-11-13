"""Lectura de los ficheros ``.txt`` del dataset y conversión a documentos.

Cada línea es un registro separado por tabuladores con 8 columnas::

    cellid  time  countrycode  smsin  smsout  callin  callout  internet

``time`` son milisegundos desde la época Unix (UTC) y marca el inicio del
intervalo de 10 minutos. Las columnas de actividad pueden venir vacías
cuando no hubo actividad de ese tipo.

Decisiones de modelado del documento:

* ``time`` se guarda como ``Date`` BSON (``datetime`` con zona UTC) para poder
  usar los operadores de fecha de MongoDB (``$hour``, ``$dateTrunc``...) con
  la zona horaria de Milán.
* Los campos de actividad vacíos **se omiten** en lugar de guardarse como
  ``null``: ahorra espacio y ``$sum`` ignora los campos ausentes.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from milan_cdr.config import ACTIVITY_FIELDS

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_N_COLUMNS = 3 + len(ACTIVITY_FIELDS)


#: Documento de la colección ``Milan_CDR_c``: ``cellid`` (int), ``time``
#: (datetime UTC), ``countrycode`` (int) y, solo si tienen valor, los campos
#: de actividad ``smsin``, ``smsout``, ``callin``, ``callout`` e ``internet``
#: (float).
type CDRDocument = dict[str, int | float | datetime]


class ParseError(ValueError):
    """Línea con un formato que no corresponde al del dataset."""


def ms_to_datetime(ms: int) -> datetime:
    """Convierte milisegundos Unix a ``datetime`` UTC (sin pérdida de precisión)."""
    return _EPOCH + timedelta(milliseconds=ms)


def parse_line(line: str) -> CDRDocument:
    r"""Convierte una línea del fichero en un documento listo para insertar.

    >>> doc = parse_line("1\t1385938800000\t39\t0.5\t\t\t\t12.3")
    >>> doc["cellid"], doc["countrycode"], doc["smsin"], doc["internet"]
    (1, 39, 0.5, 12.3)
    >>> "smsout" in doc
    False
    """
    parts = line.rstrip("\r\n").split("\t")
    if len(parts) != _N_COLUMNS:
        msg = f"Se esperaban {_N_COLUMNS} columnas y hay {len(parts)}: {line!r}"
        raise ParseError(msg)
    try:
        doc: CDRDocument = {
            "cellid": int(parts[0]),
            "time": ms_to_datetime(int(parts[1])),
            "countrycode": int(parts[2]),
        }
        for name, raw in zip(ACTIVITY_FIELDS, parts[3:], strict=True):
            if raw:
                doc[name] = float(raw)
    except ValueError as exc:
        raise ParseError(f"Valor no numérico en {line!r}") from exc
    return doc


def iter_documents(lines: Iterable[str]) -> Iterator[CDRDocument]:
    """Genera documentos a partir de líneas, ignorando líneas en blanco."""
    for line in lines:
        if line.strip():
            yield parse_line(line)


def read_file(path: Path) -> Iterator[CDRDocument]:
    """Lee un fichero diario del dataset de forma perezosa."""
    with path.open(encoding="ascii") as fh:
        yield from iter_documents(fh)


def batched[T](items: Iterable[T], size: int) -> Iterator[list[T]]:
    """Agrupa un iterable en listas de, como mucho, ``size`` elementos."""
    if size < 1:
        raise ValueError("size debe ser >= 1")
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch
