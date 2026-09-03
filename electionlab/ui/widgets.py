from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QSizePolicy,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)




class RoundedPortraitLabel(QLabel):
    """Portrait label that really clips images to rounded corners.

    Qt stylesheets can draw a rounded QLabel border, but they do not reliably clip
    the pixmap itself on Windows. This widget keeps the normal label styling/text
    fallback while painting the portrait through a rounded clipping path.
    """

    def __init__(self, *args, radius: int = 13, **kwargs):
        super().__init__(*args, **kwargs)
        self._portrait_pixmap = QPixmap()
        self._radius = radius

    def setPixmap(self, pixmap: QPixmap):  # noqa: N802 - Qt API compatibility
        self._portrait_pixmap = QPixmap(pixmap) if pixmap is not None else QPixmap()
        # Do not give the pixmap to QLabel; QLabel would paint it square.
        super().setPixmap(QPixmap())
        self.update()

    def pixmap(self):  # noqa: N802 - Qt API compatibility
        return self._portrait_pixmap

    def paintEvent(self, event):
        # Let QLabel/QSS paint the background, border and fallback initials first.
        super().paintEvent(event)
        if self._portrait_pixmap.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        inset = 2.0
        rect = QRectF(inset, inset, max(1.0, self.width() - inset * 2), max(1.0, self.height() - inset * 2))
        clip = QPainterPath()
        clip.addRoundedRect(rect, self._radius, self._radius)
        painter.setClipPath(clip)
        painter.drawPixmap(rect.toRect(), self._portrait_pixmap)


class BusyOverlay(QFrame):
    """In-window loading screen used while background work is running."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BusyOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.hide()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        panel = QFrame()
        panel.setObjectName("BusyPanel")
        panel.setFixedWidth(430)
        pv = QVBoxLayout(panel)
        pv.setContentsMargins(24, 22, 24, 22)
        pv.setSpacing(12)
        self.title = QLabel("Working…")
        self.title.setObjectName("SectionTitle")
        self.title.setAlignment(Qt.AlignCenter)
        self.message = QLabel("ElectionLab is working in the background.")
        self.message.setObjectName("Muted")
        self.message.setWordWrap(True)
        self.message.setAlignment(Qt.AlignCenter)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(True)
        pv.addWidget(self.title)
        pv.addWidget(self.message)
        pv.addWidget(self.progress)
        row.addWidget(panel)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    def begin(self, title: str, message: str = "", percent: int | None = None):
        self.title.setText(title)
        self.set_progress(percent, message)
        if self.parentWidget():
            self.setGeometry(self.parentWidget().rect())
        self.raise_()
        self.show()

    def set_progress(self, percent: int | None, message: str = ""):
        if message:
            self.message.setText(message)
        if percent is None:
            self.progress.setRange(0, 0)
            self.progress.setFormat("Working…")
        else:
            pct = max(0, min(100, int(percent)))
            self.progress.setRange(0, 100)
            self.progress.setValue(pct)
            self.progress.setFormat(f"{pct}%")

    def finish(self):
        self.hide()


class InfoButton(QToolButton):
    """Small, visible help affordance used throughout the UI.

    Hovering gives the short explanation; clicking opens the same text in a
    readable dialog so help is also usable for touchpads and accessibility.
    """

    def __init__(self, title: str, text: str, parent=None):
        super().__init__(parent)
        self.help_title = title
        self.help_text = text
        self.setObjectName("Info")
        self.setText("i")
        self.setCursor(Qt.PointingHandCursor)
        short = text.split(".", 1)[0].strip()
        self.setToolTip((short + ".") if short else f"About {title}")
        self.setAccessibleName(f"About {title}")
        self.setFixedSize(20, 20)
        self.clicked.connect(self._show_help)

    def _show_help(self):
        QMessageBox.information(self.window(), self.help_title, self.help_text)


class InfoLabel(QWidget):
    """A normal label with a compact circled-i help button."""

    def __init__(self, text: str, help_text: str, help_title: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.setObjectName("InfoLabelHost")
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)
        label = QLabel(text)
        label.setObjectName("FieldLabel")
        row.addWidget(label)
        row.addWidget(InfoButton(help_title or text, help_text))
        row.addStretch(1)


class Card(QFrame):
    def __init__(
        self,
        title: str | None = None,
        parent=None,
        hero: bool = False,
        info_text: str | None = None,
        accent: str | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("HeroCard" if hero else "Card")
        if accent:
            self.setProperty("accent", accent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(16, 14, 16, 14)
        self.layout.setSpacing(10)
        if title:
            title_row = QHBoxLayout()
            title_row.setSpacing(6)
            label = QLabel(title)
            label.setObjectName("SectionTitle")
            title_row.addWidget(label)
            if info_text:
                title_row.addWidget(InfoButton(title, info_text))
            title_row.addStretch(1)
            self.layout.addLayout(title_row)


class MetricCard(Card):
    def __init__(
        self,
        label: str,
        value: str = "—",
        sub: str = "",
        parent=None,
        info_text: str | None = None,
    ):
        super().__init__(parent=parent)
        top = QHBoxLayout()
        top.setSpacing(5)
        self.label = QLabel(label)
        self.label.setObjectName("MetricLabel")
        self.label.setWordWrap(True)
        top.addWidget(self.label)
        if info_text:
            top.addWidget(InfoButton(label, info_text))
        top.addStretch(1)
        self.layout.addLayout(top)

        self.value = QLabel(value)
        self.value.setObjectName("MetricValue")
        self.value.setWordWrap(True)
        self.value.setMinimumHeight(39)
        self.sub = QLabel(sub)
        self.sub.setObjectName("Muted")
        self.sub.setWordWrap(True)
        self.layout.addWidget(self.value)
        self.layout.addWidget(self.sub)
        self.layout.addStretch(1)


# Geographic election map. 0.11.1 uses one canonical full-canvas state-index
# raster generated directly from the original SVG. The visible map is no longer
# stitched from 51 cropped state tiles, eliminating seams/drift while retaining
# O(1) pixel hit-testing and fast dynamic recoloring.
_RASTER_MAP_ROOT = Path(__file__).resolve().parents[1] / "data" / "map_raster_v2"
_RASTER_ASSET_CACHE: dict[str, object] = {}


def _load_raster_assets() -> tuple[dict, QImage, QPixmap]:
    cached = _RASTER_ASSET_CACHE.get("bundle")
    if cached:
        return cached  # type: ignore[return-value]
    manifest = json.loads((_RASTER_MAP_ROOT / "manifest.json").read_text(encoding="utf-8"))
    width = int(manifest.get("width", 1028))
    height = int(manifest.get("height", 746))
    raw = (_RASTER_MAP_ROOT / "state_indexed.bin").read_bytes()
    expected = width * height
    if len(raw) != expected:
        raise RuntimeError(f"Election map index is invalid: expected {expected} bytes, found {len(raw)}")
    # QImage initially borrows the bytes object. copy() immediately detaches it so
    # the image remains valid after this function returns.
    indexed = QImage(raw, width, height, width, QImage.Format_Indexed8).copy()
    outline = QPixmap(str(_RASTER_MAP_ROOT / "outline.png"))
    bundle = (manifest, indexed, outline)
    _RASTER_ASSET_CACHE["bundle"] = bundle
    return bundle


class ElectoralGrid(QFrame):
    """Interactive geographic Electoral College map using a canonical index raster.

    The original SVG remains the build/source asset. At runtime one 8-bit full-map
    image stores jurisdiction IDs. Recoloring changes only its color table, so all
    state boundaries stay pixel-identical and clicks are one pixel-index lookup.
    """

    state_clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MapFrame")
        self.setMinimumHeight(420)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self._state_data: dict[str, dict] = {}
        self._a_name = "Ticket A"
        self._b_name = "Ticket B"
        self._hover_code: str | None = None
        self._selected_code: str | None = None
        self._last_tooltip_code: str | None = None
        self._base_pixmap = QPixmap()
        self._source_pixmap = QPixmap()
        self._map_title = "Electoral map"
        self._probability_label = "win chance"

        self._manifest, self._index_image, self._outline = _load_raster_assets()
        self._source_w = int(self._manifest.get("width", 1028))
        self._source_h = int(self._manifest.get("height", 746))
        self._map_rect = QRectF()
        self._state_masks: dict[str, QPixmap] = {}
        self._edge_cache: dict[tuple[str, str, int], QPixmap] = {}
        self._index_to_code = {int(k): v for k, v in (self._manifest.get("index_to_code") or {}).items()}
        self._code_to_index = {str(k): int(v) for k, v in (self._manifest.get("code_to_index") or {}).items()}
        self._rebuild_source_map()

    def sizeHint(self) -> QSize:
        return QSize(820, 500)

    @staticmethod
    def _fill_for_probability(p: float) -> QColor:
        if p >= .85:
            return QColor("#194fae")
        if p >= .65:
            return QColor("#2d67bb")
        if p > .50:
            return QColor("#567da9")
        if p <= .15:
            return QColor("#b91f3d")
        if p <= .35:
            return QColor("#a83a50")
        return QColor("#825c67")

    def set_display_context(self, title: str = "Electoral map", probability_label: str = "win chance"):
        self._map_title = title or "Electoral map"
        self._probability_label = probability_label or "win chance"
        self._rebuild_base_map()
        self.update()

    def set_results(self, states: list[dict], a_name: str, b_name: str):
        self._state_data = {s["code"]: s for s in states}
        self._a_name = a_name
        self._b_name = b_name
        if self._selected_code not in self._state_data:
            self._selected_code = None
        self._rebuild_source_map()
        self._rebuild_base_map()
        self.update()

    def select_state(self, code: str | None):
        self._selected_code = code if code in self._state_data else None
        self.update()

    def _layout_map(self):
        if self.width() <= 40 or self.height() <= 80:
            self._map_rect = QRectF()
            return
        title_h = 34.0
        legend_h = 42.0
        target = QRectF(16.0, title_h, max(80.0, self.width() - 32.0), max(80.0, self.height() - title_h - legend_h - 8.0))
        scale = min(target.width() / self._source_w, target.height() / self._source_h)
        w, h = self._source_w * scale, self._source_h * scale
        self._map_rect = QRectF(target.left() + (target.width() - w) / 2.0, target.top() + (target.height() - h) / 2.0, w, h)

    def _state_asset(self, code: str) -> QPixmap:
        if code not in self._state_masks:
            self._state_masks[code] = QPixmap(str(_RASTER_MAP_ROOT / "states" / f"{code}.png"))
        return self._state_masks[code]

    def _state_edge(self, code: str, color: QColor, radius: int = 2) -> QPixmap:
        key = (code, color.name(QColor.HexArgb), int(radius))
        cached = self._edge_cache.get(key)
        if cached is not None and not cached.isNull():
            return cached
        mask = self._state_asset(code)
        if mask.isNull():
            return QPixmap()
        radius = max(1, int(radius))
        colored = QPixmap(mask.size())
        colored.fill(color)
        color_painter = QPainter(colored)
        color_painter.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        color_painter.drawPixmap(0, 0, mask)
        color_painter.end()

        out = QPixmap(mask.width() + radius * 2, mask.height() + radius * 2)
        out.fill(Qt.transparent)
        painter = QPainter(out)
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                if dx * dx + dy * dy <= radius * radius:
                    painter.drawPixmap(radius + dx, radius + dy, colored)
        painter.setCompositionMode(QPainter.CompositionMode_DestinationOut)
        painter.drawPixmap(radius, radius, mask)
        painter.end()
        self._edge_cache[key] = out
        return out

    def _draw_state_edge(self, painter: QPainter, code: str | None, color: QColor, radius: int, opacity: float) -> None:
        if not code:
            return
        edge = self._state_edge(code, color, radius)
        target = self._target_for_state(code)
        if edge.isNull() or target.isEmpty():
            return
        sx = target.width() / max(1.0, float(edge.width() - radius * 2))
        sy = target.height() / max(1.0, float(edge.height() - radius * 2))
        expanded = target.adjusted(-radius * sx, -radius * sy, radius * sx, radius * sy)
        painter.save()
        painter.setOpacity(opacity)
        painter.drawPixmap(expanded, edge, QRectF(edge.rect()))
        painter.restore()

    def _target_for_state(self, code: str) -> QRectF:
        info = (self._manifest.get("states") or {}).get(code) or {}
        bbox = info.get("bbox") or [0, 0, 0, 0]
        if self._map_rect.isEmpty() or len(bbox) != 4:
            return QRectF()
        x0, y0, x1, y1 = [float(v) for v in bbox]
        sx = self._map_rect.width() / self._source_w
        sy = self._map_rect.height() / self._source_h
        return QRectF(self._map_rect.left() + x0 * sx, self._map_rect.top() + y0 * sy, max(1.0, (x1 - x0) * sx), max(1.0, (y1 - y0) * sy))

    def resizeEvent(self, event):
        self._layout_map()
        self._rebuild_base_map()
        super().resizeEvent(event)

    def _rebuild_source_map(self):
        """Recolor the canonical index map without reconstructing state geometry."""
        if self._index_image.isNull():
            self._source_pixmap = QPixmap()
            return
        image = self._index_image.copy()
        colors = [QColor(0, 0, 0, 0).rgba()] * 256
        for idx, code in self._index_to_code.items():
            state = self._state_data.get(code)
            fill = QColor("#253244") if not state else self._fill_for_probability(float(state.get("a_win_prob", .5)))
            if 0 <= idx < len(colors):
                colors[idx] = fill.rgba()
        image.setColorTable(colors)
        self._source_pixmap = QPixmap.fromImage(image)

    def _rebuild_base_map(self):
        if self.width() <= 0 or self.height() <= 0:
            return
        self._layout_map()
        pix = QPixmap(self.size())
        pix.fill(Qt.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.setPen(QColor("#e8edf5"))
        title_font = QFont("Segoe UI", 10)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.drawText(QRectF(16, 8, self.width() - 32, 22), Qt.AlignLeft | Qt.AlignVCenter, self._map_title)

        # Visible geography is one pre-aligned national raster. There is no
        # per-state composition here, so shared borders cannot drift or separate.
        if not self._map_rect.isEmpty() and not self._source_pixmap.isNull():
            painter.drawPixmap(self._map_rect, self._source_pixmap, QRectF(self._source_pixmap.rect()))
            if not self._outline.isNull():
                painter.drawPixmap(self._map_rect, self._outline, QRectF(self._outline.rect()))

        for code, info in (self._manifest.get("states") or {}).items():
            state = self._state_data.get(code)
            label = info.get("label")
            if not state or not label or self._map_rect.isEmpty():
                continue
            x = self._map_rect.left() + float(label[0]) / self._source_w * self._map_rect.width()
            y = self._map_rect.top() + float(label[1]) / self._source_h * self._map_rect.height()
            painter.setPen(QColor("#ffffff"))
            f = QFont("Segoe UI", 7); f.setBold(True); painter.setFont(f)
            painter.drawText(QRectF(x - 17, y - 12, 34, 13), Qt.AlignCenter, code)
            painter.setPen(QColor("#e1e8f2")); painter.setFont(QFont("Segoe UI", 6))
            painter.drawText(QRectF(x - 17, y + 1, 34, 12), Qt.AlignCenter, str(state.get("ev", "")))

        legend_y = self.height() - 24
        painter.setFont(QFont("Segoe UI", 7)); painter.setPen(QColor("#8f9bad")); painter.drawText(16, legend_y + 3, "A safer")
        x = 66
        for color in ("#194fae", "#2d67bb", "#567da9", "#825c67", "#a83a50", "#b91f3d"):
            painter.setPen(Qt.NoPen); painter.setBrush(QColor(color)); painter.drawRoundedRect(QRectF(x, legend_y - 8, 18, 12), 3, 3); x += 22
        painter.setPen(QColor("#8f9bad")); painter.drawText(x + 2, legend_y + 3, "B safer   •   label number = electoral votes")
        painter.end()
        self._base_pixmap = pix

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._base_pixmap.isNull() or self._base_pixmap.size() != self.size():
            self._rebuild_base_map()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        painter.drawPixmap(0, 0, self._base_pixmap)
        if self._hover_code and self._hover_code != self._selected_code:
            self._draw_state_edge(painter, self._hover_code, QColor(245, 249, 255, 190), 2, .82)
        self._draw_state_edge(painter, self._selected_code, QColor(255, 205, 92, 235), 3, .95)

    def _code_at(self, pos) -> str | None:
        if self._index_image.isNull() or self._map_rect.isEmpty() or not self._map_rect.contains(pos):
            return None
        sx = (float(pos.x()) - self._map_rect.left()) / self._map_rect.width() * self._source_w
        sy = (float(pos.y()) - self._map_rect.top()) / self._map_rect.height() * self._source_h
        x = max(0, min(self._source_w - 1, int(sx)))
        y = max(0, min(self._source_h - 1, int(sy)))
        return self._index_to_code.get(int(self._index_image.pixelIndex(x, y)))

    def mouseMoveEvent(self, event):
        code = self._code_at(event.position())
        if code != self._hover_code:
            self._hover_code = code
            self.setCursor(Qt.PointingHandCursor if code else Qt.ArrowCursor)
            self.update()
        if code != self._last_tooltip_code:
            self._last_tooltip_code = code
            if code and code in self._state_data:
                s = self._state_data[code]
                m = float(s.get("avg_margin_a", 0)); p = float(s.get("a_win_prob", .5))
                leader = self._a_name if m >= 0 else self._b_name
                QToolTip.showText(event.globalPosition().toPoint() + QPoint(14, 18),
                    f"{s.get('name', code)} · {s.get('ev', '?')} electoral votes\n"
                    f"Modeled leader: {leader} by {abs(m):.1f} points\n"
                    f"{self._a_name} {self._probability_label}: {p*100:.1f}%", self)
            else:
                QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_code = None; self._last_tooltip_code = None
        QToolTip.hideText(); self.setCursor(Qt.ArrowCursor); self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            code = self._code_at(event.position())
            if code and code in self._state_data:
                self._selected_code = code
                self.state_clicked.emit(self._state_data[code])
                self.update()
        super().mousePressEvent(event)


class ElectoralScoreBar(QFrame):
    """Compact 538-EV score visualization with a visible 270-to-win marker."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("MapFrame")
        self.setFixedHeight(82)
        self._a_ev = 269.0
        self._b_ev = 269.0
        self._a_name = "Ticket A"
        self._b_name = "Ticket B"
        self.setToolTip("There are 538 electoral votes. A candidate normally needs 270 to win the presidency.")

    def set_scores(self, a_ev: float, b_ev: float, a_name: str, b_name: str):
        self._a_ev = max(0.0, float(a_ev))
        self._b_ev = max(0.0, float(b_ev))
        self._a_name = a_name
        self._b_name = b_name
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        left, right = 18.0, self.width() - 18.0
        top = 38.0
        bar_h = 16.0
        width = max(40.0, right - left)
        total = max(1.0, self._a_ev + self._b_ev)
        a_w = width * self._a_ev / total

        small = QFont("Segoe UI", 8)
        small.setBold(True)
        p.setFont(small)
        p.setPen(QColor("#dce6f4"))
        p.drawText(QRectF(left, 10, width / 2 - 4, 20), Qt.AlignLeft | Qt.AlignVCenter, f"A  {self._a_ev:.0f} EV")
        p.drawText(QRectF(left + width / 2 + 4, 10, width / 2 - 4, 20), Qt.AlignRight | Qt.AlignVCenter, f"{self._b_ev:.0f} EV  B")

        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2563c7"))
        p.drawRoundedRect(QRectF(left, top, max(0, a_w), bar_h), 6, 6)
        p.setBrush(QColor("#c3344d"))
        p.drawRoundedRect(QRectF(left + a_w, top, max(0, width - a_w), bar_h), 6, 6)

        # The midpoint corresponds to 269/269; the 270 threshold is essentially
        # the center of the 538-vote scale and is shown explicitly for clarity.
        mid_x = left + width * (270 / 538)
        p.setPen(QPen(QColor("#ffffff"), 1.4))
        p.drawLine(QPointF(mid_x, top - 5), QPointF(mid_x, top + bar_h + 5))
        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QColor("#9dabc0"))
        p.drawText(QRectF(mid_x - 70, top + 22, 140, 18), Qt.AlignCenter, "270 to win")

class ToggleChip(QToolButton):
    """Compact checkable model-factor control with an explicit on/off state."""

    def __init__(self, text: str, checked: bool = True, parent=None):
        super().__init__(parent)
        self._label = text
        self.setObjectName("ToggleChip")
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.toggled.connect(self._sync_text)
        self._sync_text(self.isChecked())

    def _sync_text(self, checked: bool):
        self.setText(("✓  " if checked else "○  ") + self._label)


def nav_icon(kind: str, size: int = 18):
    """Return a small consistent monochrome navigation icon drawn by Qt itself.

    ElectionLab used assorted Unicode glyphs through 0.9, which rendered with
    different fonts/weights on Windows. These vector-ish QPainter icons use the
    same geometry and stroke weight on every sidebar item without adding image
    assets or an icon-font dependency.
    """
    from PySide6.QtGui import QIcon

    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor("#c6d3e4"), 1.65)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    s = float(size)
    k = (kind or "").lower()

    if k == "dashboard":
        w = s * .30; gap = s * .10; x = s * .14; y = s * .14
        for r in range(2):
            for c in range(2):
                p.drawRoundedRect(QRectF(x + c*(w+gap), y + r*(w+gap), w, w), 1.6, 1.6)
    elif k == "simulate":
        p.drawEllipse(QRectF(s*.17, s*.17, s*.66, s*.66))
        p.drawLine(QPointF(s*.31,s*.56), QPointF(s*.46,s*.41))
        p.drawLine(QPointF(s*.46,s*.41), QPointF(s*.57,s*.52))
        p.drawLine(QPointF(s*.57,s*.52), QPointF(s*.72,s*.34))
    elif k == "campaigns":
        p.drawRoundedRect(QRectF(s*.12,s*.26,s*.76,s*.56),2,2)
        p.drawLine(QPointF(s*.20,s*.26), QPointF(s*.34,s*.15))
        p.drawLine(QPointF(s*.34,s*.15), QPointF(s*.56,s*.15))
        p.drawLine(QPointF(s*.56,s*.15), QPointF(s*.64,s*.26))
    elif k == "hq":
        p.drawLine(QPointF(s*.16,s*.80), QPointF(s*.84,s*.80))
        p.drawLine(QPointF(s*.22,s*.80), QPointF(s*.22,s*.39))
        p.drawLine(QPointF(s*.78,s*.80), QPointF(s*.78,s*.39))
        p.drawLine(QPointF(s*.14,s*.39), QPointF(s*.50,s*.15))
        p.drawLine(QPointF(s*.50,s*.15), QPointF(s*.86,s*.39))
        p.drawLine(QPointF(s*.35,s*.80), QPointF(s*.35,s*.52))
        p.drawLine(QPointF(s*.50,s*.80), QPointF(s*.50,s*.52))
        p.drawLine(QPointF(s*.65,s*.80), QPointF(s*.65,s*.52))
    elif k == "vault":
        p.drawEllipse(QRectF(s*.18,s*.15,s*.64,s*.24))
        p.drawLine(QPointF(s*.18,s*.27), QPointF(s*.18,s*.70))
        p.drawLine(QPointF(s*.82,s*.27), QPointF(s*.82,s*.70))
        p.drawArc(QRectF(s*.18,s*.58,s*.64,s*.24), 180*16, 180*16)
        p.drawArc(QRectF(s*.18,s*.36,s*.64,s*.24), 180*16, 180*16)
    elif k == "data":
        p.drawLine(QPointF(s*.18,s*.82), QPointF(s*.82,s*.82))
        p.drawRoundedRect(QRectF(s*.22,s*.52,s*.12,s*.30),1.2,1.2)
        p.drawRoundedRect(QRectF(s*.44,s*.35,s*.12,s*.47),1.2,1.2)
        p.drawRoundedRect(QRectF(s*.66,s*.19,s*.12,s*.63),1.2,1.2)
    elif k == "settings":
        p.drawEllipse(QRectF(s*.33,s*.33,s*.34,s*.34))
        p.drawEllipse(QRectF(s*.20,s*.20,s*.60,s*.60))
        for a,b,c,d in [(.50,.08,.50,.20),(.50,.80,.50,.92),(.08,.50,.20,.50),(.80,.50,.92,.50),(.20,.20,.29,.29),(.71,.71,.80,.80),(.71,.29,.80,.20),(.20,.80,.29,.71)]:
            p.drawLine(QPointF(s*a,s*b), QPointF(s*c,s*d))
    else:
        p.drawEllipse(QRectF(s*.22,s*.22,s*.56,s*.56))
    p.end()
    return QIcon(pm)
