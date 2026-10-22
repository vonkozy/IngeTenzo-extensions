# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 — community extension for IngeTrazo.
#
# Snap to locked layers.
#
# A locked layer stays unselectable. While the switch is on, a visible
# locked layer still offers its corners, edge midpoints and points along
# its edges. A hidden layer does not. A snap the host already found on
# unlocked geometry wins.
#
# Install
#   Extensions → Open plugins folder
#   Save this file as snap_locked_layers.py and restart IngeTrazo.
#   Camera → Snap to locked layers
#
# Version of this file is recorded below. Bump VERSION and add a CHANGELOG
# line when you change it.

VERSION = "0.05"
# For IngeTrazo 0.5.9 (plugin API 2). Confirm on that build.
TESTED_INGETRAZO = "0.5.9"

# CHANGELOG
# 0.05 — 2026-10-22
#   Marked for IngeTrazo 0.5.9.
# 0.02 — 2026-10-16
#   Snap to corners, midpoints and edges of a visible locked layer.
#   The layer stays locked. Hidden layers are ignored.

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QVector3D

THRESHOLD_PX = 12.0
COLOR_ENDPOINT = (0.15, 0.75, 0.30)
COLOR_MIDPOINT = (0.20, 0.75, 0.85)
COLOR_ON_EDGE = (0.95, 0.85, 0.20)


def _xy(pixel):
    if pixel is None:
        return None
    if hasattr(pixel, "x"):
        return float(pixel.x()), float(pixel.y())
    return float(pixel[0]), float(pixel[1])


def _camera_menu(window):
    bar = window.menuBar()
    menus = []
    for action in bar.actions():
        menu = action.menu()
        if menu is None:
            continue
        menus.append(menu)
        for act in menu.actions():
            for seq in act.shortcuts():
                if seq.toString() == "Shift+P":
                    return menu
    if len(menus) > 2:
        return menus[2]
    return menus[-1] if menus else bar.addMenu("Camera")


def _add_edge(out, a, b):
    if getattr(a, "x", None) is None:
        return
    out.append((QVector3D(a), QVector3D(b)))


def _add_mesh(out, mesh, matrix):
    if mesh is None:
        return
    for edge in getattr(mesh, "edges", ()) or ():
        if getattr(edge, "hidden", False):
            continue
        a, b = edge.a, edge.b
        if matrix is not None:
            a, b = matrix.map(a), matrix.map(b)
        _add_edge(out, a, b)


def _segments(viewport):
    scene = viewport.scene
    out = []
    state = getattr(scene, "_layer_state", None)
    if state is None:
        return out
    for edge in scene.edges:
        visible, locked = state(edge)
        if visible and locked and not getattr(edge, "hidden", False):
            _add_edge(out, edge.a, edge.b)

    def walk(group, base, inherited):
        if getattr(group, "billboard", False):
            return
        xform = getattr(group, "xform", None)
        if base is not None:
            world = base if xform is None else base * xform
        else:
            world = xform
        visible, locked = state(group)
        if not visible:
            return
        if locked or inherited:
            _add_mesh(out, getattr(group, "mesh", None), world)
        for child in getattr(group, "children", None) or ():
            walk(child, world, inherited or locked)

    for root in getattr(scene, "groups", ()) or ():
        walk(root, None, False)
    return out


def _nearest(viewport, px, py, segments):
    best = None
    best_d = THRESHOLD_PX
    for a, b in segments:
        pa = _xy(viewport._world_to_pixel(a))
        pb = _xy(viewport._world_to_pixel(b))
        if pa is None or pb is None:
            continue
        mid = (a + b) * 0.5
        pmid = ((pa[0] + pb[0]) * 0.5, (pa[1] + pb[1]) * 0.5)
        for point, pixel, kind, color in (
            (a, pa, "endpoint", COLOR_ENDPOINT),
            (b, pb, "endpoint", COLOR_ENDPOINT),
            (mid, pmid, "midpoint", COLOR_MIDPOINT),
        ):
            dist = math.hypot(pixel[0] - px, pixel[1] - py)
            if dist < best_d:
                best_d = dist
                best = (point, kind, color)
        abx, aby = pb[0] - pa[0], pb[1] - pa[1]
        length = abx * abx + aby * aby
        if length < 1.0:
            continue
        t = ((px - pa[0]) * abx + (py - pa[1]) * aby) / length
        if t <= 0.04 or t >= 0.96:
            continue
        dist = math.hypot(pa[0] + abx * t - px, pa[1] + aby * t - py)
        if dist < best_d:
            best_d = dist
            best = (a + (b - a) * t, "on_edge", COLOR_ON_EDGE)
    return best


def setup(app):
    enabled = [True]
    cache = [[]]
    cache_version = [-1]

    def provide(viewport, _snap, px, py):
        if not enabled[0]:
            return None
        version = getattr(viewport.scene, "version", None)
        if cache_version[0] != version:
            cache[0] = _segments(viewport)
            cache_version[0] = version
        hit = _nearest(viewport, px, py, cache[0])
        if hit is None:
            return None
        from core.snap import SnapResult
        point, kind, color = hit
        return SnapResult(point, kind, color, label="locked layer")

    def toggle(on: bool) -> None:
        enabled[0] = bool(on)
        cache_version[0] = -1
        app.viewport.flash_status(
            "Snap to locked layers on" if on else "Snap to locked layers off",
            1500)

    action = QAction("Snap to locked layers", app.window)
    action.setCheckable(True)
    action.setChecked(True)
    action.setStatusTip(
        "Snap to a visible locked layer. The layer stays unselectable. "
        f"v{VERSION}")
    action.triggered.connect(toggle)

    menu = _camera_menu(app.window)
    menu.addAction(action)
    app.add_snap_provider(provide)

    def _place() -> None:
        menu.removeAction(action)
        menu.addSeparator()
        menu.addAction(action)

    QTimer.singleShot(0, _place)
