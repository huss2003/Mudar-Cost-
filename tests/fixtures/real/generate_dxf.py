#!/usr/bin/env python
"""Generate a representative DXF floor plan fixture with known objects.

Creates tests/fixtures/real/representative_floor_plan.dxf with:
  - 3 rooms of different sizes
  - 2 doors
  - 4 windows
  - Clean CAD layers (A-WALL, A-DOOR, A-GLAZ, A-ANNO-TEXT)
"""

from pathlib import Path

FIXTURES = Path(__file__).resolve().parent


def make_representative_dxf(path: Path) -> None:
    try:
        import ezdxf
    except ImportError:
        print("⚠  ezdxf not installed — skipping DXF fixture")
        return

    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4  # millimetres
    msp = doc.modelspace()

    # ── Overall building shell: 28' × 30' ≈ 8534 mm × 9144 mm ──────
    # Convert to mm: 1 ft = 304.8 mm
    # Room 1: 10'×12' = 3048×3658 (bottom-left)
    # Room 2: 8'×10' = 2438×3048 (bottom-right)
    # Room 3: 6'×8' = 1829×2438 (top-left)

    # Overall dimensions
    W = 8534   # overall width  (28 ft)
    H = 9144   # overall height (30 ft)

    # ── Outer walls (A-WALL layer, colour 3 = green) ────────────────
    wall_attrs = {"layer": "A-WALL", "color": 3}
    # Bottom
    msp.add_line((0, 0), (W, 0), dxfattribs=wall_attrs)
    # Top
    msp.add_line((0, H), (W, H), dxfattribs=wall_attrs)
    # Left
    msp.add_line((0, 0), (0, H), dxfattribs=wall_attrs)
    # Right
    msp.add_line((W, 0), (W, H), dxfattribs=wall_attrs)

    # ── Internal partitions ─────────────────────────────────────────
    part_attrs = {"layer": "A-WALL", "color": 4}
    # Vertical wall: separates rooms 1&3 (left) from room 2 (right)
    # x = 5486 (18 ft)
    msp.add_line((5486, 0), (5486, H), dxfattribs=part_attrs)

    # Horizontal wall: separates rooms 1 (bottom-left) from room 3 (top-left)
    # y = 5486 (18 ft)
    msp.add_line((0, 5486), (5486, 5486), dxfattribs=part_attrs)

    # ── Door 1: Room 1 entrance (bottom wall, A-DOOR layer) ────────
    door1_attrs = {"layer": "A-DOOR", "color": 1}
    door_block = doc.blocks.new("DOOR-900")  # 900 mm door
    door_block.add_arc((0, 0), 900, 0, 90, dxfattribs={"layer": "A-DOOR", "color": 1})
    door_block.add_line((0, 0), (0, 900), dxfattribs={"layer": "A-DOOR", "color": 1})
    msp.add_blockref("DOOR-900", (1500, 0), dxfattribs={"layer": "A-DOOR"})
    # Door opening indicator (gap in wall)
    msp.add_line((1500, -50), (1500, 50), dxfattribs={"layer": "A-DOOR", "color": 1})
    msp.add_line((2400, -50), (2400, 50), dxfattribs={"layer": "A-DOOR", "color": 1})
    # Arc swing
    msp.add_arc((1500, 0), 900, 0, 90, dxfattribs={"layer": "A-DOOR", "color": 1})

    # ── Door 2: Between Room 1 and Room 2 (vertical wall) ──────────
    msp.add_line((5486, 1500), (5536, 1500), dxfattribs={"layer": "A-DOOR", "color": 1})
    msp.add_line((5486, 2400), (5536, 2400), dxfattribs={"layer": "A-DOOR", "color": 1})
    msp.add_arc((5486, 1500), 900, 0, -90, dxfattribs={"layer": "A-DOOR", "color": 1})

    # ── Windows (A-GLAZ layer, colour 5 = blue) ────────────────────
    glaz_attrs = {"layer": "A-GLAZ", "color": 5}

    # Window 1: Room 1 right wall (x=5486, between y=500 and y=2000)
    msp.add_line((5486, 500), (5486, 2000), dxfattribs=glaz_attrs)
    # Double-line representation
    msp.add_line((5500, 500), (5500, 2000), dxfattribs=glaz_attrs)
    # Cross-hatch markers
    for yy in range(600, 2000, 350):
        msp.add_line((5486, yy), (5500, yy + 50), dxfattribs=glaz_attrs)

    # Window 2: Room 2 top wall (at y=9144, x=6000 to x=8000)
    msp.add_line((6000, H), (8000, H), dxfattribs=glaz_attrs)
    msp.add_line((6000, H - 14), (8000, H - 14), dxfattribs=glaz_attrs)
    for xx in range(6100, 8000, 400):
        msp.add_line((xx, H), (xx + 50, H - 14), dxfattribs=glaz_attrs)

    # Window 3: Room 3 left wall (x=0, y=6000 to y=7500)
    msp.add_line((0, 6000), (0, 7500), dxfattribs=glaz_attrs)
    msp.add_line((14, 6000), (14, 7500), dxfattribs=glaz_attrs)
    for yy in range(6100, 7500, 350):
        msp.add_line((0, yy), (14, yy + 50), dxfattribs=glaz_attrs)

    # Window 4: Room 3 top wall (x=1500 to x=3500, y=9144)
    msp.add_line((1500, H), (3500, H), dxfattribs=glaz_attrs)
    msp.add_line((1500, H - 14), (3500, H - 14), dxfattribs=glaz_attrs)
    for xx in range(1600, 3500, 400):
        msp.add_line((xx, H), (xx + 50, H - 14), dxfattribs=glaz_attrs)

    # ── Room labels (A-ANNO-TEXT layer) ────────────────────────────
    text_attrs = {"layer": "A-ANNO-TEXT", "height": 400, "color": 7}

    msp.add_text(
        "Room 1 - Office",
        dxfattribs={**text_attrs, "insert": (800, 4200)},
    )
    msp.add_text(
        "Room 2 - Conference",
        dxfattribs={**text_attrs, "insert": (6000, 3000)},
    )
    msp.add_text(
        "Room 3 - Storage",
        dxfattribs={**text_attrs, "insert": (800, 7200)},
    )

    # ── Dimension notes (A-ANNO-TEXT) ──────────────────────────────
    dim_attrs = {"layer": "A-ANNO-TEXT", "height": 250, "color": 6}

    msp.add_text("10'-0\" x 12'-0\"", dxfattribs={**dim_attrs, "insert": (800, 5800)})
    msp.add_text("8'-0\" x 10'-0\"", dxfattribs={**dim_attrs, "insert": (6000, 5600)})
    msp.add_text("6'-0\" x 8'-0\"", dxfattribs={**dim_attrs, "insert": (800, 8500)})

    # Overall dimensions
    msp.add_text("28'-0\"", dxfattribs={**dim_attrs, "insert": (W // 2, -600)})
    msp.add_text("30'-0\"", dxfattribs={**dim_attrs, "insert": (-1000, H // 2)})

    doc.saveas(path)
    print(f"  ✓ DXF fixture: {path} ({path.stat().st_size} bytes)")


def main():
    print("Generating representative DXF fixture…")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    make_representative_dxf(FIXTURES / "representative_floor_plan.dxf")
    print("Done.")


if __name__ == "__main__":
    main()
