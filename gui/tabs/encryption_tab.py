"""Tab mã hóa & giải mã ảnh."""
from __future__ import annotations

import os
import time

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import decrypt_file, encrypt_file, load_image, poly_to_str
from .. import theme
from ..settings import last_dir, remember_dir
from ..widgets import ImageDropMixin, ImagePreview, PasswordField, TaskProgress
from ..workers import TaskRunner

DEFAULT_KEY = "day-la-mot-khoa-bi-mat-vi-du"
IMAGE_FILTER = "Ảnh (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;Tất cả tệp (*)"


def encrypt_task(worker, source: str, output: str, key: str, mode: str) -> dict:
    worker.check_cancelled()
    worker.report(5, "Đang đọc ảnh và mã hóa...")
    started = time.perf_counter()
    meta = encrypt_file(source, output, key, mode=mode)
    return {"meta": meta, "elapsed": time.perf_counter() - started}


def decrypt_task(worker, source: str, output: str, key: str, reference: str) -> dict:
    worker.check_cancelled()
    worker.report(5, "Đang giải mã ảnh...")
    started = time.perf_counter()
    meta = decrypt_file(source, output, key)
    elapsed = time.perf_counter() - started
    worker.check_cancelled()
    worker.report(80, "Đang kiểm tra ảnh giải mã...")
    return {"meta": meta, "elapsed": elapsed,
            "verify": compare_decryption(reference, output)}


def compare_decryption(reference: str, decrypted_path: str) -> dict:
    """So ảnh giải mã với ảnh gốc đối chiếu; trả về dict mô tả kết quả."""
    if not reference:
        return {"kind": "skip"}
    if not os.path.isfile(reference):
        return {"kind": "missing", "reference": reference}
    try:
        original = load_image(reference)
        decrypted = load_image(decrypted_path)
    except Exception as exc:  # noqa: BLE001 - hiển thị mọi lỗi cho người dùng
        return {"kind": "error", "message": f"Không đọc được ảnh để kiểm tra: {exc}"}
    if original.shape != decrypted.shape:
        return {"kind": "shape",
                "message": f"Không so sánh được: kích thước {original.shape} ≠ {decrypted.shape}"}

    diff = original.astype(np.int16) - decrypted.astype(np.int16)
    mse = float(np.mean(diff.astype(np.float64) ** 2))
    equal = int(np.count_nonzero(diff == 0))
    psnr_text = "∞ dB" if mse == 0 else f"{10.0 * np.log10(255.0 ** 2 / mse):.2f} dB"
    return {"kind": "ok", "reference": reference, "matched": equal == original.size,
            "percent": 100.0 * equal / original.size, "mse": mse, "psnr": psnr_text}


class EncryptionTab(ImageDropMixin, QWidget):
    """Mã hóa / giải mã một ảnh và xem trước ảnh gốc, ảnh mã hóa, ảnh giải mã."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending: dict | None = None
        self._last_encrypted: str | None = None
        self._last_source: str | None = None
        self._reference = ""
        self._build_ui()
        self.runner = TaskRunner(self)
        self.runner.progress.connect(self.progress.set_progress)
        self.runner.finished.connect(self._on_task_done)
        self.runner.failed.connect(self._on_task_failed)
        self.runner.cancelled.connect(self._on_task_cancelled)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("Ảnh đầu vào:"))
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("Ảnh gốc cần mã hóa")
        row.addWidget(self.input_path, 1)
        btn_browse = QPushButton("Chọn ảnh...")
        btn_browse.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        btn_browse.clicked.connect(self.browse_image)
        row.addWidget(btn_browse)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Ảnh đầu ra:"))
        self.output_path = QLineEdit()
        self.output_path.setPlaceholderText("Bỏ trống để tự tạo cạnh ảnh đầu vào")
        row.addWidget(self.output_path, 1)
        btn_save = QPushButton("Lưu thành...")
        btn_save.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        btn_save.clicked.connect(self.browse_output)
        row.addWidget(btn_save)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Mật khẩu:"))
        self.password = PasswordField(DEFAULT_KEY)
        row.addWidget(self.password, 1)
        row.addWidget(QLabel("Chế độ:"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("CBC (khuyến nghị)", "cbc")
        self.mode_combo.addItem("ECB (chỉ minh họa)", "ecb")
        self.mode_combo.currentIndexChanged.connect(self._update_mode_hint)
        row.addWidget(self.mode_combo)
        layout.addLayout(row)

        self.mode_warning = QLabel("")
        self.mode_warning.setWordWrap(True)
        self.mode_warning.setStyleSheet(f"color: {theme.WARNING};")
        self.mode_warning.setVisible(False)
        layout.addWidget(self.mode_warning)

        row = QHBoxLayout()
        self.btn_encrypt = QPushButton("Mã hóa ảnh")
        self.btn_encrypt.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_encrypt.clicked.connect(self.handle_encrypt)
        self.btn_decrypt = QPushButton("Giải mã ảnh")
        self.btn_decrypt.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        )
        self.btn_decrypt.clicked.connect(self.handle_decrypt)
        theme.mark_primary(self.btn_encrypt)
        row.addWidget(self.btn_encrypt)
        row.addWidget(self.btn_decrypt)
        self.btn_decrypt_last = QPushButton("Giải mã ảnh vừa mã hóa")
        self.btn_decrypt_last.setToolTip(
            "Điền sẵn ảnh mã hóa vừa tạo ở lần mã hóa gần nhất rồi giải mã"
        )
        self.btn_decrypt_last.setEnabled(False)
        self.btn_decrypt_last.clicked.connect(self.handle_decrypt_last)
        row.addWidget(self.btn_decrypt_last)
        row.addStretch(1)
        layout.addLayout(row)

        self.progress = TaskProgress()
        self.progress.cancel_requested.connect(self._cancel_task)
        layout.addWidget(self.progress)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(
            f"color: {theme.SUCCESS}; font-weight: bold;"
        )
        self.result_label.setVisible(False)
        layout.addWidget(self.result_label)

        self.verify_label = QLabel("")
        self.verify_label.setWordWrap(True)
        self.verify_label.setVisible(False)
        layout.addWidget(self.verify_label)

        previews = QWidget()
        previews_layout = QHBoxLayout(previews)
        previews_layout.setContentsMargins(0, 0, 0, 0)
        previews_layout.setSpacing(8)
        self.preview_original = ImagePreview("Ảnh gốc")
        self.preview_encrypted = ImagePreview("Ảnh mã hóa")
        self.preview_decrypted = ImagePreview("Ảnh giải mã")
        for preview in (self.preview_original, self.preview_encrypted, self.preview_decrypted):
            previews_layout.addWidget(preview, 1)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("Trạng thái thực thi sẽ hiển thị ở đây...")

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(previews)
        splitter.addWidget(self.log_output)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([620, 150])
        layout.addWidget(splitter, 1)

        self._buttons = (self.btn_encrypt, self.btn_decrypt, self.btn_decrypt_last)
        self.input_path.textChanged.connect(self._preview_input)
        self.password.returnPressed.connect(self.handle_encrypt)
        self._update_mode_hint()
        self._init_image_drop()

    def _preview_input(self) -> None:
        """Xem trước ảnh ngay khi người dùng chọn hoặc kéo-thả (chưa cần mã hóa)."""
        path = self.input_path.text().strip()
        if not path:
            self.preview_original.clear()
            return
        if not os.path.isfile(path):
            return
        if os.path.isfile(path + ".meta"):
            # Đang chọn ảnh mã hóa để giải mã — tự tìm ảnh gốc tương ứng
            self.preview_encrypted.set_path(path)
            self._reference = self._guess_reference(path) or self._reference
        else:
            self.preview_original.set_path(path)
            self._reference = path

    @staticmethod
    def _guess_reference(encrypted: str) -> str:
        """Suy ra ảnh gốc từ tên tệp mã hóa (…_enc.png → ….png) nếu có."""
        root, _ = os.path.splitext(encrypted)
        for suffix in ("_enc", "_encrypted", "_cipher"):
            if root.endswith(suffix):
                candidate = root[: -len(suffix)] + ".png"
                if os.path.isfile(candidate):
                    return candidate
        return ""

    def _update_mode_hint(self) -> None:
        ecb = self.mode_combo.currentData() == "ecb"
        self.mode_warning.setVisible(ecb)
        self.mode_warning.setText(
            "ECB không dùng IV và làm lộ cấu trúc ảnh — chỉ dùng để minh họa."
            if ecb else ""
        )

    def _select_mode(self, mode: str) -> None:
        index = self.mode_combo.findData(mode.lower())
        if index < 0:
            return
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(index)
        self.mode_combo.blockSignals(False)
        self._update_mode_hint()

    def _log(self, message: str) -> None:
        self.log_output.append(f"[{time.strftime('%H:%M:%S')}] {message}")

    def _status(self, message: str) -> None:
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(message)
        if callable(getattr(window, "refresh_menu", None)):
            window.refresh_menu()

    def _remember_output(self, path: str) -> None:
        window = self.window()
        if hasattr(window, "remember_output"):
            window.remember_output(path)

    def _error(self, message: str) -> None:
        self._log(f"LỖI: {message}")
        QMessageBox.critical(self, "Lỗi", message)

    def _set_busy(self, busy: bool, message: str = "Đang xử lý...") -> None:
        for button in self._buttons:
            button.setEnabled(not busy)
        self.btn_decrypt_last.setEnabled(not busy and self._last_encrypted is not None)
        window = self.window()
        if callable(getattr(window, "set_running", None)):
            window.set_running(busy)
        if busy:
            self.progress.start(message)
        else:
            self.progress.stop()

    @staticmethod
    def _default_output(source: str, suffix: str) -> str:
        root, _ = os.path.splitext(source)
        return root + suffix + ".png"

    def _same_file(self, a: str, b: str) -> bool:
        return os.path.abspath(a) == os.path.abspath(b)

    @staticmethod
    def _find_encrypted_candidate(source: str) -> str | None:
        """Tìm ảnh mã hóa đi kèm khi người dùng chọn nhầm ảnh gốc."""
        folder = os.path.dirname(os.path.abspath(source))
        stem = os.path.splitext(os.path.basename(source))[0]
        for suffix in ("_enc", "_encrypted", "_cipher"):
            candidate = os.path.join(folder, stem + suffix + ".png")
            if os.path.isfile(candidate) and os.path.isfile(candidate + ".meta"):
                return candidate
        return None

    def _resolve_encrypted_input(self, source: str) -> str | None:
        """Bảo đảm tệp đầu vào có .meta; nếu chọn nhầm ảnh gốc thì gợi ý ảnh mã hóa."""
        if os.path.isfile(source + ".meta"):
            return source

        candidate = self._find_encrypted_candidate(source)
        if candidate is None:
            self._error(
                "Tệp này không phải ảnh mã hóa: thiếu tệp .meta đi kèm.\n\n"
                "Hãy chọn ảnh mã hóa — tệp .png được tạo ra khi bấm “Mã hóa ảnh”, "
                "thường có tên dạng <tên>_enc.png."
            )
            return None

        answer = QMessageBox.question(
            self, "Có phải bạn muốn giải mã?",
            f"Tệp bạn chọn không có .meta nên không phải ảnh mã hóa:\n{source}\n\n"
            f"Tìm thấy ảnh mã hóa đi kèm:\n{candidate}\n\nGiải mã ảnh này?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return None
        self.input_path.setText(candidate)
        current_output = self.output_path.text().strip()
        if (not current_output or self._same_file(current_output, candidate)
                or self._same_file(current_output, self._default_output(source, "_dec"))):
            self.output_path.setText(self._default_output(source, "_dec"))
        if not self._reference:
            self._reference = source
        self._log(f"Đã chuyển sang ảnh mã hóa: {candidate}")
        return candidate

    def browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh", last_dir(), IMAGE_FILTER)
        if path:
            remember_dir(path)
            self.input_path.setText(path)
            self.output_path.clear()

    def browse_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Lưu ảnh", last_dir(), "PNG (*.png)")
        if path:
            remember_dir(path)
            self.output_path.setText(path)

    def _set_verify(self, matched: bool, message: str) -> None:
        self.verify_label.setText(("✔ " if matched else "✘ ") + message)
        color = theme.SUCCESS if matched else theme.DANGER
        self.verify_label.setStyleSheet(f"font-weight: bold; color: {color};")
        self.verify_label.setVisible(True)
        self._log(message)
        self._status(message)

    def _apply_verify(self, result: dict) -> None:
        kind = result["kind"]
        if kind == "skip":
            self.verify_label.setVisible(False)
            self._log("  (Không có ảnh gốc đối chiếu — bỏ qua kiểm tra giải mã)")
            return
        if kind == "missing":
            self.verify_label.setVisible(False)
            self._log(f"  (Không tìm thấy ảnh đối chiếu: {result['reference']})")
            return
        if kind in ("error", "shape"):
            self._set_verify(False, result["message"])
            return

        self.preview_original.set_path(result["reference"])
        matched = result["matched"]
        self._set_verify(
            matched,
            f"Khớp ảnh gốc: {'CÓ' if matched else 'KHÔNG'} — "
            f"{result['percent']:.2f}% giá trị điểm ảnh,"
            f" MSE = {result['mse']:.2f}, PSNR = {result['psnr']}",
        )

    def _start_task(self, kind: str, label: str, func, *args, **pending) -> None:
        if self.runner.busy():
            return
        self._pending = {"kind": kind, "label": label, **pending}
        self._set_busy(True, f"Đang {label.lower()}...")
        if not self.runner.start(func, *args):
            self._set_busy(False)
            self._pending = None

    def _cancel_task(self) -> None:
        self.runner.cancel()

    def _end_task(self) -> None:
        self._pending = None
        self._set_busy(False)

    def _on_task_done(self, result: dict) -> None:
        pending = self._pending or {}
        kind = pending.get("kind")
        try:
            if kind == "encrypt":
                self._apply_encrypt(pending, result)
            elif kind == "decrypt":
                self._apply_decrypt(pending, result)
        finally:
            self._end_task()

    def _on_task_failed(self, message: str) -> None:
        label = (self._pending or {}).get("label", "Xử lý")
        self._end_task()
        self._error(f"{label} thất bại: {message}")

    def _on_task_cancelled(self) -> None:
        self._end_task()
        self._log("Đã huỷ tác vụ.")
        self._status("Đã huỷ tác vụ")

    def shutdown(self) -> None:
        self.runner.shutdown()

    def _apply_encrypt(self, pending: dict, result: dict) -> None:
        meta, elapsed = result["meta"], result["elapsed"]
        source, output, mode = pending["source"], pending["output"], pending["mode"]

        self._last_source, self._last_encrypted = source, output
        self.btn_decrypt_last.setEnabled(True)

        self.output_path.setText(output)
        self._log(f"Đã mã hóa trong {elapsed:.2f} s -> {output}")
        self._log(f"  f(x) = {poly_to_str(meta['poly'])}")
        self._log(f"  Chế độ = {mode.upper()}")
        if mode == "cbc":
            self._log(f"  IV   = {meta['iv']}")

        self.preview_original.set_path(source)
        self.preview_encrypted.set_path(output)
        self.preview_decrypted.clear("Chưa giải mã")
        self._reference = source
        self.verify_label.setVisible(False)
        self.verify_label.clear()
        self.result_label.setText(
            f"✔ Đã mã hóa trong {elapsed:.2f} s → {os.path.basename(output)}"
        )
        self.result_label.setVisible(True)
        self._remember_output(output)
        self._status(f"Đã mã hóa: {os.path.basename(output)}")

    def _apply_decrypt(self, pending: dict, result: dict) -> None:
        meta, elapsed = result["meta"], result["elapsed"]
        source, output = pending["source"], pending["output"]

        self.output_path.setText(output)
        cipher_mode = meta.get("cipher_mode", "cbc")
        self._select_mode(cipher_mode)
        self._log(f"Đã giải mã trong {elapsed:.2f} s -> {output}")
        self._log(f"  Chế độ = {cipher_mode.upper()} (đọc từ .meta)")
        self._log(
            f"  Kích thước gốc: {meta['orig_width']}x{meta['orig_height']}"
            f"    f(x) = {poly_to_str(meta['poly'])}"
        )

        self.preview_encrypted.set_path(source)
        self.preview_decrypted.set_path(output)
        self.result_label.setText(
            f"✔ Đã giải mã trong {elapsed:.2f} s → {os.path.basename(output)}"
        )
        self.result_label.setVisible(True)
        self._remember_output(output)
        self._status(f"Đã giải mã: {os.path.basename(output)}")
        self._apply_verify(result["verify"])

    def handle_encrypt(self) -> None:
        if self.runner.busy():
            return
        source = self.input_path.text().strip()
        if not source:
            self._error("Vui lòng chọn ảnh gốc cần mã hóa.")
            return
        if not os.path.isfile(source):
            self._error(f"Không tìm thấy ảnh: {source}")
            return
        if not self.password.text():
            self._error("Vui lòng nhập mật khẩu (khóa bí mật).")
            return
        output = self.output_path.text().strip() or self._default_output(source, "_enc")
        if not output.lower().endswith(".png"):
            self._error("Ảnh mã hóa phải lưu dạng .png (JPEG sẽ làm hỏng bản mã).")
            return
        if self._same_file(source, output):
            self._error("Ảnh đầu ra phải khác ảnh gốc.")
            return

        mode = self.mode_combo.currentData() or "cbc"
        self._start_task("encrypt", "Mã hóa", encrypt_task,
                         source, output, self.password.text(), mode,
                         source=source, output=output, mode=mode)

    def handle_decrypt(self) -> None:
        if self.runner.busy():
            return
        source = self.input_path.text().strip()
        if not source:
            self._error("Vui lòng chọn ảnh mã hóa cần giải mã.")
            return
        if not os.path.isfile(source):
            self._error(f"Không tìm thấy ảnh: {source}")
            return
        if not self.password.text():
            self._error("Vui lòng nhập mật khẩu (khóa bí mật).")
            return
        source = self._resolve_encrypted_input(source)
        if source is None:
            return
        output = self.output_path.text().strip() or self._default_output(source, "_dec")
        if self._same_file(source, output):
            self._error("Ảnh đầu ra phải khác ảnh mã hóa.")
            return

        self._start_task("decrypt", "Giải mã", decrypt_task,
                         source, output, self.password.text(),
                         self._reference,
                         source=source, output=output)

    def handle_decrypt_last(self) -> None:
        """Giải mã ảnh vừa tạo ở lần mã hóa gần nhất."""
        if not self._last_encrypted or not os.path.isfile(self._last_encrypted):
            self._error("Chưa có ảnh mã hóa nào để giải mã. Hãy mã hóa một ảnh trước.")
            return
        self.input_path.setText(self._last_encrypted)
        base = self._last_source or self._last_encrypted
        self.output_path.setText(self._default_output(base, "_dec"))
        if self._last_source:
            self._reference = self._last_source
        self.handle_decrypt()
