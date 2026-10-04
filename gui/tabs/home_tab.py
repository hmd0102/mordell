"""Tab Trang chủ: giới thiệu đồ án, thông tin tác giả và lối tắt tới các tab khác."""
from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import theme

# CHỈNH SỬA THÔNG TIN TẠI ĐÂY
SCHOOL = "HỌC VIỆN KỸ THUẬT MẬT MÃ"
DEPARTMENT = "KHOA AN TOÀN THÔNG TIN"

TITLE = "Xây dựng S-box động sử dụng đường cong Elliptic Mordell và ứng dụng trong mã hóa ảnh"

AUTHOR = "Hà Mạnh Đức - MSV: AT190211"
INSTRUCTOR = "ThS. Lê Minh Tú"
COURSE = "Đồ án tốt nghiệp"

VERSION = "1.0"

ASSET_LOGO = "logo_truong.png"
ASSET_BANNER = "banner.png"

LOGO_HEIGHT = 160
BANNER_HEIGHT = 120

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def _asset_path(name: str) -> str:
    return os.path.join(ASSETS_DIR, name)


def _placeholder(text: str, height: int) -> QFrame:
    """Khung chờ khi chưa có ảnh, ghi rõ tên tệp cần thêm."""
    frame = QFrame()
    frame.setFixedHeight(height)
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setStyleSheet(
        f"border: 1px dashed {theme.PREVIEW_BORDER}; border-radius: 6px;"
        f" background: {theme.PREVIEW_BG}; color: {theme.PLACEHOLDER};"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(8, 6, 8, 6)
    label = QLabel(f"Thêm ảnh:\ngui/assets/{text}")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    layout.addWidget(label)
    return frame


def _asset_widget(name: str, height: int) -> QWidget:
    """Ảnh trong gui/assets (thu nhỏ theo chiều cao) hoặc khung chờ."""
    path = _asset_path(name)
    pixmap = QPixmap(path) if os.path.isfile(path) else QPixmap()
    if pixmap.isNull():
        return _placeholder(name, height)
    scaled = pixmap.scaledToHeight(height, Qt.TransformationMode.SmoothTransformation)
    label = QLabel()
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setPixmap(scaled)
    label.setToolTip(path)
    return label


class HomeTab(QWidget):
    """Trang giới thiệu: logo, tên đề tài và thông tin sinh viên thực hiện."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(16)

        layout.addStretch(1)
        layout.addLayout(self._build_banner())
        layout.addWidget(self._build_school())
        layout.addWidget(self._build_title())
        layout.addWidget(self._build_info(), 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll, 1)
        # Phiên bản luôn nằm ở đáy tab (không cuộn theo nội dung)
        outer.addWidget(self._build_footer())

    def _build_banner(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(24)
        row.addStretch(1)
        row.addWidget(_asset_widget(ASSET_LOGO, LOGO_HEIGHT), 0,
                      Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(_asset_widget(ASSET_BANNER, BANNER_HEIGHT), 0,
                      Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        return row

    def _build_school(self) -> QLabel:
        school = QLabel(f"{SCHOOL} — {DEPARTMENT}")
        school.setAlignment(Qt.AlignmentFlag.AlignCenter)
        school.setWordWrap(True)
        school.setStyleSheet(
            f"color: {theme.BRAND}; font-size: 14pt; font-weight: 600;"
        )
        return school

    def _build_title(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        title = QLabel(TITLE)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setWordWrap(True)
        title.setStyleSheet(f"color: {theme.BRAND}; font-size: 22pt; font-weight: 700;")
        layout.addWidget(title)
        return panel

    def _build_info(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("infoCard")
        frame.setMinimumWidth(620)
        frame.setMaximumWidth(900)
        frame.setStyleSheet(
            "QFrame#infoCard { border: 1px solid #dcdcdc; border-radius: 10px;"
            " background: #f7fafd; }"
        )
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        rows = (
            ("Sinh viên thực hiện", AUTHOR),
            ("Giảng viên hướng dẫn", INSTRUCTOR),
            ("Học phần", COURSE),
        )
        for index, (label, value) in enumerate(rows):
            key = QLabel(f"{label}:")
            key.setStyleSheet("font-weight: 600;")
            key.setAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            val = QLabel(value)
            val.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            grid.addWidget(key, index, 0)
            grid.addWidget(val, index, 1)

        # Căn giữa cả khối chữ trong khung
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.addStretch(1)
        layout.addLayout(grid)
        layout.addStretch(1)
        return frame

    def _build_footer(self) -> QLabel:
        footer = QLabel(
            f"Phiên bản {VERSION}  ·  PyQt6 · NumPy · Pillow · Matplotlib"
        )
        footer.setWordWrap(True)
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.setStyleSheet(
            f"color: {theme.NOTE}; font-size: 9pt; padding: 6px 0;"
        )
        return footer
