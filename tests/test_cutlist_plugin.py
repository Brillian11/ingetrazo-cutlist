# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 IngeTrazo Extension Developer
"""Unit tests for the OpenCutList plugin for IngeTrazo (v1.4.0)."""
import os
import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

import cutlist_plugin as cp


@dataclass
class MockVec3:
    _x: float
    _y: float
    _z: float

    def x(self) -> float:
        return self._x

    def y(self) -> float:
        return self._y

    def z(self) -> float:
        return self._z


@dataclass
class MockVertex:
    position: MockVec3


@dataclass
class MockMesh:
    vertices: List[MockVertex] = field(default_factory=list)
    faces: List[Any] = field(default_factory=list)


@dataclass
class MockGroup:
    name: str
    mesh: MockMesh
    material: Any = None
    billboard: bool = False
    xform: Any = None
    children: Optional[List[Any]] = None
    component: bool = False


@dataclass
class MockScene:
    groups: List[MockGroup] = field(default_factory=list)
    selection: List[Any] = field(default_factory=list)


def create_box_group(name: str, dx: float, dy: float, dz: float, material: str = "Plywood") -> MockGroup:
    verts = [
        MockVertex(MockVec3(0.0, 0.0, 0.0)),
        MockVertex(MockVec3(dx, 0.0, 0.0)),
        MockVertex(MockVec3(dx, dy, 0.0)),
        MockVertex(MockVec3(0.0, dy, 0.0)),
        MockVertex(MockVec3(0.0, 0.0, dz)),
        MockVertex(MockVec3(dx, 0.0, dz)),
        MockVertex(MockVec3(dx, dy, dz)),
        MockVertex(MockVec3(0.0, dy, dz)),
    ]
    return MockGroup(name=name, mesh=MockMesh(vertices=verts), material={"mat": material})


class TestCutListPlugin(unittest.TestCase):

    def test_callout_tags(self):
        """Verify alphabetical callout tag generation A, B... Z, AA..."""
        self.assertEqual(cp.get_tag_letter(0), "A")
        self.assertEqual(cp.get_tag_letter(1), "B")
        self.assertEqual(cp.get_tag_letter(25), "Z")
        self.assertEqual(cp.get_tag_letter(26), "AA")
        self.assertEqual(cp.get_tag_letter(27), "AB")

    def test_raw_parts_tagging_and_center(self):
        """Verify grouping assigns tags to raw parts and computes 3D centers."""
        shelf = create_box_group("Shelf", dx=0.8, dy=0.4, dz=0.018)
        divider = create_box_group("Divider", dx=0.018, dy=0.4, dz=0.8)
        raw = cp.extract_parts_from_groups([shelf, divider])

        self.assertEqual(len(raw), 2)
        # Center of shelf: (0.4, 0.2, 0.009)
        self.assertAlmostEqual(raw[0].center[0], 0.4)
        self.assertAlmostEqual(raw[0].center[1], 0.2)
        self.assertAlmostEqual(raw[0].center[2], 0.009)

        entries = cp.group_parts(raw, merge_by_dimensions=True)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].tag, "A")
        # Raw parts must inherit tag "A" for 3D balloons
        self.assertEqual(raw[0].tag, "A")
        self.assertEqual(raw[1].tag, "A")

    def test_group_parts_separated_by_material_and_sorted_by_thickness(self):
        """Verify cut list entries cluster by material and sort by thickness descending."""
        parts = [
            cp.RawPart(name="Back Panel", length=2.18, width=0.65, thickness=0.003, material="Poplar"),
            cp.RawPart(name="Heavy Stile", length=2.25, width=0.07, thickness=0.040, material="Bleached wood"),
            cp.RawPart(name="Thick Shelf", length=0.80, width=0.30, thickness=0.025, material="Poplar"),
            cp.RawPart(name="Door Rail", length=1.86, width=0.10, thickness=0.018, material="goldr rr"),
            cp.RawPart(name="Door Stile", length=1.86, width=0.08, thickness=0.018, material="goldr rr"),
            cp.RawPart(name="Trim", length=2.25, width=0.03, thickness=0.018, material="Old wood"),
        ]

        entries = cp.group_parts(parts, merge_by_dimensions=True)
        self.assertEqual(len(entries), 6)

        # Check grouping by material (alphabetical: Bleached wood, goldr rr, Old wood, Poplar)
        mats = [e.material for e in entries]
        self.assertEqual(mats[0], "Bleached wood")
        self.assertEqual(mats[1], "goldr rr")
        self.assertEqual(mats[2], "goldr rr")
        self.assertEqual(mats[3], "Old wood")
        self.assertEqual(mats[4], "Poplar")
        self.assertEqual(mats[5], "Poplar")

        # Within Poplar, thick=0.025 must come BEFORE thin=0.003
        poplar_entries = [e for e in entries if e.material == "Poplar"]
        self.assertEqual(poplar_entries[0].thickness, 0.025)
        self.assertEqual(poplar_entries[1].thickness, 0.003)

    def test_format_console_table_material_headers(self):
        """Verify console output formats material section headers."""
        p1 = cp.CutListEntry(tag="A", display_name="Part 1", count=1, length=1.0, width=0.5, thickness=0.018, material="Oak")
        p2 = cp.CutListEntry(tag="B", display_name="Part 2", count=1, length=0.8, width=0.4, thickness=0.012, material="Pine")
        output = cp.format_console_table([p1, p2], unit="mm")
        self.assertIn("Material: Oak", output)
        self.assertIn("Material: Pine", output)

    def test_material_detection(self):
        self.assertEqual(cp.detect_material_type("Birch Plywood"), "Sheet")
        self.assertEqual(cp.detect_material_type("18mm MDF"), "Sheet")
        self.assertEqual(cp.detect_material_type("Solid White Oak"), "Solid")
        self.assertEqual(cp.detect_material_type("goldr rr", width=0.060, thickness=0.020), "Solid")
        self.assertEqual(cp.detect_material_type("goldr rr", width=0.600, thickness=0.018), "Sheet")

    def test_solid_wood_linear_packing(self):
        stile = cp.CutListEntry(tag="A", display_name="Stile", count=4, length=0.800, width=0.060, thickness=0.020, material="Oak")
        boards = cp.pack_linear_lumber([stile], stock_length=2.400, kerf=0.003)
        self.assertGreaterEqual(len(boards), 2)
        self.assertEqual(boards[0].material, "Oak")

    def test_sheet_goods_2d_packing(self):
        panel = cp.CutListEntry(tag="A", display_name="Side Panel", count=2, length=0.800, width=0.400, thickness=0.018, material="Plywood")
        sheets = cp.pack_sheets([panel], sheet_w=2.440, sheet_h=1.220, kerf=0.003)
        self.assertGreaterEqual(len(sheets), 1)
        self.assertEqual(sheets[0].material, "Plywood")

    def test_tool_metadata(self):
        tool = cp.CutListTool()
        self.assertEqual(tool.name, "Cut List")
        self.assertEqual(tool.menu_order, 15)
        self.assertFalse(tool.uses_snap)

    def test_extract_arched_faces_and_contour(self):
        """Verify extraction of actual arched mesh faces and 2D contour profile."""
        import math
        w, h, thk = 0.3412, 0.6935, 0.018
        h_shoulder = h - (w / 2.0)
        cx, cz, r = w / 2.0, h_shoulder, w / 2.0

        arc_pts = []
        for i in range(16 + 1):
            ang = (i / 16.0) * math.pi
            arc_pts.append((cx + r * math.cos(ang), cz + r * math.sin(ang)))

        front_loop = [(0.0, 0.0, 0.0), (w, 0.0, 0.0), (w, 0.0, h_shoulder)]
        for ax, az in reversed(arc_pts[1:-1]):
            front_loop.append((ax, 0.0, az))
        front_loop.append((0.0, 0.0, h_shoulder))

        class MockFace:
            def __init__(self, loop_pts, norm):
                self.loop = [MockVertex(MockVec3(*p)) for p in loop_pts]
                self._norm = MockVec3(*norm)
            def normal(self):
                return self._norm

        f_front = MockFace(front_loop, (0.0, -1.0, 0.0))
        grp = MockGroup(name="Arched Door", mesh=MockMesh(vertices=[v for v in f_front.loop], faces=[f_front]))

        faces = cp.extract_group_3d_faces(grp)
        self.assertEqual(len(faces), 1)
        self.assertEqual(len(faces[0][0]), len(front_loop))

        contour = cp.extract_2d_contour_from_faces(faces)
        self.assertIsNotNone(contour)
        self.assertEqual(len(contour), len(front_loop))
        # Apex of arch should reach 1.0 in normalized length coordinate
        max_u = max(pt[0] for pt in contour)
        self.assertAlmostEqual(max_u, 1.0, places=4)

    def test_recursive_leaf_part_extraction(self):
        """Verify container with nested children decomposes into leaf parts."""
        door = create_box_group("Door", dx=0.4, dy=0.8, dz=0.018)
        shelf = create_box_group("Shelf", dx=0.4, dy=0.3, dz=0.018)
        cabinet = MockGroup(name="Cabinet", mesh=MockMesh(), children=[door, shelf])

        scene = MockScene(groups=[cabinet], selection=[cabinet])
        selected = cp.get_selected_groups(scene)
        self.assertEqual(len(selected), 2)
        self.assertIn(door, selected)
        self.assertIn(shelf, selected)

    def test_ignore_grouping_and_extract_only_components(self):
        """Verify organizational groups are bypassed and only components are returned."""
        c1 = create_box_group("Component #1", dx=0.1, dy=2.0, dz=0.02)
        c1.component = True
        c2 = create_box_group("Component #2", dx=0.6, dy=0.4, dz=0.02)
        c2.component = True
        
        # Intermediate organizational group containing c2
        sub_assembly = MockGroup(name="Door SubGroup", mesh=MockMesh(), children=[c2], component=False)
        # Top-level organizational assembly containing c1 and sub_assembly
        wardrobe_group = MockGroup(name="Wardrobe Assembly", mesh=MockMesh(), children=[c1, sub_assembly], component=False)
        # Unrelated plain group (e.g. wall/floor) with mesh but not a component
        room_wall = create_box_group("Group 2 (Wall)", dx=3.0, dy=2.5, dz=0.2)
        room_wall.component = False

        scene = MockScene(groups=[wardrobe_group, room_wall], selection=[wardrobe_group, room_wall])
        selected = cp.get_selected_groups(scene)
        
        # Must return ONLY the 2 leaf components, ignoring wardrobe_group, sub_assembly, and room_wall!
        self.assertEqual(len(selected), 2)
        self.assertIn(c1, selected)
        self.assertIn(c2, selected)
        self.assertNotIn(wardrobe_group, selected)
        self.assertNotIn(sub_assembly, selected)
        self.assertNotIn(room_wall, selected)

    def test_empty_selection_extracts_only_components(self):
        """When scene selection is empty, all scene groups are evaluated and only components kept."""
        c1 = create_box_group("Stile", dx=0.07, dy=2.2, dz=0.02)
        c1.component = True
        plain_carcass = create_box_group("Group 5 (Carcass)", dx=0.6, dy=2.2, dz=0.6)
        plain_carcass.component = False

        scene = MockScene(groups=[c1, plain_carcass], selection=[])
        selected = cp.get_selected_groups(scene)
        self.assertEqual(len(selected), 1)
        self.assertIn(c1, selected)
        self.assertNotIn(plain_carcass, selected)

    def test_drawing_widget_viewport_initialization(self):
        """Verify ExplodedDrawingWidget retains and utilizes the hardware viewport reference."""
        if not cp.QT_AVAILABLE:
            self.skipTest("Qt bindings (PySide6 / PyQt6) not installed in test runner environment.")

        class MockCamera:
            def __init__(self):
                self.target = MockVec3(0, 0, 0)
                self.distance = 5.0
                self.yaw = -0.785
                self.pitch = 0.523
                self.aspect = 1.0
                self.perspective = True

            def fit_box(self, min_v, max_v, margin=1.2):
                pass

        class MockViewport:
            def __init__(self):
                self.camera = MockCamera()
                self.scene = MockScene()
                self.rendered_calls = []

            def render_image(self, w, h, overlays=False, sharp_shadows=False, transparent=True):
                self.rendered_calls.append((w, h))
                return None

        mock_vp = MockViewport()
        widget = cp.ExplodedDrawingWidget(viewport=mock_vp)
        self.assertIs(widget.viewport, mock_vp)
        self.assertTrue(hasattr(widget.viewport, "render_image"))
        self.assertTrue(hasattr(widget.viewport, "camera"))

    def test_get_material_texture_file_resolution(self):
        """Verify texture file path resolution from scene and disk cache."""
        scene = MockScene()
        scene.materials = [
            {"name": "goldr rr", "texture": {"embed": "textures/c6f875616770b0a4-pine.jpg"}},
            {"name": "metal_brushed", "texture": {"embed": "textures/b3afd6ac329570c2-metal_brushed.png"}},
            {"name": "Poplar", "texture": {"embed": "textures/9f5778ce1701652d-poplar.jpg"}},
        ]

        # Resolution from scene
        p_goldr = cp.get_material_texture_file("goldr rr", scene=scene)
        self.assertIsNotNone(p_goldr)
        self.assertTrue(p_goldr.endswith("c6f875616770b0a4-pine.jpg"))

        p_poplar = cp.get_material_texture_file("Poplar", scene=scene)
        self.assertIsNotNone(p_poplar)
        self.assertTrue(p_poplar.endswith("9f5778ce1701652d-poplar.jpg"))

        # Fallback disk resolution without scene
        p_bleached = cp.get_material_texture_file("Bleached wood", scene=None)
        if p_bleached is not None:
            self.assertTrue("bleached_wood" in p_bleached.lower())

        # Empty or nonexistent material returns None
        self.assertIsNone(cp.get_material_texture_file("", scene=scene))
        self.assertIsNone(cp.get_material_texture_file("NonExistentXYZ999", scene=None))

    def test_material_change_and_dynamic_regrouping(self):
        """Verify that changing a part's material dynamically regroups the cut list."""
        g1 = create_box_group("Carcass Side", 600, 400, 30, material="Pine")
        g1.component = True
        g2 = create_box_group("Carcass Shelf", 500, 300, 20, material="Pine")
        g2.component = True
        g3 = create_box_group("Face Frame", 400, 100, 15, material="Oak")
        g3.component = True

        raw_parts = cp.extract_parts_from_groups([g1, g2, g3])
        entries = cp.group_parts(raw_parts, merge_by_dimensions=True)

        # Before change: Pine has 2 entries (thickness 30 and 20), Oak has 1 entry (thickness 15)
        pine_entries = [e for e in entries if e.material == "Pine"]
        oak_entries = [e for e in entries if e.material == "Oak"]
        self.assertEqual(len(pine_entries), 2)
        self.assertEqual(len(oak_entries), 1)
        self.assertEqual(pine_entries[0].thickness, 30.0)
        self.assertEqual(pine_entries[1].thickness, 20.0)
        self.assertEqual(oak_entries[0].thickness, 15.0)

        # Simulate user changing the material of g2 (Shelf) from "Pine" to "Oak" via table combobox
        p2 = raw_parts[1]
        self.assertEqual(p2.name, "Carcass Shelf")
        new_mat = "Oak"
        p2.material = new_mat
        p2.group_ref.material = new_mat

        # Regroup
        new_entries = cp.group_parts(raw_parts, merge_by_dimensions=True)
        new_pine = [e for e in new_entries if e.material == "Pine"]
        new_oak = [e for e in new_entries if e.material == "Oak"]

        # After change: Pine has 1 entry (thickness 30), Oak has 2 entries (sorted by thickness: 20, then 15)
        self.assertEqual(len(new_pine), 1)
        self.assertEqual(len(new_oak), 2)
        self.assertEqual(new_pine[0].thickness, 30.0)
        self.assertEqual(new_oak[0].thickness, 20.0)  # g2 now under Oak, sorted thickest first!
        self.assertEqual(new_oak[1].thickness, 15.0)

    def test_material_thumbnail_headless_graceful(self):
        """Verify thumbnail and color parsing handle headless environments gracefully."""
        pixmap, icon = cp.get_material_thumbnail("Poplar")
        if not cp.QT_AVAILABLE:
            self.assertIsNone(pixmap)
            self.assertIsNone(icon)
            self.assertIsNone(cp.parse_material_color("rgb(100, 150, 200)"))

    def test_library_material_stock_type_mapping(self):
        """Verify stock type classification strictly follows IngeTrazo material library categories."""
        # 1. Poplar is in wood category -> Solid Lumber (Boards)
        self.assertEqual(cp.get_material_stock_label("Poplar"), "🌲 Wood (Solid Lumber)")
        self.assertTrue(cp.is_linear_stock(cp.get_material_stock_label("Poplar")))

        # 2. Bleached wood is in wood category -> Solid Lumber (Boards)
        self.assertEqual(cp.get_material_stock_label("Bleached wood"), "🌲 Wood (Solid Lumber)")
        self.assertTrue(cp.is_linear_stock(cp.get_material_stock_label("Bleached wood")))

        # 3. metal_brushed is in metal category -> Bar Stock (Bars)
        self.assertEqual(cp.get_material_stock_label("metal_brushed"), "🔩 Metal (Bar Stock)")
        self.assertTrue(cp.is_linear_stock(cp.get_material_stock_label("metal_brushed")))

        # 4. Old brown wooden floor is in floor category -> Flooring (Planks / Tiles)
        self.assertEqual(cp.get_material_stock_label("Old brown wooden floor"), "🪵 Flooring (Planks / Tiles)")
        self.assertFalse(cp.is_linear_stock(cp.get_material_stock_label("Old brown wooden floor")))

        # 5. RAL color is in colors category -> Finish / Sheet
        self.assertEqual(cp.get_material_stock_label("RAL 1000 - Green beige"), "🎨 Colors (Finish / Sheet)")
        self.assertFalse(cp.is_linear_stock(cp.get_material_stock_label("RAL 1000 - Green beige")))

        # 6. Wood with explicit sheet keyword -> Sheet / Plywood
        self.assertEqual(cp.get_material_stock_label("Birch Plywood"), "🔲 Wood (Sheet / Plywood)")
        self.assertFalse(cp.is_linear_stock(cp.get_material_stock_label("Birch Plywood")))

    def test_material_library_search_and_filter(self):
        """Verify querying and filtering all 640+ materials across categories."""
        lib = cp.get_material_library()
        self.assertGreaterEqual(len(lib.items), 640)
        self.assertIn("wood", lib.categories)
        self.assertIn("colors", lib.categories)
        self.assertIn("floor", lib.categories)

        # Exact lookup
        poplar_item = lib.find_material("Poplar")
        self.assertIsNotNone(poplar_item)
        self.assertEqual(poplar_item.category_id, "wood")
        self.assertEqual(poplar_item.stock_type, "🌲 Wood (Solid Lumber)")

        # Case-insensitive lookup
        metal_item = lib.find_material("METAL_BRUSHED")
        self.assertIsNotNone(metal_item)
        self.assertEqual(metal_item.category_id, "metal")
        self.assertEqual(metal_item.stock_type, "🔩 Metal (Bar Stock)")

        # Filtering category counts
        wood_items = [it for it in lib.items if it.category_id == "wood"]
        self.assertEqual(len(wood_items), 22)
        color_items = [it for it in lib.items if it.category_id == "colors"]
        self.assertEqual(len(color_items), 213)

    def test_stock_display_info_units(self):
        """Verify diagram dropdown icons, categories, and unit labels."""
        # Solid wood -> 🌲, Wood, Boards
        icon, cat, unit = cp.get_stock_display_info("🌲 Wood (Solid Lumber)")
        self.assertEqual(icon, "🌲")
        self.assertEqual(cat, "Wood")
        self.assertEqual(unit, "Boards")

        # Metal bar -> 🔩, Metal, Bars
        icon, cat, unit = cp.get_stock_display_info("🔩 Metal (Bar Stock)")
        self.assertEqual(icon, "🔩")
        self.assertEqual(cat, "Metal")
        self.assertEqual(unit, "Bars")

        # Flooring -> 🪵, Flooring, Tiles
        icon, cat, unit = cp.get_stock_display_info("🪵 Flooring (Planks / Tiles)")
        self.assertEqual(icon, "🪵")
        self.assertEqual(cat, "Flooring")
        self.assertEqual(unit, "Tiles")

        # Sheet goods -> 🔲, Wood, Sheets
        icon, cat, unit = cp.get_stock_display_info("🔲 Wood (Sheet / Plywood)")
        self.assertEqual(icon, "🔲")
        self.assertEqual(cat, "Wood")
        self.assertEqual(unit, "Sheets")

    def test_about_metadata_and_dialog(self):
        """Verify developer attribution to brillian11 and audience for woodworkers & cabinet makers."""
        self.assertEqual(cp.PLUGIN_AUTHOR, "brillian11")
        self.assertEqual(cp.PLUGIN_GITHUB, "https://github.com/brillian11")
        self.assertEqual(cp.PLUGIN_VERSION, "Beta 0.1")
        self.assertIn("Woodworker", cp.PLUGIN_AUDIENCE)
        self.assertIn("Cabinet Maker", cp.PLUGIN_AUDIENCE)

        # Headless show_about_dialog should execute without raising exceptions
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            cp.show_about_dialog(parent=None)
        out = buf.getvalue()
        self.assertIn("brillian11", out)
        self.assertIn("github.com/brillian11", out)
        self.assertIn("Woodworker", out)


    def test_console_dialog_and_output(self):
        """Verify console dialog prints ASCII table in headless mode and contains all data."""
        entries = [
            cp.CutListEntry("A", "Panel 1", 1, 1000.0, 500.0, 18.0, "Plywood"),
            cp.CutListEntry("B", "Leg 1, Leg 2", 2, 800.0, 50.0, 50.0, "Oak"),
        ]
        text = cp.format_console_table(entries, unit="mm")
        self.assertIn("INGETRAZO — OPEN CUT LIST", text)
        self.assertIn("Plywood", text)
        self.assertIn("Oak", text)
        self.assertIn("Total Parts: 3", text)

        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            cp.show_console_dialog(text, parent=None)
        out = buf.getvalue()
        self.assertIn("INGETRAZO — OPEN CUT LIST", out)
        self.assertIn("Panel 1", out)

    def test_in_model_materials_picker_logic(self):
        """Verify in-model materials (including custom ones like 'goldr rr') are categorized and prioritized."""
        lib = cp.get_material_library()
        in_model_mats = ["goldr rr", "metal_brushed", "Poplar"]

        # Check stock label resolution for custom in-model material
        st_goldr = cp.get_material_stock_label("goldr rr")
        self.assertIn("Wood", st_goldr)

        # Build mock in-model items as done in MaterialLibraryDialog._build_in_model_items
        seen = set()
        items = []
        for m in in_model_mats:
            if m in seen:
                continue
            seen.add(m)
            existing = lib.by_name.get(m.lower())
            st = cp.get_material_stock_label(m)
            pm = "Solid" if cp.is_linear_stock(st) else "Sheet"
            if existing:
                it = cp.LibraryMaterialItem(
                    name=m,
                    category_id="in_model",
                    category_name="⭐ In Model",
                    stock_type=existing.stock_type,
                    packing_mode=existing.packing_mode,
                )
            else:
                it = cp.LibraryMaterialItem(
                    name=m,
                    category_id="in_model",
                    category_name="⭐ In Model",
                    stock_type=st,
                    packing_mode=pm,
                )
            items.append(it)

        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].name, "goldr rr")
        self.assertEqual(items[0].category_name, "⭐ In Model")
        self.assertEqual(items[1].name, "metal_brushed")
        self.assertEqual(items[2].name, "Poplar")

    def test_render_cutlist_pdf_and_metadata(self):
        """Verify OpenCutList-styled PDF export generation and metadata mappings."""
        self.assertEqual(cp.UNIT_LONG_NAMES.get("mm"), "Millimeter")
        self.assertEqual(cp.UNIT_LONG_NAMES.get("cm"), "Centimeter")
        self.assertEqual(cp.UNIT_LONG_NAMES.get("in"), "Inch")

        self.assertTrue(cp.get_project_name(None).endswith(".skp"))

        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "test_parts_list.pdf")
            entries = [
                cp.CutListEntry("A", "Component#33", 1, 0.065, 0.012, 0.012, "0128_White"),
                cp.CutListEntry("B", "Component#34", 1, 0.065, 0.012, 0.012, "0128_White"),
                cp.CutListEntry("C", "rod", 1, 0.065, 0.012, 0.012, "0128_White"),
                cp.CutListEntry("D", "Brace", 2, 0.800, 0.050, 0.020, "Pine woods"),
            ]
            cp.render_cutlist_pdf(pdf_path, entries, unit="cm")
            self.assertTrue(os.path.exists(pdf_path))
            self.assertGreater(os.path.getsize(pdf_path), 50)

    def test_rough_cut_allowances_and_dimensions(self):
        """Verify rough cut allowances (+2mm thickness, +20mm length, +6mm width) for solid wood."""
        solid_entry = cp.CutListEntry("A", "Solid Rail", 2, 1.8662, 0.100, 0.018, "Pine woods")
        sheet_entry = cp.CutListEntry("B", "Plywood Back", 1, 2.1798, 0.648, 0.003, "Poplar")
        entries = [solid_entry, sheet_entry]

        mat_types = {
            "Pine woods": "🌲 Solid Wood (Lumber)",
            "Poplar": "🔲 Wood (Sheet / Plywood)",
        }

        cp.update_entries_rough_dimensions(
            entries,
            mat_types,
            over_length=0.020,
            over_width=0.006,
            over_thickness=0.002,
            apply_to_solid_only=True,
        )

        # Solid wood receives allowances: 18mm -> 20mm, 100mm -> 106mm, 1866.2mm -> 1886.2mm
        self.assertAlmostEqual(solid_entry.rough_thickness, 0.020, places=4)
        self.assertAlmostEqual(solid_entry.rough_width, 0.106, places=4)
        self.assertAlmostEqual(solid_entry.rough_length, 1.8862, places=4)
        self.assertAlmostEqual(solid_entry.r_thickness, 0.020, places=4)
        self.assertAlmostEqual(solid_entry.thickness, 0.018, places=4)
        self.assertGreater(solid_entry.rough_total_volume, solid_entry.total_volume)

        # Sheet goods stay at net design dimensions (0 allowance)
        self.assertAlmostEqual(sheet_entry.rough_thickness, 0.003, places=4)
        self.assertAlmostEqual(sheet_entry.rough_width, 0.648, places=4)
        self.assertAlmostEqual(sheet_entry.rough_length, 2.1798, places=4)

    def test_format_volume_and_board_feet(self):
        """Verify volume formatting in m³, dm³, and Board Feet (BF)."""
        # dm³ for small volume (< 0.01 m³)
        self.assertEqual(cp.format_volume(0.005, "mm"), "5.00 dm³")
        # m³ for larger volume (>= 0.01 m³)
        self.assertEqual(cp.format_volume(0.125, "mm"), "0.125 m³")
        # Imperial Board Feet (BF): 1 BF = 12" x 12" x 1" = 0.00235974 m³
        bf_vol = 0.00235974
        self.assertEqual(cp.format_volume(bf_vol, "in"), "1.00 BF")
        self.assertEqual(cp.format_volume(bf_vol * 10, "ft"), "10.00 BF")

    def test_format_console_table_rough_and_finished(self):
        """Verify console table outputs dual Finished and Rough Cut columns when allowances exist."""
        entry = cp.CutListEntry("A", "Table Leg", 4, 0.750, 0.080, 0.018, "Oak")
        entry.rough_length = 0.770
        entry.rough_width = 0.086
        entry.rough_thickness = 0.020

        txt = cp.format_console_table([entry], unit="mm")
        self.assertIn("Finished (L×W×T)", txt)
        self.assertIn("Rough Cut (L×W×T)", txt)
        self.assertIn("Rough Vol:", txt)
        self.assertIn("Oak", txt)

    def test_estimator_raw_stock_vs_net_parts(self):
        """Verify sheet and board cost calculations in raw_stock vs net_parts modes."""
        e_sheet = cp.CutListEntry("A", "Cabinet Side", 2, 1.20, 0.60, 0.018, "Plywood Birch")
        e_lumber = cp.CutListEntry("B", "Face Frame", 4, 1.00, 0.05, 0.020, "Pine Solid")
        entries = [e_sheet, e_lumber]

        mat_types = {
            "Plywood Birch": "🔲 Wood (Sheet / Plywood)",
            "Pine Solid": "🌲 Solid Wood (Lumber)",
        }

        pricing = {
            "Plywood Birch": cp.MaterialPricingConfig("Plywood Birch", pricing_basis="sheet", unit_price=60.0, density_kg_m3=650.0, waste_pct=10.0),
            "Pine Solid": cp.MaterialPricingConfig("Pine Solid", pricing_basis="board", unit_price=12.0, density_kg_m3=500.0, waste_pct=0.0),
        }

        # 1. Commercial Raw Stock Mode
        params_raw = cp.EstimatorParameters(estimation_mode="raw_stock", currency_symbol="$")
        summary_raw = cp.compute_project_estimate(entries, mat_types, pricing_configs=pricing, params=params_raw)

        # e_sheet total area = 1.44 m2 -> 1 raw sheet (2.44x1.22 = 2.9768 m2) -> 1 * $60 = $60
        # e_lumber total length = 4.0 m -> 2 raw boards (2.4m each) -> 2 * $12 = $24
        line_sheet_raw = next(l for l in summary_raw.material_lines if l.material_name == "Plywood Birch")
        line_lumber_raw = next(l for l in summary_raw.material_lines if l.material_name == "Pine Solid")

        self.assertEqual(line_sheet_raw.raw_units_count, 1)
        self.assertEqual(line_sheet_raw.raw_units_label, "sheets")
        self.assertAlmostEqual(line_sheet_raw.material_cost, 60.0)

        self.assertEqual(line_lumber_raw.raw_units_count, 2)
        self.assertEqual(line_lumber_raw.raw_units_label, "boards")
        self.assertAlmostEqual(line_lumber_raw.material_cost, 24.0)
        self.assertAlmostEqual(summary_raw.materials_cost_subtotal, 84.0)

        # 2. Net Parts Mode (with 10% waste for Plywood)
        params_net = cp.EstimatorParameters(estimation_mode="net_parts", currency_symbol="$")
        summary_net = cp.compute_project_estimate(entries, mat_types, pricing_configs=pricing, params=params_net)

        line_sheet_net = next(l for l in summary_net.material_lines if l.material_name == "Plywood Birch")
        line_lumber_net = next(l for l in summary_net.material_lines if l.material_name == "Pine Solid")

        std_sheet_area = 2.44 * 1.22
        expected_sheet_cost = (1.44 / std_sheet_area) * 60.0 * 1.10
        self.assertAlmostEqual(line_sheet_net.material_cost, expected_sheet_cost, places=2)

        expected_board_cost = (4.0 / 2.4) * 12.0 * 1.00
        self.assertAlmostEqual(line_lumber_net.material_cost, 20.0, places=2)

    def test_estimator_weight_and_units(self):
        """Verify weight calculation using physical density in kg and lb."""
        entry = cp.CutListEntry("A", "Oak Tabletop", 1, 2.0, 1.0, 0.030, "White Oak")
        mat_types = {"White Oak": "🔲 Wood (Sheet / Plywood)"}
        pricing = {
            "White Oak": cp.MaterialPricingConfig("White Oak", pricing_basis="volume", unit_price=1200.0, density_kg_m3=720.0),
        }

        # Finished vol = 2.0 * 1.0 * 0.030 = 0.060 m3
        # Weight = 0.060 * 720.0 = 43.2 kg
        # In kg mode
        params_kg = cp.EstimatorParameters(weight_unit="kg")
        summary_kg = cp.compute_project_estimate([entry], mat_types, pricing_configs=pricing, params=params_kg)
        self.assertAlmostEqual(summary_kg.total_weight_kg, 43.2, places=2)
        self.assertIn("43.2 kg", summary_kg.total_weight_display)

        # In lb mode (1 kg = 2.20462 lb) -> 43.2 * 2.20462 = ~95.2 lb
        params_lb = cp.EstimatorParameters(weight_unit="lb")
        summary_lb = cp.compute_project_estimate([entry], mat_types, pricing_configs=pricing, params=params_lb)
        self.assertIn("95.2 lb", summary_lb.total_weight_display)

    def test_estimator_operations_margin_tax(self):
        """Verify labor, cutting fees, edge banding, hardware, margin %, and tax %."""
        entry = cp.CutListEntry("A", "Desk Top", 1, 1.5, 0.8, 0.025, "MDF")
        mat_types = {"MDF": "🔲 Wood (Sheet / Plywood)"}
        pricing = {
            "MDF": cp.MaterialPricingConfig("MDF", pricing_basis="sheet", unit_price=40.0, density_kg_m3=700.0),
        }

        params = cp.EstimatorParameters(
            currency_symbol="$",
            estimation_mode="raw_stock",
            labor_hours=5.0,
            labor_rate_hourly=40.0,            # 5 * 40 = $200
            cutting_fee_per_sheet=10.0,         # 1 sheet * 10 = $10
            edge_banding_price_per_m=2.0,
            edge_banding_meters=15.0,           # 15 * 2 = $30 -> machining subtotal = 10 + 30 = $40
            hardware_total=50.0,                # Extras = 50 + 20 + 30 = $100
            finish_coating_total=20.0,
            shipping_delivery_total=30.0,
            overhead_margin_pct=20.0,           # 20% markup
            tax_vat_pct=10.0,                   # 10% tax
        )

        summary = cp.compute_project_estimate([entry], mat_types, pricing_configs=pricing, params=params)

        self.assertAlmostEqual(summary.materials_cost_subtotal, 40.0)
        self.assertAlmostEqual(summary.labor_cost_subtotal, 200.0)
        self.assertAlmostEqual(summary.machining_cutting_subtotal, 40.0)
        self.assertAlmostEqual(summary.hardware_extras_subtotal, 100.0)

        # Net cost = 40 + 200 + 40 + 100 = 380.0
        self.assertAlmostEqual(summary.net_cost, 380.0)

        # Overhead margin = 380 * 0.20 = 76.0 -> Subtotal with margin = 456.0
        self.assertAlmostEqual(summary.overhead_margin_amount, 76.0)

        # Tax = 456.0 * 0.10 = 45.60
        self.assertAlmostEqual(summary.tax_amount, 45.60)

        # Final quote = 456.0 + 45.60 = 501.60
        self.assertAlmostEqual(summary.total_project_quote, 501.60)

    def test_estimator_pricing_library_persistence(self):
        """Verify save_material_pricing_library and load_material_pricing_library JSON round-trip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test_pricing.json"
            orig_func = cp.get_estimator_pricing_file_path
            cp.get_estimator_pricing_file_path = lambda: test_file
            try:
                # Initially empty
                self.assertEqual(cp.load_material_pricing_library(), {})

                # Save custom configs
                configs = {
                    "Walnut": cp.MaterialPricingConfig("Walnut", "volume", 1500.0, 680.0, 5.0),
                    "Melamine White": cp.MaterialPricingConfig("Melamine White", "sheet", 35.0, 720.0, 0.0),
                }
                success = cp.save_material_pricing_library(configs)
                self.assertTrue(success)
                self.assertTrue(test_file.exists())

                # Reload and verify
                loaded = cp.load_material_pricing_library()
                self.assertIn("Walnut", loaded)
                self.assertIn("Melamine White", loaded)
                self.assertEqual(loaded["Walnut"].pricing_basis, "volume")
                self.assertAlmostEqual(loaded["Walnut"].unit_price, 1500.0)
                self.assertAlmostEqual(loaded["Walnut"].density_kg_m3, 680.0)
                self.assertAlmostEqual(loaded["Walnut"].waste_pct, 5.0)
                self.assertEqual(loaded["Melamine White"].pricing_basis, "sheet")
                self.assertAlmostEqual(loaded["Melamine White"].unit_price, 35.0)
            finally:
                cp.get_estimator_pricing_file_path = orig_func

    def test_render_estimate_pdf_and_csv(self):
        """Verify headless PDF and CSV export generation for commercial estimates."""
        entry = cp.CutListEntry("A", "Bookcase Shelf", 6, 0.80, 0.30, 0.018, "Pine")
        summary = cp.compute_project_estimate([entry])

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "estimate_test.pdf")
            cp.render_estimate_pdf(pdf_path, summary, project_name="Test Project")

            self.assertTrue(os.path.exists(pdf_path))
            with open(pdf_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("%PDF-1.4", content)
            self.assertIn("COMMERCIAL ESTIMATE & QUOTE", content)
            self.assertIn("GRAND TOTAL QUOTE", content)
            self.assertIn("Pine", content)


if __name__ == "__main__":
    unittest.main()
