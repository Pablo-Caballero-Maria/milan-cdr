"""Descarga de los ficheros ``.txt`` diarios desde Harvard Dataverse.

El dataset está protegido por un *guestbook* que exige un email antes de
permitir la descarga. El flujo es:

1. ``GET /api/datasets/:persistentId`` para obtener el listado de ficheros.
2. Para cada fichero, ``POST /api/access/datafile/{id}`` con la respuesta del
   guestbook; Dataverse devuelve una URL firmada de un solo uso.
3. ``GET`` de esa URL en streaming, escribiendo a un ``.part`` y renombrando
   al terminar (así una descarga interrumpida nunca deja un fichero "válido").
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import httpx

from milan_cdr.config import DATAVERSE_DOI, DATAVERSE_SERVER

log = logging.getLogger(__name__)

_FILENAME_RE = re.compile(r"^sms-call-internet-mi-(\d{4}-\d{2}-\d{2})\.txt$")
_CHUNK = 1 << 20  # 1 MiB


@dataclass(frozen=True, slots=True)
class DataFile:
    """Fichero diario publicado en Dataverse."""

    file_id: int
    filename: str
    size: int
    day: date


def parse_file_listing(dataset_json: dict) -> list[DataFile]:
    """Extrae los ficheros diarios del JSON devuelto por la API de datasets."""
    files: list[DataFile] = []
    for entry in dataset_json["data"]["latestVersion"]["files"]:
        data_file = entry["dataFile"]
        match = _FILENAME_RE.match(data_file["filename"])
        if match is None:
            continue
        files.append(
            DataFile(
                file_id=int(data_file["id"]),
                filename=data_file["filename"],
                size=int(data_file["filesize"]),
                day=date.fromisoformat(match.group(1)),
            )
        )
    return sorted(files, key=lambda f: f.day)


def select_days(files: Iterable[DataFile], days: Iterable[date]) -> list[DataFile]:
    """Filtra los ficheros de los días pedidos; falla si falta alguno."""
    wanted = set(days)
    selected = [f for f in files if f.day in wanted]
    missing = wanted - {f.day for f in selected}
    if missing:
        msg = f"Dataverse no publica ficheros para: {sorted(missing)}"
        raise LookupError(msg)
    return selected


class DataverseClient:
    """Cliente mínimo de la API de Dataverse para este dataset."""

    def __init__(
        self,
        email: str,
        server: str = DATAVERSE_SERVER,
        doi: str = DATAVERSE_DOI,
        client: httpx.Client | None = None,
    ) -> None:
        self.email = email
        self.doi = doi
        self._client = client or httpx.Client(base_url=server, timeout=60, follow_redirects=True)

    def list_files(self) -> list[DataFile]:
        """Devuelve los ficheros diarios del dataset ordenados por fecha."""
        response = self._client.get("/api/datasets/:persistentId/", params={"persistentId": self.doi})
        response.raise_for_status()
        return parse_file_listing(response.json())

    def signed_url(self, data_file: DataFile) -> str:
        """Envía la respuesta al guestbook y obtiene la URL firmada de descarga."""
        response = self._client.post(
            f"/api/access/datafile/{data_file.file_id}",
            json={"guestbookResponse": {"email": self.email}},
        )
        response.raise_for_status()
        return response.json()["data"]["signedUrl"]

    def download(
        self,
        data_file: DataFile,
        dest_dir: Path,
        on_progress: Callable[[int], None] | None = None,
    ) -> Path:
        """Descarga un fichero (si no existe ya con el tamaño correcto)."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / data_file.filename
        if target.exists() and target.stat().st_size == data_file.size:
            log.info("%s ya descargado, se omite", target.name)
            return target

        partial = target.with_suffix(target.suffix + ".part")
        with (
            self._client.stream("GET", self.signed_url(data_file), timeout=None) as response,
            partial.open("wb") as fh,
        ):
            response.raise_for_status()
            for chunk in response.iter_bytes(_CHUNK):
                fh.write(chunk)
                if on_progress is not None:
                    on_progress(len(chunk))

        if (size := partial.stat().st_size) != data_file.size:
            msg = f"{data_file.filename}: tamaño {size} != {data_file.size} esperado"
            raise OSError(msg)
        partial.replace(target)
        return target
