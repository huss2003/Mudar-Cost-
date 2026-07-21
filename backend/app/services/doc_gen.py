"""RFQ and Purchase Order document generation service.

Generates formatted PDF documents using reportlab:
- RFQ (Request For Quotation) grouped by vendor
- Purchase Order per vendor
- Simple Gantt chart (SVG) from productivity data
"""
from __future__ import annotations

import io
import logging
import math
from datetime import datetime, timedelta
from typing import Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable,
)

logger = logging.getLogger(__name__)

# ── RFQ Generation ───────────────────────────────────────────────────


def generate_rfq(
    vendor_name: str,
    vendor_address: str,
    vendor_gst: str,
    items: list[dict],
    project_name: str,
    project_ref: str,
    rfq_number: str | None = None,
) -> bytes:
    """Generate an RFQ PDF as bytes.

    Each item dict: {description, quantity, unit, material_code?}
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []

    rfq_no = rfq_number or f"RFQ-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Header
    elements.append(Paragraph(
        f"<b>REQUEST FOR QUOTATION</b>", styles["Title"]))
    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph(f"RFQ No: {rfq_no}", styles["Normal"]))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d-%b-%Y')}", styles["Normal"]))
    elements.append(Spacer(1, 4*mm))

    # Vendor details
    elements.append(Paragraph(f"<b>To:</b>", styles["Normal"]))
    elements.append(Paragraph(vendor_name, styles["Normal"]))
    if vendor_address:
        elements.append(Paragraph(vendor_address, styles["Normal"]))
    if vendor_gst:
        elements.append(Paragraph(f"GST: {vendor_gst}", styles["Normal"]))
    elements.append(Spacer(1, 4*mm))

    # Project reference
    elements.append(Paragraph(f"<b>Project:</b> {project_name}", styles["Normal"]))
    elements.append(Paragraph(f"Ref: {project_ref}", styles["Normal"]))
    elements.append(Spacer(1, 6*mm))

    # Items table
    elements.append(Paragraph("<b>Please quote the following items:</b>", styles["Normal"]))
    elements.append(Spacer(1, 3*mm))

    table_data = [["#", "Description", "Qty", "Unit", "Rate", "Amount"]]
    for i, item in enumerate(items, 1):
        table_data.append([
            str(i),
            item.get("description", ""),
            f"{item.get('quantity', 0):.2f}",
            item.get("unit", "nos"),
            "_____",
            "_____",
        ])

    col_widths = [20, 280, 50, 40, 60, 60]
    table = Table(table_data, colWidths=[w*mm for w in [6, 75, 12, 10, 16, 16]])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 8*mm))

    # Terms
    elements.append(Paragraph("<b>Terms:</b>", styles["Normal"]))
    elements.append(Paragraph("1. Prices to include GST as applicable.", styles["Normal"]))
    elements.append(Paragraph("2. Delivery to site address as above.", styles["Normal"]))
    elements.append(Paragraph("3. Validity: 15 days from date of this RFQ.", styles["Normal"]))
    elements.append(Paragraph("4. Payment: As per company policy.", styles["Normal"]))
    elements.append(Spacer(1, 10*mm))

    # Signature
    elements.append(Paragraph("Authorised Signatory", styles["Normal"]))
    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph("_________________________", styles["Normal"]))

    doc.build(elements)
    return buf.getvalue()


# ── Purchase Order Generation ────────────────────────────────────────


def generate_purchase_order(
    vendor_name: str,
    vendor_address: str,
    vendor_gst: str,
    items: list[dict],
    project_name: str,
    project_ref: str,
    po_number: str | None = None,
    delivery_date: str | None = None,
) -> bytes:
    """Generate a Purchase Order PDF as bytes.

    Each item dict: {description, quantity, unit, rate, amount, gst_rate?}
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []

    po_no = po_number or f"PO-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Header
    elements.append(Paragraph(
        "<b>PURCHASE ORDER</b>", styles["Title"]))
    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph(f"PO No: {po_no}", styles["Normal"]))
    elements.append(Paragraph(f"Date: {datetime.now().strftime('%d-%b-%Y')}", styles["Normal"]))
    if delivery_date:
        elements.append(Paragraph(f"Required Delivery: {delivery_date}", styles["Normal"]))
    elements.append(Spacer(1, 4*mm))

    # Vendor
    elements.append(Paragraph(f"<b>Vendor:</b> {vendor_name}", styles["Normal"]))
    if vendor_address:
        elements.append(Paragraph(vendor_address, styles["Normal"]))
    if vendor_gst:
        elements.append(Paragraph(f"GSTIN: {vendor_gst}", styles["Normal"]))
    elements.append(Spacer(1, 4*mm))

    # Project
    elements.append(Paragraph(f"<b>Project:</b> {project_name}", styles["Normal"]))
    elements.append(Paragraph(f"Ref: {project_ref}", styles["Normal"]))
    elements.append(Spacer(1, 6*mm))

    # Items table
    table_data = [["#", "Description", "Qty", "Unit", "Rate", "Amount"]]
    subtotal = 0.0
    for i, item in enumerate(items, 1):
        qty = item.get("quantity", 0)
        rate = item.get("rate", 0)
        amount = item.get("amount", qty * rate)
        subtotal += amount
        table_data.append([
            str(i),
            item.get("description", ""),
            f"{qty:.2f}",
            item.get("unit", "nos"),
            f"₹{rate:.2f}",
            f"₹{amount:.2f}",
        ])

    col_widths = [20, 280, 50, 40, 60, 60]
    table = Table(table_data, colWidths=[w*mm for w in [6, 75, 12, 10, 16, 16]])
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(table)

    # Totals
    gst = subtotal * 0.18
    grand_total = subtotal + gst
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(f"Subtotal: ₹{subtotal:,.2f}", styles["Normal"]))
    elements.append(Paragraph(f"GST @ 18%: ₹{gst:,.2f}", styles["Normal"]))
    elements.append(Paragraph(
        f"<b>Grand Total: ₹{grand_total:,.2f}</b>", styles["Normal"]))
    elements.append(Spacer(1, 8*mm))

    # Terms
    elements.append(Paragraph("<b>Terms & Conditions:</b>", styles["Normal"]))
    elements.append(Paragraph("1. Delivery as per schedule agreed.", styles["Normal"]))
    elements.append(Paragraph("2. Payment: 30 days from invoice.", styles["Normal"]))
    elements.append(Paragraph("3. GST invoice to be raised on delivery.", styles["Normal"]))
    elements.append(Paragraph("4. This PO is not transferable.", styles["Normal"]))
    elements.append(Spacer(1, 10*mm))

    elements.append(Paragraph("Authorised Signatory", styles["Normal"]))
    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph("_________________________", styles["Normal"]))

    doc.build(elements)
    return buf.getvalue()


# ── Simple Gantt Chart (SVG) ────────────────────────────────────────


def generate_gantt_svg(
    tasks: list[dict],
    title: str = "Project Schedule",
    start_date: str | None = None,
) -> str:
    """Generate a simple Gantt chart as an SVG string.

    Each task dict: {trade, label, duration_days, start_day?}
    """
    if not tasks:
        return "<svg></svg>"

    svg_width = 800
    svg_height = max(100, len(tasks) * 35 + 60)
    bar_height = 20
    row_height = 35
    label_width = 200
    chart_left = label_width + 20
    chart_width = svg_width - chart_left - 20

    # Find max duration to scale
    max_days = max(t.get("duration_days", 1) for t in tasks)
    day_width = chart_width / max_days if max_days > 0 else chart_width

    # Colors for different trades
    trade_colors = {
        "civil": "#8B4513", "structure": "#A0522D",
        "partition": "#4682B4", "gypsum": "#4682B4",
        "flooring": "#2E8B57", "painting": "#DAA520",
        "glass": "#87CEEB", "furniture": "#D2691E",
        "electrical": "#FFD700", "hvac": "#DC143C",
        "plumbing": "#4169E1", "data": "#9932CC",
        "waterproofing": "#20B2AA", "steel": "#708090",
        "fire_fighting": "#FF6347", "signages": "#FF69B4",
        "labour": "#BEBEBE",
    }

    lines = []
    lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{svg_width}" height="{svg_height}">')
    lines.append(f'  <text x="20" y="30" font-family="Arial" font-size="16" font-weight="bold">{title}</text>')

    # Draw grid lines
    for day in range(0, max_days + 1, max(1, max_days // 10)):
        x = chart_left + day * day_width
        lines.append(f'  <line x1="{x}" y1="45" x2="{x}" y2="{svg_height}" stroke="#eee" stroke-width="1"/>')
        lines.append(f'  <text x="{x}" y="{svg_height - 5}" font-family="Arial" font-size="8" text-anchor="middle">{day}d</text>')

    for i, task in enumerate(tasks):
        y = 50 + i * row_height
        label = task.get("label", task.get("trade", "unknown"))
        duration = task.get("duration_days", 1)
        start = task.get("start_day", 0)
        trade = task.get("trade", "")
        color = trade_colors.get(trade, "#666")

        # Label
        lines.append(f'  <text x="10" y="{y + bar_height - 5}" font-family="Arial" font-size="11" '
                     f'text-anchor="start">{label}</text>')

        # Bar
        bar_x = chart_left + start * day_width
        bar_w = duration * day_width
        lines.append(f'  <rect x="{bar_x}" y="{y}" width="{bar_w}" height="{bar_height}" '
                     f'rx="3" ry="3" fill="{color}" opacity="0.8"/>')

        # Duration text on bar
        if bar_w > 30:
            lines.append(f'  <text x="{bar_x + bar_w / 2}" y="{y + bar_height - 5}" '
                         f'font-family="Arial" font-size="9" fill="white" text-anchor="middle">'
                         f'{duration}d</text>')

    lines.append("</svg>")
    return "\n".join(lines)
