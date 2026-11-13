"""Interfaz de línea de comandos (``milan-cdr``).

Subcomandos principales::

    milan-cdr download --email tu@correo    # apartado 1: descarga de los .txt
    milan-cdr load                          # apartado 1: carga en MongoDB
    milan-cdr run 2                         # ejecuta un apartado concreto
    milan-cdr report                        # ejecuta todo y guarda resultados
    milan-cdr figures                       # regenera solo las figuras

Todos los parámetros de conexión se leen de :class:`milan_cdr.config.Settings`.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from milan_cdr.config import Settings

app = typer.Typer(help="Análisis de los CDR de Milán con MongoDB.", no_args_is_help=True)


def _settings(week_start: date | None = None) -> Settings:
    if week_start is None:
        return Settings()
    return Settings(week_start=week_start)


@app.callback()
def _main(verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # httpx registra cada petición a INFO, incluidas las URLs firmadas: se silencia.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # kaleido (exportación PNG de plotly) y su Chrome sin interfaz son muy verbosos a INFO.
    for name in ("kaleido", "choreographer", "logistro"):
        logging.getLogger(name).setLevel(logging.WARNING)


@app.command()
def download(
    email: Annotated[str, typer.Option(envvar="MILAN_CDR_EMAIL", help="Email para el guestbook.")],
    week_start: Annotated[str | None, typer.Option(help="Lunes de la semana (AAAA-MM-DD).")] = None,
    parallel: Annotated[int, typer.Option(min=1, max=7)] = 4,
) -> None:
    """Descarga los siete ficheros diarios de la semana elegida."""
    from milan_cdr.dataverse import DataverseClient, select_days

    settings = _settings(date.fromisoformat(week_start) if week_start else None)
    client = DataverseClient(email=email)
    files = select_days(client.list_files(), settings.week_days)
    total = sum(f.size for f in files)
    typer.echo(f"Descargando {len(files)} ficheros ({total / 1e9:.2f} GB) en {settings.data_dir}")

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        paths = list(pool.map(lambda f: client.download(f, settings.data_dir), files))
    for path in paths:
        typer.echo(f"  ✓ {path}")


@app.command()
def load(
    files: Annotated[list[Path] | None, typer.Argument(help="Ficheros .txt (por defecto, la semana).")] = None,
    workers: Annotated[int, typer.Option(min=1)] = 7,
    drop: Annotated[bool, typer.Option(help="Vaciar la colección antes de cargar.")] = True,
) -> None:
    """Carga los ficheros en la colección ``Milan_CDR_c`` de ``Milan_CDR_db``."""
    from milan_cdr.loader import load_files

    settings = _settings()
    if not files:
        files = [settings.data_dir / f"sms-call-internet-mi-{d.isoformat()}.txt" for d in settings.week_days]
    missing = [f for f in files if not f.exists()]
    if missing:
        raise typer.BadParameter(f"No existen: {', '.join(map(str, missing))}")
    stats = load_files(files, settings, workers=workers, drop=drop)
    typer.echo(f"Insertados {stats.documents:,} documentos en {stats.seconds:.1f} s")


@app.command()
def run(
    section: Annotated[int, typer.Argument(min=2, max=8, help="Apartado del enunciado (2-8).")],
) -> None:
    """Ejecuta un apartado y muestra su resultado por pantalla."""
    from milan_cdr.report import print_section

    print_section(section, _settings())


@app.command()
def report() -> None:
    """Ejecuta todos los apartados y guarda resultados (JSON, Markdown, figuras)."""
    from milan_cdr.report import build_report

    out = build_report(_settings())
    typer.echo(f"Informe generado en {out}")


@app.command()
def figures() -> None:
    """Regenera solo las figuras del apartado 8 (PNG y HTML interactivo)."""
    from milan_cdr.report import build_figures

    for path in build_figures(_settings()).values():
        typer.echo(f"  ✓ {path}")


if __name__ == "__main__":
    app()
