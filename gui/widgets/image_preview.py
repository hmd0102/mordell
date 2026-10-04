"""Widget hiển thị ảnh (đường dẫn hoặc mảng numpy) kèm tiêu đề; nhấp để xem lớn."""
from __future__ import annotations

import os

import numpy as np
from PIL import Image
from PIL.ImageQt import ImageQt
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
)

from .. import theme
from ..settings import last_dir, remember_dir

_PLACEHOLDER = "Chưa có ảnh"


class ImageZoomDialog(QDialog):
    """Cửa sổ xem ảnh ở kích thước gốc, có thanh cuộn khi ảnh lớn."""

    def __init__(self, pixmap: QPixmap, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title or "Xem ảnh")
        self._pixmap = pixmap

        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        scroll = QScrollArea()
        scroll.setWidget(label)
        scroll.setWidgetResizable(False)      # giữ kích thước gốc -> có thanh cuộn
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)

        save_button = QPushButton("Lưu ảnh...")
        save_button.clicked.connect(self._save)
        close_button = QPushButton("Đóng")
        close_button.clicked.connect(self.accept)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(save_button)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addLayout(buttons)

        screen = self.screen()
        if screen is not None:
            area = screen.availableGeometry()
            width = min(pixmap.width() + 40, int(area.width() * 0.9))
            height = min(pixmap.height() + 90, int(area.height() * 0.85))
        else:
            width, height = pixmap.width() + 40, pixmap.height() + 90
        self.resize(max(width, 480), max(height, 360))

    def _save(self) -> None:
        name = (self.windowTitle() or "anh").replace(" — ", "_").replace(" ", "_")
        default = os.path.join(last_dir(), f"{name}.png")
        path, _ = QFileDialog.getSaveFileName(
            self, "Lưu ảnh", default,
            "PNG (*.png);;JPEG (*.jpg);;Bitmap (*.bmp);;Tất cả tệp (*)",
        )
        if not path:
            return
        if not os.path.splitext(path)[1]:
            path += ".png"
        if self._pixmap.save(path):
            remember_dir(path)
            QMessageBox.information(self, "Đã lưu", f"Đã lưu ảnh:\n{path}")
        else:
            QMessageBox.critical(self, "Lỗi", f"Không lưu được ảnh:\n{path}")


class ImagePreview(QFrame):
    """Khung preview tự co giãn theo widget; nhấp vào ảnh để mở cửa sổ zoom."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._pixmap: QPixmap | None = None
        self._base_title = title

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)

        self.image_label = QLabel(_PLACEHOLDER)
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(180, 180)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding,
                                       QSizePolicy.Policy.Expanding)
        self.set_drag_active(False)
        # Cho sự kiện chuột đi qua label để khung cha nhận được cú nhấp
        self.image_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.image_label, 1)

    def set_drag_active(self, active: bool) -> None:
        """Đổi viền/nền khi người dùng đang kéo ảnh vào cửa sổ."""
        if active:
            self.image_label.setStyleSheet(
                f"background: {theme.DRAG_BG}; border: 2px dashed {theme.DRAG_BORDER};"
                f" color: {theme.DRAG_BORDER};"
            )
            self.title_label.setStyleSheet(
                f"color: {theme.DRAG_BORDER}; font-weight: bold;"
            )
        else:
            self.image_label.setStyleSheet(
                f"background: {theme.PREVIEW_BG}; border: 1px dashed {theme.PREVIEW_BORDER};"
                f" color: {theme.PLACEHOLDER};"
            )
            self.title_label.setStyleSheet("")

    def set_info(self, info: str) -> None:
        """Hiện thêm thông tin (thường là kích thước) cạnh tiêu đề."""
        self.title_label.setText(
            f"{self._base_title} — {info}" if info else self._base_title
        )

    def size_text(self) -> str:
        if self._pixmap is None:
            return ""
        return f"{self._pixmap.width()}×{self._pixmap.height()}"

    def clear(self, text: str = _PLACEHOLDER) -> None:
        self._pixmap = None
        self.unsetCursor()
        self.setToolTip("")
        self.set_info("")
        self.image_label.clear()
        self.image_label.setText(text)

    def set_path(self, path: str) -> None:
        self.set_pixmap(QPixmap(path))

    def set_array(self, arr: np.ndarray) -> None:
        # ImageQt chỉ giữ con trỏ tới bộ đệm Python; .copy() để QImage/QPixmap
        # sở hữu dữ liệu riêng, tránh truy cập vùng nhớ đã giải phóng.
        qimage = ImageQt(Image.fromarray(np.ascontiguousarray(arr))).copy()
        self.set_pixmap(QPixmap.fromImage(qimage))

    def set_pixmap(self, pixmap: QPixmap) -> None:
        if pixmap.isNull():
            self.clear("Không đọc được ảnh")
            return
        self._pixmap = pixmap
        self.set_info(f"{pixmap.width()}×{pixmap.height()}")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Nhấp để xem ảnh lớn")
        self._rescale()

    def _rescale(self) -> None:
        if self._pixmap is None:
            return
        size = self.image_label.size()
        if size.width() <= 0 or size.height() <= 0:
            return
        self.image_label.setPixmap(
            self._pixmap.scaled(
                size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event):  # noqa: N802 - API của Qt
        super().resizeEvent(event)
        self._rescale()

    def mousePressEvent(self, event):  # noqa: N802 - API của Qt
        if event.button() == Qt.MouseButton.LeftButton and self._pixmap is not None:
            ImageZoomDialog(self._pixmap, self.title_label.text(), self).exec()
            event.accept()
            return
        super().mousePressEvent(event)
