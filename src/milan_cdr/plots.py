"""Figuras de la memoria (plotly).

Cada figura se guarda dos veces: como HTML interactivo (con *hover*) y como
PNG estático, exportado con kaleido, para incrustarlo en la memoria.

Criterios de diseño: líneas finas (2 px), rejilla muy suave, como mucho 3
series por panel (más series → small multiples), un único eje Y por gráfico,
colores categoriales en orden fijo y texto siempre en tinta neutra (nunca del
color de la serie). Los números usan coma decimal y punto de miles.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots

from milan_cdr.config import GRID_SIZE, TIMEZONE
from milan_cdr.study import CellStudy, Profile, StudyResult

# Paleta (modo claro) ------------------------------------------------------
SURFACE = "#ffffff"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")  # azul, naranja, aguamarina
REFERENCE = "#b5b3ab"  # gris para la referencia "ciudad"
BLUE_RAMP = ("#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b")
DIVERGING = ("#256abf", "#86b6ef", "#f0efec", "#ec9a99", "#c73a3a")
FONT = "Noto Sans, Liberation Sans, Arial, sans-serif"

_TZ = ZoneInfo(TIMEZONE)
#: Desplazamiento (píxeles) de la etiqueta de cada celda en el mapa, para que
#: las celdas céntricas, muy próximas entre sí, no se tapen.
LABEL_OFFSETS: dict[int, tuple[int, int]] = {
    5060: (10, -56),  # Duomo
    5048: (-50, -30),  # Residencial céntrico
    4456: (-60, 0),  # Navigli
    4259: (44, 26),  # Bocconi
    4990: (0, -28),  # Linate
}
#: Nombres cortos para las etiquetas del mapa.
SHORT_NAMES: dict[int, str] = {4990: "Linate"}

DAY_NAMES = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
ACTIVITY_LABELS = {"sms": "SMS", "llamadas": "Llamadas", "internet": "Internet"}

_AXIS_STYLE: dict[str, Any] = {
    "showgrid": True,
    "gridcolor": GRID,
    "gridwidth": 1,
    "showline": True,
    "linecolor": AXIS,
    "ticks": "outside",
    "tickcolor": AXIS,
    "ticklen": 4,
    "tickfont": {"color": INK_2, "size": 11},
    "title": {"font": {"color": INK_2, "size": 12}},
    "zeroline": False,
}
pio.templates["milan"] = go.layout.Template(
    layout={
        "font": {"family": FONT, "size": 12, "color": INK_2},
        "paper_bgcolor": SURFACE,
        "plot_bgcolor": SURFACE,
        "colorway": list(SERIES),
        "separators": ",.",
        "xaxis": _AXIS_STYLE,
        "yaxis": _AXIS_STYLE,
        "legend": {"font": {"color": INK_2, "size": 12}, "bgcolor": "rgba(0,0,0,0)"},
        "hoverlabel": {"bgcolor": SURFACE, "bordercolor": AXIS, "font": {"color": INK, "family": FONT}},
        "annotationdefaults": {"font": {"color": INK, "size": 12}, "showarrow": False},
    }
)
TEMPLATE = "milan"


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def _layout(fig: go.Figure, title: str, width: int, height: int, *, legend: bool = False, **margin: int) -> None:
    """Título arriba a la izquierda y, si hay varias series, la leyenda debajo."""
    top = 96 if legend else 60
    fig.update_layout(
        template=TEMPLATE,
        width=width,
        height=height,
        title={
            "text": title,
            "x": 0.012,
            "xanchor": "left",
            "y": 1 - 20 / height,
            "yanchor": "top",
            "font": {"size": 15, "color": INK, "weight": 600},
        },
        margin={"t": top, "l": 64, "r": 24, "b": 48} | margin,
        showlegend=legend,
        legend={
            "orientation": "h",
            "x": 0.012,
            "xanchor": "left",
            "xref": "container",
            "y": 1 - 52 / height,
            "yanchor": "top",
            "yref": "container",
        },
    )


def _left_subplot_titles(fig: go.Figure) -> None:
    """Alinea los títulos de los paneles (``subplot_titles``) a la izquierda."""
    for i, annotation in enumerate(fig.layout.annotations):
        domain = fig.layout[f"xaxis{i + 1 if i else ''}"].domain
        annotation.update(x=domain[0], xanchor="left", font={"size": 12, "color": INK})


def _local(t: datetime) -> datetime:
    """Instante (UTC si no lleva zona) → hora local de Milán sin zona."""
    aware = t if t.tzinfo else t.replace(tzinfo=UTC)
    return aware.astimezone(_TZ).replace(tzinfo=None)


def _hover_time(t: datetime) -> str:
    return f"{DAY_NAMES[t.weekday()]} {t.day}, {t:%H:%M}"


def _day_axis(times: Sequence[datetime], with_date: bool = True) -> dict[str, Any]:
    """Eje X de una serie semanal: un tick a las 00:00 de cada día, en español."""
    days = sorted({t.date() for t in times})
    ticks = [datetime.combine(d, time()) for d in days]
    end = datetime.combine(date.fromordinal(days[-1].toordinal() + 1), time())
    return {
        "tickvals": ticks,
        "ticktext": [f"{DAY_NAMES[t.weekday()]} {t.day}" if with_date else DAY_NAMES[t.weekday()] for t in ticks],
        "range": [ticks[0], end],
    }


def _num(value: float, digits: int = 2) -> str:
    """Número con ``digits`` cifras significativas y coma decimal."""
    return f"{value:.{digits}g}".replace(".", ",")


def _grid(n: int, titles: Sequence[str], ncols: int = 2, **kwargs: Any) -> tuple[go.Figure, list[tuple[int, int]]]:
    """Rejilla de small multiples y las posiciones (fila, columna) de cada panel."""
    nrows = math.ceil(n / ncols)
    fig = make_subplots(rows=nrows, cols=ncols, subplot_titles=list(titles), **kwargs)
    _left_subplot_titles(fig)
    return fig, [(1 + i // ncols, 1 + i % ncols) for i in range(n)]


def cell_label(cell: CellStudy) -> str:
    """Etiqueta corta ``id · nombre`` de una celda."""
    return f"{cell.cellid} · {cell.nombre}"


# --------------------------------------------------------------------------
# Figuras
# --------------------------------------------------------------------------
def grid_map(cells: Sequence[dict[str, Any]], highlight: dict[int, str]) -> go.Figure:
    """Mapa 100x100 de la actividad total por celda (escala logarítmica)."""
    grid = np.full((GRID_SIZE, GRID_SIZE), np.nan)
    for doc in cells:
        cid = int(doc["_id"])
        grid[(cid - 1) // GRID_SIZE, (cid - 1) % GRID_SIZE] = max(doc["total"], 1e-3)
    ids = np.arange(1, GRID_SIZE * GRID_SIZE + 1).reshape(GRID_SIZE, GRID_SIZE)
    zmin = math.log10(np.nanpercentile(grid, 1))
    zmax = math.log10(np.nanmax(grid))
    ticks = list(range(math.ceil(zmin), math.floor(zmax) + 1))

    fig = go.Figure(
        go.Heatmap(
            z=np.log10(grid),
            customdata=np.dstack([ids, grid]),
            colorscale=[[i / (len(BLUE_RAMP) - 1), c] for i, c in enumerate(BLUE_RAMP)],
            zmin=zmin,
            zmax=zmax,
            hovertemplate="Celda %{customdata[0]}<br>Actividad %{customdata[1]:,.0f}<extra></extra>",
            colorbar={
                "title": {"text": "Actividad total<br>(escala log)", "side": "right", "font": {"color": INK_2}},
                "tickvals": ticks,
                "ticktext": [f"{10**e:,.0f}".replace(",", ".") for e in ticks],
                "outlinewidth": 0,
                "thickness": 14,
                "len": 0.85,
            },
        )
    )
    for cid, name in highlight.items():
        row, col = (cid - 1) // GRID_SIZE, (cid - 1) % GRID_SIZE
        dx, dy = LABEL_OFFSETS.get(cid, (24, -18))
        fig.add_annotation(
            x=col,
            y=row,
            ax=dx,
            ay=dy,
            text=f"{cid} · {SHORT_NAMES.get(cid, name)}",
            showarrow=True,
            arrowhead=0,
            arrowwidth=1,
            arrowcolor=INK_2,
            standoff=6,
            xanchor="right" if dx < 0 else ("center" if dx == 0 else "left"),
            font={"size": 11, "color": INK},
            bgcolor="rgba(255,255,255,0.85)",
        )
    fig.add_trace(
        go.Scatter(
            x=[(cid - 1) % GRID_SIZE for cid in highlight],
            y=[(cid - 1) // GRID_SIZE for cid in highlight],
            mode="markers",
            marker={"symbol": "circle-open", "size": 10, "color": INK, "line": {"width": 2}},
            hoverinfo="skip",
        )
    )
    _layout(fig, "Actividad total acumulada por celda, 2–8 dic 2013", 760, 650, r=16, t=48)
    fig.update_xaxes(title_text="Columna de la cuadrícula (oeste → este)", showgrid=False, showline=False)
    fig.update_yaxes(
        title_text="Fila de la cuadrícula (sur → norte)",
        showgrid=False,
        showline=False,
        scaleanchor="x",
        constrain="domain",
    )
    return fig


def city_series(rows: Sequence[dict[str, Any]]) -> go.Figure:
    """Actividad de toda la ciudad hora a hora, una fila por tipo de actividad."""
    times = [_local(r["_id"]) for r in rows]
    hover = [_hover_time(t) for t in times]
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.09, subplot_titles=list(ACTIVITY_LABELS.values())
    )
    _left_subplot_titles(fig)
    for i, (key, color) in enumerate(zip(ACTIVITY_LABELS, SERIES, strict=True), start=1):
        fig.add_trace(
            go.Scatter(
                x=times,
                y=[r[key] for r in rows],
                customdata=hover,
                mode="lines",
                line={"color": color, "width": 2},
                fill="tozeroy",
                fillcolor=f"rgba({int(color[1:3], 16)},{int(color[3:5], 16)},{int(color[5:7], 16)},0.10)",
                hovertemplate="%{customdata}<br>%{y:,.0f}<extra>" + ACTIVITY_LABELS[key] + "</extra>",
            ),
            row=i,
            col=1,
        )
    _layout(fig, "Milán completo: actividad por hora (hora local)", 900, 620)
    fig.update_xaxes(**_day_axis(times))
    fig.update_yaxes(tickformat="~s", rangemode="tozero")
    return fig


def study_series(result: StudyResult) -> go.Figure:
    """Small multiples: serie semanal (internet vs. SMS+llamadas) de cada celda.

    Cada serie se normaliza por su media semanal (1 = actividad media) para
    que la *forma* sea comparable entre celdas de volúmenes muy distintos.
    """
    fig, positions = _grid(len(result.cells), [cell_label(c) for c in result.cells], vertical_spacing=0.07)
    times: list[datetime] = []
    for idx, (cell, (row, col)) in enumerate(zip(result.cells, positions, strict=True)):
        times = [_local(r["hora"]) for r in cell.serie]
        hover = [_hover_time(t) for t in times]
        for key, label, color in (("internet", "Internet", SERIES[0]), (None, "SMS + llamadas", SERIES[1])):
            values = np.array([r[key] if key else r["sms"] + r["llamadas"] for r in cell.serie])
            mean = values.mean() or 1.0
            fig.add_trace(
                go.Scatter(
                    x=times,
                    y=values / mean,
                    customdata=hover,
                    name=label,
                    legendgroup=label,
                    showlegend=idx == 0,
                    mode="lines",
                    line={"color": color, "width": 1.5},
                    hovertemplate="%{customdata}<br>%{y:.2f} × media<extra>" + label + "</extra>",
                ),
                row=row,
                col=col,
            )
        fig.add_hline(y=1, line={"color": AXIS, "width": 1}, row=row, col=col)
    _layout(fig, "Serie semanal por hora, normalizada (1 = media de la celda)", 900, 900, legend=True)
    fig.update_xaxes(**_day_axis(times, with_date=False), tickfont_size=10)
    fig.update_yaxes(rangemode="tozero", tickfont_size=10)
    return fig


def _share(profile: list[float]) -> list[float]:
    total = sum(profile) or 1.0
    return [100 * v / total for v in profile]


def study_profiles(result: StudyResult, metric: str = "total") -> go.Figure:
    """Small multiples: perfil horario laborable vs. fin de semana vs. ciudad.

    Cada perfil se expresa como % de la actividad diaria que ocurre en cada
    hora, de modo que solo se compara la forma del día.
    """
    city_week: Profile = result.perfil_ciudad[False]
    fig, positions = _grid(len(result.cells), [cell_label(c) for c in result.cells], vertical_spacing=0.07)
    hours = list(range(24))
    for idx, (cell, (row, col)) in enumerate(zip(result.cells, positions, strict=True)):
        lines = (
            ("Ciudad (laborable)", city_week[metric], REFERENCE, 1.5),
            ("Laborable", cell.perfil_laborable[metric], SERIES[0], 2),
            ("Fin de semana", cell.perfil_finde[metric], SERIES[1], 2),
        )
        for label, profile, color, width in lines:
            fig.add_trace(
                go.Scatter(
                    x=hours,
                    y=_share(profile),
                    name=label,
                    legendgroup=label,
                    showlegend=idx == 0,
                    mode="lines",
                    line={"color": color, "width": width},
                    hovertemplate="%{x}:00 h<br>%{y:.1f} %<extra>" + label + "</extra>",
                ),
                row=row,
                col=col,
            )
    _layout(fig, "Perfil horario: % de la actividad diaria en cada hora", 900, 900, legend=True)
    fig.update_xaxes(tickvals=[0, 6, 12, 18, 23], range=[0, 23], tickfont_size=10)
    fig.update_yaxes(rangemode="tozero", ticksuffix=" %", tickfont_size=10)
    return fig


def study_mix(result: StudyResult) -> go.Figure:
    """Barras apiladas al 100 %: reparto SMS / llamadas / internet por celda."""
    city = result.media_ciudad
    rows = [("Media ciudad", city["media_sms"], city["media_llamadas"], city["media_internet"], city["media_total"])]
    rows += [
        (cell_label(c), c.totales["sms"], c.totales["llamadas"], c.totales["internet"], c.totales["total"])
        for c in result.cells
    ]
    labels = [r[0] for r in rows]
    fig = go.Figure()
    for i, (key, color) in enumerate(zip(ACTIVITY_LABELS, SERIES, strict=True)):
        shares = [100 * r[1 + i] / r[4] for r in rows]
        fig.add_trace(
            go.Bar(
                y=labels,
                x=shares,
                orientation="h",
                name=ACTIVITY_LABELS[key],
                marker={"color": color, "line": {"color": SURFACE, "width": 2}},
                text=[f"{s:.0f} %" if s >= 7 else "" for s in shares],
                textposition="inside",
                insidetextanchor="middle",
                textfont={"color": "white", "size": 11},
                hovertemplate="%{y}<br>%{x:.1f} %<extra>" + ACTIVITY_LABELS[key] + "</extra>",
            )
        )
    _layout(fig, "Reparto de la actividad por tipo", 860, 460, legend=True, l=200)
    fig.update_layout(barmode="stack", bargap=0.35, legend_traceorder="normal")
    fig.update_xaxes(range=[0, 100], ticksuffix=" %")
    fig.update_yaxes(autorange="reversed", showgrid=False, ticks="")
    return fig


def study_volume(result: StudyResult) -> go.Figure:
    """Barras horizontales: actividad total de cada celda en veces la media."""
    cells = sorted(result.cells, key=lambda c: c.metricas["veces_media"], reverse=True)
    values = [c.metricas["veces_media"] for c in cells]
    lo, hi = math.floor(math.log10(min(values))), math.ceil(math.log10(max(values)))
    ticks = [10.0**e for e in range(lo, hi + 1)]
    fig = go.Figure(
        go.Bar(
            y=[cell_label(c) for c in cells],
            x=values,
            orientation="h",
            marker={"color": SERIES[0]},
            text=[f"{_num(v)}×" for v in values],
            textposition="outside",
            textfont={"color": INK, "size": 11},
            cliponaxis=False,
            hovertemplate="%{y}<br>%{x:.3g} × la celda media<extra></extra>",
        )
    )
    fig.add_vline(x=1, line={"color": INK_2, "width": 1})
    _layout(fig, "Actividad total semanal respecto a la celda media (escala log)", 860, 420, l=200, r=48)
    fig.update_layout(bargap=0.4, barcornerradius=4)
    fig.update_xaxes(
        type="log",
        tickvals=ticks,
        ticktext=[f"{_num(t, 3)}×" for t in ticks],
        title_text="Veces la actividad de la celda media de la ciudad (1× = media)",
    )
    fig.update_yaxes(autorange="reversed", showgrid=False, ticks="")
    return fig


def study_daily_heatmap(result: StudyResult) -> go.Figure:
    """Mapa de calor celda x día: actividad diaria / media de laborables."""
    matrix = []
    for cell in result.cells:
        by_day = {d["_id"]["dia_semana"]: d["total"] for d in cell.diario}
        workday_mean = np.mean([by_day[d] for d in range(1, 6)])
        matrix.append([by_day[d] / workday_mean for d in range(1, 8)])
    data = np.array(matrix)
    log_data = np.log2(data)
    span = max(float(np.abs(log_data).max()), 0.1)
    ticks = [t for t in (-2, -1, 0, 1, 2) if abs(t) <= span]
    columns = [f"{n}<br>{d}" for n, d in zip(DAY_NAMES, range(2, 9), strict=True)]
    fig = go.Figure(
        go.Heatmap(
            z=log_data,
            x=columns,
            y=[cell_label(c) for c in result.cells],
            customdata=data,
            text=[[f"{v:.2f}".replace(".", ",") for v in row] for row in data],
            texttemplate="%{text}",
            textfont={"color": INK, "size": 11},
            colorscale=[[i / (len(DIVERGING) - 1), c] for i, c in enumerate(DIVERGING)],
            zmid=0,
            zmin=-span,
            zmax=span,
            xgap=2,
            ygap=2,
            hovertemplate="%{y} · %{x}<br>%{customdata:.2f} × un laborable medio<extra></extra>",
            colorbar={
                "tickvals": ticks,
                "ticktext": [f"{_num(2.0**t)}×" for t in ticks],
                "outlinewidth": 0,
                "thickness": 14,
            },
        )
    )
    _layout(fig, "Actividad diaria / media de lunes a viernes (dic 2013)", 860, 460, l=200)
    fig.update_xaxes(showgrid=False, showline=False, ticks="", side="bottom")
    fig.update_yaxes(showgrid=False, showline=False, ticks="", autorange="reversed")
    return fig


#: Nombre de fichero (sin extensión) de cada figura.
FILE_NAMES = {
    "mapa": "mapa_celdas",
    "ciudad": "serie_ciudad",
    "volumen": "volumen_celdas",
    "mezcla": "mezcla_actividad",
    "perfiles": "perfiles_horarios",
    "series": "series_semanales",
    "diario": "mapa_calor_diario",
}


def study_figures(result: StudyResult, cell_docs: Sequence[dict[str, Any]]) -> dict[str, go.Figure]:
    """Construye todas las figuras del apartado 8, por nombre."""
    highlight = {c.cellid: c.nombre for c in result.cells}
    return {
        "mapa": grid_map(cell_docs, highlight),
        "ciudad": city_series(result.serie_ciudad),
        "volumen": study_volume(result),
        "mezcla": study_mix(result),
        "perfiles": study_profiles(result),
        "series": study_series(result),
        "diario": study_daily_heatmap(result),
    }


def save_figures(figures: Mapping[str, go.Figure], out_dir: Path) -> dict[str, Path]:
    """Guarda cada figura como PNG (doble resolución) y como HTML interactivo.

    Los PNG se exportan juntos para reutilizar una única sesión de kaleido
    (un Chrome sin interfaz). Devuelve las rutas PNG por nombre.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {name: out_dir / f"{FILE_NAMES.get(name, name)}.png" for name in figures}
    figs: list[dict | go.Figure] = list(figures.values())
    files: list[str | Path] = list(paths.values())
    # write_images no toma el tamaño del layout de cada figura: se pasa explícito.
    pio.write_images(
        figs,
        files,
        scale=2,
        width=[f.layout.width for f in figures.values()],
        height=[f.layout.height for f in figures.values()],
    )
    for name, fig in figures.items():
        fig.write_html(
            paths[name].with_suffix(".html"), include_plotlyjs="cdn", config={"displaylogo": False, "responsive": True}
        )
    return paths


def all_study_figures(result: StudyResult, cell_docs: Sequence[dict[str, Any]], out_dir: Path) -> dict[str, Path]:
    """Genera y guarda todas las figuras; devuelve las rutas PNG por nombre."""
    return save_figures(study_figures(result, cell_docs), out_dir)
