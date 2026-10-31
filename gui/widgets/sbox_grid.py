"""Lưới S-box 16×16 tự vẽ: ô luôn vuông và tự co theo khung chứa."""
from __future__ import annotations

from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPainter
from PyQt6.QtWidgets import QWidget

from .. import theme

GRID_COLOR = "#d9e2ec"
HEADER_BG = "#eef3f8"
VALUE_COLOR = "#1f2933"


class SboxGrid(QWidget):
    """Vẽ bảng thế S-box 16×16 kèm tiêu đề hàng/cột, ô vuông đều."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = list(range(256))
        self._hex = True
        self.setMinimumSize(220, 220)

    def sizeHint(self) -> QSize:  # noqa: N802 - API của Qt
        return QSize(520, 520)

    def set_sbox(self, values: list[int], hexa: bool = True) -> None:
        self._values = list(values)
        self._hex = hexa
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - API của Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        width, height = self.width(), self.height()
        cell = max(10, min(width, height) // 17)
        side = cell * 17
        left = (width - side) // 2
        top = (height - side) // 2

        painter.fillRect(QRect(left, top, side, side), QColor("white"))
        painter.fillRect(QRect(left, top, side, cell), QColor(HEADER_BG))
        painter.fillRect(QRect(left, top, cell, side), QColor(HEADER_BG))

        font = QFont(self.font())
        size = max(8, min(18, int(cell * 0.42)))
        font.setPixelSize(size)
        painter.setFont(font)

        painter.setPen(QColor(theme.BRAND))
        for index in range(16):
            painter.drawText(
                QRect(left + (index + 1) * cell, top, cell, cell),
                Qt.AlignmentFlag.AlignCenter, f"{index:X}",
            )
            painter.drawText(
                QRect(left, top + (index + 1) * cell, cell, cell),
                Qt.AlignmentFlag.AlignCenter, f"{index:X}",
            )

        painter.setPen(QColor(VALUE_COLOR))
        for row in range(16):
            for column in range(16):
                value = self._values[row * 16 + column]
                painter.drawText(
                    QRect(left + (column + 1) * cell, top + (row + 1) * cell, cell, cell),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{value:02X}" if self._hex else str(value),
                )

        painter.setPen(QColor(GRID_COLOR))
        for index in range(18):
            position = left + index * cell
            painter.drawLine(position, top, position, top + side)
            position = top + index * cell
            painter.drawLine(left, position, left + side, position)
