"""Hỗ trợ kéo-thả ảnh vào các tab có ô `input_path`."""
from __future__ import annotations

import os
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".gif", ".webp"}


def dropped_image_path(event) -> str | None:
    """Trả về đường dẫn ảnh đầu tiên trong sự kiện kéo-thả, hoặc None."""
    if not event.mimeData().hasUrls():
        return None
    for url in event.mimeData().urls():
        path = url.toLocalFile()
        if not path:
            continue
        path = os.path.normpath(path)
        if Path(path).suffix.lower() in IMAGE_SUFFIXES and os.path.isfile(path):
            return path
    return None


class ImageDropMixin:
    """Trộn vào tab (trước QWidget) để nhận ảnh kéo-thả vào cửa sổ."""

    _PREVIEW_NAMES = (
        "preview_original", "preview_encrypted", "preview_decrypted",
        "preview_ecb", "preview_cbc",
    )

    def _init_image_drop(self) -> None:
        self.setAcceptDrops(True)
        self.input_path.setAcceptDrops(False)   # để sự kiện nổi lên tab

    def _set_drag_active(self, active: bool) -> None:
        """Tô sáng các khung xem trước khi đang kéo ảnh vào."""
        for name in self._PREVIEW_NAMES:
            preview = getattr(self, name, None)
            if preview is not None:
                preview.set_drag_active(active)

    def dragEnterEvent(self, event):  # noqa: N802 - API của Qt
        if dropped_image_path(event):
            self._set_drag_active(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):  # noqa: N802 - API của Qt
        if dropped_image_path(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):  # noqa: N802 - API của Qt
        self._set_drag_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):  # noqa: N802 - API của Qt
        self._set_drag_active(False)
        path = dropped_image_path(event)
        if not path:
            event.ignore()
            return
        self.input_path.setText(path)
        if hasattr(self, "output_path"):
            self.output_path.clear()
        event.acceptProposedAction()
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(f"Đã nhận ảnh: {os.path.basename(path)}")
