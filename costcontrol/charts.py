"""Gráficos SVG en línea (sin dependencias externas, adaptados a claro/oscuro).

Se usan tonos de una sola serie (azul) porque el trabajo de estos gráficos es
representar *magnitud* de una medida (coste) por categoría o por mes. Los
colores se toman por rol vía clases CSS, de modo que el tema claro/oscuro se
resuelve en la hoja de estilos.
"""

from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import List, Sequence, Tuple


def _eur(v) -> str:
    try:
        d = Decimal(str(v or 0))
    except Exception:
        return str(v)
    s = f"{d:,.0f}".replace(",", ".")
    return f"{s} €"


def barras_horizontales(datos: Sequence[Tuple[str, float]], *, alto_barra: int = 26,
                        ancho: int = 520, mostrar_valor: bool = True) -> str:
    """datos = [(etiqueta, valor), ...] ya ordenados. Devuelve un <svg> string."""
    datos = [(str(l), float(v or 0)) for l, v in datos]
    if not datos:
        return '<p class="empty">Sin datos.</p>'
    maxv = max((v for _, v in datos), default=0) or 1
    label_w = 130
    val_w = 92 if mostrar_valor else 8
    bar_area = ancho - label_w - val_w
    gap = 12
    alto = len(datos) * (alto_barra + gap) + gap
    rows = []
    y = gap
    for label, v in datos:
        w = max(2, bar_area * (v / maxv))
        cy = y + alto_barra / 2
        rows.append(
            f'<text x="{label_w - 8}" y="{cy + 4}" text-anchor="end" '
            f'class="chart-label" font-size="12.5">{escape(label[:20])}</text>'
            f'<rect x="{label_w}" y="{y}" width="{w:.1f}" height="{alto_barra}" '
            f'rx="4" class="chart-bar"></rect>'
        )
        if mostrar_valor:
            rows.append(
                f'<text x="{label_w + w + 8:.1f}" y="{cy + 4}" class="chart-value" '
                f'font-size="12.5">{_eur(v)}</text>'
            )
        y += alto_barra + gap
    return (
        f'<svg viewBox="0 0 {ancho} {alto}" width="100%" role="img" '
        f'class="chart" preserveAspectRatio="xMinYMin meet">{"".join(rows)}</svg>'
    )


def barras_verticales(datos: Sequence[Tuple[str, float]], *, ancho: int = 560,
                      alto: int = 200) -> str:
    """Evolución por periodo. datos = [(etiqueta_mes, valor), ...]."""
    datos = [(str(l), float(v or 0)) for l, v in datos]
    if not datos:
        return '<p class="empty">Sin datos.</p>'
    maxv = max((v for _, v in datos), default=0) or 1
    pad_b, pad_t, pad_l = 26, 18, 10
    plot_h = alto - pad_b - pad_t
    n = len(datos)
    slot = (ancho - pad_l * 2) / n
    bw = min(46, slot * 0.6)
    marks = []
    for i, (label, v) in enumerate(datos):
        h = max(2, plot_h * (v / maxv))
        x = pad_l + slot * i + (slot - bw) / 2
        yb = pad_t + (plot_h - h)
        marks.append(
            f'<rect x="{x:.1f}" y="{yb:.1f}" width="{bw:.1f}" height="{h:.1f}" '
            f'rx="4" class="chart-bar"><title>{escape(label)}: {_eur(v)}</title></rect>'
            f'<text x="{x + bw/2:.1f}" y="{alto - 9}" text-anchor="middle" '
            f'class="chart-label" font-size="11.5">{escape(label)}</text>'
            f'<text x="{x + bw/2:.1f}" y="{yb - 5:.1f}" text-anchor="middle" '
            f'class="chart-value" font-size="10.5">{_eur(v)}</text>'
        )
    return (
        f'<svg viewBox="0 0 {ancho} {alto}" width="100%" role="img" '
        f'class="chart chart-vert" style="max-height:260px" '
        f'preserveAspectRatio="xMidYMin meet">{"".join(marks)}</svg>'
    )


def barras_comparativa(datos, *, ancho: int = 680, alto: int = 230) -> str:
    """Comparativa por mes de dos ejercicios. datos = [(mes, año_anterior, año_actual), ...].

    El año anterior se dibuja en gris (referencia) y el actual en verde.
    """
    datos = [(str(l), float(a or 0), float(b or 0)) for l, a, b in datos]
    if not datos:
        return '<p class="empty">Sin datos.</p>'
    maxv = max((max(a, b) for _, a, b in datos), default=0) or 1
    pad_b, pad_t, pad_l = 24, 14, 8
    plot_h = alto - pad_b - pad_t
    n = len(datos)
    slot = (ancho - pad_l * 2) / n
    bw = min(18, slot * 0.32)
    gap = 3
    marks = []
    for i, (label, ant, act) in enumerate(datos):
        x0 = pad_l + slot * i + (slot - (bw * 2 + gap)) / 2
        for j, (val, cls) in enumerate([(ant, "chart-bar-prev"), (act, "chart-bar")]):
            h = max(0, plot_h * (val / maxv))
            x = x0 + j * (bw + gap)
            y = pad_t + (plot_h - h)
            marks.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                f'rx="3" class="{cls}"><title>{escape(label)}: {_eur(val)}</title></rect>')
        marks.append(
            f'<text x="{pad_l + slot*i + slot/2:.1f}" y="{alto-8}" text-anchor="middle" '
            f'class="chart-label" font-size="11">{escape(label)}</text>')
    return (
        f'<svg viewBox="0 0 {ancho} {alto}" width="100%" role="img" '
        f'class="chart chart-vert" style="max-height:250px" '
        f'preserveAspectRatio="xMidYMin meet">{"".join(marks)}</svg>'
    )
