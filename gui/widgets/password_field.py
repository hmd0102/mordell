"""Ô nhập mật khẩu kèm nút hiện/ẩn."""
from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget


class PasswordField(QWidget):
    """QLineEdit bị che ký tự + nút bật/tắt hiển thị mật khẩu."""

    #: Phát ra khi người dùng nhấn Enter trong ô mật khẩu
    returnPressed = pyqtSignal()

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.edit = QLineEdit(text)
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText("Khóa bí mật dùng để sinh S-box và AES-256")
        self.edit.returnPressed.connect(self.returnPressed)

        self.toggle = QPushButton("Hiện")
        self.toggle.setCheckable(True)
        self.toggle.setFixedWidth(56)
        self.toggle.toggled.connect(self._on_toggled)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self.edit, 1)
        layout.addWidget(self.toggle)

    def _on_toggled(self, visible: bool) -> None:
        self.edit.setEchoMode(
            QLineEdit.EchoMode.Normal if visible else QLineEdit.EchoMode.Password
        )
        self.toggle.setText("Ẩn" if visible else "Hiện")

    def text(self) -> str:
        return self.edit.text()

    def setText(self, value: str) -> None:
        self.edit.setText(value)
