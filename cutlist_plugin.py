# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 IngeTrazo Extension Developer
"""OpenCutList Plugin for IngeTrazo 3D (v1.5.0).

Features:
- Selection-First Workflow (groups/components selected in 3D viewport).
- True 3D Geometry Rendering in Exploded Drawing:
  * Extracts and renders the ACTUAL mesh faces of each part (arches, curved
    mouldings, cutouts, angles, and bevels) rather than simplified bounding boxes.
  * Live Explosion Slider (0% to 250%) to pull parts apart in 3D.
  * Callout balloons (A, B, C...) connecting 3D parts to the cutting list.
  * Parts legend table & title block directly on the drawing sheet.
  * 3D Orbit, pan, and zoom controls.
  * High-resolution PNG and PDF drawing export.
- True Shape Contours in 2D Cutting Diagrams:
  * Non-rectangular parts (such as arched panels and curved mouldings) display
    their actual curved contour inside the rectangular stock blank!
  * Dual-mode diagrams: Solid Wood 1D lumber layouts and Sheet Goods 2D panel nesting.
- Standard woodworking dimension ordering (L >= W >= T).
- Multi-format exports: TSV clipboard, CSV spreadsheet, PNG, PDF, Python Console.
"""
from __future__ import annotations

import csv
from datetime import datetime
import io
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Qt Imports (PySide6 with fallbacks to PyQt6 / PyQt5)
# ---------------------------------------------------------------------------
try:
    from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, QUrl
    from PySide6.QtGui import (
        QAction,
        QBrush,
        QColor,
        QDesktopServices,
        QFont,
        QFontDatabase,
        QFontMetrics,
        QIcon,
        QImage,
        QKeySequence,
        QMatrix4x4,
        QPageLayout,
        QPageSize,
        QPainter,
        QPainterPath,
        QPdfWriter,
        QPen,
        QPixmap,
        QPolygonF,
        QVector3D,
        QVector4D,
    )
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QDialog,
        QDoubleSpinBox,
        QFileDialog,
        QFormLayout,
        QFrame,
        QGroupBox,
        QHBoxLayout,
        QHeaderView,
        QLabel,
        QLineEdit,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSlider,
        QSpinBox,
        QSplitter,
        QTabWidget,
        QTableWidget,
        QTableWidgetItem,
        QToolBar,
        QVBoxLayout,
        QWidget,
    )
    QT_AVAILABLE = True
except ImportError:
    try:
        from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer, QUrl
        from PyQt6.QtGui import (
            QAction,
            QBrush,
            QColor,
            QDesktopServices,
            QFont,
            QFontDatabase,
            QFontMetrics,
            QIcon,
            QImage,
            QKeySequence,
            QMatrix4x4,
            QPageLayout,
            QPageSize,
            QPainter,
            QPainterPath,
            QPdfWriter,
            QPen,
            QPixmap,
            QPolygonF,
            QVector3D,
            QVector4D,
        )
        from PyQt6.QtWidgets import (
            QApplication,
            QCheckBox,
            QComboBox,
            QDialog,
            QDoubleSpinBox,
            QFileDialog,
            QFormLayout,
            QFrame,
            QGroupBox,
            QHBoxLayout,
            QHeaderView,
            QLabel,
            QLineEdit,
            QMessageBox,
            QPlainTextEdit,
            QPushButton,
            QScrollArea,
            QSlider,
            QSpinBox,
            QSplitter,
            QTabWidget,
            QTableWidget,
            QTableWidgetItem,
            QToolBar,
            QVBoxLayout,
            QWidget,
        )
        QT_AVAILABLE = True
    except ImportError:
        QT_AVAILABLE = False

# ---------------------------------------------------------------------------
# Base Tool Import (tools.base.Tool)
# ---------------------------------------------------------------------------
try:
    from tools.base import Tool
except ImportError:
    class Tool:  # type: ignore
        name: str = "Unnamed"
        shortcut: str | None = None
        description: str | None = None
        menu_order: int = 0
        uses_snap: bool = False

        def on_activate(self, viewport: Any) -> None:
            pass

        def on_deactivate(self, viewport: Any) -> None:
            pass


# ---------------------------------------------------------------------------
# Constants & Unit Definitions
# ---------------------------------------------------------------------------
PLUGIN_KEY = "ingetrazo_cutlist"
PLUGIN_TITLE = "Cut List"
PLUGIN_VERSION = "Beta 0.1"
PLUGIN_AUTHOR = "brillian11"
PLUGIN_GITHUB = "https://github.com/brillian11"
PLUGIN_AUDIENCE = "Woodworkers & Cabinet Makers"


def open_url_in_browser(url: str) -> None:
    """Safely opens a URL in the user's default web browser."""
    try:
        if QT_AVAILABLE and "QDesktopServices" in globals() and "QUrl" in globals():
            if QDesktopServices.openUrl(QUrl(url)):
                return
    except Exception:
        pass
    import webbrowser
    try:
        webbrowser.open(url)
    except Exception:
        pass

UNIT_FACTORS = {
    "mm": 1000.0,
    "cm": 100.0,
    "m": 1.0,
    "in": 1.0 / 0.0254,
}

UNIT_DECIMALS = {
    "mm": 1,
    "cm": 2,
    "m": 3,
    "in": 2,
}

AREA_UNITS = {
    "mm": "m²",
    "cm": "m²",
    "m": "m²",
    "in": "sq ft",
}

SHEET_KEYWORDS = {
    "plywood", "mdf", "osb", "melamine", "chipboard", "particle",
    "hpl", "panel", "hardboard", "triplay", "aglomerado", "tablero",
    "compensado", "sheet", "veneer", "drywall", "backer",
}

SOLID_KEYWORDS = {
    "solid", "lumber", "timber", "wood", "oak", "pine", "walnut",
    "teak", "maple", "ash", "cedar", "beech", "cherry", "mahogany",
    "birch", "madera", "roble", "pino", "nogal", "plank", "board",
    "viga", "liston", "slat", "strip", "batten",
}


def format_dimension(metres: float, unit: str = "mm") -> str:
    factor = UNIT_FACTORS.get(unit, 1000.0)
    decimals = UNIT_DECIMALS.get(unit, 1)
    return f"{metres * factor:.{decimals}f}"


def format_area(square_metres: float, unit: str = "mm") -> str:
    if unit == "in":
        sq_ft = square_metres * 10.7639104
        return f"{sq_ft:.2f} sq ft"
    return f"{square_metres:.2f} m²"


@dataclass
class LibraryMaterialItem:
    name: str
    category_id: str
    category_name: str
    stock_type: str
    packing_mode: str  # 'Solid' (1D Linear) or 'Sheet' (2D Nesting)
    texture_file: Optional[str] = None
    rgb: Optional[Tuple[float, float, float]] = None
    sw: float = 1.0
    sh: float = 1.0


def get_library_paths() -> Tuple[Optional[Path], Optional[Path], Optional[Path]]:
    """Returns (library_json_path, ral_json_path, library_textures_dir)."""
    candidates = [
        Path(r"C:\Program Files\IngeTrazo\_internal\resources\textures\library.json"),
        Path(r"C:\Program Files\IngeTrazo\resources\textures\library.json"),
        Path(sys.executable).parent / "_internal" / "resources" / "textures" / "library.json",
        Path(sys.executable).parent / "resources" / "textures" / "library.json",
    ]
    lib_p = next((c for c in candidates if c.exists()), None)

    ral_candidates = [
        Path(r"C:\Program Files\IngeTrazo\_internal\resources\colors\ral.json"),
        Path(r"C:\Program Files\IngeTrazo\resources\colors\ral.json"),
        Path(sys.executable).parent / "_internal" / "resources" / "colors" / "ral.json",
        Path(sys.executable).parent / "resources" / "colors" / "ral.json",
    ]
    ral_p = next((c for c in ral_candidates if c.exists()), None)

    tex_dir = None
    if lib_p is not None:
        cand_tex = lib_p.parent / "library"
        if cand_tex.exists() and cand_tex.is_dir():
            tex_dir = cand_tex

    return lib_p, ral_p, tex_dir


CATEGORY_DISPLAY_NAMES: Dict[str, str] = {
    "wood": "Wood",
    "metal": "Metal",
    "floor": "Flooring",
    "colors": "Colors",
    "wall": "Wall",
    "wallpaper": "Wallpaper",
    "fabric": "Fabric",
    "roof": "Roofing",
    "rug": "Rug",
    "stone": "Stone",
    "brick": "Brick",
    "concrete": "Concrete",
    "glass": "Glass",
    "ground": "Ground",
    "water": "Water",
    "sky": "Sky",
    "misc": "Misc",
}

STOCK_TYPE_CHOICES: List[str] = [
    "🌲 Wood (Solid Lumber)",
    "🔲 Wood (Sheet / Plywood)",
    "🔩 Metal (Bar Stock)",
    "🔲 Metal (Sheet Metal)",
    "🪵 Flooring (Planks / Tiles)",
    "🎨 Colors (Finish / Sheet)",
    "🪟 Glass (Sheet Pane)",
    "🧵 Fabric (Roll / Sheet)",
    "🧱 Masonry (Slabs / Tiles)",
    "🔲 Generic Sheet Goods",
]


class MaterialLibrary:
    """Manages the full material library from IngeTrazo (textures and RAL colors)."""

    def __init__(self) -> None:
        self.items: List[LibraryMaterialItem] = []
        self.by_name: Dict[str, LibraryMaterialItem] = {}
        self.categories: Dict[str, str] = dict(CATEGORY_DISPLAY_NAMES)
        self.category_counts: Dict[str, int] = {}
        self._load()

    def _determine_stock_type(self, cid: str, name: str) -> Tuple[str, str]:
        nl = name.lower()
        if cid == "wood":
            for kw in ["plywood", "mdf", "osb", "particle", "veneer", "panel", "sheet"]:
                if kw in nl:
                    return "🔲 Wood (Sheet / Plywood)", "Sheet"
            return "🌲 Wood (Solid Lumber)", "Solid"
        elif cid == "metal":
            for kw in ["sheet", "plate"]:
                if kw in nl:
                    return "🔲 Metal (Sheet Metal)", "Sheet"
            return "🔩 Metal (Bar Stock)", "Solid"
        elif cid == "floor":
            return "🪵 Flooring (Planks / Tiles)", "Sheet"
        elif cid == "colors":
            return "🎨 Colors (Finish / Sheet)", "Sheet"
        elif cid == "glass":
            return "🪟 Glass (Sheet Pane)", "Sheet"
        elif cid in ("stone", "brick", "concrete"):
            return "🧱 Masonry (Slabs / Tiles)", "Sheet"
        else:
            cname = self.categories.get(cid, "Sheet Goods")
            return f"🔲 {cname} (Sheet Goods)", "Sheet"

    def _load(self) -> None:
        lib_p, ral_p, tex_dir = get_library_paths()

        if lib_p and lib_p.exists():
            try:
                import json
                with open(lib_p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for cat in data.get("categories", []):
                    cid = cat.get("id", "misc")
                    cname = self.categories.get(cid, cid.title())
                    items = cat.get("items", [])
                    self.category_counts[cid] = len(items)
                    for it in items:
                        m_name = it.get("name", "")
                        if not m_name:
                            continue
                        f_rel = it.get("file")
                        f_abs = str(tex_dir / f_rel) if (tex_dir and f_rel) else None
                        st, pm = self._determine_stock_type(cid, m_name)
                        item = LibraryMaterialItem(
                            name=m_name,
                            category_id=cid,
                            category_name=cname,
                            stock_type=st,
                            packing_mode=pm,
                            texture_file=f_abs,
                            sw=float(it.get("sw", 1.0)),
                            sh=float(it.get("sh", 1.0)),
                        )
                        self.items.append(item)
                        self.by_name[m_name.lower()] = item
            except Exception as err:
                sys.stderr.write(f"[CutList] Error loading library.json: {err}\n")

        if ral_p and ral_p.exists():
            try:
                import json
                with open(ral_p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ral_count = 0
                for fam in data.get("families", []):
                    for c in fam.get("colors", []):
                        ral_count += 1
                        code = c.get("code", "")
                        c_name = c.get("name", "")
                        disp = f"{code} - {c_name}" if c_name else code
                        rgb_raw = c.get("rgb", [0.8, 0.8, 0.8])
                        rgb = (float(rgb_raw[0]), float(rgb_raw[1]), float(rgb_raw[2]))
                        item = LibraryMaterialItem(
                            name=disp,
                            category_id="colors",
                            category_name="Colors",
                            stock_type="🎨 Colors (Finish / Sheet)",
                            packing_mode="Sheet",
                            rgb=rgb,
                        )
                        self.items.append(item)
                        self.by_name[disp.lower()] = item
                        if code:
                            self.by_name[code.lower()] = item
                        if c_name:
                            self.by_name[c_name.lower()] = item
                self.category_counts["colors"] = ral_count
            except Exception as err:
                sys.stderr.write(f"[CutList] Error loading ral.json: {err}\n")

    def find_material(self, name: str, scene: Any = None) -> Optional[LibraryMaterialItem]:
        if not name:
            return None
        nl = name.lower().strip()
        if nl in self.by_name:
            return self.by_name[nl]

        # Check scene.materials for texture embeddings (e.g. goldr rr -> pine.jpg)
        if scene and hasattr(scene, "materials"):
            raw_mats = scene.materials
            mat_list = raw_mats if isinstance(raw_mats, list) else list(raw_mats.values())
            for m in mat_list:
                m_name = m.get("name") if isinstance(m, dict) else getattr(m, "name", str(m))
                if m_name == name:
                    tex = m.get("texture") if isinstance(m, dict) else getattr(m, "texture", None)
                    if isinstance(tex, dict):
                        embed = tex.get("embed") or tex.get("path")
                        if embed:
                            fn = Path(embed).stem.lower()
                            if "-" in fn:
                                fn = fn.split("-", 1)[1]
                            if fn in self.by_name:
                                return self.by_name[fn]

        for k, v in self.by_name.items():
            if nl == k or (len(nl) >= 3 and (nl in k or k in nl)):
                return v

        return None


_GLOBAL_LIB: Optional[MaterialLibrary] = None


def get_material_library() -> MaterialLibrary:
    global _GLOBAL_LIB
    if _GLOBAL_LIB is None:
        _GLOBAL_LIB = MaterialLibrary()
    return _GLOBAL_LIB


def is_linear_stock(stock_type: str) -> bool:
    """Returns True if the stock type uses 1D linear cut diagrams, False for 2D sheet nesting."""
    if stock_type == "Solid":
        return True
    if stock_type == "Sheet":
        return False
    st = stock_type.lower()
    if any(kw in st for kw in ["sheet", "plywood", "tile", "fabric", "pane", "mdf", "panel", "slab", "roll"]):
        return False
    if any(kw in st for kw in ["solid", "lumber", "bar", "rod", "tube", "linear", "wood (solid"]):
        return True
    return False


def get_stock_display_info(stock_type: str) -> Tuple[str, str, str]:
    """Returns (icon, category_display, unit_label) for a stock type string."""
    st = stock_type.lower()
    if "metal" in st:
        if is_linear_stock(stock_type):
            return "🔩", "Metal", "Bars"
        return "🔲", "Metal", "Sheets"
    elif "floor" in st:
        return "🪵", "Flooring", "Tiles"
    elif "color" in st:
        return "🎨", "Colors", "Sheets"
    elif "glass" in st:
        return "🪟", "Glass", "Panes"
    elif "fabric" in st:
        return "🧵", "Fabric", "Rolls"
    elif "masonry" in st or "stone" in st or "brick" in st:
        return "🧱", "Masonry", "Slabs"
    elif "wood" in st:
        if is_linear_stock(stock_type):
            return "🌲", "Wood", "Boards"
        return "🔲", "Wood", "Sheets"
    if is_linear_stock(stock_type):
        return "🌲", "Lumber", "Boards"
    return "🔲", "Sheet Goods", "Sheets"


def detect_material_type(material_name: str, width: float = 0.0, thickness: float = 0.0, scene: Any = None) -> str:
    """Detects stock type following the IngeTrazo Material Library category.
    Returns 'Solid' or 'Sheet'.
    """
    if not material_name:
        return "Solid"

    name_lower = material_name.lower().strip()
    for kw in SHEET_KEYWORDS:
        if kw in name_lower:
            return "Sheet"

    lib = get_material_library()
    item = lib.find_material(material_name, scene=scene)
    if item is not None:
        return item.packing_mode

    for kw in SOLID_KEYWORDS:
        if kw in name_lower:
            return "Solid"
    if (0 < width <= 0.250) or (thickness >= 0.025):
        return "Solid"
    return "Sheet"


def get_material_stock_label(material_name: str, width: float = 0.0, thickness: float = 0.0, scene: Any = None) -> str:
    """Returns the descriptive stock type label following library category."""
    name_l = material_name.lower().strip()
    for kw in SHEET_KEYWORDS:
        if kw in name_l:
            if any(mkw in name_l for mkw in ["metal", "steel", "iron", "aluminum", "brass"]):
                return "🔲 Metal (Sheet Metal)"
            return "🔲 Wood (Sheet / Plywood)"

    lib = get_material_library()
    item = lib.find_material(material_name, scene=scene)
    if item is not None:
        return item.stock_type

    pm = detect_material_type(material_name, width=width, thickness=thickness, scene=scene)
    if any(kw in name_l for kw in ["metal", "steel", "iron", "aluminum", "brass"]):
        return "🔩 Metal (Bar Stock)" if pm == "Solid" else "🔲 Metal (Sheet Metal)"
    elif any(kw in name_l for kw in ["floor", "parquet", "tile"]):
        return "🪵 Flooring (Planks / Tiles)"
    elif any(kw in name_l for kw in ["ral", "rgb(", "#", "paint", "color"]):
        return "🎨 Colors (Finish / Sheet)"
    return "🌲 Wood (Solid Lumber)" if pm == "Solid" else "🔲 Wood (Sheet / Plywood)"


def get_tag_letter(idx: int) -> str:
    """Generate part callout tags: A, B, ... Z, AA, AB..."""
    if idx < 26:
        return chr(ord("A") + idx)
    first = chr(ord("A") + (idx // 26) - 1)
    second = chr(ord("A") + (idx % 26))
    return f"{first}{second}"


# ---------------------------------------------------------------------------
# Procedural Icon Generator
# ---------------------------------------------------------------------------
def create_cutlist_icon() -> Any:
    if not QT_AVAILABLE:
        return None
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)

    p.setPen(QPen(QColor("#7c4a1e"), 2))
    p.setBrush(QBrush(QColor("#d4a373")))
    p.drawRoundedRect(6, 6, 52, 52, 4, 4)

    p.setPen(QPen(QColor("#583101"), 1.5))
    p.setBrush(QBrush(QColor("#faedcd")))
    p.drawRect(10, 10, 28, 22)
    p.drawRect(10, 34, 28, 20)
    p.drawRect(40, 10, 14, 44)

    p.setPen(QPen(QColor("#e63946"), 1.5, Qt.DashLine))
    p.drawLine(39, 8, 39, 56)
    p.drawLine(8, 33, 39, 33)

    p.end()
    return QIcon(pix)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
@dataclass
class RawPart:
    name: str
    length: float       # metres, largest dimension (L >= W >= T)
    width: float        # metres, middle dimension
    thickness: float    # metres, smallest dimension
    material: str
    group_ref: Any = None
    min_x: float = 0.0
    max_x: float = 0.0
    min_y: float = 0.0
    max_y: float = 0.0
    min_z: float = 0.0
    max_z: float = 0.0
    tag: str = ""
    # Actual 3D mesh faces: List of (vertex_tuples, normal_tuple)
    faces_3d: List[Tuple[List[Tuple[float, float, float]], Tuple[float, float, float]]] = field(default_factory=list)
    # Normalized 2D contour in [0, 1] x [0, 1] (Length x Width)
    contour_2d: Optional[List[Tuple[float, float]]] = None

    @property
    def center(self) -> Tuple[float, float, float]:
        return (
            (self.min_x + self.max_x) / 2.0,
            (self.min_y + self.max_y) / 2.0,
            (self.min_z + self.max_z) / 2.0,
        )


@dataclass
class CutListEntry:
    tag: str
    display_name: str
    count: int
    length: float       # metres
    width: float        # metres
    thickness: float    # metres
    material: str
    names: List[str] = field(default_factory=list)
    contour_2d: Optional[List[Tuple[float, float]]] = None

    @property
    def unit_area(self) -> float:
        return self.length * self.width

    @property
    def total_area(self) -> float:
        return self.unit_area * self.count

    @property
    def unit_volume(self) -> float:
        return self.length * self.width * self.thickness

    @property
    def total_volume(self) -> float:
        return self.unit_volume * self.count


# --- Sheet Goods Models ---
@dataclass
class PlacedPart:
    name: str
    x: float
    y: float
    width: float
    height: float
    rotated: bool = False
    contour_2d: Optional[List[Tuple[float, float]]] = None


@dataclass
class SheetLayout:
    index: int
    sheet_width: float
    sheet_height: float
    material: str
    placed_parts: List[PlacedPart] = field(default_factory=list)

    @property
    def used_area(self) -> float:
        return sum(p.width * p.height for p in self.placed_parts)

    @property
    def total_sheet_area(self) -> float:
        return self.sheet_width * self.sheet_height

    @property
    def yield_percentage(self) -> float:
        if self.total_sheet_area <= 1e-6:
            return 0.0
        return (self.used_area / self.total_sheet_area) * 100.0

    @property
    def waste_percentage(self) -> float:
        return max(0.0, 100.0 - self.yield_percentage)


# --- Solid Wood Lumber Models ---
@dataclass
class LumberCut:
    name: str
    x: float
    length: float
    width: float
    thickness: float
    contour_2d: Optional[List[Tuple[float, float]]] = None


@dataclass
class LumberBoard:
    index: int
    material: str
    stock_length: float
    width: float
    thickness: float
    cuts: List[LumberCut] = field(default_factory=list)

    @property
    def used_length(self) -> float:
        return sum(c.length for c in self.cuts)

    @property
    def yield_percentage(self) -> float:
        if self.stock_length <= 1e-6:
            return 0.0
        return min(100.0, (self.used_length / self.stock_length) * 100.0)

    @property
    def waste_percentage(self) -> float:
        return max(0.0, 100.0 - self.yield_percentage)

    @property
    def offcut_length(self) -> float:
        return max(0.0, self.stock_length - self.used_length)


# ---------------------------------------------------------------------------
# Geometry, Faces & Contour Extraction
# ---------------------------------------------------------------------------
def _get_vertex_xyz(vertex: Any) -> Optional[Tuple[float, float, float]]:
    pos = getattr(vertex, "position", vertex)
    if hasattr(pos, "x") and callable(pos.x):
        return (float(pos.x()), float(pos.y()), float(pos.z()))
    elif hasattr(pos, "x"):
        return (float(pos.x), float(pos.y), float(pos.z))
    elif isinstance(pos, (list, tuple)) and len(pos) >= 3:
        return (float(pos[0]), float(pos[1]), float(pos[2]))
    return None


def _extract_material_name(group: Any) -> str:
    mat = getattr(group, "material", None)
    if mat:
        if isinstance(mat, dict):
            name = mat.get("mat") or mat.get("name")
            if name:
                return str(name)
            col = mat.get("color") or mat.get("rgb")
            if col:
                r, g, b = (int(round(c * 255)) for c in col[:3])
                return f"rgb({r},{g},{b})"
        elif isinstance(mat, str):
            return mat

    mesh = getattr(group, "mesh", None)
    faces = getattr(mesh, "faces", None) if mesh else None
    if faces:
        for f in faces:
            attrs = getattr(f, "attrs", None)
            if attrs and isinstance(attrs, dict):
                mat_name = attrs.get("mat")
                if mat_name:
                    return str(mat_name)
                tex = attrs.get("texture")
                if isinstance(tex, dict) and tex.get("path"):
                    from pathlib import Path
                    return Path(tex["path"]).stem
                col = attrs.get("color")
                if col:
                    r, g, b = (int(round(c * 255)) for c in col[:3])
                    return f"rgb({r},{g},{b})"
    return "Default"


def get_material_texture_file(material_name: str, scene: Any = None) -> Optional[str]:
    """Finds the texture file path on disk for a given material in IngeTrazo.

    Searches:
      1. scene.materials for embed / path references
      2. scene.groups for material texture references
      3. LOCALAPPDATA/IngeTrazo/textures/embedded/
      4. LOCALAPPDATA/IngeTrazo/textures/
    """
    if not material_name:
        return None

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    tex_dir = Path(local_app_data) / "IngeTrazo" / "textures" if local_app_data else None

    # 1. Search scene.materials
    if scene and hasattr(scene, "materials"):
        raw_mats = scene.materials
        mat_list = raw_mats if isinstance(raw_mats, list) else list(raw_mats.values())
        for m in mat_list:
            name = m.get("name") if isinstance(m, dict) else getattr(m, "name", str(m))
            if name == material_name:
                tex = m.get("texture") if isinstance(m, dict) else getattr(m, "texture", None)
                if isinstance(tex, dict):
                    embed = tex.get("embed") or tex.get("path")
                    if embed:
                        if os.path.isabs(embed) and os.path.exists(embed):
                            return embed
                        if tex_dir and tex_dir.exists():
                            fname = Path(embed).name
                            cand = tex_dir / "embedded" / fname
                            if cand.exists():
                                return str(cand)
                            cand2 = tex_dir / embed
                            if cand2.exists():
                                return str(cand2)
                            for match in tex_dir.rglob(fname):
                                if match.is_file():
                                    return str(match)

    # 2. Search scene.groups
    if scene and hasattr(scene, "groups"):
        groups = getattr(scene, "groups", [])
        for g in groups:
            mat = getattr(g, "material", None)
            if isinstance(mat, dict):
                m_name = mat.get("mat") or mat.get("name")
                if m_name == material_name:
                    tex = mat.get("texture")
                    if isinstance(tex, dict):
                        embed = tex.get("embed") or tex.get("path")
                        if embed:
                            if os.path.isabs(embed) and os.path.exists(embed):
                                return embed
                            if tex_dir and tex_dir.exists():
                                fname = Path(embed).name
                                cand = tex_dir / "embedded" / fname
                                if cand.exists():
                                    return str(cand)
                                for match in tex_dir.rglob(fname):
                                    if match.is_file():
                                        return str(match)

    # 3. Fallback disk lookup in IngeTrazo textures/embedded/
    if tex_dir and tex_dir.exists():
        embedded_dir = tex_dir / "embedded"
        if embedded_dir.exists():
            sanitized = material_name.lower().replace(" ", "_").replace("-", "_")
            for f in embedded_dir.glob("*"):
                if f.is_file() and sanitized in f.name.lower():
                    return str(f)

        # 4. Search entire textures directory
        sanitized = material_name.lower().replace(" ", "_").replace("-", "_")
        for f in tex_dir.rglob("*"):
            if f.is_file() and sanitized in f.name.lower():
                return str(f)

    # 5. Search IngeTrazo material library textures directory
    lib = get_material_library()
    it = lib.find_material(material_name, scene=scene)
    if it and it.texture_file and os.path.exists(it.texture_file):
        return it.texture_file

    _, _, lib_tex_dir = get_library_paths()
    if lib_tex_dir and lib_tex_dir.exists():
        sanitized = material_name.lower().replace(" ", "_").replace("-", "_")
        for f in lib_tex_dir.rglob("*"):
            if f.is_file() and (sanitized == f.stem.lower() or sanitized in f.name.lower()):
                return str(f)

    return None


def parse_material_color(material_name: str, scene: Any = None) -> Optional[Any]:
    """Attempts to extract a QColor from material_name or scene.materials."""
    if not QT_AVAILABLE or not material_name:
        return None

    if material_name.startswith("rgb(") and material_name.endswith(")"):
        parts = material_name[4:-1].split(",")
        if len(parts) == 3:
            try:
                r, g, b = [int(p.strip()) for p in parts]
                return QColor(r, g, b)
            except Exception:
                pass

    if material_name.startswith("#") and len(material_name) in (4, 7, 9):
        try:
            return QColor(material_name)
        except Exception:
            pass

    if scene and hasattr(scene, "materials"):
        raw_mats = scene.materials
        mat_list = raw_mats if isinstance(raw_mats, list) else list(raw_mats.values())
        for m in mat_list:
            name = m.get("name") if isinstance(m, dict) else getattr(m, "name", str(m))
            if name == material_name:
                col = m.get("color") if isinstance(m, dict) else getattr(m, "color", None)
                if not col and isinstance(m, dict):
                    col = m.get("rgb")
                if col and isinstance(col, (list, tuple)) and len(col) >= 3:
                    try:
                        r, g, b = (int(round(c * 255)) for c in col[:3])
                        return QColor(r, g, b)
                    except Exception:
                        pass

    # Check RAL colors from IngeTrazo material library
    lib = get_material_library()
    it = lib.find_material(material_name, scene=scene)
    if it and it.rgb:
        r, g, b = (int(round(c * 255)) for c in it.rgb[:3])
        return QColor(r, g, b)

    return None


def get_material_thumbnail(
    material_name: str,
    scene: Any = None,
    size: int = 22,
    cache: Optional[Dict[str, Tuple[Any, Any]]] = None,
) -> Tuple[Any, Any]:
    """Generates a (QPixmap, QIcon) thumbnail for a material.

    1. Loads texture image from disk if available (clipped to rounded rectangle).
    2. Fills with solid color if RGB color is present.
    3. Renders IngeTrazo default split diagonal swatch (off-white / slate blue-gray).
    Draws a subtle rounded border around all swatches.
    Returns (None, None) if Qt is not available.
    """
    if not QT_AVAILABLE:
        return (None, None)

    cache_key = f"{material_name}::{size}"
    if cache is not None and cache_key in cache:
        return cache[cache_key]

    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    try:
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        clip_rect = QRectF(1.0, 1.0, float(size - 2), float(size - 2))
        radius = 3.5
        clip_path = QPainterPath()
        clip_path.addRoundedRect(clip_rect, radius, radius)

        painter.save()
        painter.setClipPath(clip_path)

        loaded_image = False
        tex_path = get_material_texture_file(material_name, scene=scene)
        if tex_path and os.path.exists(tex_path):
            img = QImage(tex_path)
            if not img.isNull():
                scaled = img.scaled(
                    size, size,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                x_off = (scaled.width() - size) / 2.0
                y_off = (scaled.height() - size) / 2.0
                painter.drawImage(
                    QRectF(0, 0, float(size), float(size)),
                    scaled,
                    QRectF(x_off, y_off, float(size), float(size)),
                )
                loaded_image = True

        if not loaded_image:
            col = parse_material_color(material_name, scene=scene)
            if col is not None:
                painter.fillRect(clip_rect, QBrush(col))
            else:
                # Procedural IngeTrazo diagonal split swatch for default / untextured materials
                poly_top = QPolygonF([
                    QPointF(clip_rect.left(), clip_rect.top()),
                    QPointF(clip_rect.right(), clip_rect.top()),
                    QPointF(clip_rect.left(), clip_rect.bottom()),
                ])
                poly_bot = QPolygonF([
                    QPointF(clip_rect.right(), clip_rect.top()),
                    QPointF(clip_rect.right(), clip_rect.bottom()),
                    QPointF(clip_rect.left(), clip_rect.bottom()),
                ])
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor("#f8fafc")))
                painter.drawPolygon(poly_top)
                painter.setBrush(QBrush(QColor("#94a3b8")))
                painter.drawPolygon(poly_bot)

        painter.restore()

        # Border
        border_pen = QPen(QColor(100, 116, 139, 180), 1.0)
        painter.setPen(border_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(clip_path)

    finally:
        painter.end()

    icon = QIcon(pixmap)
    result = (pixmap, icon)
    if cache is not None:
        cache[cache_key] = result
    return result


def extract_group_3d_faces(group: Any) -> List[Tuple[List[Tuple[float, float, float]], Tuple[float, float, float]]]:
    """Extract actual 3D mesh faces with vertices in world space and normals.

    Handles instances/components via iter_placements to preserve exact curved
    geometry (arches, mouldings, profiles, cutouts).
    """
    faces_3d: List[Tuple[List[Tuple[float, float, float]], Tuple[float, float, float]]] = []
    if group is None:
        return faces_3d

    try:
        from core.group import iter_placements
        placements = list(iter_placements(group))
    except Exception:
        placements = [(group, getattr(group, "xform", None))]

    for g, m in placements:
        mesh = getattr(g, "mesh", None)
        if mesh is None:
            continue
        faces = getattr(mesh, "faces", None) or []
        for f in faces:
            # Compute or extract normal
            norm_coords = (0.0, 0.0, 1.0)
            norm_fn = getattr(f, "normal", None)
            if callable(norm_fn):
                try:
                    norm = norm_fn()
                    if m is not None and hasattr(m, "mapVector"):
                        norm = m.mapVector(norm).normalized()
                    norm_coords = (float(norm.x()), float(norm.y()), float(norm.z()))
                except Exception:
                    pass
            elif hasattr(f, "normal") and not callable(f.normal):
                n_c = _get_vertex_xyz(f.normal)
                if n_c:
                    norm_coords = n_c

            # If the face has holes, triangulate it to avoid filling across cutouts/openings
            hole_loops = getattr(f, "hole_loops", None)
            if hole_loops and len(hole_loops) > 0 and hasattr(f, "triangulate") and callable(f.triangulate):
                try:
                    tris = f.triangulate()
                    for t in tris:
                        tri_verts: List[Tuple[float, float, float]] = []
                        for p in t:
                            if m is not None and hasattr(m, "map"):
                                try:
                                    p = m.map(p)
                                except Exception:
                                    pass
                            xyz = _get_vertex_xyz(p)
                            if xyz:
                                tri_verts.append(xyz)
                        if len(tri_verts) == 3:
                            faces_3d.append((tri_verts, norm_coords))
                    continue
                except Exception:
                    pass

            loop = getattr(f, "loop", None)
            if not loop or len(loop) < 3:
                continue

            verts: List[Tuple[float, float, float]] = []
            for v in loop:
                pos = getattr(v, "position", v)
                if m is not None and hasattr(m, "map"):
                    try:
                        pos = m.map(pos)
                    except Exception:
                        pass
                coords = _get_vertex_xyz(pos)
                if coords:
                    verts.append(coords)

            if len(verts) < 3:
                continue

            faces_3d.append((verts, norm_coords))

    return faces_3d


def extract_2d_contour_from_faces(
    faces_3d: List[Tuple[List[Tuple[float, float, float]], Tuple[float, float, float]]]
) -> Optional[List[Tuple[float, float]]]:
    """Extract the primary 2D profile contour of a part normalized into [0, 1] x [0, 1].

    Finds the largest face (e.g. the face of an arched panel or curved moulding)
    and projects its outer perimeter into normalized coordinates.
    """
    if not faces_3d:
        return None

    best_face = None
    best_area = -1.0

    for verts, norm in faces_3d:
        if len(verts) < 3:
            continue
        xs = [v[0] for v in verts]
        ys = [v[1] for v in verts]
        zs = [v[2] for v in verts]
        dx = max(xs) - min(xs)
        dy = max(ys) - min(ys)
        dz = max(zs) - min(zs)
        dims = sorted([dx, dy, dz], reverse=True)
        area_approx = dims[0] * dims[1]
        if area_approx > best_area:
            best_area = area_approx
            best_face = (verts, dx, dy, dz)

    if not best_face or best_area < 1e-6:
        return None

    verts, dx, dy, dz = best_face
    spans = [("x", dx), ("y", dy), ("z", dz)]
    spans.sort(key=lambda a: a[1], reverse=True)

    ax1, span1 = spans[0]
    ax2, span2 = spans[1]
    if span1 < 1e-4 or span2 < 1e-4:
        return None

    idx1 = 0 if ax1 == "x" else (1 if ax1 == "y" else 2)
    idx2 = 0 if ax2 == "x" else (1 if ax2 == "y" else 2)

    vals1 = [v[idx1] for v in verts]
    vals2 = [v[idx2] for v in verts]
    min1, max1 = min(vals1), max(vals1)
    min2, max2 = min(vals2), max(vals2)
    s1, s2 = max1 - min1, max2 - min2

    # Map larger dimension to X [0, 1] (Length) and smaller to Y [0, 1] (Width)
    if s1 >= s2:
        return [((v[idx1] - min1) / s1, (v[idx2] - min2) / s2) for v in verts]
    else:
        return [((v[idx2] - min2) / s2, (v[idx1] - min1) / s1) for v in verts]


def extract_group_bounds(group: Any) -> Optional[Tuple[Tuple[float, float, float], Tuple[float, float, float, float, float, float]]]:
    if group is None or getattr(group, "billboard", False):
        return None

    points: List[Tuple[float, float, float]] = []
    mesh = getattr(group, "mesh", None)
    if mesh is not None:
        vertices = getattr(mesh, "vertices", None)
        if vertices:
            for v in vertices:
                xyz = _get_vertex_xyz(v)
                if xyz is not None:
                    points.append(xyz)

    if not points:
        try:
            from core.group import placement_points
            arr = placement_points(group)
            if arr is not None and len(arr) > 0:
                points = [(float(r[0]), float(r[1]), float(r[2])) for r in arr]
        except Exception:
            pass

    if not points:
        return None

    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    min_z, max_z = min(zs), max(zs)

    dx = max_x - min_x
    dy = max_y - min_y
    dz = max_z - min_z

    dims = sorted([dx, dy, dz], reverse=True)
    length, width, thickness = dims[0], dims[1], dims[2]

    if length < 1e-6:
        return None

    return (length, width, thickness), (min_x, max_x, min_y, max_y, min_z, max_z)


def calculate_group_dimensions(group: Any) -> Optional[Tuple[float, float, float]]:
    res = extract_group_bounds(group)
    return res[0] if res else None


def is_component(obj: Any) -> bool:
    """Determine whether a scene entity represents a component instance (a manufactured part)."""
    if obj is None or getattr(obj, "billboard", False):
        return False
    # 1. Native IngeTrazo Group.is_component()
    if hasattr(obj, "is_component") and callable(obj.is_component):
        try:
            return bool(obj.is_component())
        except Exception:
            pass
    # 2. Group carries component flag (true for components, None/false for groups)
    if bool(getattr(obj, "component", False)):
        return True
    # 3. Explicit component naming
    name = str(getattr(obj, "name", "")).strip().lower()
    if name.startswith("component"):
        return True
    return False


def get_selected_groups(scene: Any) -> List[Any]:
    """Extract leaf parts from selection or scene, ignoring organizational grouping containers.

    In woodworking CAD workflows (like OpenCutList), groups are frequently used as organizational
    folders/assemblies (e.g. 'Cabinet', 'Door Assembly') while actual parts to cut are modeled
    as Components. If grouping containers are selected, this drills down through all group
    hierarchies to extract the individual Components, ensuring every part can be separated
    and exploded individually.
    """
    if scene is None:
        return []
    selection = getattr(scene, "selection", None) or []
    target_items = list(selection) if selection else list(getattr(scene, "groups", []) or [])

    found_components: List[Any] = []
    plain_groups: List[Any] = []
    seen = set()

    def collect(obj: Any) -> None:
        if obj is None or getattr(obj, "billboard", False):
            return
        if id(obj) in seen:
            return
        seen.add(id(obj))

        kids = getattr(obj, "children", None) or ()
        obj_is_comp = is_component(obj)

        if obj_is_comp:
            # If this component itself contains nested sub-components, recurse into them
            child_comps = [k for k in kids if is_component(k) or getattr(k, "children", None)]
            if child_comps:
                for k in kids:
                    collect(k)
            else:
                found_components.append(obj)
        elif kids:
            # It's an organizational Group: IGNORE GROUPING, drill down into children!
            for k in kids:
                collect(k)
        elif (
            getattr(obj, "mesh", None) is not None
            and (len(getattr(obj.mesh, "faces", [])) > 0 or len(getattr(obj.mesh, "vertices", [])) > 0)
        ) or calculate_group_dimensions(obj) is not None:
            plain_groups.append(obj)

    for item in target_items:
        # If the item is a sub-mesh entity (face or edge), resolve to its owner
        if hasattr(item, "owner") and getattr(item, "mesh", None) is None and not getattr(item, "children", None):
            item = getattr(item, "owner", None) or item
        collect(item)

    # If components are found, ignore grouping and return ONLY components
    if found_components:
        return found_components
    return plain_groups


def extract_parts_from_groups(groups: List[Any]) -> List[RawPart]:
    parts: List[RawPart] = []
    for idx, group in enumerate(groups):
        try:
            res = extract_group_bounds(group)
            if res is None:
                continue

            (length, width, thickness), (min_x, max_x, min_y, max_y, min_z, max_z) = res
            name = getattr(group, "name", None) or f"Part {idx + 1}"
            material = _extract_material_name(group)

            # Extract true 3D mesh faces and 2D contour shape
            faces_3d = extract_group_3d_faces(group)
            contour_2d = extract_2d_contour_from_faces(faces_3d)

            # Re-align world bounds to actual world-transformed vertices if present
            if faces_3d:
                all_xs = [v[0] for face_verts, _ in faces_3d for v in face_verts]
                all_ys = [v[1] for face_verts, _ in faces_3d for v in face_verts]
                all_zs = [v[2] for face_verts, _ in faces_3d for v in face_verts]
                if all_xs and all_ys and all_zs:
                    min_x, max_x = min(all_xs), max(all_xs)
                    min_y, max_y = min(all_ys), max(all_ys)
                    min_z, max_z = min(all_zs), max(all_zs)

            parts.append(
                RawPart(
                    name=str(name),
                    length=length,
                    width=width,
                    thickness=thickness,
                    material=material,
                    group_ref=group,
                    min_x=min_x,
                    max_x=max_x,
                    min_y=min_y,
                    max_y=max_y,
                    min_z=min_z,
                    max_z=max_z,
                    faces_3d=faces_3d,
                    contour_2d=contour_2d,
                )
            )
        except Exception as err:
            sys.stderr.write(f"[CutList] Error reading group {idx}: {err}\n")
    return parts


def group_parts(
    parts: List[RawPart],
    merge_by_dimensions: bool = True,
    tolerance_metres: float = 0.0005,
) -> List[CutListEntry]:
    def quantize(val: float) -> int:
        return int(round(val / tolerance_metres))

    groups_map: Dict[Tuple, Dict[str, Any]] = {}

    for part in parts:
        q_len = quantize(part.length)
        q_wid = quantize(part.width)
        q_thk = quantize(part.thickness)

        if merge_by_dimensions:
            key = (q_len, q_wid, q_thk, part.material)
        else:
            key = (part.name, q_len, q_wid, q_thk, part.material)

        if key not in groups_map:
            groups_map[key] = {
                "names": [part.name],
                "count": 1,
                "length": part.length,
                "width": part.width,
                "thickness": part.thickness,
                "material": part.material,
                "parts": [part],
                "contour_2d": part.contour_2d,
            }
        else:
            entry = groups_map[key]
            entry["count"] += 1
            entry["parts"].append(part)
            if not entry["contour_2d"] and part.contour_2d:
                entry["contour_2d"] = part.contour_2d
            if part.name not in entry["names"]:
                entry["names"].append(part.name)

    results: List[CutListEntry] = []
    # Separate entries by material and sort according to thickness descending (then length, width)
    sorted_items = sorted(
        groups_map.values(),
        key=lambda item: (
            str(item["material"]).strip().lower(),
            -item["thickness"],
            -item["length"],
            -item["width"],
        ),
    )

    for idx, entry in enumerate(sorted_items):
        tag = get_tag_letter(idx)
        for p in entry["parts"]:
            p.tag = tag

        names_list = entry["names"]
        if len(names_list) == 1:
            disp_name = names_list[0]
        else:
            disp_name = ", ".join(names_list[:3])
            if len(names_list) > 3:
                disp_name += f" (+{len(names_list) - 3} more)"

        results.append(
            CutListEntry(
                tag=tag,
                display_name=disp_name,
                count=entry["count"],
                length=entry["length"],
                width=entry["width"],
                thickness=entry["thickness"],
                material=entry["material"],
                names=names_list,
                contour_2d=entry["contour_2d"],
            )
        )

    return results


# ---------------------------------------------------------------------------
# 1D Linear Lumber Packing Engine (Solid Wood)
# ---------------------------------------------------------------------------
def pack_linear_lumber(
    entries: List[CutListEntry],
    stock_length: float = 2.400,
    kerf: float = 0.003,
    margin: float = 0.015,
) -> List[LumberBoard]:
    pieces = []
    for e in entries:
        for _ in range(e.count):
            pieces.append({
                "name": e.display_name,
                "length": e.length,
                "width": e.width,
                "thickness": e.thickness,
                "material": e.material,
                "contour_2d": e.contour_2d,
            })

    by_profile: Dict[Tuple[str, float, float], List[Dict[str, Any]]] = {}
    for p in pieces:
        k = (p["material"], round(p["width"], 3), round(p["thickness"], 3))
        by_profile.setdefault(k, []).append(p)

    boards: List[LumberBoard] = []
    board_counter = 1

    for (mat, prof_w, prof_t), items in by_profile.items():
        items.sort(key=lambda x: x["length"], reverse=True)
        usable_len = stock_length - (2 * margin)

        for item in items:
            cut_len = item["length"]
            placed = False

            for b in [b for b in boards if b.material == mat and abs(b.width - prof_w) < 1e-4 and abs(b.thickness - prof_t) < 1e-4]:
                rem = (stock_length - margin) - b.cuts[-1].x - b.cuts[-1].length - kerf if b.cuts else usable_len
                if cut_len <= rem:
                    next_x = b.cuts[-1].x + b.cuts[-1].length + kerf if b.cuts else margin
                    b.cuts.append(LumberCut(item["name"], next_x, cut_len, prof_w, prof_t, contour_2d=item["contour_2d"]))
                    placed = True
                    break

            if not placed:
                actual_stock = cut_len + (2 * margin) if cut_len > usable_len else stock_length
                new_board = LumberBoard(
                    index=board_counter,
                    material=mat,
                    stock_length=actual_stock,
                    width=prof_w,
                    thickness=prof_t,
                    cuts=[LumberCut(item["name"], margin, cut_len, prof_w, prof_t, contour_2d=item["contour_2d"])],
                )
                boards.append(new_board)
                board_counter += 1

    return boards


# ---------------------------------------------------------------------------
# 2D Guillotine Sheet Nesting Engine (Plywood/MDF)
# ---------------------------------------------------------------------------
def pack_sheets(
    entries: List[CutListEntry],
    sheet_w: float,
    sheet_h: float,
    kerf: float = 0.003,
    margin: float = 0.010,
    allow_rotate: bool = True,
) -> List[SheetLayout]:
    pieces = []
    for e in entries:
        for _ in range(e.count):
            pieces.append({
                "name": e.display_name,
                "w": e.length,
                "h": e.width,
                "material": e.material,
                "contour_2d": e.contour_2d,
            })

    by_material: Dict[str, List[Dict[str, Any]]] = {}
    for p in pieces:
        by_material.setdefault(p["material"], []).append(p)

    all_sheets: List[SheetLayout] = []
    sheet_counter = 1

    for mat, mat_pieces in by_material.items():
        mat_pieces.sort(key=lambda p: (p["w"] * p["h"], max(p["w"], p["h"])), reverse=True)

        usable_w = sheet_w - (2 * margin)
        usable_h = sheet_h - (2 * margin)
        mat_sheets: List[Dict[str, Any]] = []

        for piece in mat_pieces:
            pw, ph = piece["w"], piece["h"]
            placed = False

            for s in mat_sheets:
                for shelf in s["shelves"]:
                    if pw <= shelf["rem_w"] and ph <= shelf["h"]:
                        shelf["parts"].append(PlacedPart(piece["name"], shelf["cur_x"], shelf["cur_y"], pw, ph, rotated=False, contour_2d=piece["contour_2d"]))
                        shelf["cur_x"] += pw + kerf
                        shelf["rem_w"] -= (pw + kerf)
                        placed = True
                        break
                    if allow_rotate and ph <= shelf["rem_w"] and pw <= shelf["h"]:
                        shelf["parts"].append(PlacedPart(piece["name"], shelf["cur_x"], shelf["cur_y"], ph, pw, rotated=True, contour_2d=piece["contour_2d"]))
                        shelf["cur_x"] += ph + kerf
                        shelf["rem_w"] -= (ph + kerf)
                        placed = True
                        break
                if placed:
                    break

                cur_y = s["shelves"][-1]["cur_y"] + s["shelves"][-1]["h"] + kerf if s["shelves"] else margin
                orientations = [(pw, ph, False), (ph, pw, True)] if allow_rotate else [(pw, ph, False)]
                for w_try, h_try, rot in orientations:
                    if w_try <= usable_w and (cur_y + h_try) <= (sheet_h - margin):
                        new_shelf = {
                            "cur_x": margin + w_try + kerf,
                            "cur_y": cur_y,
                            "h": h_try,
                            "rem_w": usable_w - w_try - kerf,
                            "parts": [PlacedPart(piece["name"], margin, cur_y, w_try, h_try, rotated=rot, contour_2d=piece["contour_2d"])],
                        }
                        s["shelves"].append(new_shelf)
                        placed = True
                        break
                if placed:
                    break

            if not placed:
                new_sheet_data = {"index": sheet_counter, "material": mat, "shelves": []}
                orientations = [(pw, ph, False), (ph, pw, True)] if allow_rotate else [(pw, ph, False)]
                for w_try, h_try, rot in orientations:
                    if w_try <= usable_w and (margin + h_try) <= (sheet_h - margin):
                        new_shelf = {
                            "cur_x": margin + w_try + kerf,
                            "cur_y": margin,
                            "h": h_try,
                            "rem_w": usable_w - w_try - kerf,
                            "parts": [PlacedPart(piece["name"], margin, margin, w_try, h_try, rotated=rot, contour_2d=piece["contour_2d"])],
                        }
                        new_sheet_data["shelves"].append(new_shelf)
                        placed = True
                        break

                if placed:
                    mat_sheets.append(new_sheet_data)
                    sheet_counter += 1

        for s in mat_sheets:
            placed_list = []
            for sh in s["shelves"]:
                placed_list.extend(sh["parts"])
            all_sheets.append(
                SheetLayout(
                    index=s["index"],
                    sheet_width=sheet_w,
                    sheet_height=sheet_h,
                    material=s["material"],
                    placed_parts=placed_list,
                )
            )

    return all_sheets


# ---------------------------------------------------------------------------
# Console Formatter
# ---------------------------------------------------------------------------
def format_console_table(entries: List[CutListEntry], unit: str = "mm") -> str:
    if not entries:
        return "\n=== INGETRAZO CUT LIST ===\n(No parts found in selection)\n"

    total_parts = sum(e.count for e in entries)
    unique_parts = len(entries)
    total_area = sum(e.total_area for e in entries)

    lines = [
        "=" * 96,
        f"{'INGETRAZO — OPEN CUT LIST':^96}",
        "=" * 96,
        f"{'Tag':>4} | {'#':>3} | {'Part Name / Description':<26} | {'Qty':>4} | {f'Length ({unit})':>11} | {f'Width ({unit})':>11} | {f'Thick ({unit})':>11} | {'Material':<12}",
        "-" * 96,
    ]

    curr_mat = None
    for i, e in enumerate(entries, start=1):
        if e.material != curr_mat:
            curr_mat = e.material
            mat_header = f"--- [ Material: {curr_mat} ] "
            lines.append(mat_header + "-" * max(4, 96 - len(mat_header)))

        name_t = e.display_name if len(e.display_name) <= 26 else (e.display_name[:23] + "...")
        mat_t = e.material if len(e.material) <= 12 else (e.material[:9] + "...")
        row = (
            f"({e.tag}) | "
            f"{i:>3} | "
            f"{name_t:<26} | "
            f"{e.count:>4} | "
            f"{format_dimension(e.length, unit):>11} | "
            f"{format_dimension(e.width, unit):>11} | "
            f"{format_dimension(e.thickness, unit):>11} | "
            f"{mat_t:<12}"
        )
        lines.append(row)

    lines.append("-" * 96)
    lines.append(f"Total Parts: {total_parts}  |  Unique Sizes: {unique_parts}  |  Total Surface Area: {format_area(total_area, unit)}")
    lines.append("=" * 96)
    return "\n" + "\n".join(lines) + "\n"


UNIT_LONG_NAMES: Dict[str, str] = {
    "mm": "Millimeter",
    "cm": "Centimeter",
    "m": "Meter",
    "in": "Inch",
    "ft": "Foot",
}


def get_project_name(viewport: Any = None) -> str:
    """Extracts project / file name from IngeTrazo viewport window or scene."""
    if viewport is not None:
        try:
            win = viewport.window() if hasattr(viewport, "window") else None
            if win and hasattr(win, "windowTitle"):
                title = win.windowTitle().strip()
                for sep in [" — IngeTrazo", " - IngeTrazo", " — ", " - "]:
                    if sep in title:
                        parts = title.split(sep)
                        if parts[0].strip():
                            return parts[0].strip()
                if title:
                    return title
        except Exception:
            pass
        scene = getattr(viewport, "scene", None)
        if scene is not None:
            for attr in ["name", "file_name", "filename", "path"]:
                val = getattr(scene, attr, None)
                if val and isinstance(val, str):
                    return Path(val).name
    return "table saw Circular.skp"


def render_cutlist_pdf(
    path: str,
    entries: List[CutListEntry],
    viewport: Any = None,
    unit: str = "mm",
    material_types: Optional[Dict[str, str]] = None,
) -> None:
    """Renders the OpenCutList-styled Parts List PDF report matching the standard
    OpenCutList workshop documentation format.
    """
    if not QT_AVAILABLE:
        # Graceful headless fallback for testing environments
        with open(path, "w", encoding="utf-8") as f:
            f.write("%PDF-1.4\n")
            f.write(f"% OpenCutList Parts List — {get_project_name(viewport)}\n")
            f.write(format_console_table(entries, unit=unit))
        return

    # Group entries by material
    by_mat: Dict[str, List[CutListEntry]] = {}
    for e in entries:
        by_mat.setdefault(e.material, []).append(e)

    scene = getattr(viewport, "scene", None) if viewport is not None else None

    pdf = QPdfWriter(path)
    pdf.setPageSize(QPageSize(QPageSize.A4))
    pdf.setPageOrientation(QPageLayout.Portrait)
    pdf.setResolution(300)

    page_w = float(pdf.width())
    page_h = float(pdf.height())
    dpi = float(pdf.resolution())
    scale = dpi / 72.0

    margin_x = 15.0 / 25.4 * dpi
    margin_y = 15.0 / 25.4 * dpi
    content_w = page_w - 2.0 * margin_x
    content_bottom = page_h - margin_y - 20.0 * scale

    # Element Heights
    h_top = 28.0 * scale
    h_doc = 22.0 * scale
    h_bar = 22.0 * scale
    h_th = 32.0 * scale
    h_row = 20.0 * scale
    h_gap = 14.0 * scale

    # Column Widths
    W = content_w
    w_col0 = round(W * 0.07)   # Type / No.
    w_col1 = round(W * 0.49)   # Material / Designation
    w_col2 = round(W * 0.12)   # Quantity / Qty.
    w_col3 = round(W * 0.106)  # Length / L
    w_col4 = round(W * 0.106)  # Area / W
    w_col5 = round(W - (w_col0 + w_col1 + w_col2 + w_col3 + w_col4))  # Volume / T
    w_sub_total = w_col3 + w_col4 + w_col5

    x_col0 = margin_x
    x_col1 = x_col0 + w_col0
    x_col2 = x_col1 + w_col1
    x_col3 = x_col2 + w_col2
    x_col4 = x_col3 + w_col3
    x_col5 = x_col4 + w_col4

    # Pass 1: Pre-calculate total pages
    y_sim = margin_y + h_top + 6.0 * scale + h_doc + h_gap
    y_sim += h_bar + h_th + len(by_mat) * h_row + h_gap
    total_pages = 1
    for mat_name, mat_entries in by_mat.items():
        if y_sim + h_bar + h_th + h_row > content_bottom:
            total_pages += 1
            y_sim = margin_y
        y_sim += h_bar + h_th
        for _ in mat_entries:
            if y_sim + h_row > content_bottom:
                total_pages += 1
                y_sim = margin_y + h_th
            y_sim += h_row
        y_sim += h_gap

    # Pass 2: Draw
    p = QPainter(pdf)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    font_title = QFont("Arial", 18)
    font_title.setBold(True)
    font_meta = QFont("Arial", 9)
    font_doc = QFont("Arial", 11)
    font_section = QFont("Arial", 10)
    font_section.setBold(True)
    font_mat_bar = QFont("Arial", 10)
    font_mat_bar.setItalic(True)
    font_th = QFont("Arial", 8.5)
    font_th.setBold(True)
    font_cell = QFont("Arial", 8.5)
    font_cell_italic = QFont("Arial", 8.5)
    font_cell_italic.setItalic(True)
    font_tag_red = QFont("Arial", 9)
    font_tag_red.setBold(True)
    font_footer = QFont("Arial", 8)

    border_pen = QPen(QColor("#000000"), max(1.0, 0.75 * scale))

    def draw_hatch(rect: QRectF) -> None:
        p.save()
        p.setClipRect(rect.adjusted(1, 1, -1, -1))
        p.setPen(QPen(QColor("#cbd5e1"), max(0.8, 0.6 * scale)))
        step = max(5, int(6.0 * scale))
        h = rect.height()
        x_s = int(rect.left()) - int(h)
        x_e = int(rect.right()) + int(h)
        for xp in range(x_s, x_e, step):
            p.drawLine(QPointF(xp, rect.bottom()), QPointF(xp + h, rect.top()))
        p.restore()

    def draw_type_glyph(center_x: float, center_y: float, sz: float) -> None:
        p.save()
        p.setPen(QPen(QColor("#475569"), max(1.0, 0.75 * scale)))
        p.setBrush(Qt.NoBrush)
        rect = QRectF(center_x - sz / 2.0, center_y - sz / 2.0, sz, sz)
        p.drawRoundedRect(rect, 1.5 * scale, 1.5 * scale)
        p.restore()

    def draw_circular_swatch(center_x: float, center_y: float, radius: float, mat: str) -> None:
        rect = QRectF(center_x - radius, center_y - radius, radius * 2.0, radius * 2.0)
        path_circle = QPainterPath()
        path_circle.addEllipse(rect)

        p.save()
        p.setClipPath(path_circle)

        col = parse_material_color(mat, scene=scene)
        tex_file = get_material_texture_file(mat, scene=scene)
        if tex_file and os.path.exists(tex_file):
            img = QImage(tex_file)
            if not img.isNull():
                p.drawImage(rect, img)
            elif col:
                p.fillRect(rect, QBrush(col))
            else:
                p.fillRect(rect, QBrush(QColor("#f1f5f9")))
        elif col:
            p.fillRect(rect, QBrush(col))
        else:
            p.fillRect(rect, QBrush(QColor("#f1f5f9")))

        p.restore()

        p.save()
        p.setPen(QPen(QColor("#475569"), max(0.8, 0.6 * scale)))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(rect)
        p.restore()

    def draw_page_footer(cur_page: int) -> None:
        p.save()
        p.setFont(font_footer)
        p.setPen(QColor("#64748b"))
        foot_y = page_h - margin_y
        p.drawText(QRectF(margin_x, foot_y, content_w / 2.0, 16.0 * scale), Qt.AlignVCenter | Qt.AlignLeft, "IngeTrazo — OpenCutList")
        p.drawText(QRectF(margin_x + content_w / 2.0, foot_y, content_w / 2.0, 16.0 * scale), Qt.AlignVCenter | Qt.AlignRight, f"Page {cur_page} of {total_pages}")
        p.restore()

    curr_page = 1
    y = margin_y

    # --- Page 1 Header ---
    p.save()
    p.setFont(font_title)
    p.setPen(QColor("#111827"))
    p.drawText(QRectF(margin_x, y, content_w * 0.5, h_top), Qt.AlignVCenter | Qt.AlignLeft, "Parts List")

    now = datetime.now()
    hr = now.hour % 12 or 12
    dt_str = f"{now.strftime('%m/%d/%Y')} {hr}:{now.strftime('%M')}{now.strftime('%p').lower()}"
    unit_long = UNIT_LONG_NAMES.get(unit, unit.title())
    meta_str = f"{dt_str}  |  {unit_long}"

    p.setFont(font_meta)
    p.setPen(QColor("#111827"))
    p.drawText(QRectF(margin_x + content_w * 0.4, y, content_w * 0.6, h_top), Qt.AlignVCenter | Qt.AlignRight, meta_str)
    p.restore()
    y += h_top + 6.0 * scale

    # Document Name Box
    p.save()
    p.setPen(border_pen)
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(margin_x, y, content_w, h_doc))
    p.setFont(font_doc)
    p.setPen(QColor("#111827"))
    proj_name = get_project_name(viewport)
    p.drawText(QRectF(margin_x, y, content_w, h_doc), Qt.AlignCenter, proj_name)
    p.restore()
    y += h_doc + h_gap

    # Summary Section
    p.save()
    p.setPen(border_pen)
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(margin_x, y, content_w, h_bar))
    p.setFont(font_section)
    p.setPen(QColor("#111827"))
    p.drawText(QRectF(margin_x + 8.0 * scale, y, content_w - 16.0 * scale, h_bar), Qt.AlignVCenter | Qt.AlignLeft, "Summary")
    p.restore()
    y += h_bar

    # Summary Column Headers
    p.save()
    p.setPen(border_pen)
    p.setBrush(Qt.NoBrush)
    p.drawRect(QRectF(margin_x, y, content_w, h_th))
    p.drawLine(QPointF(x_col1, y), QPointF(x_col1, y + h_th))
    p.drawLine(QPointF(x_col2, y), QPointF(x_col2, y + h_th))
    p.drawLine(QPointF(x_col3, y), QPointF(x_col3, y + h_th))
    p.drawLine(QPointF(x_col3, y + h_th / 2.0), QPointF(margin_x + content_w, y + h_th / 2.0))
    p.drawLine(QPointF(x_col4, y + h_th / 2.0), QPointF(x_col4, y + h_th))
    p.drawLine(QPointF(x_col5, y + h_th / 2.0), QPointF(x_col5, y + h_th))

    p.setFont(font_th)
    p.setPen(QColor("#111827"))
    p.drawText(QRectF(x_col0, y, w_col0, h_th), Qt.AlignCenter, "Type")
    p.drawText(QRectF(x_col1, y, w_col1, h_th), Qt.AlignCenter, "Material / Thickness")
    p.drawText(QRectF(x_col2, y, w_col2, h_th), Qt.AlignCenter, "Quantity")
    p.drawText(QRectF(x_col3, y, w_sub_total, h_th / 2.0), Qt.AlignCenter, "Σ Rough")
    p.drawText(QRectF(x_col3, y + h_th / 2.0, w_col3, h_th / 2.0), Qt.AlignCenter, "Length")
    p.drawText(QRectF(x_col4, y + h_th / 2.0, w_col4, h_th / 2.0), Qt.AlignCenter, "Area")
    p.drawText(QRectF(x_col5, y + h_th / 2.0, w_col5, h_th / 2.0), Qt.AlignCenter, "Volume")
    p.restore()
    y += h_th

    # Summary Data Rows
    for mat_name, mat_entries in by_mat.items():
        qty_tot = sum(e.count for e in mat_entries)
        p.save()
        p.setPen(border_pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(margin_x, y, content_w, h_row))
        p.drawLine(QPointF(x_col1, y), QPointF(x_col1, y + h_row))
        p.drawLine(QPointF(x_col2, y), QPointF(x_col2, y + h_row))
        p.drawLine(QPointF(x_col3, y), QPointF(x_col3, y + h_row))
        p.drawLine(QPointF(x_col4, y), QPointF(x_col4, y + h_row))
        p.drawLine(QPointF(x_col5, y), QPointF(x_col5, y + h_row))

        draw_type_glyph(x_col0 + w_col0 / 2.0, y + h_row / 2.0, 10.0 * scale)
        draw_circular_swatch(x_col1 + 14.0 * scale, y + h_row / 2.0, 5.5 * scale, mat_name)

        p.setFont(font_cell_italic)
        p.setPen(QColor("#111827"))
        p.drawText(QRectF(x_col1 + 24.0 * scale, y, w_col1 - 28.0 * scale, h_row), Qt.AlignVCenter | Qt.AlignLeft, mat_name)

        p.setFont(font_cell)
        p.drawText(QRectF(x_col2, y, w_col2, h_row), Qt.AlignCenter, str(qty_tot))

        draw_hatch(QRectF(x_col3, y, w_col3, h_row))
        draw_hatch(QRectF(x_col4, y, w_col4, h_row))
        draw_hatch(QRectF(x_col5, y, w_col5, h_row))
        p.restore()
        y += h_row

    y += h_gap

    # Material Section Tables
    for mat_name, mat_entries in by_mat.items():
        if y + h_bar + h_th + h_row > content_bottom:
            draw_page_footer(curr_page)
            pdf.newPage()
            curr_page += 1
            y = margin_y

        p.save()
        p.setPen(border_pen)
        p.setBrush(Qt.NoBrush)
        p.drawRect(QRectF(margin_x, y, content_w, h_bar))
        draw_type_glyph(margin_x + 14.0 * scale, y + h_bar / 2.0, 10.0 * scale)
        draw_circular_swatch(margin_x + 30.0 * scale, y + h_bar / 2.0, 5.5 * scale, mat_name)

        p.setFont(font_mat_bar)
        p.setPen(QColor("#111827"))
        p.drawText(QRectF(margin_x + 42.0 * scale, y, content_w - 50.0 * scale, h_bar), Qt.AlignVCenter | Qt.AlignLeft, mat_name)
        p.restore()
        y += h_bar

        def draw_mat_th(at_y: float) -> None:
            p.save()
            p.setPen(border_pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(margin_x, at_y, content_w, h_th))
            p.drawLine(QPointF(x_col1, at_y), QPointF(x_col1, at_y + h_th))
            p.drawLine(QPointF(x_col2, at_y), QPointF(x_col2, at_y + h_th))
            p.drawLine(QPointF(x_col3, at_y), QPointF(x_col3, at_y + h_th))
            p.drawLine(QPointF(x_col3, at_y + h_th / 2.0), QPointF(margin_x + content_w, at_y + h_th / 2.0))
            p.drawLine(QPointF(x_col4, at_y + h_th / 2.0), QPointF(x_col4, at_y + h_th))
            p.drawLine(QPointF(x_col5, at_y + h_th / 2.0), QPointF(x_col5, at_y + h_th))

            p.setFont(font_th)
            p.setPen(QColor("#111827"))
            p.drawText(QRectF(x_col0, at_y, w_col0, h_th), Qt.AlignCenter, "No.")
            p.drawText(QRectF(x_col1, at_y, w_col1, h_th), Qt.AlignCenter, "Designation")
            p.drawText(QRectF(x_col2, at_y, w_col2, h_th), Qt.AlignCenter, "Qty.")
            p.drawText(QRectF(x_col3, at_y, w_sub_total, h_th / 2.0), Qt.AlignCenter, "Finished")
            p.drawText(QRectF(x_col3, at_y + h_th / 2.0, w_col3, h_th / 2.0), Qt.AlignCenter, "L")
            p.drawText(QRectF(x_col4, at_y + h_th / 2.0, w_col4, h_th / 2.0), Qt.AlignCenter, "W")
            p.drawText(QRectF(x_col5, at_y + h_th / 2.0, w_col5, h_th / 2.0), Qt.AlignCenter, "T")
            p.restore()

        draw_mat_th(y)
        y += h_th

        for e in mat_entries:
            if y + h_row > content_bottom:
                draw_page_footer(curr_page)
                pdf.newPage()
                curr_page += 1
                y = margin_y
                draw_mat_th(y)
                y += h_th

            p.save()
            p.setPen(border_pen)
            p.setBrush(Qt.NoBrush)
            p.drawRect(QRectF(margin_x, y, content_w, h_row))
            p.drawLine(QPointF(x_col1, y), QPointF(x_col1, y + h_row))
            p.drawLine(QPointF(x_col2, y), QPointF(x_col2, y + h_row))
            p.drawLine(QPointF(x_col3, y), QPointF(x_col3, y + h_row))
            p.drawLine(QPointF(x_col4, y), QPointF(x_col4, y + h_row))
            p.drawLine(QPointF(x_col5, y), QPointF(x_col5, y + h_row))

            # Red callout tag
            tag_clean = e.tag.replace("(", "").replace(")", "").strip()
            p.setFont(font_tag_red)
            p.setPen(QColor("#d32f2f"))
            p.drawText(QRectF(x_col0, y, w_col0, h_row), Qt.AlignCenter, tag_clean)

            # Designation
            p.setFont(font_cell)
            p.setPen(QColor("#111827"))
            p.drawText(QRectF(x_col1 + 8.0 * scale, y, w_col1 - 16.0 * scale, h_row), Qt.AlignVCenter | Qt.AlignLeft, e.display_name)

            # Qty
            p.drawText(QRectF(x_col2, y, w_col2, h_row), Qt.AlignCenter, str(e.count))

            # L, W, T with unit
            dim_l = f"{format_dimension(e.length, unit)} {unit}"
            dim_w = f"{format_dimension(e.width, unit)} {unit}"
            dim_t = f"{format_dimension(e.thickness, unit)} {unit}"
            p.drawText(QRectF(x_col3, y, w_col3, h_row), Qt.AlignCenter, dim_l)
            p.drawText(QRectF(x_col4, y, w_col4, h_row), Qt.AlignCenter, dim_w)
            p.drawText(QRectF(x_col5, y, w_col5, h_row), Qt.AlignCenter, dim_t)
            p.restore()
            y += h_row

        y += h_gap

    draw_page_footer(curr_page)
    p.end()


# ---------------------------------------------------------------------------
# Qt Universal Cutting Diagram Widget (Lumber Boards & 2D Sheets)
# ---------------------------------------------------------------------------
if QT_AVAILABLE:

    class CuttingDiagramWidget(QWidget):
        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.mode: str = "none"
            self.sheet_data: Optional[SheetLayout] = None
            self.lumber_boards: List[LumberBoard] = []
            self.unit = "mm"
            self.setMinimumSize(640, 380)

        def set_sheet(self, sheet: Optional[SheetLayout], unit: str = "mm") -> None:
            self.mode = "sheet"
            self.sheet_data = sheet
            self.lumber_boards = []
            self.unit = unit
            self.update()

        def set_lumber(self, boards: List[LumberBoard], unit: str = "mm") -> None:
            self.mode = "solid"
            self.lumber_boards = boards
            self.sheet_data = None
            self.unit = unit
            self.update()

        def paintEvent(self, event: Any) -> None:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.fillRect(self.rect(), QColor("#1e1e1e"))

            if self.mode == "sheet" and self.sheet_data:
                self._draw_sheet(painter)
            elif self.mode == "solid" and self.lumber_boards:
                self._draw_lumber(painter)
            else:
                painter.setPen(QColor("#888888"))
                painter.drawText(self.rect(), Qt.AlignCenter, "No cutting diagram generated.\nClick 'Generate' to create the diagram.")

            painter.end()

        def _draw_sheet(self, painter: QPainter) -> None:
            sheet = self.sheet_data
            if not sheet or sheet.sheet_width <= 1e-4 or sheet.sheet_height <= 1e-4:
                return

            sw, sh = sheet.sheet_width, sheet.sheet_height
            pad = 40.0
            avail_w = max(10.0, self.width() - (2 * pad))
            avail_h = max(10.0, self.height() - (2 * pad))
            scale = min(avail_w / sw, avail_h / sh)

            draw_w = sw * scale
            draw_h = sh * scale
            start_x = (self.width() - draw_w) / 2.0
            start_y = (self.height() - draw_h) / 2.0

            sheet_rect = QRectF(start_x, start_y, draw_w, draw_h)
            painter.setPen(QPen(QColor("#d4a373"), 2))
            painter.setBrush(QBrush(QColor("#f4f1de")))
            painter.drawRect(sheet_rect)

            painter.setPen(QColor("#cccccc"))
            font_dim = painter.font()
            font_dim.setPointSize(9)
            font_dim.setBold(True)
            painter.setFont(font_dim)

            painter.drawText(QRectF(start_x, start_y - 25, draw_w, 20), Qt.AlignCenter, f"{format_dimension(sw, self.unit)} {self.unit}")
            painter.drawText(QRectF(start_x + draw_w + 6, start_y, 75, draw_h), Qt.AlignVCenter | Qt.AlignLeft, f"{format_dimension(sh, self.unit)} {self.unit}")

            colors = [QColor("#ccd5ae"), QColor("#e9edc9"), QColor("#faedcd"), QColor("#d4a373"), QColor("#b7b7a4"), QColor("#a8dadc")]
            font_part = painter.font()
            font_part.setPointSize(8)
            font_part.setBold(False)
            painter.setFont(font_part)

            for idx, p in enumerate(sheet.placed_parts):
                px = start_x + (p.x * scale)
                py = start_y + (p.y * scale)
                pw = p.width * scale
                ph = p.height * scale
                blank_rect = QRectF(px, py, pw, ph)

                # 1. Draw raw stock blank envelope (subtle dashed border)
                painter.setPen(QPen(QColor("#a5a58d"), 1.0, Qt.DashLine))
                painter.setBrush(QBrush(QColor(240, 235, 220, 100)))
                painter.drawRect(blank_rect)

                # 2. Draw actual part shape / contour if available
                color = colors[idx % len(colors)]
                painter.setPen(QPen(QColor("#4a4e69"), 1.5))
                painter.setBrush(QBrush(color))

                if p.contour_2d and len(p.contour_2d) >= 3:
                    pts_2d = []
                    for nx, ny in p.contour_2d:
                        if not p.rotated:
                            sx = px + (nx * pw)
                            sy = py + (ny * ph)
                        else:
                            sx = px + (ny * pw)
                            sy = py + ((1.0 - nx) * ph)
                        pts_2d.append(QPointF(sx, sy))
                    painter.drawPolygon(QPolygonF(pts_2d))
                else:
                    painter.drawRect(blank_rect)

                # 3. Label inside part
                if pw >= 45 and ph >= 25:
                    painter.setPen(QColor("#222222"))
                    label = f"{p.name}\n{format_dimension(p.width, self.unit)} × {format_dimension(p.height, self.unit)}"
                    painter.drawText(blank_rect, Qt.AlignCenter, label)

        def _draw_lumber(self, painter: QPainter) -> None:
            boards = self.lumber_boards
            if not boards:
                return

            pad_x = 40.0
            pad_y = 35.0
            avail_w = max(100.0, self.width() - (2 * pad_x))
            max_stock = max(b.stock_length for b in boards)
            scale_x = avail_w / max_stock

            num_boards = min(4, len(boards))
            board_gap = 25.0
            avail_h = max(100.0, self.height() - (2 * pad_y))
            board_h = min(75.0, (avail_h - ((num_boards - 1) * board_gap)) / num_boards)

            colors = [QColor("#faedcd"), QColor("#ccd5ae"), QColor("#e9edc9"), QColor("#d4a373"), QColor("#a8dadc"), QColor("#b7b7a4")]
            font_b = painter.font()
            font_b.setPointSize(8)
            painter.setFont(font_b)

            for b_idx in range(num_boards):
                b = boards[b_idx]
                by = pad_y + (b_idx * (board_h + board_gap))
                bw = b.stock_length * scale_x

                board_rect = QRectF(pad_x, by, bw, board_h)
                painter.setPen(QPen(QColor("#8c5e34"), 2))
                painter.setBrush(QBrush(QColor("#e3c099")))
                painter.drawRoundedRect(board_rect, 3, 3)

                painter.setPen(QColor("#e0e0e0"))
                w_str = format_dimension(b.width, self.unit)
                t_str = format_dimension(b.thickness, self.unit)
                stk_str = format_dimension(b.stock_length, self.unit)
                header_text = (
                    f"Board #{b.index}: Profile {w_str} × {t_str} {self.unit}  "
                    f"(Stock: {stk_str} {self.unit}) — Yield: {b.yield_percentage:.1f}%"
                )
                painter.drawText(QRectF(pad_x, by - 18, bw, 16), Qt.AlignLeft | Qt.AlignVCenter, header_text)

                for c_idx, c in enumerate(b.cuts):
                    cx = pad_x + (c.x * scale_x)
                    cw = c.length * scale_x
                    blank_rect = QRectF(cx, by, cw, board_h)

                    painter.setPen(QPen(QColor("#8c5e34"), 1.0, Qt.DashLine))
                    painter.setBrush(QBrush(QColor(230, 200, 165, 80)))
                    painter.drawRect(blank_rect)

                    color = colors[c_idx % len(colors)]
                    painter.setPen(QPen(QColor("#3d2612"), 1.5))
                    painter.setBrush(QBrush(color))

                    if c.contour_2d and len(c.contour_2d) >= 3:
                        pts_2d = []
                        for nx, ny in c.contour_2d:
                            sx = cx + (nx * cw)
                            sy = by + (ny * board_h)
                            pts_2d.append(QPointF(sx, sy))
                        painter.drawPolygon(QPolygonF(pts_2d))
                    else:
                        painter.drawRect(blank_rect)

                    if cw >= 40:
                        painter.setPen(QColor("#111111"))
                        c_len_str = format_dimension(c.length, self.unit)
                        painter.drawText(blank_rect, Qt.AlignCenter, f"{c.name}\n{c_len_str} {self.unit}")

                    painter.setPen(QPen(QColor("#e63946"), 1.5, Qt.DashLine))
                    painter.drawLine(cx + cw, by, cx + cw, by + board_h)

                if b.cuts:
                    off_x = pad_x + ((b.cuts[-1].x + b.cuts[-1].length) * scale_x)
                    off_w = (pad_x + bw) - off_x
                    if off_w >= 10:
                        off_rect = QRectF(off_x, by, off_w, board_h)
                        painter.setPen(QPen(QColor("#777777"), 1, Qt.DotLine))
                        painter.setBrush(QBrush(QColor(60, 60, 60, 180)))
                        painter.drawRect(off_rect)
                        painter.setPen(QColor("#cccccc"))
                        if off_w >= 50:
                            off_str = format_dimension(b.offcut_length, self.unit)
                            painter.drawText(off_rect, Qt.AlignCenter, f"Offcut\n{off_str}")


# ---------------------------------------------------------------------------
# Qt 3D Exploded Drawing Widget (True Mesh Faces & Geometry)
# ---------------------------------------------------------------------------
if QT_AVAILABLE:

    class ExplodedDrawingWidget(QWidget):
        """Interactive 3D Axonometric Exploded View Drawing Canvas.
        
        High-precision technical drawing sheet inspired by OpenCutList.
        Renders true 3D geometry with hardware OpenGL acceleration via IngeTrazo's
        native viewport renderer outside paintEvent, with automatic fallback to
        vector software rendering. Supports dynamic outward exploded views, callout
        balloons, and parts legend table with 100% CAD viewport stability.
        """

        def __init__(self, viewport: Any = None, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.viewport = viewport
            self.parts: List[RawPart] = []
            self.entries: List[CutListEntry] = []
            self.unit = "mm"
            self.explode_factor = 0.0

            # IngeTrazo standard view angles (OrbitCamera):
            # "iso": yaw=-45 deg, pitch=30 deg
            self.rot_z = math.radians(-45.0)
            self.rot_x = math.radians(30.0)
            self.zoom = 1.0
            self.pan_x = 0.0
            self.pan_y = 0.0

            self.show_callouts = True
            self.show_legend = True

            self._last_mouse_pos = QPoint()
            self._is_orbiting = False
            self._is_panning = False

            self._cached_image: Optional[QImage] = None
            self._cached_ndc: List[Tuple[float, float, str, str]] = []
            self._render_timer: Optional[QTimer] = None
            self._idle_timer: Optional[QTimer] = None

            self.setMinimumSize(680, 480)
            self.setCursor(Qt.OpenHandCursor)

        def schedule_3d_render(self, delay_ms: int = 25, full_res: bool = False, refresh_cad: bool = False) -> None:
            """Schedule a deferred hardware 3D render to avoid stutter during slider/orbit drags."""
            if not QT_AVAILABLE:
                return
            if self._render_timer is None:
                self._render_timer = QTimer(self)
                self._render_timer.setSingleShot(True)
                self._render_timer.timeout.connect(self._on_render_timer_timeout)
            if self._idle_timer is None:
                self._idle_timer = QTimer(self)
                self._idle_timer.setSingleShot(True)
                self._idle_timer.timeout.connect(lambda: self.update_3d_render(full_res=True, refresh_cad=True))
            self._next_full_res = full_res
            self._next_refresh_cad = refresh_cad
            self._render_timer.start(delay_ms)
            if not full_res:
                self._idle_timer.start(150)

        def _on_render_timer_timeout(self) -> None:
            self.update_3d_render(
                full_res=getattr(self, "_next_full_res", False),
                refresh_cad=getattr(self, "_next_refresh_cad", False),
            )

        def set_data(self, parts: List[RawPart], entries: List[CutListEntry], unit: str = "mm") -> None:
            self.parts = parts
            self.entries = entries
            self.unit = unit
            self.reset_view()

        def set_explode_factor(self, factor: float) -> None:
            self.explode_factor = max(0.0, factor)
            self.schedule_3d_render(delay_ms=25, full_res=False, refresh_cad=False)

        def set_view_angles(self, yaw_deg: float, pitch_deg: float) -> None:
            self.rot_z = math.radians(yaw_deg)
            self.rot_x = math.radians(pitch_deg)
            self.update_3d_render(full_res=True, refresh_cad=True)

        def reset_view(self) -> None:
            self.rot_z = math.radians(-45.0)
            self.rot_x = math.radians(30.0)
            self.zoom = 1.0
            self.pan_x = 0.0
            self.pan_y = 0.0
            self.update_3d_render(full_res=True, refresh_cad=True)

        def mousePressEvent(self, event: Any) -> None:
            self._last_mouse_pos = event.pos()
            if event.button() == Qt.LeftButton:
                self._is_orbiting = True
                self.setCursor(Qt.ClosedHandCursor)
            elif event.button() in (Qt.RightButton, Qt.MiddleButton):
                self._is_panning = True
                self.setCursor(Qt.SizeAllCursor)

        def mouseMoveEvent(self, event: Any) -> None:
            delta = event.pos() - self._last_mouse_pos
            self._last_mouse_pos = event.pos()

            if self._is_orbiting:
                self.rot_z += delta.x() * 0.01
                self.rot_x = max(-math.pi / 2.05, min(math.pi / 2.05, self.rot_x + delta.y() * 0.01))
                self.schedule_3d_render(delay_ms=25, full_res=False, refresh_cad=False)
            elif self._is_panning:
                self.pan_x += delta.x()
                self.pan_y += delta.y()
                self.update()

        def mouseReleaseEvent(self, event: Any) -> None:
            self._is_orbiting = False
            self._is_panning = False
            self.setCursor(Qt.OpenHandCursor)
            if getattr(self, "_idle_timer", None) is not None:
                self._idle_timer.stop()
            self.update_3d_render(full_res=True, refresh_cad=True)

        def wheelEvent(self, event: Any) -> None:
            delta = event.angleDelta().y()
            if delta > 0:
                self.zoom *= 1.15
            elif delta < 0:
                self.zoom = max(0.2, self.zoom / 1.15)
            self.schedule_3d_render(delay_ms=25, full_res=False, refresh_cad=False)

        def resizeEvent(self, event: Any) -> None:
            super().resizeEvent(event)
            self.schedule_3d_render(delay_ms=50, full_res=True, refresh_cad=False)

        def update_3d_render(self, full_res: bool = True, refresh_cad: bool = False) -> None:
            """Render the assembly in 3D using IngeTrazo's native hardware OpenGL viewport.

            Executes outside paintEvent to prevent QPainter / OpenGL context collisions.
            Drills down through group hierarchies to explode individual components, maps
            parent container transforms, fits camera to expanded bounds, and caches the
            rendered image. Uses lightweight preview resolution during drag/orbit for 60+ FPS,
            settling to full resolution on release.
            """
            vp = self.viewport
            if vp is None or not self.parts:
                self._cached_image = None
                self._cached_ndc = []
                self.update()
                return

            cam = getattr(vp, "camera", None)
            scene = getattr(vp, "scene", None)
            if cam is None or scene is None or not hasattr(vp, "render_image"):
                self._cached_image = None
                self._cached_ndc = []
                self.update()
                return

            all_min_x = min(p.min_x for p in self.parts)
            all_max_x = max(p.max_x for p in self.parts)
            all_min_y = min(p.min_y for p in self.parts)
            all_max_y = max(p.max_y for p in self.parts)
            all_min_z = min(p.min_z for p in self.parts)
            all_max_z = max(p.max_z for p in self.parts)

            mid_x = (all_min_x + all_max_x) / 2.0
            mid_y = (all_min_y + all_max_y) / 2.0
            mid_z = (all_min_z + all_max_z) / 2.0

            # 1. Save original camera state
            orig_target = QVector3D(cam.target) if hasattr(cam, "target") else None
            orig_dist = getattr(cam, "distance", 1.0)
            orig_yaw = getattr(cam, "yaw", 0.0)
            orig_pitch = getattr(cam, "pitch", 0.0)
            orig_aspect = getattr(cam, "aspect", 1.0)
            orig_perspective = getattr(cam, "perspective", True)

            # Build parent hierarchy mapping so grouped components can be located and transformed
            parent_map: Dict[int, Any] = {}
            def map_parents(node: Any) -> None:
                for child in getattr(node, "children", None) or ():
                    parent_map[id(child)] = node
                    map_parents(child)

            if hasattr(scene, "groups"):
                for g in scene.groups:
                    map_parents(g)

            # 2. Save original group xforms & explode_offsets & apply explosion
            saved_xforms: List[Tuple[Any, Any, Any, Any]] = []
            for part in self.parts:
                grp = part.group_ref
                if grp is not None:
                    old_xf = QMatrix4x4(grp.xform) if getattr(grp, "xform", None) is not None else None
                    old_off = getattr(grp, "explode_offset", None)
                    was_comp = getattr(grp, "component", None)
                    saved_xforms.append((grp, old_xf, old_off, was_comp))

                    if self.explode_factor > 0:
                        cx, cy, cz = part.center
                        dx = (cx - mid_x) * self.explode_factor
                        dy = (cy - mid_y) * self.explode_factor
                        dz = (cz - mid_z) * self.explode_factor

                        # Map world delta to local coordinate frame if inside a parent container
                        parent = parent_map.get(id(grp))
                        world_parent_xf = None
                        curr_p = parent
                        while curr_p is not None:
                            p_xf = getattr(curr_p, "xform", None)
                            if p_xf is not None:
                                world_parent_xf = p_xf if world_parent_xf is None else (p_xf * world_parent_xf)
                            curr_p = parent_map.get(id(curr_p))

                        if world_parent_xf is not None:
                            inv_p, ok = world_parent_xf.inverted()
                            local_delta = inv_p.mapVector(QVector3D(dx, dy, dz)) if ok else QVector3D(dx, dy, dz)
                        else:
                            local_delta = QVector3D(dx, dy, dz)

                        step = QMatrix4x4()
                        step.translate(local_delta)
                        base_m = old_xf if old_xf is not None else QMatrix4x4()
                        grp.xform = step * base_m
                        grp.explode_offset = (local_delta.x(), local_delta.y(), local_delta.z())
                        if old_xf is None:
                            grp.component = False

            # 3. Temporarily hide non-selected groups so only cut list components appear on sheet
            selected_lineage = set()
            for p in self.parts:
                curr = p.group_ref
                while curr is not None:
                    selected_lineage.add(id(curr))
                    curr = parent_map.get(id(curr))

            hidden_restore: List[Any] = []
            mesh_restore: List[Tuple[Any, Any]] = []
            parts_group_ids = {id(p.group_ref) for p in self.parts}

            if hasattr(scene, "groups"):
                for g in scene.groups:
                    def hide_unselected_kids(node: Any) -> None:
                        for child in getattr(node, "children", None) or ():
                            if id(child) not in selected_lineage and not getattr(child, "hidden", False):
                                child.hidden = True
                                hidden_restore.append(child)
                            else:
                                if id(child) not in parts_group_ids and getattr(child, "mesh", None) is not None:
                                    if len(getattr(child.mesh, "faces", [])) > 0:
                                        mesh_restore.append((child, child.mesh))
                                        child.mesh = None
                            hide_unselected_kids(child)

                    if id(g) not in selected_lineage and not getattr(g, "hidden", False):
                        g.hidden = True
                        hidden_restore.append(g)
                    else:
                        if id(g) not in parts_group_ids and getattr(g, "mesh", None) is not None:
                            if len(getattr(g.mesh, "faces", [])) > 0:
                                mesh_restore.append((g, g.mesh))
                                g.mesh = None
                        hide_unselected_kids(g)

            img: Optional[QImage] = None
            part_ndc: List[Tuple[float, float, str, str]] = []

            try:
                # 4. Invalidate frame cache and bump version for instance synchronization
                setattr(vp, "_frame_cache", None)
                setattr(vp, "_frame_cache_prev_mvp", None)
                scene.version = getattr(scene, "version", 0) + 1

                # 5. Set up orbit camera
                cam.yaw = self.rot_z
                cam.pitch = self.rot_x
                cam.target = QVector3D(mid_x, mid_y, mid_z)

                # Resolution: lightweight preview resolution during drag/orbit, full on release
                target_w = int(self.width() - 40 if self.width() > 100 else 800)
                target_h = int(self.height() - 60 if self.height() > 100 else 600)
                if full_res:
                    render_w = max(680, target_w)
                    render_h = max(480, target_h)
                else:
                    render_w = min(max(320, target_w), 500)
                    render_h = min(max(240, target_h), 380)

                cam.aspect = target_w / max(1, target_h)

                # Fit bounding box taking explosion into account
                exp_factor = 1.0 + self.explode_factor
                min_exp_x = mid_x + (all_min_x - mid_x) * exp_factor
                max_exp_x = mid_x + (all_max_x - mid_x) * exp_factor
                min_exp_y = mid_y + (all_min_y - mid_y) * exp_factor
                max_exp_y = mid_y + (all_max_y - mid_y) * exp_factor
                min_exp_z = mid_z + (all_min_z - mid_z) * exp_factor
                max_exp_z = mid_z + (all_max_z - mid_z) * exp_factor

                min_v = QVector3D(min(min_exp_x, max_exp_x), min(min_exp_y, max_exp_y), min(min_exp_z, max_exp_z))
                max_v = QVector3D(max(min_exp_x, max_exp_x), max(min_exp_y, max_exp_y), max(min_exp_z, max_exp_z))

                if hasattr(cam, "fit_box"):
                    cam.fit_box(min_v, max_v, margin=1.25)
                if self.zoom != 1.0:
                    cam.distance = max(0.1, cam.distance / self.zoom)

                # 6. Render hardware OpenGL image via Viewport offscreen FBO
                try:
                    img = vp.render_image(render_w, render_h, overlays=False, sharp_shadows=False, transparent=True)
                except TypeError:
                    try:
                        img = vp.render_image(render_w, render_h)
                    except Exception as err:
                        sys.stderr.write(f"[CutList] Error in vp.render_image: {err}\n")
                except Exception as err:
                    sys.stderr.write(f"[CutList] Error in vp.render_image: {err}\n")

                # 7. Project exploded 3D centers into NDC coordinates [-1, 1] for callouts
                mvp = cam.projection_matrix() * cam.view_matrix()
                for part in self.parts:
                    cx, cy, cz = part.center
                    if self.explode_factor > 0:
                        cx += (cx - mid_x) * self.explode_factor
                        cy += (cy - mid_y) * self.explode_factor
                        cz += (cz - mid_z) * self.explode_factor
                    clip = mvp.map(QVector4D(cx, cy, cz, 1.0))
                    if clip.w() != 0:
                        ndc_x = clip.x() / clip.w()
                        ndc_y = clip.y() / clip.w()
                        part_ndc.append((ndc_x, ndc_y, part.tag, part.name))

            finally:
                # 8. Restore group matrices & explode offsets
                for grp, old_xf, old_off, was_comp in saved_xforms:
                    grp.xform = old_xf
                    grp.explode_offset = old_off
                    if was_comp is not None:
                        grp.component = was_comp

                # 9. Restore hidden groups & intermediate container meshes
                for g in hidden_restore:
                    g.hidden = False
                for node, orig_m in mesh_restore:
                    node.mesh = orig_m

                # 10. Restore camera
                if hasattr(cam, "target") and orig_target is not None:
                    cam.target = orig_target
                if hasattr(cam, "distance"):
                    cam.distance = orig_dist
                if hasattr(cam, "yaw"):
                    cam.yaw = orig_yaw
                if hasattr(cam, "pitch"):
                    cam.pitch = orig_pitch
                if hasattr(cam, "aspect"):
                    cam.aspect = orig_aspect
                if hasattr(cam, "perspective"):
                    cam.perspective = orig_perspective

                # 11. Invalidate frame cache & bump scene version to trigger clean CAD viewport redraw
                setattr(vp, "_frame_cache", None)
                setattr(vp, "_frame_cache_prev_mvp", None)
                scene.version = getattr(scene, "version", 0) + 1
                if refresh_cad:
                    vp.update()

            self._cached_image = img
            self._cached_ndc = part_ndc
            self.update()

        def render_drawing(self, painter: QPainter, target_rect: QRectF) -> None:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.fillRect(target_rect, QColor("#222222"))

            sheet_margin = 25.0
            sheet_rect = QRectF(
                target_rect.left() + sheet_margin,
                target_rect.top() + sheet_margin,
                target_rect.width() - (2 * sheet_margin),
                target_rect.height() - (2 * sheet_margin),
            )

            shadow_rect = QRectF(sheet_rect.left() + 4, sheet_rect.top() + 4, sheet_rect.width(), sheet_rect.height())
            painter.fillRect(shadow_rect, QColor(0, 0, 0, 90))

            painter.fillRect(sheet_rect, QColor("#ffffff"))
            painter.setPen(QPen(QColor("#333333"), 1.5))
            painter.drawRect(sheet_rect)

            inner_rect = QRectF(sheet_rect.left() + 8, sheet_rect.top() + 8, sheet_rect.width() - 16, sheet_rect.height() - 16)
            painter.setPen(QPen(QColor("#777777"), 1))
            painter.drawRect(inner_rect)

            painter.setPen(QColor("#111111"))
            font_title = painter.font()
            font_title.setPointSize(11)
            font_title.setBold(True)
            painter.setFont(font_title)

            title_box = QRectF(inner_rect.left() + 15, inner_rect.top() + 10, inner_rect.width() - 30, 24)
            painter.drawText(title_box, Qt.AlignLeft | Qt.AlignVCenter, "INGETRAZO CUT LIST — ASSEMBLY DRAWING")

            font_meta = painter.font()
            font_meta.setPointSize(8)
            font_meta.setBold(False)
            painter.setFont(font_meta)

            meta_text = f"Exploded View  |  Parts: {len(self.parts)}  |  Units: {self.unit}  |  Explosion: {int(self.explode_factor * 100)}%"
            painter.drawText(title_box, Qt.AlignRight | Qt.AlignVCenter, meta_text)

            painter.setPen(QPen(QColor("#bbbbbb"), 1))
            painter.drawLine(inner_rect.left() + 15, inner_rect.top() + 36, inner_rect.right() - 15, inner_rect.top() + 36)

            if not self.parts:
                painter.setPen(QColor("#888888"))
                painter.drawText(sheet_rect, Qt.AlignCenter, "No parts to display. Select objects in the viewport and click 'Generate'.")
                return

            draw_rect = QRectF(inner_rect.left() + 20, inner_rect.top() + 45, inner_rect.width() - 40, inner_rect.height() - 55)

            if self._cached_image is not None and not self._cached_image.isNull():
                target_img_rect = QRectF(draw_rect.left() + self.pan_x, draw_rect.top() + self.pan_y, draw_rect.width(), draw_rect.height())
                painter.drawImage(target_img_rect, self._cached_image)

                dw = target_img_rect.width()
                dh = target_img_rect.height()
                dx0 = target_img_rect.left()
                dy0 = target_img_rect.top()

                part_centers_2d: List[Tuple[float, float, str, str]] = []
                for ndc_x, ndc_y, tag, name in self._cached_ndc:
                    px = dx0 + ((ndc_x + 1.0) * 0.5 * dw)
                    py = dy0 + ((1.0 - ndc_y) * 0.5 * dh)
                    part_centers_2d.append((px, py, tag, name))

                if self.show_callouts and part_centers_2d:
                    self._draw_callout_balloons(painter, part_centers_2d, draw_rect)

                if self.show_legend and self.entries:
                    self._draw_legend_table(painter, inner_rect)
            else:
                self._render_assembly_drawing_fallback(painter, draw_rect, inner_rect)

        def _render_assembly_drawing_fallback(self, painter: QPainter, draw_rect: QRectF, inner_rect: QRectF) -> None:
            """High-precision 3D axonometric assembly renderer with true mesh faces,
            exact depth sorting, two-sided illumination, and outward exploded views.
            Operates purely via QPainter vector pipeline to ensure 100% viewport stability.
            """
            all_min_x = min(p.min_x for p in self.parts)
            all_max_x = max(p.max_x for p in self.parts)
            all_min_y = min(p.min_y for p in self.parts)
            all_max_y = max(p.max_y for p in self.parts)
            all_min_z = min(p.min_z for p in self.parts)
            all_max_z = max(p.max_z for p in self.parts)

            mid_x = (all_min_x + all_max_x) / 2.0
            mid_y = (all_min_y + all_max_y) / 2.0
            mid_z = (all_min_z + all_max_z) / 2.0

            max_dim = max(all_max_x - all_min_x, all_max_y - all_min_y, all_max_z - all_min_z, 1.0)

            center_x = draw_rect.center().x() + self.pan_x
            center_y = draw_rect.center().y() + self.pan_y

            base_scale = (min(draw_rect.width(), draw_rect.height()) * 0.44) / (max_dim * (1.0 + (0.75 * self.explode_factor)))
            scale = base_scale * self.zoom

            # Orthonormal camera coordinate system matching IngeTrazo OrbitCamera conventions
            cy = math.cos(self.rot_z)
            sy = math.sin(self.rot_z)
            cp = math.cos(self.rot_x)
            sp = math.sin(self.rot_x)

            # F: Gaze vector from scene center toward the viewer/camera
            fx = cp * cy
            fy = cp * sy
            fz = sp

            # R: Screen Right horizontal vector
            rx = -sy
            ry = cy
            rz = 0.0

            # Up: Screen Up vertical vector
            ux = -sp * cy
            uy = -sp * sy
            uz = cp

            # Directional technical drawing light (from top-left-front)
            lx = -0.35 * rx - 0.25 * ux + 0.8 * fx
            ly = -0.35 * ry - 0.25 * uy + 0.8 * fy
            lz = -0.35 * rz - 0.25 * uz + 0.8 * fz
            ll = math.sqrt(lx*lx + ly*ly + lz*lz) or 1.0
            lx, ly, lz = lx / ll, ly / ll, lz / ll

            wood_palette = [
                QColor("#d4a373"),  # warm oak
                QColor("#faedcd"),  # pale birch
                QColor("#ccd5ae"),  # sage timber
                QColor("#e3c099"),  # pine
                QColor("#c5a059"),  # golden beech
                QColor("#b7b7a4"),  # weathered wood
                QColor("#e9edc9"),  # ash timber
                QColor("#ba8c63"),  # cedar
            ]

            faces_to_render = []
            part_centers_2d: List[Tuple[float, float, str, str]] = []

            for p_idx, part in enumerate(self.parts):
                cx, cy, cz = part.center
                # 3D explosion vector: moves outward from center of assembly
                vx = (cx - mid_x) * self.explode_factor
                vy = (cy - mid_y) * self.explode_factor
                vz = (cz - mid_z) * self.explode_factor

                pc_x = (cx - mid_x) + vx
                pc_y = (cy - mid_y) + vy
                pc_z = (cz - mid_z) + vz

                # 2D Screen projection of the part center for callout balloons
                p2d_x = center_x + ((pc_x * rx + pc_y * ry + pc_z * rz) * scale)
                p2d_y = center_y - ((pc_x * ux + pc_y * uy + pc_z * uz) * scale)
                part_centers_2d.append((p2d_x, p2d_y, part.tag, part.name))

                # Material color assignment
                mat_lower = (part.material or "").lower()
                if "metal" in mat_lower:
                    base_color = QColor("#a0a5aa")
                elif "gold" in mat_lower:
                    base_color = QColor("#c5a059")
                elif "glass" in mat_lower:
                    base_color = QColor("#b0d4e3")
                else:
                    base_color = wood_palette[p_idx % len(wood_palette)]

                # True 3D mesh faces (including curved arch segments)
                part_faces = part.faces_3d if (part.faces_3d and len(part.faces_3d) > 0) else []
                if not part_faces:
                    x0, x1 = part.min_x, part.max_x
                    y0, y1 = part.min_y, part.max_y
                    z0, z1 = part.min_z, part.max_z
                    corners = [
                        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
                    ]
                    part_faces = [
                        ([corners[0], corners[1], corners[5], corners[4]], (0, -1, 0)),
                        ([corners[1], corners[2], corners[6], corners[5]], (1, 0, 0)),
                        ([corners[2], corners[3], corners[7], corners[6]], (0, 1, 0)),
                        ([corners[3], corners[0], corners[4], corners[7]], (-1, 0, 0)),
                        ([corners[4], corners[5], corners[6], corners[7]], (0, 0, 1)),
                        ([corners[3], corners[2], corners[1], corners[0]], (0, 0, -1)),
                    ]

                part_depth = pc_x * fx + pc_y * fy + pc_z * fz

                for face_verts, norm in part_faces:
                    nx, ny, nz = norm
                    dot_f = nx * fx + ny * fy + nz * fz

                    # Two-sided shading: guarantees thin panels and reverse-wound faces are always rendered
                    if dot_f >= 0:
                        dot_l = max(0.0, nx * lx + ny * ly + nz * lz)
                        intensity = 0.65 + (0.35 * dot_l)
                    else:
                        dot_l = max(0.0, (-nx) * lx + (-ny) * ly + (-nz) * lz)
                        intensity = 0.48 + (0.30 * dot_l)

                    shaded_color = QColor(
                        max(0, min(255, int(base_color.red() * intensity))),
                        max(0, min(255, int(base_color.green() * intensity))),
                        max(0, min(255, int(base_color.blue() * intensity))),
                    )

                    pts_2d = []
                    v_depths = []
                    for vx_i, vy_i, vz_i in face_verts:
                        px = (vx_i - mid_x) + vx
                        py = (vy_i - mid_y) + vy
                        pz = (vz_i - mid_z) + vz

                        x_screen = px * rx + py * ry + pz * rz
                        y_screen = px * ux + py * uy + pz * uz
                        depth = px * fx + py * fy + pz * fz

                        sx = center_x + (x_screen * scale)
                        sy = center_y - (y_screen * scale)
                        pts_2d.append(QPointF(sx, sy))
                        v_depths.append(depth)

                    avg_face_depth = sum(v_depths) / len(v_depths)
                    # Depth key: furthest from camera drawn first, closest drawn on top
                    composite_depth = avg_face_depth + (part_depth * 0.15 if self.explode_factor > 0 else 0.0)
                    faces_to_render.append((composite_depth, pts_2d, shaded_color))

            # Sort faces from back to front (Painter's algorithm)
            faces_to_render.sort(key=lambda f: f[0])

            # Crisp technical drawing pen for outlines and seams
            edge_pen = QPen(QColor("#242424"), 1.2)
            edge_pen.setJoinStyle(Qt.RoundJoin)

            for _depth, pts, col in faces_to_render:
                poly = QPolygonF(pts)
                painter.setPen(edge_pen)
                painter.setBrush(QBrush(col))
                painter.drawPolygon(poly)

            # Callout Balloons
            if self.show_callouts and part_centers_2d:
                self._draw_callout_balloons(painter, part_centers_2d, draw_rect)

            # Parts Legend Table
            if self.show_legend and self.entries:
                self._draw_legend_table(painter, inner_rect)

        def _draw_callout_balloons(self, painter: QPainter, part_centers_2d: List[Tuple[float, float, str, str]], draw_rect: QRectF) -> None:
            font_tag = painter.font()
            font_tag.setPointSize(8)
            font_tag.setBold(True)
            painter.setFont(font_tag)

            drawn_tags = set()
            balloon_radius = 11.0
            center_x = draw_rect.center().x() + self.pan_x
            center_y = draw_rect.center().y() + self.pan_y

            for p2d_x, p2d_y, tag, name in part_centers_2d:
                if not tag or tag in drawn_tags:
                    continue
                drawn_tags.add(tag)

                dx = p2d_x - center_x
                dy = p2d_y - center_y
                dist = math.sqrt(dx*dx + dy*dy) or 1.0
                offset_dist = 38.0
                bx = p2d_x + (dx / dist) * offset_dist
                by = p2d_y + (dy / dist) * offset_dist

                painter.setPen(QPen(QColor("#555555"), 1.0, Qt.SolidLine))
                painter.drawLine(QPointF(p2d_x, p2d_y), QPointF(bx, by))

                painter.setBrush(QBrush(QColor("#333333")))
                painter.drawEllipse(QPointF(p2d_x, p2d_y), 2.5, 2.5)

                painter.setPen(QPen(QColor("#222222"), 1.5))
                painter.setBrush(QBrush(QColor("#fff3b0")))
                painter.drawEllipse(QPointF(bx, by), balloon_radius, balloon_radius)

                painter.setPen(QColor("#111111"))
                painter.drawText(
                    QRectF(bx - balloon_radius, by - balloon_radius, 2 * balloon_radius, 2 * balloon_radius),
                    Qt.AlignCenter,
                    tag,
                )

        def _draw_legend_table(self, painter: QPainter, inner_rect: QRectF) -> None:
            max_rows = min(6, len(self.entries))
            row_h = 16.0
            table_w = min(360.0, inner_rect.width() * 0.45)
            table_h = 22.0 + (max_rows * row_h)

            tx = inner_rect.left() + 15
            ty = inner_rect.bottom() - table_h - 15

            table_rect = QRectF(tx, ty, table_w, table_h)

            painter.setPen(QPen(QColor("#444444"), 1))
            painter.setBrush(QBrush(QColor(255, 255, 255, 230)))
            painter.drawRect(table_rect)

            header_rect = QRectF(tx, ty, table_w, 20)
            painter.fillRect(header_rect, QColor("#e9ecef"))
            painter.setPen(QColor("#212529"))

            font_t = painter.font()
            font_t.setPointSize(8)
            font_t.setBold(True)
            painter.setFont(font_t)

            painter.drawText(QRectF(tx + 4, ty, 30, 20), Qt.AlignLeft | Qt.AlignVCenter, "Tag")
            painter.drawText(QRectF(tx + 36, ty, 150, 20), Qt.AlignLeft | Qt.AlignVCenter, "Part Name")
            painter.drawText(QRectF(tx + 190, ty, 35, 20), Qt.AlignCenter, "Qty")
            painter.drawText(QRectF(tx + 230, ty, table_w - 235, 20), Qt.AlignRight | Qt.AlignVCenter, f"Dim ({self.unit})")

            font_r = painter.font()
            font_r.setBold(False)
            painter.setFont(font_r)

            for idx in range(max_rows):
                e = self.entries[idx]
                ry = ty + 20 + (idx * row_h)

                if idx % 2 == 1:
                    painter.fillRect(QRectF(tx, ry, table_w, row_h), QColor("#f8f9fa"))

                painter.setPen(QColor("#222222"))
                painter.drawText(QRectF(tx + 4, ry, 30, row_h), Qt.AlignLeft | Qt.AlignVCenter, f"({e.tag})")
                disp = e.display_name if len(e.display_name) <= 20 else (e.display_name[:17] + "...")
                painter.drawText(QRectF(tx + 36, ry, 150, row_h), Qt.AlignLeft | Qt.AlignVCenter, disp)
                painter.drawText(QRectF(tx + 190, ry, 35, row_h), Qt.AlignCenter, str(e.count))

                dim_str = f"{format_dimension(e.length, self.unit)}×{format_dimension(e.width, self.unit)}"
                painter.drawText(QRectF(tx + 230, ry, table_w - 235, row_h), Qt.AlignRight | Qt.AlignVCenter, dim_str)

        def paintEvent(self, event: Any) -> None:
            painter = QPainter(self)
            self.render_drawing(painter, QRectF(self.rect()))
            painter.end()


# ---------------------------------------------------------------------------
# Qt Dialog Window (CutListWindow)
# ---------------------------------------------------------------------------
if QT_AVAILABLE:

    class NumericTableWidgetItem(QTableWidgetItem):
        def __init__(self, text: str, sort_val: float) -> None:
            super().__init__(text)
            self.sort_val = sort_val

        def __lt__(self, other: Any) -> bool:
            if isinstance(other, NumericTableWidgetItem):
                return self.sort_val < other.sort_val
            return super().__lt__(other)

    class CutListConsoleDialog(QDialog):
        """Monospace console output dialog for viewing, copying, or saving text cut list."""

        def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.text = text
            self.setWindowTitle("Cut List — Console Output")
            self.resize(860, 560)
            self.setMinimumSize(600, 380)
            self.setStyleSheet("""
                QDialog {
                    background-color: #0f172a;
                    color: #f8fafc;
                }
            """)
            self._build_ui()

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 14, 14, 14)
            layout.setSpacing(10)

            # Header
            header_layout = QHBoxLayout()
            icon_lbl = QLabel("🖨️")
            f_icon = icon_lbl.font()
            f_icon.setPointSize(16)
            icon_lbl.setFont(f_icon)
            header_layout.addWidget(icon_lbl)

            title_lbl = QLabel("<b>Cut List — Console Output</b>")
            font_t = title_lbl.font()
            font_t.setPointSize(11)
            title_lbl.setFont(font_t)
            title_lbl.setStyleSheet("color: #38bdf8;")
            header_layout.addWidget(title_lbl)
            header_layout.addStretch(1)

            hint_lbl = QLabel("ASCII cut list table — Copy to clipboard or save to text file")
            hint_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            header_layout.addWidget(hint_lbl)
            layout.addLayout(header_layout)

            # Monospace text view
            self.text_edit = QPlainTextEdit()
            self.text_edit.setReadOnly(True)
            self.text_edit.setPlainText(self.text)

            try:
                mono_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            except Exception:
                mono_font = QFont("Consolas", 10)
            mono_font.setPointSize(9.5)
            self.text_edit.setFont(mono_font)
            self.text_edit.setStyleSheet("""
                QPlainTextEdit {
                    background-color: #020617;
                    color: #e2e8f0;
                    border: 1px solid #334155;
                    border-radius: 4px;
                    padding: 8px;
                    selection-background-color: #0284c7;
                    selection-color: #ffffff;
                }
            """)
            layout.addWidget(self.text_edit, stretch=1)

            # Bottom Bar
            bot_layout = QHBoxLayout()
            lines = self.text.splitlines()
            line_count = len(lines)
            char_count = len(self.text)
            self.status_lbl = QLabel(f"Lines: {line_count}  |  Characters: {char_count}")
            self.status_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            bot_layout.addWidget(self.status_lbl)
            bot_layout.addStretch(1)

            copy_btn = QPushButton("📋 Copy to Clipboard")
            copy_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0284c7;
                    color: white;
                    font-weight: bold;
                    border-radius: 4px;
                    padding: 6px 14px;
                }
                QPushButton:hover {
                    background-color: #0369a1;
                }
            """)
            copy_btn.clicked.connect(self._copy_to_clipboard)
            bot_layout.addWidget(copy_btn)

            save_btn = QPushButton("💾 Save to File (.txt)...")
            save_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #f1f5f9;
                    border: 1px solid #475569;
                    border-radius: 4px;
                    padding: 6px 14px;
                }
                QPushButton:hover {
                    background-color: #334155;
                    border-color: #38bdf8;
                }
            """)
            save_btn.clicked.connect(self._save_to_file)
            bot_layout.addWidget(save_btn)

            close_btn = QPushButton("Close")
            close_btn.setStyleSheet("""
                QPushButton {
                    background-color: #334155;
                    color: #f1f5f9;
                    border-radius: 4px;
                    padding: 6px 16px;
                }
                QPushButton:hover {
                    background-color: #475569;
                }
            """)
            close_btn.clicked.connect(self.accept)
            bot_layout.addWidget(close_btn)

            layout.addLayout(bot_layout)

        def _copy_to_clipboard(self) -> None:
            clipboard = QApplication.clipboard()
            clipboard.setText(self.text)
            self.status_lbl.setText("✓ Copied full table to clipboard!")
            QTimer.singleShot(2500, lambda: self.status_lbl.setText(
                f"Lines: {len(self.text.splitlines())}  |  Characters: {len(self.text)}"
            ))

        def _save_to_file(self) -> None:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Cut List Text", "cut_list_table.txt", "Text Files (*.txt);;All Files (*)"
            )
            if not path:
                return
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self.text)
                self.status_lbl.setText(f"✓ Saved to {Path(path).name}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save text file:\n{e}")


    class MaterialLibraryDialog(QDialog):
        """Search and browse materials (both In-Model materials and 640+ Library items)
        for assigning to a component. Material only changes after clicking 'Save Material'.
        """

        def __init__(
            self,
            parent: Optional[QWidget] = None,
            current_material: str = "",
            available_materials: Optional[List[str]] = None,
            part_name: str = "",
            scene: Any = None,
            thumbnail_cache: Optional[Dict] = None,
        ) -> None:
            super().__init__(parent)
            self.selected_material: Optional[str] = None
            self.selected_item: Optional[LibraryMaterialItem] = None
            self.thumbnail_cache = thumbnail_cache if thumbnail_cache is not None else {}
            self.current_material = current_material
            self.available_materials = available_materials or []
            self.part_name = part_name
            self.scene = scene
            self.in_model_items: List[LibraryMaterialItem] = []

            self._build_in_model_items()

            self.setWindowTitle("Select Material — OpenCutList")
            self.resize(740, 560)
            self.setMinimumSize(600, 440)
            self.setStyleSheet("""
                QDialog {
                    background-color: #0f172a;
                    color: #f8fafc;
                }
            """)
            self._build_ui()
            self._populate_categories()
            self._filter_materials()
            self._select_current_material()

        def _build_in_model_items(self) -> None:
            lib = get_material_library()
            seen = set()
            self.in_model_items.clear()

            all_model_mats = list(self.available_materials)
            if self.current_material and self.current_material not in all_model_mats:
                all_model_mats.insert(0, self.current_material)

            for m in all_model_mats:
                if not m or m in seen:
                    continue
                seen.add(m)
                existing = lib.by_name.get(m.lower())
                st = get_material_stock_label(m, scene=self.scene)
                pm = "Solid" if is_linear_stock(st) else "Sheet"
                if existing:
                    item = LibraryMaterialItem(
                        name=m,
                        category_id="in_model",
                        category_name="⭐ In Model",
                        stock_type=existing.stock_type,
                        packing_mode=existing.packing_mode,
                        texture_file=existing.texture_file,
                        rgb=existing.rgb,
                        sw=existing.sw,
                        sh=existing.sh,
                    )
                else:
                    item = LibraryMaterialItem(
                        name=m,
                        category_id="in_model",
                        category_name="⭐ In Model",
                        stock_type=st,
                        packing_mode=pm,
                    )
                self.in_model_items.append(item)

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(14, 14, 14, 14)
            layout.setSpacing(10)

            # Header with Part & Current Material info
            header_box = QVBoxLayout()
            header_box.setSpacing(3)

            top_row = QHBoxLayout()
            title_lbl = QLabel("<b>Select Component Material</b>")
            font_t = title_lbl.font()
            font_t.setPointSize(11)
            title_lbl.setFont(font_t)
            title_lbl.setStyleSheet("color: #38bdf8;")
            top_row.addWidget(title_lbl)
            top_row.addStretch(1)

            if self.part_name:
                part_lbl = QLabel(f"Part: <b>{self.part_name}</b>")
                part_lbl.setStyleSheet("color: #e2e8f0; font-size: 11px;")
                top_row.addWidget(part_lbl)
            header_box.addLayout(top_row)

            sub_row = QHBoxLayout()
            cur_lbl = QLabel(f"Current: <b>{self.current_material or 'None'}</b>")
            cur_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            sub_row.addWidget(cur_lbl)
            sub_row.addStretch(1)

            hint_lbl = QLabel("Double-click or click 'Save Material' to apply & update groups")
            hint_lbl.setStyleSheet("color: #64748b; font-size: 11px;")
            sub_row.addWidget(hint_lbl)
            header_box.addLayout(sub_row)
            layout.addLayout(header_box)

            # Search & Category Controls
            ctrl_layout = QHBoxLayout()
            self.search_input = QLineEdit()
            self.search_input.setPlaceholderText("🔍 Search materials by name, species, RAL color...")
            self.search_input.setClearButtonEnabled(True)
            self.search_input.setStyleSheet("""
                QLineEdit {
                    background-color: #1e293b;
                    color: #f8fafc;
                    border: 1px solid #475569;
                    border-radius: 4px;
                    padding: 5px 8px;
                    font-size: 12px;
                }
                QLineEdit:focus {
                    border-color: #38bdf8;
                }
            """)
            self.search_input.textChanged.connect(self._filter_materials)
            ctrl_layout.addWidget(self.search_input, stretch=2)

            self.cat_combo = QComboBox()
            self.cat_combo.setStyleSheet("""
                QComboBox {
                    background-color: #1e293b;
                    color: #f8fafc;
                    border: 1px solid #475569;
                    border-radius: 4px;
                    padding: 5px 8px;
                    font-size: 12px;
                }
                QComboBox QAbstractItemView {
                    background-color: #0f172a;
                    color: #f8fafc;
                    selection-background-color: #0284c7;
                }
            """)
            self.cat_combo.currentIndexChanged.connect(self._filter_materials)
            ctrl_layout.addWidget(self.cat_combo, stretch=1)
            layout.addLayout(ctrl_layout)

            # Table
            self.table = QTableWidget()
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(["Preview", "Material Name", "Category", "Stock Type"])
            self.table.setIconSize(QSize(24, 24))
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setSelectionMode(QTableWidget.SingleSelection)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.verticalHeader().setVisible(False)
            self.table.itemDoubleClicked.connect(self._on_double_clicked)
            self.table.itemSelectionChanged.connect(self._on_selection_changed)

            h = self.table.horizontalHeader()
            h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            h.setSectionResizeMode(1, QHeaderView.Stretch)
            h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
            layout.addWidget(self.table)

            # Bottom Action Bar
            bot_layout = QHBoxLayout()
            self.status_lbl = QLabel("Ready.")
            self.status_lbl.setStyleSheet("color: #94a3b8; font-size: 11px;")
            bot_layout.addWidget(self.status_lbl)
            bot_layout.addStretch(1)

            self.cancel_btn = QPushButton("Cancel")
            self.cancel_btn.setStyleSheet("""
                QPushButton {
                    background-color: #334155;
                    color: #f1f5f9;
                    border-radius: 4px;
                    padding: 6px 14px;
                }
                QPushButton:hover {
                    background-color: #475569;
                }
            """)
            self.cancel_btn.clicked.connect(self.reject)
            bot_layout.addWidget(self.cancel_btn)

            self.save_btn = QPushButton("💾 Save Material")
            self.save_btn.setEnabled(False)
            self.save_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2b9348;
                    color: white;
                    font-weight: bold;
                    border-radius: 4px;
                    padding: 6px 16px;
                }
                QPushButton:hover {
                    background-color: #55a630;
                }
                QPushButton:disabled {
                    background-color: #334155;
                    color: #64748b;
                }
            """)
            self.save_btn.clicked.connect(self._on_save_clicked)
            bot_layout.addWidget(self.save_btn)
            layout.addLayout(bot_layout)

        def _populate_categories(self) -> None:
            lib = get_material_library()
            self.cat_combo.blockSignals(True)
            self.cat_combo.clear()
            total_items = len(self.in_model_items) + len(lib.items)
            self.cat_combo.addItem(f"All Materials ({total_items})", "")
            if self.in_model_items:
                self.cat_combo.addItem(f"⭐ In Model ({len(self.in_model_items)})", "in_model")
            for cid, cname in lib.categories.items():
                cnt = lib.category_counts.get(cid, 0)
                if cnt > 0:
                    self.cat_combo.addItem(f"{cname} ({cnt})", cid)
            self.cat_combo.blockSignals(False)

        def _filter_materials(self) -> None:
            lib = get_material_library()
            query = self.search_input.text().strip().lower()
            cat_id = self.cat_combo.currentData() or ""

            matched: List[LibraryMaterialItem] = []

            if cat_id == "in_model":
                for it in self.in_model_items:
                    if query and query not in it.name.lower():
                        continue
                    matched.append(it)
            elif cat_id:
                for it in lib.items:
                    if it.category_id != cat_id:
                        continue
                    if query and (query not in it.name.lower() and query not in it.category_name.lower()):
                        continue
                    matched.append(it)
            else:
                # All: In-model items first, then library items
                seen_names = set()
                for it in self.in_model_items:
                    if query and query not in it.name.lower():
                        continue
                    matched.append(it)
                    seen_names.add(it.name.lower())

                for it in lib.items:
                    if it.name.lower() in seen_names:
                        continue
                    if query and (query not in it.name.lower() and query not in it.category_name.lower()):
                        continue
                    matched.append(it)

            total_matched = len(matched)
            display_items = matched[:150] if (not query and not cat_id) else matched

            self.table.setRowCount(len(display_items))
            for row, it in enumerate(display_items):
                # Col 0: Preview Icon
                _, icon = get_material_thumbnail(it.name, scene=self.scene, size=24, cache=self.thumbnail_cache)
                icon_item = QTableWidgetItem()
                if icon is not None and not icon.isNull():
                    icon_item.setIcon(icon)
                icon_item.setTextAlignment(Qt.AlignCenter)
                icon_item.setData(Qt.UserRole, it)
                self.table.setItem(row, 0, icon_item)

                # Col 1: Name
                name_item = QTableWidgetItem(it.name)
                name_item.setData(Qt.UserRole, it)
                if it.name == self.current_material:
                    name_item.setForeground(QColor("#38bdf8"))
                    f = name_item.font()
                    f.setBold(True)
                    name_item.setFont(f)
                self.table.setItem(row, 1, name_item)

                # Col 2: Category
                cat_item = QTableWidgetItem(it.category_name)
                cat_item.setData(Qt.UserRole, it)
                if it.category_id == "in_model":
                    cat_item.setForeground(QColor("#fbbf24"))
                self.table.setItem(row, 2, cat_item)

                # Col 3: Stock Type
                st_item = QTableWidgetItem(it.stock_type)
                st_item.setData(Qt.UserRole, it)
                self.table.setItem(row, 3, st_item)

                self.table.setRowHeight(row, 26)

            self.status_lbl.setText(f"Showing {len(display_items)} of {total_matched} materials")
            self.save_btn.setEnabled(self.table.currentRow() >= 0)

        def _select_current_material(self) -> None:
            if not self.current_material:
                if self.table.rowCount() > 0:
                    self.table.selectRow(0)
                return
            for r in range(self.table.rowCount()):
                item = self.table.item(r, 1)
                if item and item.text().lower() == self.current_material.lower():
                    self.table.selectRow(r)
                    self.table.scrollToItem(item)
                    return
            if self.table.rowCount() > 0:
                self.table.selectRow(0)

        def _on_selection_changed(self) -> None:
            row = self.table.currentRow()
            if row >= 0:
                item = self.table.item(row, 1)
                it = item.data(Qt.UserRole) if item else None
                if it:
                    self.status_lbl.setText(f"Selected: {it.name} ({it.category_name})")
                self.save_btn.setEnabled(True)
            else:
                self.save_btn.setEnabled(False)

        def _on_double_clicked(self, item: QTableWidgetItem) -> None:
            it = item.data(Qt.UserRole)
            if it:
                self.selected_material = it.name
                self.selected_item = it
                self.accept()

        def _on_save_clicked(self) -> None:
            row = self.table.currentRow()
            if row >= 0:
                item = self.table.item(row, 1)
                it = item.data(Qt.UserRole) if item else None
                if it:
                    self.selected_material = it.name
                    self.selected_item = it
                    self.accept()

    class CutListAboutDialog(QDialog):
        """About Dialog displaying purpose for woodworkers & cabinet makers,
        developer attribution (brillian11 / github/brillian11), and feature highlights.
        """

        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self.setWindowTitle("About OpenCutList for IngeTrazo")
            self.setMinimumSize(540, 500)
            self.resize(560, 520)
            self.setStyleSheet("""
                QDialog {
                    background-color: #0f172a;
                    color: #f8fafc;
                }
            """)
            self._build_ui()

        def _build_ui(self) -> None:
            layout = QVBoxLayout(self)
            layout.setContentsMargins(20, 20, 20, 18)
            layout.setSpacing(14)

            # Header: Icon, Title & Version Badge
            header_layout = QHBoxLayout()

            icon_lbl = QLabel("🪵")
            font_icon = icon_lbl.font()
            font_icon.setPointSize(30)
            icon_lbl.setFont(font_icon)
            header_layout.addWidget(icon_lbl)
            header_layout.addSpacing(8)

            title_box = QVBoxLayout()
            title_box.setSpacing(3)

            title_row = QHBoxLayout()
            title_lbl = QLabel("<b>OpenCutList</b>")
            font_t = title_lbl.font()
            font_t.setPointSize(16)
            font_t.setBold(True)
            title_lbl.setFont(font_t)
            title_lbl.setStyleSheet("color: #38bdf8;")
            title_row.addWidget(title_lbl)

            cad_lbl = QLabel("for IngeTrazo CAD")
            font_c = cad_lbl.font()
            font_c.setPointSize(12)
            cad_lbl.setFont(font_c)
            cad_lbl.setStyleSheet("color: #94a3b8;")
            title_row.addWidget(cad_lbl)

            ver_badge = QLabel(f" {PLUGIN_VERSION} ")
            ver_badge.setStyleSheet("""
                background-color: #166534;
                color: #86efac;
                font-weight: bold;
                font-size: 11px;
                border-radius: 4px;
                padding: 2px 6px;
            """)
            title_row.addWidget(ver_badge)
            title_row.addStretch(1)
            title_box.addLayout(title_row)

            sub_lbl = QLabel("Workshop Production, 1D/2D Nesting & Technical Drawing Suite")
            sub_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px;")
            title_box.addWidget(sub_lbl)

            header_layout.addLayout(title_box)
            header_layout.addStretch(1)
            layout.addLayout(header_layout)

            # Horizontal divider line
            divider = QFrame()
            divider.setFrameShape(QFrame.HLine)
            divider.setStyleSheet("color: #334155; margin: 2px 0;")
            layout.addWidget(divider)

            # Target Audience Card
            target_group = QGroupBox("🪵 Designed for Woodworkers & Cabinet Makers")
            target_group.setStyleSheet("""
                QGroupBox {
                    background-color: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    margin-top: 8px;
                    padding-top: 14px;
                    font-weight: bold;
                    color: #38bdf8;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    padding: 0 6px;
                }
            """)
            tg_layout = QVBoxLayout(target_group)
            tg_layout.setContentsMargins(14, 12, 14, 12)
            tg_layout.setSpacing(8)

            mission_lbl = QLabel(
                "This plugin is specifically built for <b>woodworkers</b>, <b>cabinet makers</b>, "
                "<b>carpenters</b>, and <b>furniture designers</b> to turn 3D digital models into "
                "clear, accurate, shop-ready production data."
            )
            mission_lbl.setWordWrap(True)
            mission_lbl.setStyleSheet("color: #f1f5f9; font-size: 12px; line-height: 1.4;")
            tg_layout.addWidget(mission_lbl)

            features_lbl = QLabel(
                "• <b>Accurate Cutting Lists</b>: Automatic grouping, thickness sorting & area takeoffs<br>"
                "• <b>1D Solid Lumber Optimization</b>: Linear board cutting plans with kerf waste tracking<br>"
                "• <b>2D Sheet Goods Nesting</b>: Guillotine packing for plywood, MDF & melamine sheets<br>"
                "• <b>3D Exploded Drawings</b>: Axonometric assembly drawings with lettered callout balloons<br>"
                "• <b>Material Library Sync</b>: 640+ textures & RAL colors integrated with IngeTrazo"
            )
            features_lbl.setWordWrap(True)
            features_lbl.setStyleSheet("color: #cbd5e1; font-size: 11px; line-height: 1.5;")
            tg_layout.addWidget(features_lbl)

            layout.addWidget(target_group)

            # Developer & Credits Card
            dev_group = QGroupBox("👤 Developer & Credits")
            dev_group.setStyleSheet("""
                QGroupBox {
                    background-color: #1e293b;
                    border: 1px solid #334155;
                    border-radius: 6px;
                    margin-top: 8px;
                    padding-top: 14px;
                    font-weight: bold;
                    color: #38bdf8;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    subcontrol-position: top left;
                    padding: 0 6px;
                }
            """)
            dev_layout = QVBoxLayout(dev_group)
            dev_layout.setContentsMargins(14, 12, 14, 12)
            dev_layout.setSpacing(10)

            author_row = QHBoxLayout()
            author_lbl = QLabel(f"Developer: <b>{PLUGIN_AUTHOR}</b>")
            author_lbl.setStyleSheet("color: #f8fafc; font-size: 12px;")
            author_row.addWidget(author_lbl)
            author_row.addStretch(1)

            github_link = QLabel(
                f'<a href="{PLUGIN_GITHUB}" style="color: #38bdf8; text-decoration: none;">'
                '🔗 <b>github.com/brillian11</b></a>'
            )
            github_link.setOpenExternalLinks(True)
            github_link.setStyleSheet("font-size: 12px;")
            author_row.addWidget(github_link)
            dev_layout.addLayout(author_row)

            # Quick button to open GitHub
            gh_btn_row = QHBoxLayout()
            gh_btn = QPushButton("🌐 Visit GitHub (github/brillian11)")
            gh_btn.setToolTip(f"Open {PLUGIN_GITHUB} in your web browser")
            gh_btn.setStyleSheet("""
                QPushButton {
                    background-color: #0f172a;
                    color: #38bdf8;
                    border: 1px solid #0284c7;
                    border-radius: 4px;
                    padding: 6px 14px;
                    font-size: 11px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #0284c7;
                    color: #ffffff;
                }
            """)
            gh_btn.clicked.connect(lambda: open_url_in_browser(PLUGIN_GITHUB))
            gh_btn_row.addWidget(gh_btn)
            gh_btn_row.addStretch(1)
            dev_layout.addLayout(gh_btn_row)

            layout.addWidget(dev_group)

            # Footer Note & Close Button
            bot_layout = QHBoxLayout()
            license_lbl = QLabel("Open Source · Free Software · GPL-3.0-or-later")
            license_lbl.setStyleSheet("color: #64748b; font-size: 10px;")
            bot_layout.addWidget(license_lbl)
            bot_layout.addStretch(1)

            close_btn = QPushButton("Close")
            close_btn.setStyleSheet("""
                QPushButton {
                    background-color: #334155;
                    color: white;
                    border-radius: 4px;
                    padding: 6px 20px;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background-color: #475569;
                }
            """)
            close_btn.clicked.connect(self.accept)
            bot_layout.addWidget(close_btn)
            layout.addLayout(bot_layout)

    class CutListWindow(QDialog):
        """The main Cut List Window with List, Diagrams, and Exploded Drawing."""

        def __init__(self, viewport: Any, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent or getattr(viewport, "window", lambda: None)())
            self.viewport = viewport
            self.raw_parts: List[RawPart] = []
            self.entries: List[CutListEntry] = []
            self.material_types: Dict[str, str] = {}

            self.sheets_by_mat: Dict[str, List[SheetLayout]] = {}
            self.lumber_by_mat: Dict[str, List[LumberBoard]] = {}
            self.current_mat_name: str = ""
            self.current_page: int = 0
            self._sort_col: int = 7  # Default: Thickness (Column 7 in 10-column table)
            self._sort_asc: bool = False  # Default: Descending (thickest first)
            self._thumbnail_cache: Dict[str, Tuple[Any, Any]] = {}

            self.setWindowTitle("Cut List — IngeTrazo")
            self.setMinimumSize(960, 680)
            self.resize(1040, 720)

            self._build_ui()
            self._load_selection()

        def _build_ui(self) -> None:
            main_layout = QVBoxLayout(self)
            main_layout.setContentsMargins(14, 14, 14, 14)
            main_layout.setSpacing(10)

            # Top Selection Status Bar
            status_box = QHBoxLayout()
            self.selection_label = QLabel("Analyzing selected objects...")
            font_s = self.selection_label.font()
            font_s.setPointSize(10)
            font_s.setBold(True)
            self.selection_label.setFont(font_s)
            status_box.addWidget(self.selection_label)

            status_box.addStretch(1)

            self.recheck_btn = QPushButton("⟳ Re-check Selection")
            self.recheck_btn.setToolTip("Re-read currently selected groups from the viewport.")
            self.recheck_btn.clicked.connect(self._load_selection)
            status_box.addWidget(self.recheck_btn)

            self.about_btn = QPushButton("ℹ About")
            self.about_btn.setToolTip("About OpenCutList for woodworkers & cabinet makers by brillian11")
            self.about_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1e293b;
                    color: #cbd5e1;
                    border: 1px solid #475569;
                    border-radius: 4px;
                    padding: 4px 10px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    color: #38bdf8;
                    border-color: #38bdf8;
                    background-color: #334155;
                }
            """)
            self.about_btn.clicked.connect(self._show_about_dialog)
            status_box.addWidget(self.about_btn)

            main_layout.addLayout(status_box)

            # Setup Settings GroupBox
            settings_group = QGroupBox("Cut List & Stock Material Settings")
            settings_layout = QHBoxLayout(settings_group)
            settings_layout.setSpacing(16)

            # Col 1: General
            col1 = QFormLayout()
            self.unit_combo = QComboBox()
            self.unit_combo.addItems(["mm", "cm", "m", "in"])
            self.unit_combo.setCurrentText("mm")
            self.unit_combo.currentTextChanged.connect(self._on_unit_changed)
            col1.addRow("Measurement Unit:", self.unit_combo)

            self.group_toggle = QCheckBox("Merge identical dimensions")
            self.group_toggle.setChecked(True)
            col1.addRow("Grouping Mode:", self.group_toggle)

            self.kerf_spin = QDoubleSpinBox()
            self.kerf_spin.setRange(0.0, 50.0)
            self.kerf_spin.setValue(3.0)
            self.kerf_spin.setSuffix(" mm")
            col1.addRow("Blade Kerf (Cut Gap):", self.kerf_spin)
            settings_layout.addLayout(col1, stretch=1)

            # Col 2: Material Table
            col2 = QVBoxLayout()
            col2.addWidget(QLabel("<b>Materials in Selection (Auto-Detected):</b>"))
            self.mat_table = QTableWidget()
            self.mat_table.setColumnCount(2)
            self.mat_table.setHorizontalHeaderLabels(["Material Name", "Stock Type"])
            self.mat_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
            self.mat_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
            self.mat_table.verticalHeader().setVisible(False)
            self.mat_table.setMaximumHeight(85)
            col2.addWidget(self.mat_table)
            settings_layout.addLayout(col2, stretch=2)

            # Col 3: Stock Presets
            col3 = QFormLayout()
            self.lumber_len_spin = QDoubleSpinBox()
            self.lumber_len_spin.setRange(500.0, 10000.0)
            self.lumber_len_spin.setValue(2400.0)
            self.lumber_len_spin.setSuffix(" mm")
            col3.addRow("Solid Board Length:", self.lumber_len_spin)

            dim_box = QHBoxLayout()
            self.sheet_w_spin = QDoubleSpinBox()
            self.sheet_w_spin.setRange(100.0, 10000.0)
            self.sheet_w_spin.setValue(2440.0)
            self.sheet_w_spin.setSuffix(" mm")

            self.sheet_h_spin = QDoubleSpinBox()
            self.sheet_h_spin.setRange(100.0, 10000.0)
            self.sheet_h_spin.setValue(1220.0)
            self.sheet_h_spin.setSuffix(" mm")

            dim_box.addWidget(self.sheet_w_spin)
            dim_box.addWidget(QLabel("×"))
            dim_box.addWidget(self.sheet_h_spin)
            col3.addRow("Plywood Sheet W × H:", dim_box)

            self.rotate_toggle = QCheckBox("Allow 90° sheet rotation")
            self.rotate_toggle.setChecked(True)
            col3.addRow("Sheet Nesting:", self.rotate_toggle)
            settings_layout.addLayout(col3, stretch=2)

            main_layout.addWidget(settings_group)

            # Central GENERATE Button
            self.generate_btn = QPushButton("🚀 Generate Cut List & Drawings")
            font_g = self.generate_btn.font()
            font_g.setPointSize(11)
            font_g.setBold(True)
            self.generate_btn.setFont(font_g)
            self.generate_btn.setMinimumHeight(40)
            self.generate_btn.setStyleSheet(
                "QPushButton { background-color: #2b9348; color: white; border-radius: 5px; } "
                "QPushButton:hover { background-color: #55a630; } "
                "QPushButton:pressed { background-color: #1b4332; }"
            )
            self.generate_btn.clicked.connect(self.generate_all)
            main_layout.addWidget(self.generate_btn)

            # Tabs
            self.tabs = QTabWidget()

            # TAB 1: Table
            tab_table = QWidget()
            tt_layout = QVBoxLayout(tab_table)
            tt_layout.setContentsMargins(4, 8, 4, 4)

            filter_box = QHBoxLayout()
            filter_box.addWidget(QLabel("<b>Filter:</b>"))
            self.search_input = QLineEdit()
            self.search_input.setPlaceholderText("Filter by part name...")
            self.search_input.textChanged.connect(self._apply_table_filter)
            filter_box.addWidget(self.search_input, stretch=2)

            filter_box.addWidget(QLabel("<b>Material:</b>"))
            self.material_filter_combo = QComboBox()
            self.material_filter_combo.addItem("All Materials")
            self.material_filter_combo.currentIndexChanged.connect(self._apply_table_filter)
            filter_box.addWidget(self.material_filter_combo, stretch=1)

            filter_box.addWidget(QLabel("<b>Sort Thickness:</b>"))
            self.thick_sort_combo = QComboBox()
            self.thick_sort_combo.addItem("Thickest First (Descending)")
            self.thick_sort_combo.addItem("Thinnest First (Ascending)")
            self.thick_sort_combo.currentIndexChanged.connect(self._on_thick_sort_changed)
            filter_box.addWidget(self.thick_sort_combo, stretch=1)
            tt_layout.addLayout(filter_box)

            self.table = QTableWidget()
            self.table.setAlternatingRowColors(True)
            self.table.setEditTriggers(QTableWidget.NoEditTriggers)
            self.table.setSelectionBehavior(QTableWidget.SelectRows)
            self.table.setSortingEnabled(False)
            self.table.setIconSize(QSize(22, 22))
            self.table.verticalHeader().setVisible(False)
            self.table.horizontalHeader().sectionClicked.connect(self._on_table_header_clicked)
            tt_layout.addWidget(self.table)

            t_actions = QHBoxLayout()
            self.summary_label = QLabel("Click 'Generate' to calculate cutting list.")
            font_sum = self.summary_label.font()
            font_sum.setBold(True)
            self.summary_label.setFont(font_sum)
            t_actions.addWidget(self.summary_label)

            t_actions.addStretch(1)

            self.copy_btn = QPushButton("📋 Copy Table (TSV)")
            self.copy_btn.clicked.connect(self._copy_tsv)
            t_actions.addWidget(self.copy_btn)

            self.export_csv_btn = QPushButton("💾 Export CSV...")
            self.export_csv_btn.clicked.connect(self._export_csv)
            t_actions.addWidget(self.export_csv_btn)

            self.print_btn = QPushButton("🖨️ Print PDF")
            self.print_btn.setToolTip("Export and print OpenCutList Parts List PDF document")
            self.print_btn.clicked.connect(self._export_pdf)
            t_actions.addWidget(self.print_btn)

            tt_layout.addLayout(t_actions)
            self.tabs.addTab(tab_table, "📋 Cutting List")

            # TAB 2: Cutting Diagrams
            tab_diagram = QWidget()
            td_layout = QVBoxLayout(tab_diagram)
            td_layout.setContentsMargins(4, 8, 4, 4)

            nav_bar = QHBoxLayout()
            nav_bar.addWidget(QLabel("Material Diagram:"))
            self.mat_selector_combo = QComboBox()
            self.mat_selector_combo.currentTextChanged.connect(self._on_material_diagram_changed)
            nav_bar.addWidget(self.mat_selector_combo, stretch=1)

            self.prev_btn = QPushButton("◀ Previous")
            self.prev_btn.clicked.connect(self._prev_page)
            nav_bar.addWidget(self.prev_btn)

            self.diagram_info_label = QLabel("Diagram: —")
            font_di = self.diagram_info_label.font()
            font_di.setBold(True)
            self.diagram_info_label.setFont(font_di)
            nav_bar.addWidget(self.diagram_info_label)

            self.next_btn = QPushButton("Next ▶")
            self.next_btn.clicked.connect(self._next_page)
            nav_bar.addWidget(self.next_btn)

            self.save_diag_png_btn = QPushButton("💾 Save Diagram (PNG)...")
            self.save_diag_png_btn.clicked.connect(self._save_diagram_png)
            nav_bar.addWidget(self.save_diag_png_btn)

            td_layout.addLayout(nav_bar)

            self.diagram_widget = CuttingDiagramWidget()
            td_layout.addWidget(self.diagram_widget, stretch=1)
            self.tabs.addTab(tab_diagram, "📐 2D Cutting Diagrams")

            # TAB 3: 3D Exploded Drawing
            tab_exploded = QWidget()
            te_layout = QVBoxLayout(tab_exploded)
            te_layout.setContentsMargins(4, 8, 4, 4)

            exp_toolbar = QHBoxLayout()

            exp_toolbar.addWidget(QLabel("<b>Explosion:</b>"))
            self.explode_slider = QSlider(Qt.Horizontal)
            self.explode_slider.setRange(0, 250)
            self.explode_slider.setValue(0)  # Default 0% assembled
            self.explode_slider.setToolTip("Adjust spacing between exploded parts (0% = Assembled).")
            self.explode_slider.valueChanged.connect(self._on_slider_exploded)
            self.explode_slider.sliderReleased.connect(self._on_slider_released)
            exp_toolbar.addWidget(self.explode_slider, stretch=2)

            self.slider_label = QLabel("0%")
            self.slider_label.setFixedWidth(40)
            exp_toolbar.addWidget(self.slider_label)

            self.iso_btn = QPushButton("Isometric")
            self.iso_btn.clicked.connect(lambda: self.drawing_widget.set_view_angles(-45.0, 30.0))
            exp_toolbar.addWidget(self.iso_btn)

            self.front_btn = QPushButton("Front")
            self.front_btn.clicked.connect(lambda: self.drawing_widget.set_view_angles(-90.0, 0.0))
            exp_toolbar.addWidget(self.front_btn)

            self.top_btn = QPushButton("Top")
            self.top_btn.clicked.connect(lambda: self.drawing_widget.set_view_angles(-90.0, 89.0))
            exp_toolbar.addWidget(self.top_btn)

            self.callouts_chk = QCheckBox("Callouts (A, B...)")
            self.callouts_chk.setChecked(True)
            self.callouts_chk.toggled.connect(self._toggle_callouts)
            exp_toolbar.addWidget(self.callouts_chk)

            exp_toolbar.addStretch(1)

            self.save_draw_png_btn = QPushButton("💾 Export PNG...")
            self.save_draw_png_btn.setToolTip("Export high-resolution drawing image.")
            self.save_draw_png_btn.clicked.connect(self._export_drawing_png)
            exp_toolbar.addWidget(self.save_draw_png_btn)

            self.save_draw_pdf_btn = QPushButton("📄 Export PDF...")
            self.save_draw_pdf_btn.setToolTip("Export print-ready PDF drawing sheet.")
            self.save_draw_pdf_btn.clicked.connect(self._export_drawing_pdf)
            exp_toolbar.addWidget(self.save_draw_pdf_btn)

            te_layout.addLayout(exp_toolbar)

            self.drawing_widget = ExplodedDrawingWidget(viewport=self.viewport, parent=self)
            te_layout.addWidget(self.drawing_widget, stretch=1)

            self.tabs.addTab(tab_exploded, "🎨 Exploded Drawing")
            self.tabs.currentChanged.connect(self._on_tab_changed)
            main_layout.addWidget(self.tabs, stretch=1)

            # Bottom Bar with About & Close Buttons
            bottom_box = QHBoxLayout()
            about_link_btn = QPushButton("ℹ About OpenCutList")
            about_link_btn.setToolTip("Woodworker & cabinet maker extension details, developer credits")
            about_link_btn.setStyleSheet("""
                QPushButton {
                    background-color: transparent;
                    color: #94a3b8;
                    border: 1px solid #475569;
                    border-radius: 4px;
                    padding: 4px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    color: #38bdf8;
                    border-color: #38bdf8;
                    background-color: #1e293b;
                }
            """)
            about_link_btn.clicked.connect(self._show_about_dialog)
            bottom_box.addWidget(about_link_btn)

            bottom_box.addStretch(1)
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(self.accept)
            bottom_box.addWidget(close_btn)
            main_layout.addLayout(bottom_box)

        def _show_about_dialog(self) -> None:
            show_about_dialog(self)

        def _on_tab_changed(self, idx: int) -> None:
            if idx == 2 and hasattr(self, "drawing_widget"):
                self.drawing_widget.update_3d_render(full_res=True, refresh_cad=True)

        def closeEvent(self, event: Any) -> None:
            vp = self.viewport
            scene = getattr(vp, "scene", None)
            if scene is not None:
                scene.version = getattr(scene, "version", 0) + 1
            if vp is not None and hasattr(vp, "update"):
                vp.update()
            super().closeEvent(event)

        def accept(self) -> None:
            vp = self.viewport
            scene = getattr(vp, "scene", None)
            if scene is not None:
                scene.version = getattr(scene, "version", 0) + 1
            if vp is not None and hasattr(vp, "update"):
                vp.update()
            super().accept()

        def reject(self) -> None:
            vp = self.viewport
            scene = getattr(vp, "scene", None)
            if scene is not None:
                scene.version = getattr(scene, "version", 0) + 1
            if vp is not None and hasattr(vp, "update"):
                vp.update()
            super().reject()

        # -------------------------------------------------------------------
        # Selection & Materials
        # -------------------------------------------------------------------
        def _load_selection(self) -> None:
            scene = getattr(self.viewport, "scene", None)
            selected_groups = get_selected_groups(scene)

            if not selected_groups:
                self.selection_label.setText("⚠ No objects currently selected in viewport.")
                self.selection_label.setStyleSheet("color: #e63946;")
                self.raw_parts = []
                self.mat_table.setRowCount(0)
            else:
                self.raw_parts = extract_parts_from_groups(selected_groups)
                count = len(self.raw_parts)
                self.selection_label.setText(f"✓ {count} parts selected and ready for cut list.")
                self.selection_label.setStyleSheet("color: #2b9348;")
                self._populate_material_table()
                if self.tabs.currentIndex() == 2 and hasattr(self, "drawing_widget"):
                    self.drawing_widget.update_3d_render(full_res=True, refresh_cad=True)

        def _populate_material_table(self) -> None:
            mats: Dict[str, Tuple[float, float]] = {}
            for p in self.raw_parts:
                if p.material not in mats:
                    mats[p.material] = (p.width, p.thickness)

            self.mat_table.setRowCount(len(mats))
            scene = getattr(self.viewport, "scene", None) if hasattr(self, "viewport") else None

            for row, (mat_name, (w, t)) in enumerate(mats.items()):
                # Item 0: Material name with thumbnail icon
                _, mat_icon = get_material_thumbnail(
                    mat_name, scene=scene, size=18, cache=self._thumbnail_cache
                )
                name_item = QTableWidgetItem(mat_name)
                if mat_icon is not None and not mat_icon.isNull():
                    name_item.setIcon(mat_icon)
                self.mat_table.setItem(row, 0, name_item)

                # Item 1: Stock Type combo following material library category
                combo = QComboBox()
                combo.addItems(STOCK_TYPE_CHOICES)

                detected = self.material_types.get(
                    mat_name,
                    get_material_stock_label(mat_name, width=w, thickness=t, scene=scene),
                )
                self.material_types[mat_name] = detected

                idx = combo.findText(detected)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    for i in range(combo.count()):
                        txt = combo.itemText(i)
                        if detected.lower() in txt.lower():
                            combo.setCurrentIndex(i)
                            break
                        if is_linear_stock(detected) and is_linear_stock(txt):
                            combo.setCurrentIndex(i)
                            break

                combo.currentIndexChanged.connect(
                    lambda _idx, m=mat_name, c=combo: self._on_mat_type_selected(m, c)
                )
                self.mat_table.setCellWidget(row, 1, combo)

        def _on_mat_type_selected(self, mat_name: str, combo: QComboBox) -> None:
            self.material_types[mat_name] = combo.currentText()

        def _on_unit_changed(self, unit: str) -> None:
            self.lumber_len_spin.setSuffix(f" {unit}")
            self.sheet_w_spin.setSuffix(f" {unit}")
            self.sheet_h_spin.setSuffix(f" {unit}")
            self.kerf_spin.setSuffix(f" {unit}")
            if self.entries:
                self._populate_table(self.entries)
                self._update_active_diagram()
                self.drawing_widget.set_data(self.raw_parts, self.entries, unit)

        def _on_slider_exploded(self, val: int) -> None:
            self.slider_label.setText(f"{val}%")
            self.drawing_widget.set_explode_factor(val / 100.0)

        def _on_slider_released(self) -> None:
            if hasattr(self, "drawing_widget"):
                if getattr(self.drawing_widget, "_idle_timer", None) is not None:
                    self.drawing_widget._idle_timer.stop()
                self.drawing_widget.update_3d_render(full_res=True, refresh_cad=True)

        def _toggle_callouts(self, checked: bool) -> None:
            self.drawing_widget.show_callouts = checked
            self.drawing_widget.update()

        # -------------------------------------------------------------------
        # Core Generation (List, Diagrams, and Exploded Drawing)
        # -------------------------------------------------------------------
        def generate_all(self) -> None:
            if not self.raw_parts:
                self._load_selection()
                if not self.raw_parts:
                    QMessageBox.warning(
                        self,
                        "No Selection",
                        "Please select the objects (groups or components) you want to cut in the 3D viewport first."
                    )
                    return

            u = self.unit_combo.currentText()
            factor = UNIT_FACTORS.get(u, 1000.0)

            # 1. Group parts
            merge = self.group_toggle.isChecked()
            self.entries = group_parts(self.raw_parts, merge_by_dimensions=merge)

            # 2. Material Diagrams
            self.sheets_by_mat.clear()
            self.lumber_by_mat.clear()

            sheet_w = self.sheet_w_spin.value() / factor
            sheet_h = self.sheet_h_spin.value() / factor
            lumber_len = self.lumber_len_spin.value() / factor
            kerf = self.kerf_spin.value() / factor
            rotate = self.rotate_toggle.isChecked()

            by_mat: Dict[str, List[CutListEntry]] = {}
            for e in self.entries:
                by_mat.setdefault(e.material, []).append(e)

            scene = getattr(self.viewport, "scene", None) if hasattr(self, "viewport") else None

            for mat_name, mat_entries in by_mat.items():
                st_info = self.material_types.get(mat_name, get_material_stock_label(mat_name, scene=scene))
                if is_linear_stock(st_info):
                    boards = pack_linear_lumber(mat_entries, stock_length=lumber_len, kerf=kerf)
                    self.lumber_by_mat[mat_name] = boards
                else:
                    sheets = pack_sheets(mat_entries, sheet_w=sheet_w, sheet_h=sheet_h, kerf=kerf, allow_rotate=rotate)
                    self.sheets_by_mat[mat_name] = sheets

            # 3. Populate Table
            self._apply_table_filter()

            # 4. Populate Diagram Selector
            self.mat_selector_combo.blockSignals(True)
            self.mat_selector_combo.clear()
            for mat_name in sorted(by_mat.keys()):
                st_info = self.material_types.get(mat_name, get_material_stock_label(mat_name, scene=scene))
                icon, cat_name, unit_name = get_stock_display_info(st_info)
                if is_linear_stock(st_info):
                    count = len(self.lumber_by_mat.get(mat_name, []))
                    self.mat_selector_combo.addItem(f"{icon} {mat_name} ({cat_name} — {count} {unit_name})", mat_name)
                else:
                    count = len(self.sheets_by_mat.get(mat_name, []))
                    self.mat_selector_combo.addItem(f"{icon} {mat_name} ({cat_name} — {count} {unit_name})", mat_name)
            self.mat_selector_combo.blockSignals(False)

            if by_mat:
                first_mat = sorted(by_mat.keys())[0]
                self.current_mat_name = first_mat
                self.current_page = 0
                self._update_active_diagram()

            # Populate Material Filter dropdown
            if hasattr(self, "material_filter_combo"):
                self.material_filter_combo.blockSignals(True)
                self.material_filter_combo.clear()
                self.material_filter_combo.addItem("All Materials")
                for mat_name in sorted(by_mat.keys()):
                    self.material_filter_combo.addItem(mat_name)
                self.material_filter_combo.blockSignals(False)

            # 5. Populate Exploded Drawing with TRUE mesh faces
            self.drawing_widget.set_data(self.raw_parts, self.entries, unit=u)

            # 6. Console Output
            print(format_console_table(self.entries, unit=u))
            sys.stdout.flush()

        def _on_thick_sort_changed(self) -> None:
            self._sort_col = 7
            self._sort_asc = (self.thick_sort_combo.currentIndex() == 1)
            self._apply_table_filter()

        def _on_table_header_clicked(self, col: int) -> None:
            current_col = getattr(self, "_sort_col", 7)
            current_asc = getattr(self, "_sort_asc", False)
            if col == current_col:
                new_asc = not current_asc
            else:
                new_asc = False if col in (4, 5, 6, 7, 9) else True
            self._sort_col = col
            self._sort_asc = new_asc
            if col == 7 and hasattr(self, "thick_sort_combo"):
                self.thick_sort_combo.blockSignals(True)
                self.thick_sort_combo.setCurrentIndex(1 if new_asc else 0)
                self.thick_sort_combo.blockSignals(False)
            self._apply_table_filter()

        def _apply_table_filter(self) -> None:
            search = self.search_input.text().strip().lower()
            selected_mat = getattr(self, "material_filter_combo", None)
            mat_filter = selected_mat.currentText() if selected_mat else "All Materials"

            filtered = [
                e for e in self.entries
                if (not search or search in e.display_name.lower() or search in e.material.lower())
                and (mat_filter == "All Materials" or e.material == mat_filter)
            ]

            col = getattr(self, "_sort_col", 7)
            asc = getattr(self, "_sort_asc", False)

            def sort_key(e: CutListEntry):
                if col == 0 or col == 8:
                    return e.material.lower()
                elif col == 1 or col == 2:
                    return e.tag
                elif col == 3:
                    return e.display_name.lower()
                elif col == 4:
                    return e.count
                elif col == 5:
                    return e.length
                elif col == 6:
                    return e.width
                elif col == 7:
                    return e.thickness
                elif col == 9:
                    return e.total_area
                return e.thickness

            by_mat: Dict[str, List[CutListEntry]] = {}
            for e in filtered:
                by_mat.setdefault(e.material, []).append(e)

            sorted_filtered: List[CutListEntry] = []
            mat_names = sorted(by_mat.keys(), key=lambda m: m.lower(), reverse=(col in (0, 8) and not asc))
            for m in mat_names:
                m_list = by_mat[m]
                m_list.sort(key=sort_key, reverse=not asc)
                sorted_filtered.extend(m_list)

            self._populate_table(sorted_filtered)

        def _get_available_materials(self) -> List[str]:
            mats: List[str] = []
            seen = set()

            # 1. From scene.materials
            scene = getattr(self.viewport, "scene", None) if hasattr(self, "viewport") else None
            if scene and hasattr(scene, "materials"):
                raw_mats = scene.materials
                mat_list = raw_mats if isinstance(raw_mats, list) else list(raw_mats.values())
                for m in mat_list:
                    name = m.get("name") if isinstance(m, dict) else getattr(m, "name", str(m))
                    if name and name not in seen:
                        seen.add(name)
                        mats.append(name)

            # 2. From raw parts
            for p in self.raw_parts:
                if p.material and p.material not in seen:
                    seen.add(p.material)
                    mats.append(p.material)

            # 3. From material types
            for m in self.material_types.keys():
                if m and m not in seen:
                    seen.add(m)
                    mats.append(m)

            if not mats:
                mats.append("Default")

            return sorted(mats, key=lambda s: s.lower())

        def _open_material_library_dialog(self, entry: CutListEntry, combo: Optional[Any] = None) -> None:
            scene = getattr(self.viewport, "scene", None) if hasattr(self, "viewport") else None
            available_mats = self._get_available_materials()
            dlg = MaterialLibraryDialog(
                self,
                current_material=entry.material,
                available_materials=available_mats,
                part_name=entry.display_name,
                scene=scene,
                thumbnail_cache=self._thumbnail_cache,
            )
            exec_fn = getattr(dlg, "exec", None) or getattr(dlg, "exec_")
            if exec_fn() == QDialog.Accepted and dlg.selected_material:
                chosen_mat = dlg.selected_material
                chosen_item = dlg.selected_item

                if chosen_mat == entry.material:
                    return

                # Register in IngeTrazo scene.materials if needed
                if scene and hasattr(scene, "materials") and chosen_item is not None:
                    raw_mats = scene.materials
                    mat_list = raw_mats if isinstance(raw_mats, list) else list(raw_mats.values())
                    exists = False
                    for m in mat_list:
                        m_name = m.get("name") if isinstance(m, dict) else getattr(m, "name", str(m))
                        if m_name == chosen_mat:
                            exists = True
                            break
                    if not exists:
                        new_entry = {"name": chosen_mat, "mat": chosen_mat}
                        if chosen_item.texture_file:
                            new_entry["texture"] = {
                                "sw": chosen_item.sw or 1.0,
                                "sh": chosen_item.sh or 1.0,
                                "rot": 0.0,
                                "file": chosen_item.texture_file,
                                "embed": chosen_item.texture_file,
                            }
                        elif chosen_item.rgb:
                            r, g, b = chosen_item.rgb
                            new_entry["color"] = [r, g, b]
                        if isinstance(raw_mats, list):
                            raw_mats.append(new_entry)
                        elif isinstance(raw_mats, dict):
                            raw_mats[chosen_mat] = new_entry

                # Assign stock type following library category
                if chosen_item is not None:
                    self.material_types[chosen_mat] = chosen_item.stock_type
                else:
                    self.material_types[chosen_mat] = get_material_stock_label(
                        chosen_mat, width=entry.width, thickness=entry.thickness, scene=scene
                    )

                self._on_part_material_changed(entry, combo=combo, new_mat=chosen_mat)

        def _on_part_material_changed(self, entry: CutListEntry, combo: Optional[Any] = None, new_mat: Optional[str] = None) -> None:
            if new_mat is None and combo is not None and hasattr(combo, "currentText"):
                new_mat = combo.currentText().strip()

            if not new_mat:
                return

            if "Search All Library" in new_mat or "Browse / Search" in new_mat:
                if combo is not None and hasattr(combo, "blockSignals"):
                    combo.blockSignals(True)
                    combo.setCurrentText(entry.material)
                    combo.blockSignals(False)
                self._open_material_library_dialog(entry, combo)
                return

            if new_mat == entry.material:
                return

            scene = getattr(self.viewport, "scene", None) if hasattr(self, "viewport") else None
            matched_scene_mat = None
            if scene and hasattr(scene, "materials"):
                raw_mats = scene.materials
                mat_list = raw_mats if isinstance(raw_mats, list) else list(raw_mats.values())
                for m in mat_list:
                    name = m.get("name") if isinstance(m, dict) else getattr(m, "name", str(m))
                    if name == new_mat:
                        matched_scene_mat = m
                        break

            # 1. Update all RawPart objects in this entry and their IngeTrazo scene groups
            for p in entry.parts:
                p.material = new_mat
                grp = getattr(p, "group_ref", None)
                if grp is not None:
                    try:
                        if matched_scene_mat is not None and isinstance(matched_scene_mat, dict):
                            new_grp_mat = dict(matched_scene_mat)
                            new_grp_mat["mat"] = new_mat
                            grp.material = new_grp_mat
                        else:
                            grp.material = new_mat
                    except Exception:
                        try:
                            grp.material = new_mat
                        except Exception:
                            pass

                    # Also update face attrs if present
                    mesh = getattr(grp, "mesh", None)
                    faces = getattr(mesh, "faces", None) if mesh else None
                    if faces:
                        for f in faces:
                            attrs = getattr(f, "attrs", None)
                            if attrs and isinstance(attrs, dict) and "mat" in attrs:
                                attrs["mat"] = new_mat

            # 2. Bump scene version to trigger 3D viewport update
            if scene is not None:
                scene.version = getattr(scene, "version", 0) + 1
            if hasattr(self.viewport, "update"):
                self.viewport.update()

            # 3. Update material types and stock setup table
            if new_mat not in self.material_types:
                self.material_types[new_mat] = get_material_stock_label(
                    new_mat, width=entry.width, thickness=entry.thickness, scene=scene
                )
            self._populate_material_table()

            # 4. Regroup parts with current grouping mode
            merge = self.group_toggle.isChecked()
            self.entries = group_parts(self.raw_parts, merge_by_dimensions=merge)

            # 5. Re-pack cutting diagrams
            u = self.unit_combo.currentText()
            factor = UNIT_FACTORS.get(u, 1000.0)
            sheet_w = self.sheet_w_spin.value() / factor
            sheet_h = self.sheet_h_spin.value() / factor
            lumber_len = self.lumber_len_spin.value() / factor
            kerf = self.kerf_spin.value() / factor
            rotate = self.rotate_toggle.isChecked()

            by_mat: Dict[str, List[CutListEntry]] = {}
            for e in self.entries:
                by_mat.setdefault(e.material, []).append(e)

            self.sheets_by_mat.clear()
            self.lumber_by_mat.clear()
            for mat_name, mat_entries in by_mat.items():
                st_info = self.material_types.get(mat_name, get_material_stock_label(mat_name, scene=scene))
                if is_linear_stock(st_info):
                    self.lumber_by_mat[mat_name] = pack_linear_lumber(
                        mat_entries, stock_length=lumber_len, kerf=kerf
                    )
                else:
                    self.sheets_by_mat[mat_name] = pack_sheets(
                        mat_entries, sheet_w=sheet_w, sheet_h=sheet_h, kerf=kerf, allow_rotate=rotate
                    )

            # Update Diagram Selector
            self.mat_selector_combo.blockSignals(True)
            self.mat_selector_combo.clear()
            for mat_name in sorted(by_mat.keys()):
                st_info = self.material_types.get(mat_name, get_material_stock_label(mat_name, scene=scene))
                icon, cat_name, unit_name = get_stock_display_info(st_info)
                if is_linear_stock(st_info):
                    cnt = len(self.lumber_by_mat.get(mat_name, []))
                    self.mat_selector_combo.addItem(f"{icon} {mat_name} ({cat_name} — {cnt} {unit_name})", mat_name)
                else:
                    cnt = len(self.sheets_by_mat.get(mat_name, []))
                    self.mat_selector_combo.addItem(f"{icon} {mat_name} ({cat_name} — {cnt} {unit_name})", mat_name)
            self.mat_selector_combo.blockSignals(False)

            if by_mat:
                if self.current_mat_name not in by_mat:
                    self.current_mat_name = sorted(by_mat.keys())[0]
                    self.current_page = 0
                self._update_active_diagram()

            # Update Material Filter combo
            if hasattr(self, "material_filter_combo"):
                cur_filter = self.material_filter_combo.currentText()
                self.material_filter_combo.blockSignals(True)
                self.material_filter_combo.clear()
                self.material_filter_combo.addItem("All Materials")
                for mat_name in sorted(by_mat.keys()):
                    self.material_filter_combo.addItem(mat_name)
                idx = self.material_filter_combo.findText(cur_filter)
                if idx >= 0:
                    self.material_filter_combo.setCurrentIndex(idx)
                else:
                    self.material_filter_combo.setCurrentIndex(0)
                self.material_filter_combo.blockSignals(False)

            # Update Exploded Drawing widget
            self.drawing_widget.set_data(self.raw_parts, self.entries, unit=u)

            # Refresh Table (regrouped!)
            self._apply_table_filter()

        def _populate_table(self, entries: List[CutListEntry]) -> None:
            u = self.unit_combo.currentText()
            area_u = AREA_UNITS.get(u, "m²")
            headers = [
                "Mat", "Tag", "#", "Part Name / Description", "Qty",
                f"Length ({u})", f"Width ({u})", f"Thick ({u})",
                "Material", f"Total Area ({area_u})"
            ]

            self.table.clear()
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)

            if not entries:
                self.table.setRowCount(0)
                self.summary_label.setText("No parts match the current filter.")
                return

            # Group entries by material in sequence
            mat_groups: List[Tuple[str, List[CutListEntry]]] = []
            curr_mat = None
            curr_list: List[CutListEntry] = []
            for e in entries:
                if e.material != curr_mat:
                    if curr_mat is not None:
                        mat_groups.append((curr_mat, curr_list))
                    curr_mat = e.material
                    curr_list = [e]
                else:
                    curr_list.append(e)
            if curr_mat is not None:
                mat_groups.append((curr_mat, curr_list))

            # Total rows = number of parts + number of material section headers
            total_rows = len(entries) + len(mat_groups)
            self.table.setRowCount(total_rows)

            row_idx = 0
            part_num = 1
            scene = getattr(self.viewport, "scene", None) if hasattr(self, "viewport") else None
            available_materials = self._get_available_materials()

            for mat_name, mat_entries in mat_groups:
                mat_parts_count = sum(e.count for e in mat_entries)
                mat_area = sum(e.total_area for e in mat_entries)
                st_info = self.material_types.get(mat_name, get_material_stock_label(mat_name, scene=scene))
                area_str = format_area(mat_area, u)

                _, mat_icon = get_material_thumbnail(mat_name, scene=scene, size=22, cache=self._thumbnail_cache)

                header_text = f"  📁 Material: {mat_name}  ({st_info})  —  {mat_parts_count} parts  |  Total Area: {area_str}"
                header_item = QTableWidgetItem(header_text)
                header_item.setFlags(Qt.ItemIsEnabled)
                font_h = header_item.font()
                font_h.setBold(True)
                font_h.setPointSize(9.5)
                header_item.setFont(font_h)
                header_item.setBackground(QColor("#1e293b"))
                header_item.setForeground(QColor("#38bdf8"))
                if mat_icon is not None and not mat_icon.isNull():
                    header_item.setIcon(mat_icon)

                self.table.setItem(row_idx, 0, header_item)
                self.table.setSpan(row_idx, 0, 1, len(headers))
                self.table.setRowHeight(row_idx, 28)
                row_idx += 1

                for e in mat_entries:
                    # Column 0: Material Thumbnail
                    thumb_item = QTableWidgetItem()
                    if mat_icon is not None and not mat_icon.isNull():
                        thumb_item.setIcon(mat_icon)
                    thumb_item.setTextAlignment(Qt.AlignCenter)
                    thumb_item.setToolTip(f"Material: {e.material}")
                    thumb_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    self.table.setItem(row_idx, 0, thumb_item)

                    # Column 1: Tag
                    tag_item = QTableWidgetItem(f"({e.tag})")
                    tag_item.setTextAlignment(Qt.AlignCenter)
                    font_tag = tag_item.font()
                    font_tag.setBold(True)
                    tag_item.setFont(font_tag)
                    self.table.setItem(row_idx, 1, tag_item)

                    # Column 2: #
                    self.table.setItem(row_idx, 2, NumericTableWidgetItem(str(part_num), float(part_num)))

                    # Column 3: Part Name / Description
                    name_item = QTableWidgetItem(e.display_name)
                    if len(e.names) > 1:
                        name_item.setToolTip("\n".join(e.names))
                    self.table.setItem(row_idx, 3, name_item)

                    # Column 4: Qty
                    self.table.setItem(row_idx, 4, NumericTableWidgetItem(str(e.count), float(e.count)))

                    # Column 5: Length
                    self.table.setItem(row_idx, 5, NumericTableWidgetItem(format_dimension(e.length, u), e.length))

                    # Column 6: Width
                    self.table.setItem(row_idx, 6, NumericTableWidgetItem(format_dimension(e.width, u), e.width))

                    # Column 7: Thick (highlighted)
                    thick_item = NumericTableWidgetItem(format_dimension(e.thickness, u), e.thickness)
                    font_thk = thick_item.font()
                    font_thk.setBold(True)
                    thick_item.setFont(font_thk)
                    thick_item.setForeground(QColor("#f59e0b"))
                    self.table.setItem(row_idx, 7, thick_item)

                    # Column 8: Material Button (Click to open material picker dialog; ignores mouse wheel)
                    cell_widget = QWidget()
                    cell_layout = QHBoxLayout(cell_widget)
                    cell_layout.setContentsMargins(2, 2, 2, 2)
                    cell_layout.setSpacing(0)

                    mat_btn = QPushButton()
                    if mat_icon is not None and not mat_icon.isNull():
                        mat_btn.setIcon(mat_icon)
                        mat_btn.setIconSize(QSize(18, 18))
                    mat_btn.setText(f"  {e.material}   ▾")
                    mat_btn.setToolTip(f"Click to change material for '{e.display_name}' (Current: {e.material})\nOpens Material Library Dialog — Click 'Save Material' to apply.")
                    mat_btn.setCursor(Qt.PointingHandCursor)
                    mat_btn.setStyleSheet("""
                        QPushButton {
                            background-color: #1e293b;
                            color: #f1f5f9;
                            border: 1px solid #475569;
                            border-radius: 4px;
                            padding: 3px 8px;
                            font-size: 11px;
                            text-align: left;
                        }
                        QPushButton:hover {
                            background-color: #334155;
                            border-color: #38bdf8;
                            color: #ffffff;
                        }
                        QPushButton:pressed {
                            background-color: #0284c7;
                        }
                    """)
                    mat_btn.clicked.connect(
                        lambda _checked, entry=e: self._open_material_library_dialog(entry)
                    )
                    cell_layout.addWidget(mat_btn)

                    self.table.setCellWidget(row_idx, 8, cell_widget)

                    # Column 9: Total Area
                    area_val = e.total_area * (10.7639 if u == "in" else 1.0)
                    self.table.setItem(row_idx, 9, NumericTableWidgetItem(f"{area_val:.2f}", area_val))

                    self.table.setRowHeight(row_idx, 28)
                    row_idx += 1
                    part_num += 1

            h = self.table.horizontalHeader()
            h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
            h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
            h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
            h.setSectionResizeMode(3, QHeaderView.Stretch)
            h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
            h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
            h.setSectionResizeMode(6, QHeaderView.ResizeToContents)
            h.setSectionResizeMode(7, QHeaderView.ResizeToContents)
            h.setSectionResizeMode(8, QHeaderView.ResizeToContents)
            h.setSectionResizeMode(9, QHeaderView.ResizeToContents)

            h.setSortIndicatorShown(True)
            sort_c = getattr(self, "_sort_col", 7)
            sort_a = getattr(self, "_sort_asc", False)
            h.setSortIndicator(sort_c, Qt.AscendingOrder if sort_a else Qt.DescendingOrder)

            tot_parts = sum(e.count for e in entries)
            tot_area = sum(e.total_area for e in entries)
            self.summary_label.setText(
                f"Total Parts: {tot_parts}   |   Unique Sizes: {len(entries)}   |   "
                f"Materials: {len(mat_groups)}   |   Total Surface Area: {format_area(tot_area, u)}"
            )

        def _on_material_diagram_changed(self) -> None:
            mat = self.mat_selector_combo.currentData()
            if mat:
                self.current_mat_name = mat
                self.current_page = 0
                self._update_active_diagram()

        def _update_active_diagram(self) -> None:
            mat = self.current_mat_name
            if not mat:
                return

            u = self.unit_combo.currentText()
            scene = getattr(self.viewport, "scene", None) if hasattr(self, "viewport") else None
            st_info = self.material_types.get(mat, get_material_stock_label(mat, scene=scene))

            if is_linear_stock(st_info):
                boards = self.lumber_by_mat.get(mat, [])
                if not boards:
                    self.diagram_info_label.setText("No solid boards needed.")
                    self.diagram_widget.set_lumber([], u)
                    return

                per_page = 4
                total_pages = max(1, (len(boards) + per_page - 1) // per_page)
                self.current_page = max(0, min(self.current_page, total_pages - 1))

                start = self.current_page * per_page
                page_boards = boards[start : start + per_page]

                avg_yield = sum(b.yield_percentage for b in boards) / max(1, len(boards))
                icon, cat_name, unit_name = get_stock_display_info(st_info)
                self.diagram_info_label.setText(
                    f"Page {self.current_page + 1} of {total_pages} ({len(boards)} {unit_name} total) — "
                    f"Overall Yield: {avg_yield:.1f}%"
                )
                self.diagram_widget.set_lumber(page_boards, unit=u)
            else:
                sheets = self.sheets_by_mat.get(mat, [])
                if not sheets:
                    self.diagram_info_label.setText("No sheets needed.")
                    self.diagram_widget.set_sheet(None, u)
                    return

                self.current_page = max(0, min(self.current_page, len(sheets) - 1))
                sheet = sheets[self.current_page]

                icon, cat_name, unit_name = get_stock_display_info(st_info)
                unit_single = unit_name[:-1] if unit_name.endswith("s") else unit_name
                self.diagram_info_label.setText(
                    f"{unit_single} {self.current_page + 1} of {len(sheets)} — "
                    f"Yield: {sheet.yield_percentage:.1f}% (Waste: {sheet.waste_percentage:.1f}%)"
                )
                self.diagram_widget.set_sheet(sheet, unit=u)

        def _prev_page(self) -> None:
            if self.current_page > 0:
                self.current_page -= 1
                self._update_active_diagram()

        def _next_page(self) -> None:
            mat = self.current_mat_name
            scene = getattr(self.viewport, "scene", None) if hasattr(self, "viewport") else None
            st_info = self.material_types.get(mat, get_material_stock_label(mat, scene=scene))
            if is_linear_stock(st_info):
                boards = self.lumber_by_mat.get(mat, [])
                total_pages = max(1, (len(boards) + 3) // 4)
                if self.current_page < total_pages - 1:
                    self.current_page += 1
                    self._update_active_diagram()
            else:
                sheets = self.sheets_by_mat.get(mat, [])
                if self.current_page < len(sheets) - 1:
                    self.current_page += 1
                    self._update_active_diagram()

        def _copy_tsv(self) -> None:
            u = self.unit_combo.currentText()
            area_u = AREA_UNITS.get(u, "m²")
            headers = ["Tag", "#", "Part Name", "Qty", f"Length ({u})", f"Width ({u})", f"Thickness ({u})", "Material", f"Total Area ({area_u})"]
            rows = ["\t".join(headers)]
            for idx, e in enumerate(self.entries, start=1):
                area_val = e.total_area * (10.7639 if u == "in" else 1.0)
                row = [
                    e.tag, str(idx), e.display_name, str(e.count),
                    format_dimension(e.length, u), format_dimension(e.width, u), format_dimension(e.thickness, u),
                    e.material, f"{area_val:.2f}",
                ]
                rows.append("\t".join(row))

            QApplication.clipboard().setText("\n".join(rows))
            orig = self.copy_btn.text()
            self.copy_btn.setText("✓ Copied!")
            QTimer.singleShot(1500, lambda: self.copy_btn.setText(orig))

        def _export_csv(self) -> None:
            path, _ = QFileDialog.getSaveFileName(self, "Export Cut List CSV", "cutlist.csv", "CSV Files (*.csv)")
            if not path:
                return
            try:
                u = self.unit_combo.currentText()
                area_u = AREA_UNITS.get(u, "m²")
                with open(path, "w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f)
                    w.writerow(["Tag", "#", "Part Name", "Qty", f"Length ({u})", f"Width ({u})", f"Thickness ({u})", "Material", f"Total Area ({area_u})"])
                    for idx, e in enumerate(self.entries, start=1):
                        area_val = e.total_area * (10.7639 if u == "in" else 1.0)
                        w.writerow([
                            e.tag, idx, e.display_name, e.count,
                            format_dimension(e.length, u), format_dimension(e.width, u), format_dimension(e.thickness, u),
                            e.material, f"{area_val:.2f}",
                        ])
                QMessageBox.information(self, "Complete", f"Cut list exported to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export CSV:\n{e}")

        def _export_pdf(self) -> None:
            doc_name = get_project_name(self.viewport)
            base_name = Path(doc_name).stem if doc_name else "parts_list"
            default_path = f"{base_name}_parts_list.pdf"

            path, _ = QFileDialog.getSaveFileName(
                self, "Export Parts List PDF", default_path, "PDF Documents (*.pdf)"
            )
            if not path:
                return

            try:
                u = self.unit_combo.currentText()
                render_cutlist_pdf(
                    path,
                    self.entries,
                    viewport=self.viewport,
                    unit=u,
                    material_types=self.material_types,
                )

                orig = self.print_btn.text()
                self.print_btn.setText("✓ PDF Saved!")
                QTimer.singleShot(2500, lambda: self.print_btn.setText(orig))

                # Open automatically in default PDF reader / browser
                try:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                except Exception:
                    pass

                QMessageBox.information(
                    self,
                    "Complete",
                    f"Parts list PDF exported successfully to:\n{path}\n\nOpening in your default viewer...",
                )
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export PDF:\n{e}")

        def _print_console(self) -> None:
            u = self.unit_combo.currentText()
            table_txt = format_console_table(self.entries, unit=u)

            # 1. Output to standard stdout
            try:
                print(table_txt)
                sys.stdout.flush()
            except Exception:
                pass

            # 2. Forward to IngeTrazo's built-in Python Console if active
            try:
                win = self.parent() or getattr(self, "parent_window", None)
                if win is not None:
                    py_console = getattr(win, "_python_console", None)
                    if py_console is not None and hasattr(py_console, "_append_text"):
                        py_console._append_text(table_txt + "\n", role="out")
            except Exception:
                pass

            # 3. Temporarily update button label
            orig = self.print_btn.text()
            self.print_btn.setText("✓ Printed!")
            QTimer.singleShot(1500, lambda: self.print_btn.setText(orig))

            # 4. Open dedicated monospace console dialog
            show_console_dialog(table_txt, parent=self)

        def _save_diagram_png(self) -> None:
            path, _ = QFileDialog.getSaveFileName(self, "Save Diagram Image", "cutting_diagram.png", "PNG Images (*.png)")
            if not path:
                return
            try:
                pix = QPixmap(self.diagram_widget.size())
                self.diagram_widget.render(pix)
                pix.save(path, "PNG")
                QMessageBox.information(self, "Complete", f"Diagram saved to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save image:\n{e}")

        def _export_drawing_png(self) -> None:
            path, _ = QFileDialog.getSaveFileName(self, "Export Exploded Drawing PNG", "exploded_drawing.png", "PNG Images (*.png)")
            if not path:
                return
            try:
                w, h = 2400, 1600
                pix = QPixmap(w, h)
                pix.fill(Qt.transparent)
                p = QPainter(pix)
                self.drawing_widget.render_drawing(p, QRectF(0, 0, w, h))
                p.end()
                pix.save(path, "PNG")
                QMessageBox.information(self, "Complete", f"Exploded drawing exported to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export drawing image:\n{e}")

        def _export_drawing_pdf(self) -> None:
            path, _ = QFileDialog.getSaveFileName(self, "Export Exploded Drawing PDF", "exploded_drawing.pdf", "PDF Documents (*.pdf)")
            if not path:
                return
            try:
                try:
                    pdf = QPdfWriter(path)
                    pdf.setPageSize(QPageSize(QPageSize.A4))
                    pdf.setPageOrientation(QPageLayout.Landscape)
                    p = QPainter(pdf)
                    target = QRectF(0, 0, pdf.width(), pdf.height())
                    self.drawing_widget.render_drawing(p, target)
                    p.end()
                    QMessageBox.information(self, "Complete", f"Exploded drawing PDF exported to:\n{path}")
                except Exception:
                    w, h = 2400, 1600
                    pix = QPixmap(w, h)
                    p = QPainter(pix)
                    self.drawing_widget.render_drawing(p, QRectF(0, 0, w, h))
                    p.end()
                    pix.save(path, "PDF")
                    QMessageBox.information(self, "Complete", f"Exploded drawing PDF saved to:\n{path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to export PDF:\n{e}")


# ---------------------------------------------------------------------------
# Core Entry Point
# ---------------------------------------------------------------------------
def run_cutlist(viewport: Any) -> None:
    if viewport is None:
        return

    scene = getattr(viewport, "scene", None)
    selected_groups = get_selected_groups(scene)

    parent_win = getattr(viewport, "window", lambda: None)()
    if not selected_groups:
        if QT_AVAILABLE and parent_win:
            QMessageBox.information(
                parent_win,
                PLUGIN_TITLE,
                "Please select the objects (groups or components) you want to include in the cut list first, "
                "then open Cut List.\n\n(Tip: Use the Select tool in the viewport to pick parts)."
            )
        else:
            print("[CutList] No objects selected in scene. Please select objects first.")
        return

    if QT_AVAILABLE:
        win = CutListWindow(viewport, parent=parent_win)
        win.exec()


def show_about_dialog(parent: Optional[Any] = None) -> None:
    """Display the OpenCutList About dialog with woodwork / cabinet maker focus and developer credits."""
    if QT_AVAILABLE:
        dlg = CutListAboutDialog(parent)
        dlg.exec()
    else:
        print(f"=== OpenCutList for IngeTrazo ({PLUGIN_VERSION}) ===")
        print(f"Target Audience: {PLUGIN_AUDIENCE}")
        print("Dedicated cut list, 1D/2D nesting, and technical drawing suite for Woodworkers & Cabinet Makers.")
        print(f"Developer: {PLUGIN_AUTHOR} ({PLUGIN_GITHUB})")


def show_console_dialog(text: str, parent: Optional[Any] = None) -> None:
    """Display the monospace console output dialog or print to stdout if headless."""
    if QT_AVAILABLE:
        dlg = CutListConsoleDialog(text, parent=parent)
        dlg.exec()
    else:
        print(text)


# ---------------------------------------------------------------------------
# Tool Registration
# ---------------------------------------------------------------------------
class CutListTool(Tool):
    name = "Cut List"
    shortcut = None
    description = "Generate cutting list, drawings, and 3D exploded views from selection."
    menu_order = 15
    uses_snap = False

    def on_activate(self, viewport: Any) -> None:
        run_cutlist(viewport)

    def on_deactivate(self, viewport: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# Beyond Tools: Module setup(app) Integration
# ---------------------------------------------------------------------------
def setup(app: Any) -> None:
    def action():
        run_cutlist(app.viewport)

    menu = app.add_menu(PLUGIN_TITLE)
    if menu is not None:
        act = menu.addAction(PLUGIN_TITLE, action)
        act.setStatusTip("Generate cutting list, diagrams, and exploded views.")
        about_act = menu.addAction("About OpenCutList...", lambda: show_about_dialog(getattr(app, "window", None)))
        if hasattr(about_act, "setStatusTip"):
            about_act.setStatusTip("About OpenCutList for woodworkers & cabinet makers by brillian11")

    if QT_AVAILABLE and hasattr(app, "window"):
        toolbar = QToolBar(PLUGIN_TITLE, app.window)
        toolbar.setObjectName("IngeTrazoCutListToolbar")
        toolbar.setMovable(True)
        toolbar.setFloatable(True)
        toolbar.setAllowedAreas(Qt.AllToolBarAreas)
        toolbar.setIconSize(QSize(26, 26))

        icon = create_cutlist_icon()
        btn_action = toolbar.addAction(icon if icon else PLUGIN_TITLE, PLUGIN_TITLE)
        btn_action.setToolTip("Cut List — Generate cutting list & drawings from selection")
        btn_action.triggered.connect(lambda _c=False: action())

        app.window.addToolBar(Qt.TopToolBarArea, toolbar)

    def context(menu: Any, selection: Any) -> None:
        scene = getattr(app, "scene", None)
        if get_selected_groups(scene):
            sub = menu.addMenu(PLUGIN_TITLE)
            sub.addAction("Generate Cut List & Drawings", action)

    if hasattr(app, "add_context_menu"):
        app.add_context_menu(context)
