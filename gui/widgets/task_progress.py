"""Thanh tiến trình + nút Huỷ cho tác vụ chạy nền (tự ẩn khi rảnh)."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QProgressBar, QPushButton, QWidget


class TaskProgress(QWidget):
    """Hiện nhãn trạng thái, phần trăm và nút Huỷ trong lúc tác vụ chạy."""

    cancel_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.label = QLabel("")
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setFixedWidth(170)
        self.bar.setTextVisible(True)

        self.btn_cancel = QPushButton("Huỷ")
        self.btn_cancel.setToolTip("Dừng tác vụ sau bước đang chạy")
        self.btn_cancel.clicked.connect(self._request_cancel)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.label, 1)
        layout.addWidget(self.bar)
        layout.addWidget(self.btn_cancel)

        self.setVisible(False)

    def start(self, message: str = "Đang xử lý...", cancellable: bool = True) -> None:
        self.bar.setValue(0)
        self.label.setText(message)
        self.btn_cancel.setEnabled(cancellable)
        self.btn_cancel.setVisible(cancellable)
        self.setVisible(True)

    def set_progress(self, percent: int, message: str = "") -> None:
        self.bar.setValue(int(percent))
        if message:
            self.label.setText(message)

    def stop(self) -> None:
        self.bar.setValue(0)
        self.label.clear()
        self.setVisible(False)

    def _request_cancel(self) -> None:
        self.btn_cancel.setEnabled(False)
        self.label.setText("Đang dừng...")
        self.cancel_requested.emit()
