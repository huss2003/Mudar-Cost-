"""Branded proposal template generation — Jasfo Design.

Generates a branded proposal PDF with cover page, project info, BOQ,
cost breakdown, material selections, and terms. Uses reportlab.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm, inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, Image, ListFlowable, ListItem,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY

logger = logging.getLogger(__name__)

# ── Brand constants ──────────────────────────────────────────────────
BRAND_COLOR = colors.HexColor("#1a237e")       # Deep indigo
ACCENT_COLOR = colors.HexColor("#ff6f00")       # Amber accent
BG_COLOR = colors.HexColor("#f5f5f5")
TEXT_COLOR = colors.HexColor("#212121")
MUTED_COLOR = colors.HexColor("#757575")
WHITE = colors.white

# ── Styles ───────────────────────────────────────────────────────────

styles = getSampleStyleSheet()

styles.add(ParagraphStyle(
    "CoverTitle", fontName="Helvetica-Bold", fontSize=28,
    textColor=BRAND_COLOR, alignment=TA_CENTER, spaceAfter=6*mm,
))
styles.add(ParagraphStyle(
    "CoverSubtitle", fontName="Helvetica", fontSize=14,
    textColor=MUTED_COLOR, alignment=TA_CENTER, spaceAfter=4*mm,
))
styles.add(ParagraphStyle(
    "SectionTitle", fontName="Helvetica-Bold", fontSize=16,
    textColor=BRAND_COLOR, spaceBefore=8*mm, spaceAfter=4*mm,
))
styles.add(ParagraphStyle(
    "SubSection", fontName="Helvetica-Bold", fontSize=12,
    textColor=TEXT_COLOR, spaceBefore=4*mm, spaceAfter=2*mm,
))
styles.add(ParagraphStyle(
    "Body", fontName="Helvetica", fontSize=10,
    textColor=TEXT_COLOR, leading=14, spaceAfter=2*mm,
))
styles.add(ParagraphStyle(
    "BodyBold", fontName="Helvetica-Bold", fontSize=10,
    textColor=TEXT_COLOR, leading=14, spaceAfter=2*mm,
))
styles.add(ParagraphStyle(
    "SmallText", fontName="Helvetica", fontSize=8,
    textColor=MUTED_COLOR, leading=10,
))
styles.add(ParagraphStyle(
    "Footer", fontName="Helvetica", fontSize=7,
    textColor=MUTED_COLOR, alignment=TA_CENTER,
))
styles.add(ParagraphStyle(
    "TermsText", fontName="Helvetica", fontSize=9,
    textColor=TEXT_COLOR, leading=13, spaceAfter=1*mm,
))

# ── Table styles ─────────────────────────────────────────────────────

BOQ_HEADER_STYLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), BRAND_COLOR),
    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, 0), 9),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 1), (-1, -1), 8),
    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
    ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f0f0")),
])


# ── Helper functions ─────────────────────────────────────────────────


def _make_table(data: list[list], col_widths: list[int] | None = None) -> Table:
    """Create a styled table from row data."""
    w = [w*mm for w in (col_widths or [50, 100, 20, 15, 25, 25])]
    t = Table(data, colWidths=w, repeatRows=1)
    t.setStyle(BOQ_HEADER_STYLE)
    return t


def _format_currency(value: float) -> str:
    """Format INR currency."""
    if value >= 1_00_000:
        return f"₹{value / 1_00_000:,.2f}L"
    return f"₹{value:,.0f}"


def _section(title: str) -> list:
    """Return elements for a section header + horizontal rule."""
    return [
        Paragraph(title, styles["SectionTitle"]),
        HRFlowable(width="100%", thickness=1, color=BRAND_COLOR),
        Spacer(1, 3*mm),
    ]


# ── Proposal Generator ───────────────────────────────────────────────


def generate_proposal(
    project_name: str,
    project_client: str,
    project_location: str,
    proposal_number: str,
    total_area: float,
    total_cost: float,
    estimated_duration: int,
    trades: list[dict],
    materials: list[dict],
    terms: list[str],
    company_logo_path: str | None = None,
) -> bytes:
    """Generate a branded Jasfo proposal PDF.

    Args:
        project_name: Project name
        project_client: Client name
        project_location: Project location
        proposal_number: Unique proposal reference
        total_area: Total floor area in sqm
        total_cost: Grand total cost
        estimated_duration: Duration in days
        trades: List of {trade, items: [{description, quantity, unit, rate, total}]}
        materials: List of {name, brand, quantity, unit}
        terms: List of terms and conditions
        company_logo_path: Optional path to company logo image
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=25*mm, bottomMargin=20*mm,
        leftMargin=20*mm, rightMargin=20*mm,
    )
    elements = []

    # ── Cover Page ───────────────────────────────────────────────────
    elements.append(Spacer(1, 40*mm))

    # Logo placeholder
    if company_logo_path:
        try:
            img = Image(company_logo_path, width=40*mm, height=15*mm)
            img.hAlign = TA_CENTER
            elements.append(img)
            elements.append(Spacer(1, 10*mm))
        except Exception:
            pass

    elements.append(Paragraph("JASFO DESIGN", styles["CoverTitle"]))
    elements.append(Paragraph("Interior Fit-Out & Execution", styles["CoverSubtitle"]))
    elements.append(Spacer(1, 15*mm))
    elements.append(Paragraph("PROJECT PROPOSAL", styles["CoverTitle"]))
    elements.append(Spacer(1, 5*mm))

    # Project info box
    info_data = [
        ["Project:", project_name],
        ["Client:", project_client],
        ["Location:", project_location],
        ["Proposal No:", proposal_number],
        ["Date:", datetime.now().strftime("%d %B %Y")],
    ]
    info_table = Table(info_data, colWidths=[50*mm, 100*mm])
    info_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(info_table)

    elements.append(Spacer(1, 15*mm))
    elements.append(Paragraph(
        "Prepared by Jasfo Design · Confidential",
        styles["SmallText"],
    ))
    elements.append(PageBreak())

    # ── Executive Summary ────────────────────────────────────────────
    elements.extend(_section("1. Executive Summary"))
    elements.append(Paragraph(
        f"This proposal outlines the estimated cost and scope of work for the "
        f"interior fit-out of <b>{project_name}</b> located at {project_location}. "
        f"The estimate covers all civil, partition, flooring, ceiling, electrical, "
        f"HVAC, plumbing, and finishing works as per the provided drawings.",
        styles["Body"],
    ))
    elements.append(Spacer(1, 3*mm))

    summary_data = [
        ["Total Floor Area", f"{total_area:,.0f} sqm"],
        ["Estimated Cost", _format_currency(total_cost)],
        ["Estimated Duration", f"{estimated_duration} days"],
        ["Trades Included", f"{len(trades)}"],
        ["Proposal Validity", "15 days"],
    ]
    s_table = Table(summary_data, colWidths=[60*mm, 60*mm])
    s_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e0e0e0")),
        ("BACKGROUND", (0, 0), (-1, -1), BG_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    elements.append(s_table)
    elements.append(PageBreak())

    # ── Scope of Work ────────────────────────────────────────────────
    elements.extend(_section("2. Scope of Work"))
    trade_names = [t.get("trade", "Other").replace("_", " ").title() for t in trades]
    trade_items = [ListItem(Paragraph(f"<b>{tn}</b> — {len(t.get('items', []))} line items", styles["Body"]))
                   for tn, t in zip(trade_names, trades)]
    elements.append(ListFlowable(trade_items, bulletType="bullet"))
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph(
        f"Total detected objects: {sum(len(t.get('items', [])) for t in trades)} items across {len(trades)} trade categories.",
        styles["Body"],
    ))
    elements.append(PageBreak())

    # ── Bill of Quantities ───────────────────────────────────────────
    elements.extend(_section("3. Bill of Quantities"))

    for trade_group in trades:
        trade_name = trade_group.get("trade", "Other").replace("_", " ").title()
        items = trade_group.get("items", [])
        if not items:
            continue

        elements.append(Paragraph(trade_name, styles["SubSection"]))

        data = [["#", "Description", "Qty", "Unit", "Rate", "Total"]]
        trade_total = 0
        for i, item in enumerate(items, 1):
            qty = item.get("quantity", 0)
            rate = item.get("rate", 0)
            total = item.get("total", qty * rate)
            trade_total += total
            data.append([
                str(i), item.get("description", ""),
                f"{qty:.2f}", item.get("unit", "nos"),
                _format_currency(rate), _format_currency(total),
            ])
        data.append(["", "", "", "", "Trade Total", _format_currency(trade_total)])

        t = _make_table(data, [10, 80, 15, 12, 20, 20])
        elements.append(t)
        elements.append(Spacer(1, 4*mm))

    elements.append(PageBreak())

    # ── Cost Summary ─────────────────────────────────────────────────
    elements.extend(_section("4. Cost Summary"))

    total_materials = sum(
        item.get("quantity", 0) * item.get("rate", 0)
        for t in trades for item in t.get("items", [])
    )
    cost_data = [
        ["Total Material Cost", _format_currency(total_materials)],
        ["Labour", _format_currency(total_materials * 0.25)],
        ["Transport", _format_currency(total_materials * 0.05)],
        ["Overheads", _format_currency(total_materials * 0.10)],
        ["", ""],
        ["Grand Total", _format_currency(total_cost)],
        ["GST @18%", _format_currency(total_cost * 0.18)],
        ["Total with GST", _format_currency(total_cost * 1.18)],
    ]
    c_table = Table(cost_data, colWidths=[80*mm, 50*mm])
    c_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -2), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("GRID", (0, 0), (-1, -3), 0.5, colors.HexColor("#e0e0e0")),
        ("LINEBELOW", (0, -2), (-1, -2), 1, BRAND_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f0f0")),
    ]))
    elements.append(c_table)
    elements.append(PageBreak())

    # ── Material Highlights ──────────────────────────────────────────
    elements.extend(_section("5. Selected Materials"))

    mat_data = [["#", "Material", "Brand", "Qty", "Unit"]]
    for i, mat in enumerate(materials, 1):
        mat_data.append([
            str(i),
            mat.get("name", ""),
            mat.get("brand", ""),
            f"{mat.get('quantity', 0):.1f}",
            mat.get("unit", "nos"),
        ])
    t = _make_table(mat_data, [10, 70, 50, 20, 15])
    elements.append(t)
    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph(
        "Material rates are indicative and subject to change based on market conditions. "
        "Final pricing will be confirmed in the purchase order.",
        styles["SmallText"],
    ))
    elements.append(PageBreak())

    # ── Terms & Conditions ───────────────────────────────────────────
    elements.extend(_section("6. Terms & Conditions"))

    for term in terms:
        elements.append(Paragraph(f"• {term}", styles["TermsText"]))
    elements.append(Spacer(1, 5*mm))

    elements.append(Paragraph(
        "This proposal is valid for 15 days from the date above. "
        "Any work outside the scope described above will be billed separately. "
        "Payment terms: 50% advance, 40% on completion, 10% on handover.",
        styles["TermsText"],
    ))
    elements.append(Spacer(1, 15*mm))

    # Signature
    elements.append(Paragraph("Authorised Signatory", styles["BodyBold"]))
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph("_________________________", styles["Body"]))
    elements.append(Paragraph("Jasfo Design", styles["Body"]))

    # ── Build ────────────────────────────────────────────────────────
    doc.build(elements)
    return buf.getvalue()
