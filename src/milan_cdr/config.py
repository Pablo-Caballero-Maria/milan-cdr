"""Configuración central del proyecto.

Todas las constantes del dominio (campos de actividad, códigos de país
especiales, celdas de estudio...) y los parámetros de ejecución (URI de
MongoDB, semana elegida, directorios) viven aquí para que el resto de
módulos no tenga valores "mágicos" repartidos.

Los parámetros de ejecución se pueden sobrescribir con variables de entorno
(prefijo ``MILAN_CDR_``), lo que permite, por ejemplo, ejecutar los tests
contra otra base de datos sin tocar el código.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Final, Literal

#: Nombre de un campo de actividad de un registro CDR.
type ActivityField = Literal["smsin", "smsout", "callin", "callout", "internet"]

#: Campos numéricos de actividad presentes en cada registro CDR.
ACTIVITY_FIELDS: Final[tuple[ActivityField, ...]] = (
    "smsin",
    "smsout",
    "callin",
    "callout",
    "internet",
)

#: Grupos de actividad usados en los análisis agregados.
ACTIVITY_GROUPS: Final[dict[str, tuple[str, ...]]] = {
    "sms": ("smsin", "smsout"),
    "llamadas": ("callin", "callout"),
    "internet": ("internet",),
}

#: Prefijo telefónico de Italia.
ITALY_CODE: Final[int] = 39

#: Código de país 0: el dataset lo usa para registros sin país identificado.
UNKNOWN_CODE: Final[int] = 0

#: Celdas que se estudian en el apartado 8, con una etiqueta descriptiva.
STUDY_CELLS: Final[dict[int, str]] = {
    4259: "Bocconi",
    4456: "Navigli",
    5060: "Duomo",
    1419: "Terreno agrícola",
    2436: "Área industrial",
    4990: "Aeropuerto de Linate",
    945: "Residencial aislado",
    5048: "Residencial céntrico",
}

#: La cuadrícula de Milán es de 100 x 100 celdas (ids 1..10000).
GRID_SIZE: Final[int] = 100

#: Zona horaria en la que se interpretan horas y días.
TIMEZONE: Final[str] = "Europe/Rome"

#: DOI del dataset "Telecommunications - SMS, Call, Internet - MI".
DATAVERSE_DOI: Final[str] = "doi:10.7910/DVN/EGZHFV"
DATAVERSE_SERVER: Final[str] = "https://dataverse.harvard.edu"

#: Lunes de la semana analizada (2 de diciembre de 2013).
DEFAULT_WEEK_START: Final[date] = date(2013, 12, 2)


def _env(name: str, default: str) -> str:
    return os.environ.get(f"MILAN_CDR_{name}", default)


@dataclass(frozen=True, slots=True)
class Settings:
    """Parámetros de ejecución, sobrescribibles con variables de entorno."""

    mongo_uri: str = field(default_factory=lambda: _env("MONGO_URI", "mongodb://localhost:27017"))
    db_name: str = field(default_factory=lambda: _env("DB", "Milan_CDR_db"))
    collection: str = field(default_factory=lambda: _env("COLLECTION", "Milan_CDR_c"))
    cell_collection: str = field(default_factory=lambda: _env("CELL_COLLECTION", "Milan_CDR_celdas"))
    cell_hour_collection: str = field(default_factory=lambda: _env("CELL_HOUR_COLLECTION", "Milan_CDR_celda_hora"))
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "data/raw")))
    results_dir: Path = field(default_factory=lambda: Path(_env("RESULTS_DIR", "results")))
    week_start: date = field(
        default_factory=lambda: date.fromisoformat(_env("WEEK_START", DEFAULT_WEEK_START.isoformat()))
    )

    @property
    def week_days(self) -> list[date]:
        """Los siete días (lunes a domingo) de la semana analizada."""
        return [self.week_start + timedelta(days=i) for i in range(7)]

    def __post_init__(self) -> None:
        if self.week_start.weekday() != 0:
            msg = f"La semana debe empezar en lunes; {self.week_start} no lo es."
            raise ValueError(msg)
