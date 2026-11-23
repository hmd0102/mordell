"""Tab tấn công ảnh mã hóa: cắt bản mã, nhiễu muối tiêu, sửa 1 bit, giải mã bằng khóa sai,
mã hóa ảnh toàn đen/toàn trắng (kiểu tấn công bản rõ chọn lọc).

Mỗi kiểu tấn công chạy ở hai lớp: lớp mã hóa ảnh (không xác thực, vẫn giải mã ra ảnh và đo PSNR)
và lớp tệp (PBKDF2 + HMAC, bản mã bị sửa hoặc sai khóa sẽ bị từ chối trước khi giải mã).
"""
from __future__ import annotations

import os
import tempfile
import time

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
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

from core import AuthenticationError, decrypt_array, decrypt_file, encrypt_array, encrypt_file, load_image
from core.image_cipher import save_image
from core.keyderive import normalize_key
from metrics import image_metrics as im
from metrics.image_metrics import psnr
from .. import theme
from ..settings import last_dir, remember_dir
from ..widgets import ImageDropMixin, ImagePreview, PasswordField, TaskProgress
from ..workers import TaskRunner

DEFAULT_KEY = "day-la-mot-khoa-bi-mat-vi-du"
IMAGE_FILTER = "Ảnh (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;Tất cả tệp (*)"
ATTACKS = {
    "crop16": "Cắt mất 1/16 bản mã",
    "crop4": "Cắt mất 1/4 bản mã",
    "noise": "Nhiễu muối tiêu",
    "bitflip": "Sửa 1 bit bản mã",
    "wrongkey": "Giải mã bằng khóa sai",
    "black": "Mã hóa ảnh toàn đen",
    "white": "Mã hóa ảnh toàn trắng",
}
PLAIN = {"black": ("Ảnh toàn đen", 0), "white": ("Ảnh toàn trắng", 255)}


def wrong_password(password: str) -> str:
    return password[:-1] + chr(ord(password[-1]) ^ 1)


def apply_attack(enc: np.ndarray, kind: str, density: float) -> np.ndarray:
    out = enc.copy()
    height, width = out.shape[:2]
    if kind == "crop16":
        out[:height // 4, :width // 4] = 0
    elif kind == "crop4":
        out[:height // 2, :width // 2] = 0
    elif kind == "noise":
        rng = np.random.default_rng(1)
        mask = rng.random(out.shape) < density
        out[mask] = rng.choice(np.array([0, 255], dtype=np.uint8), size=int(mask.sum()))
    elif kind == "bitflip":
        out.reshape(-1)[out.size // 2] ^= 1
    return out


def file_layer(worker, source: str, password: str, kinds: list[str], density: float) -> dict:
    """Mã hóa tệp một lần, rồi thử từng kiểu tấn công lên bản sao của tệp mã hóa."""
    results = {}
    with tempfile.TemporaryDirectory(prefix="mordell_attack_") as folder:
        clean = os.path.join(folder, "goc.png")
        meta = encrypt_file(source, clean, password, tick=worker.check_cancelled)
        enc = load_image(clean)
        for kind in kinds:
            worker.check_cancelled()
            target = os.path.join(folder, f"{kind}.png")
            output = os.path.join(folder, f"{kind}_dec.png")
            save_image(enc if kind == "wrongkey" else apply_attack(enc, kind, density), target)
            with open(clean + ".meta", encoding="utf-8") as src, open(target + ".meta", "w", encoding="utf-8") as dst:
                dst.write(src.read())
            key = wrong_password(password) if kind == "wrongkey" else password
            try:
                decrypt_file(target, output, key, tick=worker.check_cancelled)
                message = "giải mã được"
                rejected = False
            except AuthenticationError as exc:
                message = str(exc)
                rejected = True
            results[kind] = {"rejected": rejected, "written": os.path.exists(output), "message": message}
    results["_iterations"] = meta["iterations"]
    return results


def attack_task(worker, source: str, password: str, kinds: list[str], density: float) -> dict:
    started = time.perf_counter()
    iv = bytes(16)
    worker.report(3, "Đang đọc ảnh...")
    image = load_image(source)
    worker.report(8, "Đang mã hóa ảnh (lớp mã hóa ảnh)...")
    enc = encrypt_array(image, password, iv, tick=worker.check_cancelled)
    wrong_key = bytearray(normalize_key(password))
    wrong_key[0] ^= 1

    rows = {}
    step = 50 / len(kinds)
    for i, kind in enumerate(kinds):
        worker.check_cancelled()
        worker.report(10 + int(i * step), f"Lớp mã hóa ảnh: {ATTACKS[kind].lower()}...")
        if kind in PLAIN:
            plain = np.full_like(image, PLAIN[kind][1])
            cipher = encrypt_array(plain, password, iv, tick=worker.check_cancelled)
            dec = decrypt_array(cipher, password, iv, plain.shape[0], tick=worker.check_cancelled)
            rows[kind] = {"plain": plain, "attacked": cipher, "decrypted": dec,
                          "psnr": psnr(plain, dec), "metrics": im.evaluate_image(cipher)}
            continue
        attacked = enc if kind == "wrongkey" else apply_attack(enc, kind, density)
        key = bytes(wrong_key) if kind == "wrongkey" else password
        dec = decrypt_array(attacked, key, iv, image.shape[0], tick=worker.check_cancelled)
        diff = dec != image
        blocks = np.flatnonzero(diff.reshape(-1)) // 16
        rows[kind] = {
            "attacked": attacked, "decrypted": dec, "psnr": psnr(image, dec),
            "changed": float(diff.mean() * 100), "changed_bytes": int(diff.sum()),
            "blocks": int(np.unique(blocks).size),
        }

    cipher_kinds = [k for k in kinds if k not in PLAIN]
    if cipher_kinds:
        worker.report(62, "Lớp tệp: dẫn xuất khóa PBKDF2 và kiểm tra HMAC...")
        files = file_layer(worker, source, password, cipher_kinds, density)
        for kind in cipher_kinds:
            rows[kind]["file"] = files[kind]
    worker.report(98, "Đang tổng hợp...")
    return {"image": image, "encrypted": enc, "rows": rows, "density": density,
            "report": format_report(rows, density, image), "elapsed": time.perf_counter() - started}


def describe(kind: str, density: float) -> str:
    return f"{ATTACKS[kind]} {density * 100:g}%" if kind == "noise" else ATTACKS[kind]


def format_report(rows: dict, density: float, image: np.ndarray) -> str:
    lines = []
    attacks = {k: r for k, r in rows.items() if k not in PLAIN}
    if attacks:
        lines += [f"{'Kiểu tấn công':<28}{'PSNR (dB)':>11}{'Byte sai':>11}   Lớp tệp (HMAC)", "-" * 78]
    for kind, row in attacks.items():
        value = "∞" if np.isinf(row["psnr"]) else f"{row['psnr']:.2f}"
        file_text = "TỪ CHỐI, không ghi tệp" if row["file"]["rejected"] and not row["file"]["written"] \
            else "giải mã được"
        changed = f"{row['changed']:.2f}%" if row["changed"] >= 0.01 else f"{row['changed_bytes']} byte"
        lines.append(f"{describe(kind, density):<28}{value:>11}{changed:>11}   {file_text}")
    if attacks:
        lines += ["", "PSNR và Byte sai: ảnh giải mã ở lớp mã hóa ảnh so với ảnh gốc "
                      f"({image.shape[1]}×{image.shape[0]}). PSNR ≈ 9 dB nghĩa là ảnh không còn nhận ra."]
    if "bitflip" in rows:
        row = rows["bitflip"]
        lines.append(f"Sửa 1 bit: {row['changed_bytes']} byte sai, nằm trong {row['blocks']} khối 16 byte "
                     "(khối bị sửa hỏng hoàn toàn, khối sau sai đúng 1 bit, do CBC). "
                     "Bằng mắt khó thấy, nhưng ở lớp tệp HMAC phát hiện ngay.")
    plains = {k: r for k, r in rows.items() if k in PLAIN}
    if plains:
        if attacks:
            lines.append("")
        lines += [f"BẢN RÕ CHỌN LỌC — ảnh một màu cùng kích thước {image.shape[1]}×{image.shape[0]}, cùng khóa",
                  f"{'Ảnh':<18}{'Entropy':>9}{'Chi-square':>12}{'TQ ngang':>10}{'TQ dọc':>9}{'TQ chéo':>9}   Giải mã",
                  "-" * 78]
        for kind, row in plains.items():
            m, c = row["metrics"], row["metrics"]["corr"]
            ok = "đúng" if np.isinf(row["psnr"]) else "SAI"
            lines.append(f"{PLAIN[kind][0]:<18}{m['entropy']:>9.4f}{m['chi2']:>12.2f}{c['horizontal']:>10.4f}"
                         f"{c['vertical']:>9.4f}{c['diagonal']:>9.4f}   {ok}")
        if len(plains) == 2:
            cmp = im.compare_images(plains["black"]["attacked"], plains["white"]["attacked"])
            lines.append(f"Bản mã ảnh đen so với bản mã ảnh trắng: NPCR = {cmp['NPCR']:.2f}%, UACI = {cmp['UACI']:.2f}%")
        lines.append(f"Ảnh gốc không có thông tin (entropy 0) nhưng bản mã vẫn có entropy ≈ 8, tương quan ≈ 0, "
                     f"histogram đều (chi-square < {im.CHI2_CRIT_255}). Đây là kiểm tra thống kê, "
                     "không phải chứng minh chống tấn công bản rõ chọn lọc.")
    return "\n".join(lines)


class AttackTab(ImageDropMixin, QWidget):
    """Thử các kiểu tấn công lên ảnh mã hóa và so sánh hai lớp: mã hóa ảnh và tệp."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending: dict | None = None
        self._last_result: dict | None = None
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
        row.addWidget(QLabel("Ảnh cần thử:"))
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText("Đường dẫn ảnh (png, jpg, bmp...) — hoặc kéo-thả ảnh vào cửa sổ")
        row.addWidget(self.input_path, 1)
        btn_browse = QPushButton("Chọn ảnh...")
        btn_browse.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        btn_browse.clicked.connect(self.browse_image)
        row.addWidget(btn_browse)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Mật khẩu:"))
        self.password = PasswordField(DEFAULT_KEY)
        row.addWidget(self.password, 1)
        row.addWidget(QLabel("Kiểu tấn công:"))
        self.attack_combo = QComboBox()
        for value, label in ATTACKS.items():
            self.attack_combo.addItem(label, value)
        self.attack_combo.currentIndexChanged.connect(self._on_attack_changed)
        row.addWidget(self.attack_combo)
        row.addWidget(QLabel("Mức nhiễu:"))
        self.density = QDoubleSpinBox()
        self.density.setRange(0.1, 50.0)
        self.density.setSingleStep(0.5)
        self.density.setDecimals(1)
        self.density.setValue(1.0)
        self.density.setSuffix(" %")
        self.density.setToolTip("Tỷ lệ byte của ảnh mã hóa bị đổi thành 0 hoặc 255")
        row.addWidget(self.density)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.btn_run = QPushButton("Tấn công")
        self.btn_run.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_run.clicked.connect(self.handle_run)
        theme.mark_primary(self.btn_run)
        row.addWidget(self.btn_run)
        self.btn_run_all = QPushButton("Chạy tất cả")
        self.btn_run_all.setToolTip("Chạy cả 7 kiểu tấn công và lập bảng tổng hợp")
        self.btn_run_all.clicked.connect(self.handle_run_all)
        row.addWidget(self.btn_run_all)
        row.addWidget(QLabel(
            "Lớp mã hóa ảnh: vẫn giải mã và đo PSNR. Lớp tệp: HMAC từ chối nếu bản mã bị sửa hoặc sai khóa."
        ), 1)
        layout.addLayout(row)

        self.progress = TaskProgress()
        self.progress.cancel_requested.connect(self.runner_cancel)
        layout.addWidget(self.progress)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(f"color: {theme.SUCCESS}; font-weight: bold;")
        self.result_label.setVisible(False)
        layout.addWidget(self.result_label)

        preview_panel = QWidget()
        previews = QHBoxLayout(preview_panel)
        previews.setContentsMargins(0, 0, 0, 0)
        previews.setSpacing(8)
        self.preview_original = ImagePreview("Ảnh gốc")
        self.preview_encrypted = ImagePreview("Bản mã bị tấn công")
        self.preview_decrypted = ImagePreview("Ảnh giải mã")
        for preview in (self.preview_original, self.preview_encrypted, self.preview_decrypted):
            previews.addWidget(preview, 1)

        self.report = QTextEdit()
        self.report.setReadOnly(True)
        self.report.setPlaceholderText("Kết quả tấn công sẽ hiện ở đây...")
        self.report.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        split = QSplitter(Qt.Orientation.Vertical)
        split.setChildrenCollapsible(False)
        split.addWidget(preview_panel)
        split.addWidget(self.report)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 2)
        split.setSizes([500, 240])
        layout.addWidget(split, 1)

        self.input_path.textChanged.connect(self._preview_input)
        self.password.returnPressed.connect(self.handle_run)
        self._on_attack_changed()
        self._init_image_drop()

    def runner_cancel(self) -> None:
        self.runner.cancel()

    def current_attack(self) -> str:
        return self.attack_combo.currentData()

    def _on_attack_changed(self) -> None:
        self.density.setEnabled(self.current_attack() == "noise")
        if self._last_result and self.current_attack() in self._last_result["rows"]:
            self._show_row(self.current_attack())

    def browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh", last_dir(), IMAGE_FILTER)
        if path:
            remember_dir(path)
            self.input_path.setText(path)

    def _preview_input(self) -> None:
        path = self.input_path.text().strip()
        if not path:
            self.preview_original.clear()
        elif os.path.isfile(path):
            self.preview_original.set_path(path)

    def _validated_source(self) -> str | None:
        source = self.input_path.text().strip()
        if not source:
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng chọn ảnh cần thử.")
            return None
        if not os.path.isfile(source):
            QMessageBox.critical(self, "Lỗi", f"Không tìm thấy ảnh: {source}")
            return None
        if not self.password.text():
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng nhập mật khẩu.")
            return None
        return source

    def handle_run(self) -> None:
        self._start([self.current_attack()])

    def handle_run_all(self) -> None:
        self._start(list(ATTACKS))

    def _start(self, kinds: list[str]) -> None:
        source = self._validated_source()
        if source is None or self.runner.busy():
            return
        self._pending = {"source": source, "key": self.password.text()}
        self._set_busy(True, "Đang tấn công...")
        if not self.runner.start(attack_task, source, self.password.text(), kinds,
                                 self.density.value() / 100):
            self._end_task()

    def _set_busy(self, busy: bool, message: str = "Đang xử lý...") -> None:
        self.btn_run.setEnabled(not busy)
        self.btn_run_all.setEnabled(not busy)
        window = self.window()
        if callable(getattr(window, "set_running", None)):
            window.set_running(busy)
        if busy:
            self.progress.start(message)
        else:
            self.progress.stop()

    def _end_task(self) -> None:
        self._pending = None
        self._set_busy(False)

    def _status(self, message: str) -> None:
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(message)

    def _on_task_done(self, result: dict) -> None:
        source = (self._pending or {}).get("source", "")
        try:
            self._last_result = result
            self.report.setPlainText(result["report"])
            kind = self.current_attack() if self.current_attack() in result["rows"] else next(iter(result["rows"]))
            self._show_row(kind)
            files = [r["file"] for r in result["rows"].values() if "file" in r]
            text = (f"✔ Đã thử {len(result['rows'])} kiểu tấn công lên {os.path.basename(source)} trong "
                    f"{result['elapsed']:.2f} s")
            if files:
                text += f" — lớp tệp từ chối {sum(f['rejected'] for f in files)}/{len(files)}"
            self.result_label.setText(text)
            self.result_label.setVisible(True)
            self._status(f"Đã tấn công: {os.path.basename(source)}")
        finally:
            self._end_task()

    def _show_row(self, kind: str) -> None:
        row = self._last_result["rows"][kind]
        density = self._last_result["density"]
        if "plain" in row:
            self.preview_original.set_array(row["plain"])
            self.preview_original.set_info(PLAIN[kind][0].lower())
        else:
            self.preview_original.set_array(self._last_result["image"])
            self.preview_original.set_info("")
        self.preview_encrypted.set_array(row["attacked"])
        self.preview_decrypted.set_array(row["decrypted"])
        value = "∞" if np.isinf(row["psnr"]) else f"{row['psnr']:.2f} dB"
        self.preview_encrypted.set_info(describe(kind, density))
        self.preview_decrypted.set_info(f"PSNR {value}")

    def _on_task_failed(self, message: str) -> None:
        self._end_task()
        QMessageBox.critical(self, "Lỗi", f"Không thể chạy tấn công: {message}")

    def _on_task_cancelled(self) -> None:
        self._end_task()
        self._status("Đã huỷ tác vụ")

    def shutdown(self) -> None:
        self.runner.shutdown()
