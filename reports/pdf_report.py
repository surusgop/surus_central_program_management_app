"""Generate a two-section (YTD + Prior Week) PDF report for the Contacts page."""

from __future__ import annotations

import io
from datetime import date

import matplotlib
matplotlib.use("Agg")  # non-interactive backend — must be set before pyplot import
import matplotlib.pyplot as plt

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable, Image, PageBreak, Paragraph,
    SimpleDocTemplate, Spacer, Table, TableStyle,
)

# ── Brand colours ─────────────────────────────────────────────────────────────
BRAND_RED  = colors.HexColor("#C1272D")
BRAND_DARK = colors.HexColor("#2A313C")
BRAND_GRAY = colors.HexColor("#75859E")
CARD_BG    = colors.HexColor("#F8F9FA")
BORDER     = colors.HexColor("#DEE2E6")

CHART_COLORS = ["#C1272D", "#2A313C", "#75859E", "#E8A020", "#5B8FA8", "#8B4A6E", "#6B7A8D"]

# ── Paragraph styles ──────────────────────────────────────────────────────────
_base = ParagraphStyle("base", fontName="Helvetica", fontSize=10, leading=14, textColor=BRAND_DARK)

_S = {
    "title":    ParagraphStyle("title",    parent=_base, fontSize=20, fontName="Helvetica-Bold", textColor=BRAND_RED,  spaceAfter=6),
    "subtitle": ParagraphStyle("subtitle", parent=_base, fontSize=12, textColor=BRAND_DARK,       spaceAfter=2),
    "meta":     ParagraphStyle("meta",     parent=_base, fontSize=9,  textColor=BRAND_GRAY,       spaceAfter=2),
    "section":  ParagraphStyle("section",  parent=_base, fontSize=13, fontName="Helvetica-Bold", textColor=BRAND_DARK, spaceBefore=10, spaceAfter=6),
    "kpi_val":  ParagraphStyle("kpi_val",  parent=_base, fontSize=22, fontName="Helvetica-Bold", textColor=BRAND_RED,  alignment=TA_CENTER, leading=26),
    "kpi_lbl":  ParagraphStyle("kpi_lbl",  parent=_base, fontSize=8,  textColor=BRAND_GRAY,       alignment=TA_CENTER, leading=10, spaceAfter=4),
}


def _fmt_date(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def _pie_to_image(fig, title: str, width_in: float, height_in: float) -> Image:
    """Render a Plotly Pie figure as a matplotlib donut chart via PNG bytes."""
    dpi = 150
    fig_mpl, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
    fig_mpl.patch.set_facecolor("white")

    has_data = fig.data and hasattr(fig.data[0], "labels") and fig.data[0].values is not None and len(fig.data[0].values) > 0

    if has_data:
        trace   = fig.data[0]
        labels  = list(trace.labels)
        values  = list(trace.values)
        clrs    = list(trace.marker.colors) if (trace.marker and trace.marker.colors) else CHART_COLORS[:len(labels)]

        wedges, _ = ax.pie(
            values,
            labels=None,
            colors=clrs,
            startangle=90,
            wedgeprops={"width": 0.55},  # donut hole
        )

        total = sum(values)
        legend_labels = [f"{l}  {v / total * 100:.1f}%" for l, v in zip(labels, values)]
        ax.legend(
            wedges, legend_labels,
            loc="center left",
            bbox_to_anchor=(0.95, 0.5),
            fontsize=7,
            frameon=False,
        )
    else:
        ax.text(0.5, 0.5, "No data", ha="center", va="center",
                transform=ax.transAxes, color="#75859E", fontsize=10)
        ax.axis("off")

    ax.set_title(title, fontsize=10, color="#2A313C", pad=8, fontweight="bold")

    buf = io.BytesIO()
    fig_mpl.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig_mpl)
    buf.seek(0)

    return Image(buf, width=width_in * inch, height=height_in * inch)


def _kpi_grid(kpis: list[tuple[str, str]]) -> Table:
    """3-column KPI card grid from (label, value) pairs."""
    padded = list(kpis) + [("", "")] * ((3 - len(kpis) % 3) % 3)
    data = []
    for i in range(0, len(padded), 3):
        row = []
        for label, value in padded[i:i + 3]:
            row.append([
                Paragraph(value if value else "—", _S["kpi_val"]),
                Paragraph(label,                    _S["kpi_lbl"]),
            ])
        data.append(row)

    col_w = (7.0 * inch) / 3
    t = Table(data, colWidths=[col_w] * 3)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), CARD_BG),
        ("BOX",           (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
    ]))
    return t


def _section_flowables(heading: str, kpis: list[tuple[str, str]], fig_type, fig_freq) -> list:
    chart_w, chart_h = 3.3, 2.6
    chart_table = Table(
        [[
            _pie_to_image(fig_type, "Contact Type Breakdown", chart_w, chart_h),
            _pie_to_image(fig_freq, "Contacts by Frequency",  chart_w, chart_h),
        ]],
        colWidths=[chart_w * inch, chart_w * inch],
    )
    chart_table.setStyle(TableStyle([
        ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return [
        Paragraph(heading, _S["section"]),
        HRFlowable(width="100%", thickness=1, color=BORDER, spaceAfter=8),
        _kpi_grid(kpis),
        Spacer(1, 0.2 * inch),
        chart_table,
    ]


def build_report(
    pw_heading:   str,
    pw_kpis:      list[tuple[str, str]],
    pw_fig_type,
    pw_fig_freq,
    pm_heading:   str,
    pm_kpis:      list[tuple[str, str]],
    pm_fig_type,
    pm_fig_freq,
    ytd_heading:  str,
    ytd_kpis:     list[tuple[str, str]],
    ytd_fig_type,
    ytd_fig_freq,
    filter_context: str,
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        topMargin=0.75 * inch,  bottomMargin=0.75 * inch,
    )

    today = date.today()
    story = [
        Paragraph("Surus Central Program Management", _S["title"]),
        Paragraph("Contact Summary Report",    _S["subtitle"]),
        Paragraph(f"Filters: {filter_context}", _S["meta"]),
        Paragraph(f"Generated: {_fmt_date(today)}", _S["meta"]),
        HRFlowable(width="100%", thickness=1.5, color=BRAND_RED, spaceAfter=12),
        *_section_flowables(pw_heading,  pw_kpis,  pw_fig_type,  pw_fig_freq),
        PageBreak(),
        *_section_flowables(pm_heading,  pm_kpis,  pm_fig_type,  pm_fig_freq),
        PageBreak(),
        *_section_flowables(ytd_heading, ytd_kpis, ytd_fig_type, ytd_fig_freq),
    ]

    doc.build(story)
    return buf.getvalue()
