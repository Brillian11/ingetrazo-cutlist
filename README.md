# OpenCutList for IngeTrazo CAD (v1.5.1)

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-3776ab.svg)](https://www.python.org/)
[![Target: Woodworking](https://img.shields.io/badge/Made%20for-Woodworkers%20%26%20Cabinet%20Makers-8B4513.svg)]()

A comprehensive **Cut List, 1D/2D Nesting Optimization, and 3D Technical Drawing suite** for [IngeTrazo](https://ingetrazo.com) (the free, open-source 3D CAD modeler for architecture, engineering, and woodworking).

Developed by **[brillian11](https://github.com/brillian11)**.

---

## 🪵 Designed for Woodworkers & Cabinet Makers

Transform your 3D digital models into accurate, shop-ready production data with one click:
- **Automatic Part Extraction & Grouping**: Intelligently decomposes assemblies, components, and nested groups down to true leaf parts.
- **Accurate Dimensioning**: Length $\ge$ Width $\ge$ Thickness sorting following standard woodworking grain conventions.
- **Thickness Classification**: Automatically separates parts by material and sorts descending by thickness (thickest parts first).
- **1D Solid Lumber Optimization**: Linear board cutting layouts with kerf gap compensation and board yield analytics.
- **2D Sheet Goods Nesting**: Guillotine nesting optimization for plywood, MDF, particle board, and veneers with 90° grain orientation toggle.
- **3D Exploded Axonometric Drawings**: High-precision 3D vector drawings with live explosion slider (0% to 250%), lettered callout tags, and parts schedule.
- **Material Library Integration**: Full synchronization with IngeTrazo's built-in 640+ textures and RAL colors.

---

## ✨ Features Overview

### 1. 📋 Cutting List Table
- **Material Thumbnails**: Swatch previews with rounded borders for every part and section header.
- **Interactive Material Picker**: Change any component's material on the fly from an in-table dropdown.
- **Search All Library (640+)**: Built-in library browser with live search and category filters (`Wood`, `Metal`, `Flooring`, `Colors`, etc.).
- **Dynamic Regrouping**: Changing a component's material dynamically updates the 3D scene, face attributes, regroups the table, and repacks cutting diagrams.
- **Exporting**: Copy to TSV (spreadsheet paste) or export to CSV.

### 2. 📐 1D & 2D Cutting Diagrams
- **Dual Stock Detection**: Solid lumber (Poplar, Pine, Oak, Bleached Wood, Metal bars) automatically gets 1D linear cut diagrams; Sheet goods (Plywood, MDF, Flooring, RAL panels) get 2D sheet nesting diagrams.
- **Customizable Stock Sizes**: Configurable standard board length, sheet dimensions ($2440 \times 1220\text{ mm}$ default), and blade kerf.
- **Visual Nesting**: Displays exact cutting coordinates, part callout tags, and percentage yield / waste metrics.

### 3. 🎨 3D Exploded Assembly Drawings
- **Axonometric Projection**: Orthonormal technical camera basis matching IngeTrazo's camera conventions.
- **Live Explosion Slider**: Smoothly pull components outward from the assembly center.
- **Leader Line Callout Balloons**: Circular lettered tags `(A)`, `(B)`, `(C)` linking the 3D drawing directly to the cutting list.
- **True Mesh Geometry**: Renders actual arched segments, curved contours, cutouts, and seams.
- **Export Options**: Export high-resolution PNG (300 DPI) or print-ready landscape PDF drawing sheets.

---

## 🚀 Getting Started

### Installation
Copy `cutlist_plugin.py` to your IngeTrazo plugins directory:
```bash
# Windows
%APPDATA%\IngeTrazo\plugins\cutlist_plugin.py
```
Or clone the repository:
```bash
git clone https://github.com/brillian11/ingetrazo-cutlist.git
```

### Usage
1. Open your 3D model in **IngeTrazo**.
2. Select the parts or assembly you want to cut using the Select tool (`Spacebar`).
3. Click the **Cut List** icon on the toolbar or choose **Cut List ▸ Cut List** from the menu.
4. Review your parts in **Cutting List**, inspect cutting layouts in **2D Cutting Diagrams**, and generate assembly sheets in **Exploded Drawing**.

---

## 👤 Developer & Credits

- **Developer**: [brillian11](https://github.com/brillian11)
- **GitHub**: [github.com/brillian11](https://github.com/brillian11)

---

## 📄 License

This project is licensed under the **GNU General Public License v3.0** (GPL-3.0-or-later). See [LICENSE](LICENSE) for details.
