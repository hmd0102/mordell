"""Cấu hình nhỏ của giao diện (thư mục gần nhất, tab đang mở, tỉ lệ khung...)."""
from __future__ import annotations

import os

from PyQt6.QtCore import QSettings

ORG = "Mordell"
APP = "SboxImageCipher"


def settings() -> QSettings:
    """QSettings dùng chung cho ứng dụng (lưu trong registry trên Windows)."""
    return QSettings(ORG, APP)


def last_dir() -> str:
    """Thư mục ảnh/tệp dùng gần nhất, hoặc chuỗi rỗng nếu chưa có."""
    folder = settings().value("ui/last_dir", "", type=str)
    return folder if folder and os.path.isdir(folder) else ""


def remember_dir(path: str) -> None:
    """Ghi nhớ thư mục của tệp vừa chọn/lưu để lần sau mở đúng chỗ."""
    if not path:
        return
    folder = path if os.path.isdir(path) else os.path.dirname(os.path.abspath(path))
    if os.path.isdir(folder):
        store = settings()
        store.setValue("ui/last_dir", folder)
        store.sync()
