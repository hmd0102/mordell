"""Màu sắc, cỡ chữ, stylesheet và icon dùng chung cho giao diện.

Gom về một chỗ để không phải hard-code màu trong từng tab (và để sau này đổi
giao diện chỉ cần sửa tệp này).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QPushButton

WARNING = "#b35c00"
NOTE = "#555555"
SUCCESS = "#1b5e20"
DANGER = "#b71c1c"
PLACEHOLDER = "#777777"

PREVIEW_BG = "#f2f2f2"
PREVIEW_BORDER = "#bbbbbb"
DRAG_BG = "#e6f1fb"
DRAG_BORDER = "#2f7fd1"

BRAND = "#1f5f8b"

FONT_POINT_SIZE = 10

STYLESHEET = f"""
QPushButton {{
    padding: 5px 12px;
}}
QPushButton[primary="true"] {{
    font-weight: 600;
    padding: 6px 16px;
}}
QLineEdit, QComboBox {{
    padding: 4px 6px;
}}
QTabWidget::pane {{
    border: 1px solid #dcdcdc;
}}
QGroupBox {{
    font-weight: 600;
    margin-top: 6px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QSplitter::handle {{
    background: #e8e8e8;
}}
QSplitter::handle:vertical {{
    height: 4px;
}}
QSplitter::handle:horizontal {{
    width: 4px;
}}
"""


def apply_theme(app: QApplication) -> None:
    """Đặt cỡ chữ và stylesheet chung cho toàn bộ ứng dụng."""
    font = QFont(app.font())
    if 0 < font.pointSize() < FONT_POINT_SIZE:
        font.setPointSize(FONT_POINT_SIZE)
    app.setFont(font)
    app.setStyleSheet(STYLESHEET)


def mark_primary(*buttons: QPushButton) -> None:
    """Đánh dấu nút hành động chính để stylesheet tô đậm."""
    for button in buttons:
        button.setProperty("primary", True)


def build_app_icon() -> QIcon:
    """Icon ứng dụng vẽ bằng QPainter (không cần tệp ảnh đi kèm)."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(BRAND))
        radius = size * 0.22
        painter.drawRoundedRect(0, 0, size, size, radius, radius)
        font = QFont("Segoe UI")
        font.setBold(True)
        font.setPixelSize(max(7, int(size * 0.58)))
        painter.setFont(font)
        painter.setPen(QColor("white"))
        painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "S")
        painter.end()
        icon.addPixmap(pixmap)
    return icon
