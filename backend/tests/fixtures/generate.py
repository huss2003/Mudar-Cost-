#!/usr/bin/env python3
"""Generate test fixture files: sample DXF floor plan and sample PDF floor plan.

Usage:
    python tests/fixtures/generate.py

Output:
    tests/fixtures/sample_floor_plan.dxf
    tests/fixtures/sample_floor_plan.pdf
"""
import math
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent


def make_dxf(path: Path) -> None:
    """Create a simple floor plan DXF with walls, door, window, room label."""
    try:
        import ezdxf
    except ImportError:
        print("⚠  ezdxf not installed — skipping DXF fixture")
        return

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # millimetres
    msp = doc.modelspace()

    # ── Outer walls (10m × 8m rectangle, wall thickness 200mm) ────────
    # Bottom wall: (0,0) to (10000,0)
    msp.add_line((0, 0), (10000, 0), dxfattribs={"layer": "A-WALL", "color": 3})
    # Top wall: (0,8000) to (10000,8000)
    msp.add_line((0, 8000), (10000, 8000), dxfattribs={"layer": "A-WALL", "color": 3})
    # Left wall: (0,0) to (0,8000)
    msp.add_line((0, 0), (0, 8000), dxfattribs={"layer": "A-WALL", "color": 3})
    # Right wall: (10000,0) to (10000,8000)
    msp.add_line((10000, 0), (10000, 8000), dxfattribs={"layer": "A-WALL", "color": 3})

    # ── Internal partition (divides into 2 rooms) ─────────────────────
    # Vertical partition at x=5000, from y=0 to y=8000
    msp.add_line((5000, 0), (5000, 8000), dxfattribs={"layer": "A-PART", "color": 4})

    # ── Door block (on bottom wall, between x=3000 and x=4200) ────────
    # Door opening represented by a BlockReference
    door_block = doc.blocks.new("DOOR-900")  # 900mm door
    # Arc for door swing (radius 900, from 0 to 90 degrees)
    door_block.add_arc((0, 0), 900, 0, 90, dxfattribs={"layer": "A-DOOR", "color": 1})
    # Door leaf line
    door_block.add_line((0, 0), (0, 900), dxfattribs={"layer": "A-DOOR", "color": 1})
    msp.add_blockref("DOOR-900", (3000, 0), dxfattribs={"layer": "A-DOOR"})

    # ── Window block (on right wall, between y=2000 and y=4000) ───────
    win_block = doc.blocks.new("WIN-2000")  # 2000mm window
    win_block.add_line((0, 0), (2000, 0), dxfattribs={"layer": "A-WINDOW", "color": 5})
    win_block.add_line((0, 100), (2000, 100), dxfattribs={"layer": "A-WINDOW", "color": 5})
    msp.add_blockref("WIN-2000", (10000, 2000), dxfattribs={"layer": "A-WINDOW"})

    # ── Furniture blocks ──────────────────────────────────────────────
    desk_block = doc.blocks.new("DESK-1500")
    desk_block.add_lwpolyline(
        [(0, 0), (1500, 0), (1500, 750), (0, 750), (0, 0)],
        dxfattribs={"layer": "A-FURN", "color": 6},
    )
    msp.add_blockref("DESK-1500", (1500, 1000), dxfattribs={"layer": "A-FURN"})
    msp.add_blockref("DESK-1500", (6500, 4500), dxfattribs={"layer": "A-FURN"})

    # ── Room labels ───────────────────────────────────────────────────
    msp.add_text(
        "Office Area",
        dxfattribs={
            "layer": "A-TEXT",
            "height": 400,
            "insert": (2500, 5000),
        },
    )
    msp.add_text(
        "Conference Room",
        dxfattribs={
            "layer": "A-TEXT",
            "height": 400,
            "insert": (7500, 2000),
        },
    )

    # ── Dimension lines ───────────────────────────────────────────────
    msp.add_text("10000", dxfattribs={"layer": "A-DIMS", "height": 250, "insert": (5000, -500)})
    msp.add_text("8000", dxfattribs={"layer": "A-DIMS", "height": 250, "insert": (-800, 4000)})

    doc.saveas(path)
    print(f"  ✓ DXF fixture: {path} ({path.stat().st_size} bytes)")


def make_pdf(path: Path) -> None:
    """Create a simple floor plan PDF using reportlab or fpdf2."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        print("⚠  reportlab not installed — trying fpdf2")
        try:
            from fpdf import FPDF

            pdf = FPDF(orientation="L", unit="mm", format="A4")
            pdf.add_page()
            # Draw outer walls
            pdf.set_line_width(1.5)
            pdf.set_draw_color(0, 100, 0)
            pdf.rect(20, 20, 200, 160)  # 200mm x 160mm representing 10m x 8m
            # Internal partition
            pdf.set_draw_color(0, 0, 150)
            pdf.line(120, 20, 120, 180)
            # Door gap marking
            pdf.set_fill_color(200, 200, 200)
            pdf.rect(80, 20, 30, 10, style="F")
            # Window marking
            pdf.set_fill_color(200, 230, 255)
            pdf.rect(220, 60, 10, 40, style="F")
            # Text labels
            pdf.set_font("Helvetica", size=12)
            pdf.text(50, 120, "Office Area")
            pdf.text(140, 80, "Conference")
            pdf.text(143, 92, "Room")
            # Dimension labels
            pdf.set_font("Helvetica", size=8)
            pdf.text(100, 15, "10000 mm")
            pdf.text(5, 100, "8000 mm")
            pdf.output(str(path))
            print(f"  ✓ PDF fixture (fpdf2): {path} ({path.stat().st_size} bytes)")
            return
        except ImportError:
            print("⚠  fpdf2 not installed either — skipping PDF fixture")
            return

    # reportlab path
    c = canvas.Canvas(str(path), pagesize=A4)
    c.setStrokeColor(colors.green)
    c.setLineWidth(1.5)
    # Outer walls: A4 landscape = 297x210mm, scale factor 0.02 (10m → 200mm)
    c.rect(48, 25, 200, 160)
    # Internal partition
    c.setStrokeColor(colors.blue)
    c.line(148, 25, 148, 185)
    # Door indicator
    c.setFillColor(colors.lightgrey)
    c.rect(100, 25, 30, 10, fill=1, stroke=0)
    c.setStrokeColor(colors.red)
    c.rect(100, 25, 30, 10)
    # Window indicator
    c.setFillColor(colors.lightblue)
    c.rect(248, 60, 10, 40, fill=1, stroke=0)
    # Room labels
    c.setFont("Helvetica", 14)
    c.drawString(80, 130, "Office Area")
    c.drawString(175, 90, "Conference")
    c.drawString(175, 78, "Room")
    # Dimensions
    c.setFont("Helvetica", 8)
    c.drawString(130, 15, "10000 mm")
    c.drawString(15, 100, "8000 mm")
    c.save()
    print(f"  ✓ PDF fixture (reportlab): {path} ({path.stat().st_size} bytes)")


def main():
    print("Generating fixture files…")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    make_dxf(FIXTURES / "sample_floor_plan.dxf")
    make_pdf(FIXTURES / "sample_floor_plan.pdf")
    print("Done.")


if __name__ == "__main__":
    main()
