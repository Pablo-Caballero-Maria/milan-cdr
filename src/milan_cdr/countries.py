"""Traducción de prefijos telefónicos (``countrycode``) a países.

El campo ``countrycode`` es el prefijo internacional E.164 (39 = Italia,
33 = Francia...). Hay dos particularidades en el dataset:

* ``0`` agrupa registros sin país identificado.
* Algunos códigos son más largos que un prefijo E.164 porque incluyen dígitos
  adicionales que identifican el país dentro de una zona compartida. El caso
  típico es el Plan de Numeración de Norteamérica (prefijo 1): ``1204`` es
  Canadá (Manitoba), ``1809`` la República Dominicana, etc. Lo mismo ocurre en
  la zona 7 (Rusia / Kazajistán).

Para resolverlos se usa ``phonenumbers`` (port de libphonenumber de Google)
construyendo un número de ejemplo con ese prefijo, y ``babel`` (datos CLDR)
para obtener el nombre del país en español.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import phonenumbers
from babel import Locale

from milan_cdr.config import ITALY_CODE, UNKNOWN_CODE

_LOCALE = Locale("es")
#: Región que libphonenumber asigna a servicios no geográficos (satélite, redes globales).
NON_GEOGRAPHIC: str = phonenumbers.REGION_CODE_FOR_NON_GEO_ENTITY  # "001"
# Dígitos de relleno para formar un número nacional plausible de 10 cifras.
_FILLER = "2345678901"


@dataclass(frozen=True, slots=True)
class Country:
    """País (o entidad) asociado a un prefijo."""

    code: int
    region: str | None
    name: str

    @property
    def is_foreign(self) -> bool:
        """``True`` si es un país identificado distinto de Italia."""
        return self.code not in (ITALY_CODE, UNKNOWN_CODE)


def _split_calling_code(digits: str) -> tuple[int, str] | None:
    """Separa un código en (prefijo E.164 válido, dígitos restantes)."""
    for length in (1, 2, 3):
        prefix = int(digits[:length])
        if phonenumbers.region_codes_for_country_code(prefix):
            return prefix, digits[length:]
    return None


def _region_for(code: int) -> str | None:
    digits = str(code)
    split = _split_calling_code(digits)
    if split is None:
        return None
    calling_code, rest = split
    regions = phonenumbers.region_codes_for_country_code(calling_code)
    if not rest:
        # Prefijo "puro": región principal (p. ej. 1 -> US, 7 -> RU, 39 -> IT).
        return regions[0]
    national = rest + _FILLER[: max(0, 10 - len(rest))]
    try:
        number = phonenumbers.parse(f"+{calling_code}{national}")
    except phonenumbers.NumberParseException:
        return regions[0]
    return phonenumbers.region_code_for_number(number) or regions[0]


def _region_name(region: str) -> str:
    if region == NON_GEOGRAPHIC:
        return "Servicio internacional no geográfico"
    return _LOCALE.territories.get(region, region)


@cache
def lookup(code: int) -> Country:
    """Devuelve el país correspondiente a un ``countrycode`` del dataset.

    >>> lookup(39).name
    'Italia'
    >>> lookup(1204).name
    'Canadá'
    >>> lookup(0).name
    'Desconocido (código 0)'
    """
    if code == UNKNOWN_CODE:
        return Country(code, None, "Desconocido (código 0)")
    region = _region_for(code)
    if region is None:
        return Country(code, None, f"Código no asignado ({code})")
    return Country(code, region, _region_name(region))


def country_name(code: int) -> str:
    """Atajo para obtener solo el nombre en español."""
    return lookup(code).name
