# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 — community extension for IngeTrazo.
#
# Camera history.
#
# Keeps the last ten camera stops and walks them as a circle.
# Alt+Left steps back. Alt+Right steps forward. Both wrap.
# A stop is stored 0.1 s after the mouse button goes up, or 0.1 s
# after the scroll wheel stops. Walking the history does not record
# a new stop. The next real move keeps the stops just walked, in that
# order, and drops anything past ten.
# Previous and next use the SketchUp circular-arrow shape, drawn as
# an IngeTrazo line icon.
#
# Install
#   Extensions → Open plugins folder
#   Save this file as camera_history.py and restart IngeTrazo.
#   Camera → Camera history → Camera history back / forward
#
# Version of this file is recorded below. Bump VERSION and add a CHANGELOG
# line when you change it.

VERSION = "0.11"
# For IngeTrazo 0.5.9 (plugin API 2). Confirm on that build.
TESTED_INGETRAZO = "0.5.9"

# CHANGELOG
# 0.11 — 2026-10-22
#   QPointF and QRectF come from PySide6.QtCore. QtGui does not export them,
#   so 0.10 failed to load.
# 0.10 — 2026-10-22
#   Marked for IngeTrazo 0.5.9.
# 0.07 — 2026-10-16
#   Previous and next icons: SketchUp's circular arrow, IngeTrazo stroke.
# 0.06 — 2026-10-16
#   Ten stops, 0.1 s after the mouse or the wheel rests.
#   Alt+Left back, Alt+Right forward, both wrapping.
#   A new move keeps the walk just made and drops anything past ten.

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction, QColor, QIcon, QKeySequence, QPainter, QPainterPath, QPen,
    QPixmap, QPolygonF, QVector3D,
)
from PySide6.QtWidgets import QApplication

KEEP = 10
SETTLE_MS = 100
POLL_MS = 50


def _shot(cam):
    t = cam.target
    return (
        t.x(), t.y(), t.z(), cam.distance, cam.yaw, cam.pitch,
        float(cam.fov_deg), bool(cam.perspective),
        bool(getattr(cam, "two_point", False)),
    )


def _apply(cam, shot):
    cam.target = QVector3D(shot[0], shot[1], shot[2])
    cam.distance = shot[3]
    cam.yaw = shot[4]
    cam.pitch = shot[5]
    cam.fov_deg = shot[6]
    cam.perspective = shot[7]
    cam.two_point = shot[8]


def _same(a, b) -> bool:
    if a is None or b is None:
        return False
    if a[7] != b[7] or a[8] != b[8]:
        return False
    if math.dist(a[:3], b[:3]) > 1e-4:
        return False
    if abs(a[3] - b[3]) > 1e-4:
        return False
    return (
        abs(a[4] - b[4]) < 1e-5
        and abs(a[5] - b[5]) < 1e-5
        and abs(a[6] - b[6]) < 1e-3
    )


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


def _history_icon(forward: bool) -> QIcon:
    """SketchUp Previous / Next: one circular arrow. Drawn like an IngeTrazo
    icon — 48 px, a 3 px round stroke in the palette ink, no SketchUp colour."""
    size = 48
    image = QPixmap(size, size)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    ink = QColor(40, 44, 52)
    app = QApplication.instance()
    if app is not None:
        color = app.palette().windowText().color()
        ink = QColor(color.red(), color.green(), color.blue())
    pen = QPen(ink, 3.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    if forward:
        painter.translate(size, 0)
        painter.scale(-1, 1)
    box = QRectF(13, 11, 24, 24)
    path = QPainterPath()
    path.arcMoveTo(box, 35)
    path.arcTo(box, 35, 270)
    painter.drawPath(path)
    end = path.pointAtPercent(1.0)
    before = path.pointAtPercent(0.94)
    dx, dy = end.x() - before.x(), end.y() - before.y()
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    side_x, side_y = -uy, ux
    tip = QPointF(end.x() + ux * 3.0, end.y() + uy * 3.0)
    painter.setPen(Qt.NoPen)
    painter.setBrush(ink)
    painter.drawPolygon(QPolygonF([
        tip,
        QPointF(tip.x() - ux * 9 + side_x * 5.5, tip.y() - uy * 9 + side_y * 5.5),
        QPointF(tip.x() - ux * 9 - side_x * 5.5, tip.y() - uy * 9 - side_y * 5.5),
    ]))
    painter.end()
    return QIcon(image)


def setup(app):
    ring: list = []
    index = [-1]
    walked: list = []
    busy = [False]
    pending = [None]
    still_for = [0]

    def active():
        if index[0] < 0 or not ring:
            return None
        return ring[index[0]]

    def show() -> None:
        app.viewport.flash_status(
            f"Camera view {index[0] + 1} / {len(ring)}", 1200)

    def commit(shot) -> None:
        path = list(ring) + list(walked) + [tuple(shot)]
        del path[:-KEEP]
        ring[:] = path
        walked.clear()
        index[0] = len(ring) - 1

    def sample() -> None:
        if busy[0] or QApplication.mouseButtons() != Qt.NoButton:
            still_for[0] = 0
            pending[0] = None
            return
        shot = _shot(app.viewport.camera)
        if _same(active(), shot):
            still_for[0] = 0
            pending[0] = None
            return
        if pending[0] is None or not _same(pending[0], shot):
            pending[0] = shot
            still_for[0] = 0
            return
        still_for[0] += POLL_MS
        if still_for[0] < SETTLE_MS:
            return
        commit(pending[0])
        pending[0] = None
        still_for[0] = 0

    def go(delta: int) -> None:
        n = len(ring)
        if n < 2:
            app.viewport.flash_status("No further camera view", 1500)
            return
        index[0] = (index[0] + delta) % n
        walked.append(ring[index[0]])
        busy[0] = True
        _apply(app.viewport.camera, ring[index[0]])
        app.viewport.update()
        busy[0] = False
        pending[0] = None
        still_for[0] = 0
        show()

    timer = QTimer(app.window)
    timer.setInterval(POLL_MS)
    timer.timeout.connect(sample)
    timer.start()
    app.window._camera_history_timer = timer

    forward = QAction("Camera history forward", app.window)
    forward.setShortcut(QKeySequence("Alt+Right"))
    forward.setShortcutContext(Qt.WindowShortcut)
    forward.setIcon(_history_icon(True))
    forward.setStatusTip(f"Step to the next stored camera view. v{VERSION}")
    forward.triggered.connect(lambda: go(1))
    back = QAction("Camera history back", app.window)
    back.setShortcut(QKeySequence("Alt+Left"))
    back.setShortcutContext(Qt.WindowShortcut)
    back.setIcon(_history_icon(False))
    back.setStatusTip(f"Step to the previous stored camera view. v{VERSION}")
    back.triggered.connect(lambda: go(-1))
    app.window.addAction(forward)
    app.window.addAction(back)

    menu = _camera_menu(app.window)
    menu.addSeparator()
    history = menu.addMenu("Camera history")
    history.addAction(back)
    history.addAction(forward)
