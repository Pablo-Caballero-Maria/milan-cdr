"""Esquema tipado de las colecciones: qué forma tiene cada documento y cómo acceder a ellas.

Cada colección se usa a través de un ``Collection[...]`` de PyMongo parametrizado con su tipo de
documento (un ``TypedDict``), de modo que el comprobador de tipos (``ty``) revisa las inserciones,
los filtros por ``_id`` y los campos que se leen de los resultados.

* :class:`CDRDocument`: ``Milan_CDR_c``, un registro de 10 minutos por celda y país (apartado 1).
* :class:`CellDocument`: ``Milan_CDR_celdas``, los acumulados de cada celda (apartado 6).
* :class:`CellHourDocument`: ``Milan_CDR_celda_hora``, los de cada celda y hora (apartado 7).
"""

# Sin `from __future__ import annotations`: TypedDict debe ver NotRequired al crear la clase
# (para saber qué campos son opcionales también en tiempo de ejecución).
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NotRequired, TypedDict, cast

from pymongo.collection import Collection
from pymongo.database import Database

from milan_cdr.config import Settings


class CDRDocument(TypedDict):
    """Un registro del dataset. Los campos de actividad sin valor no se guardan."""

    cellid: int
    #: Inicio del intervalo de 10 minutos (fecha BSON, UTC).
    time: datetime
    countrycode: int
    smsin: NotRequired[float]
    smsout: NotRequired[float]
    callin: NotRequired[float]
    callout: NotRequired[float]
    internet: NotRequired[float]


class _Totals(TypedDict):
    """Sumas por campo y por grupo de actividad (``pipelines.sum_fields`` y ``group_totals``)."""

    smsin: float
    smsout: float
    callin: float
    callout: float
    internet: float
    sms: float
    llamadas: float
    sms_llamadas: float
    total: float


class CellDocument(_Totals):
    """Una celda de la cuadrícula con los acumulados de toda la semana (``pipelines.cell_totals``)."""

    _id: int  # cellid
    registros: int
    total_extranjero: float
    n_paises: int
    fila: int
    columna: int


class CellTotal(TypedDict):
    """Lo que el mapa de la cuadrícula lee de una celda (la proyección ``{"total": 1}``)."""

    _id: int
    total: float


class CellHourKey(TypedDict):
    """El ``_id`` de :class:`CellHourDocument`: la celda y la hora."""

    cellid: int
    hora: datetime


class CellHourDocument(_Totals):
    """Una celda en una hora concreta (``pipelines.cell_hour_totals``)."""

    _id: CellHourKey
    cellid: int
    #: Inicio de la hora, en la zona horaria de Milán.
    hora: datetime
    fecha: str
    #: Día de la semana ISO: 1 = lunes … 7 = domingo.
    dia_semana: int
    hora_dia: int


def typed_collection[T: Mapping[str, Any]](
    db: Database[dict[str, Any]], name: str, _document: type[T]
) -> Collection[T]:
    """La colección ``name`` con documentos de tipo ``T`` (las colecciones de PyMongo son genéricas)."""
    return cast("Collection[T]", db.get_collection(name))


@dataclass(frozen=True, slots=True)
class Collections:
    """Las tres colecciones del trabajo, cada una con su tipo de documento."""

    cdr: Collection[CDRDocument]
    cells: Collection[CellDocument]
    cell_hours: Collection[CellHourDocument]


def collections(db: Database[dict[str, Any]], settings: Settings) -> Collections:
    """Las colecciones de ``settings`` en ``db``, tipadas."""
    return Collections(
        cdr=typed_collection(db, settings.collection, CDRDocument),
        cells=typed_collection(db, settings.cell_collection, CellDocument),
        cell_hours=typed_collection(db, settings.cell_hour_collection, CellHourDocument),
    )
