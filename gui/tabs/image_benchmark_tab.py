"""Tab benchmark chất lượng ảnh mã hóa."""
from __future__ import annotations

import os
import time

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import decrypt_array, encrypt_array, load_image, normalize_key
from metrics import image_metrics as im
from .. import theme
from ..export import APP_NAME, export_report, format_table, image_metric_pairs, timestamp
from ..settings import last_dir, remember_dir
from ..widgets import ImageDropMixin, ImagePreview, PasswordField, TaskProgress
from ..workers import TaskRunner

DEFAULT_KEY = "day-la-mot-khoa-bi-mat-vi-du"
IMAGE_FILTER = "Ảnh (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;Tất cả tệp (*)"


def benchmark_task(worker, source: str, key: str) -> dict:
    """Mã hóa/giải mã + tính toàn bộ chỉ số và độ nhạy (chạy ở luồng nền)."""
    total_started = time.perf_counter()
    iv = bytes(16)
    worker.report(3, "Đang đọc ảnh...")
    image = load_image(source)

    worker.check_cancelled()
    worker.report(10, "Đang mã hóa ảnh...")
    started = time.perf_counter()
    encrypted = encrypt_array(image, key, iv)
    encrypt_time = time.perf_counter() - started

    worker.check_cancelled()
    worker.report(28, "Đang giải mã và kiểm tra khôi phục...")
    started = time.perf_counter()
    decrypted = decrypt_array(encrypted, key, iv, image.shape[0])
    decrypt_time = time.perf_counter() - started
    roundtrip_ok = decrypted.shape == image.shape and bool((decrypted == image).all())

    worker.check_cancelled()
    worker.report(42, "Đang tính chỉ số ảnh gốc...")
    original_metrics = im.evaluate_image(image)
    worker.report(58, "Đang tính chỉ số ảnh mã hóa...")
    encrypted_metrics = im.evaluate_image(encrypted)

    worker.check_cancelled()
    worker.report(70, "Đang đo độ nhạy bản rõ...")
    changed = image.copy()
    changed.reshape(-1)[0] ^= 1
    changed_encrypted = encrypt_array(changed, key, iv)
    plaintext_sensitivity = im.compare_images(encrypted, changed_encrypted)

    worker.check_cancelled()
    worker.report(86, "Đang đo độ nhạy khóa...")
    wrong_key = bytearray(normalize_key(key))
    wrong_key[0] ^= 1
    key_changed_encrypted = encrypt_array(image, bytes(wrong_key), iv)
    key_sensitivity = im.compare_images(encrypted, key_changed_encrypted)

    worker.report(96, "Đang tổng hợp kết quả...")
    report = "\n".join([
        "ẢNH GỐC",
        im.format_report(original_metrics),
        "",
        "ẢNH MÃ HÓA",
        im.format_report(encrypted_metrics),
        "",
        "ĐỘ NHẠY",
        f"  Bản rõ (đổi 1 bit) : NPCR = {plaintext_sensitivity['NPCR']:.4f}%"
        f"   UACI = {plaintext_sensitivity['UACI']:.4f}%",
        f"  Khóa (đổi 1 bit)   : NPCR = {key_sensitivity['NPCR']:.4f}%"
        f"   UACI = {key_sensitivity['UACI']:.4f}%",
        "",
        f"Giải mã khôi phục đúng ảnh gốc: {'CÓ' if roundtrip_ok else 'KHÔNG'}",
        f"Thời gian: mã hóa {encrypt_time:.2f} s | giải mã {decrypt_time:.2f} s",
    ])
    return {
        "image": image, "encrypted": encrypted, "decrypted": decrypted,
        "changed_encrypted": changed_encrypted, "key_changed_encrypted": key_changed_encrypted,
        "plaintext_sensitivity": plaintext_sensitivity, "key_sensitivity": key_sensitivity,
        "original_metrics": original_metrics, "encrypted_metrics": encrypted_metrics,
        "encrypt_time": encrypt_time, "decrypt_time": decrypt_time,
        "roundtrip_ok": roundtrip_ok, "report": report,
        "elapsed": time.perf_counter() - total_started,
    }


def ecb_cbc_task(worker, source: str, key: str) -> dict:
    """Mã hóa cùng ảnh ở cả ECB và CBC để so sánh (chạy ở luồng nền)."""
    total_started = time.perf_counter()
    iv = bytes(16)
    worker.report(3, "Đang đọc ảnh...")
    image = load_image(source)

    worker.check_cancelled()
    worker.report(15, "Đang mã hóa chế độ ECB...")
    started = time.perf_counter()
    encrypted_ecb = encrypt_array(image, key, iv, mode="ecb")
    ecb_time = time.perf_counter() - started

    worker.check_cancelled()
    worker.report(55, "Đang mã hóa chế độ CBC...")
    started = time.perf_counter()
    encrypted_cbc = encrypt_array(image, key, iv, mode="cbc")
    cbc_time = time.perf_counter() - started

    worker.check_cancelled()
    worker.report(80, "Đang tính chỉ số hai bản mã...")
    ecb_metrics = im.evaluate_image(encrypted_ecb)
    cbc_metrics = im.evaluate_image(encrypted_cbc)
    difference = im.compare_images(encrypted_ecb, encrypted_cbc)

    report = "\n".join([
        "SO SÁNH ECB vs CBC (cùng ảnh, cùng khóa, cùng IV)",
        "",
        "ECB",
        im.format_report(ecb_metrics),
        "",
        "CBC",
        im.format_report(cbc_metrics),
        "",
        f"Khác biệt giữa hai bản mã: NPCR = {difference['NPCR']:.2f}%"
        f"   UACI = {difference['UACI']:.2f}%",
        f"Thời gian: ECB {ecb_time:.2f} s | CBC {cbc_time:.2f} s",
        "",
        "ECB mã hóa từng khối độc lập nên các vùng đồng màu của ảnh gốc vẫn lộ rõ",
        "trong bản mã; CBC dùng IV và móc xích các khối nên che cấu trúc tốt hơn.",
    ])
    return {"ecb": encrypted_ecb, "cbc": encrypted_cbc, "report": report,
            "ecb_metrics": ecb_metrics, "cbc_metrics": cbc_metrics,
            "difference": difference, "ecb_time": ecb_time, "cbc_time": cbc_time,
            "elapsed": time.perf_counter() - total_started}


class ImageBenchmarkTab(ImageDropMixin, QWidget):
    """Mã hóa một ảnh và hiển thị các chỉ số entropy, tương quan, NPCR, UACI..."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pending: dict | None = None
        self._last_benchmark: dict | None = None
        self._last_ecb_cbc: dict | None = None
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
        row.addWidget(QLabel("Ảnh cần đánh giá:"))
        self.input_path = QLineEdit()
        self.input_path.setPlaceholderText(
            "Đường dẫn ảnh (png, jpg, bmp...) — hoặc kéo-thả ảnh vào cửa sổ"
        )
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
        layout.addLayout(row)

        row = QHBoxLayout()
        self.btn_run = QPushButton("Đánh giá ảnh mã hóa")
        self.btn_run.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_run.clicked.connect(self.handle_run)
        theme.mark_primary(self.btn_run)
        row.addWidget(self.btn_run)
        self.btn_export = QPushButton("Xuất báo cáo...")
        self.btn_export.setToolTip("Xuất chỉ số ảnh ra TXT/CSV/JSON")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.handle_export)
        row.addWidget(self.btn_export)
        self.btn_copy = QPushButton("Sao chép chỉ số")
        self.btn_copy.setToolTip("Sao chép bảng chỉ số dạng TSV để dán vào Excel/báo cáo")
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self.handle_copy)
        row.addWidget(self.btn_copy)
        row.addWidget(QLabel(
            "Tính entropy, tương quan, GLCM, NPCR/UACI và kiểm tra giải mã."
        ), 1)
        layout.addLayout(row)

        self.progress = TaskProgress()
        self.progress.cancel_requested.connect(self._cancel_task)
        layout.addWidget(self.progress)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(f"color: {theme.SUCCESS}; font-weight: bold;")
        self.result_label.setVisible(False)
        layout.addWidget(self.result_label)

        self.result_tabs = QTabWidget()

        summary = QWidget()
        summary_layout = QVBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        preview_panel = QWidget()
        previews = QHBoxLayout(preview_panel)
        previews.setContentsMargins(0, 0, 0, 0)
        previews.setSpacing(8)
        self.preview_original = ImagePreview("Ảnh gốc")
        self.preview_encrypted = ImagePreview("Ảnh mã hóa")
        self.preview_decrypted = ImagePreview("Ảnh giải mã")
        for preview in (self.preview_original, self.preview_encrypted, self.preview_decrypted):
            previews.addWidget(preview, 1)

        self.report = QTextEdit()
        self.report.setReadOnly(True)
        self.report.setPlaceholderText("Kết quả chỉ số đánh giá ảnh sẽ hiện ở đây...")
        self.report.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        summary_split = QSplitter(Qt.Orientation.Vertical)
        summary_split.setChildrenCollapsible(False)
        summary_split.addWidget(preview_panel)
        summary_split.addWidget(self.report)
        summary_split.setStretchFactor(0, 4)
        summary_split.setStretchFactor(1, 2)
        summary_split.setSizes([500, 240])
        summary_layout.addWidget(summary_split, 1)

        charts = QWidget()
        charts_layout = QVBoxLayout(charts)
        self.figure = Figure(figsize=(7.5, 5.0), dpi=100)
        self.figure.text(0.5, 0.5, "Chạy đánh giá ảnh để xem biểu đồ...",
                         ha="center", va="center", color=theme.PLACEHOLDER)
        self.canvas = FigureCanvasQTAgg(self.figure)
        toolbar = NavigationToolbar2QT(self.canvas, charts)
        charts_layout.addWidget(toolbar)
        charts_layout.addWidget(self.canvas, 1)

        ecb_cbc = QWidget()
        ecb_cbc_layout = QVBoxLayout(ecb_cbc)
        ecb_cbc_layout.setContentsMargins(0, 0, 0, 0)
        ecb_row = QHBoxLayout()
        self.btn_ecb_cbc = QPushButton("So sánh ECB vs CBC")
        self.btn_ecb_cbc.clicked.connect(self.handle_ecb_cbc)
        ecb_row.addWidget(self.btn_ecb_cbc)
        self.btn_export_ecb = QPushButton("Xuất kết quả...")
        self.btn_export_ecb.setToolTip("Xuất chỉ số ECB vs CBC ra TXT/CSV/JSON")
        self.btn_export_ecb.setEnabled(False)
        self.btn_export_ecb.clicked.connect(self.handle_export_ecb_cbc)
        ecb_row.addWidget(self.btn_export_ecb)
        ecb_row.addWidget(QLabel(
            "Mã hóa cùng một ảnh ở cả hai chế độ — ECB để lộ cấu trúc ảnh, CBC thì không."
        ), 1)
        ecb_cbc_layout.addLayout(ecb_row)

        ecb_vis = QWidget()
        ecb_vis_layout = QVBoxLayout(ecb_vis)
        ecb_vis_layout.setContentsMargins(0, 0, 0, 0)
        ecb_vis_layout.setSpacing(6)

        ecb_previews = QHBoxLayout()
        ecb_previews.setSpacing(8)
        self.preview_ecb = ImagePreview("Mã hóa ECB")
        self.preview_cbc = ImagePreview("Mã hóa CBC")
        for preview in (self.preview_ecb, self.preview_cbc):
            ecb_previews.addWidget(preview, 1)
        ecb_vis_layout.addLayout(ecb_previews, 3)

        self.ecb_cbc_figure = Figure(figsize=(7.5, 2.6), dpi=100, layout="constrained")
        self.ecb_cbc_figure.text(0.5, 0.5, "Bấm “So sánh ECB vs CBC” để xem histogram...",
                                 ha="center", va="center", color=theme.NOTE)
        self.ecb_cbc_canvas = FigureCanvasQTAgg(self.ecb_cbc_figure)
        ecb_vis_layout.addWidget(self.ecb_cbc_canvas, 2)

        self.ecb_cbc_report = QTextEdit()
        self.ecb_cbc_report.setReadOnly(True)
        self.ecb_cbc_report.setPlaceholderText("Chỉ số của hai bản mã ECB và CBC hiện ở đây...")
        self.ecb_cbc_report.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))

        ecb_split = QSplitter(Qt.Orientation.Vertical)
        ecb_split.setChildrenCollapsible(False)
        ecb_split.addWidget(ecb_vis)
        ecb_split.addWidget(self.ecb_cbc_report)
        ecb_split.setStretchFactor(0, 6)
        ecb_split.setStretchFactor(1, 1)
        ecb_split.setSizes([700, 160])
        ecb_cbc_layout.addWidget(ecb_split, 1)

        sensitivity = QWidget()
        sens_layout = QVBoxLayout(sensitivity)
        self.sens_figure = Figure(figsize=(7.5, 3.2), dpi=100, layout="constrained")
        self.sens_figure.text(0.5, 0.5, "Chạy đánh giá để xem bản đồ sai khác...",
                              ha="center", va="center", color=theme.PLACEHOLDER)
        self.sens_canvas = FigureCanvasQTAgg(self.sens_figure)
        sens_toolbar = NavigationToolbar2QT(self.sens_canvas, sensitivity)
        sens_layout.addWidget(sens_toolbar)
        sens_layout.addWidget(self.sens_canvas, 1)
        self.sens_note = QLabel(
            "Bản đồ sai khác giữa hai bản mã khi đổi 1 bit bản rõ (trái) và 1 bit khóa (phải)."
        )
        self.sens_note.setWordWrap(True)
        sens_layout.addWidget(self.sens_note)

        self.result_tabs.addTab(summary, "Ảnh & chỉ số")
        self.result_tabs.addTab(charts, "Biểu đồ")
        self.result_tabs.addTab(ecb_cbc, "ECB vs CBC")
        self.result_tabs.addTab(sensitivity, "Độ nhạy")
        layout.addWidget(self.result_tabs, 1)
        self.input_path.textChanged.connect(self._preview_input)
        self.password.returnPressed.connect(self.handle_run)
        self._init_image_drop()

    def _status(self, message: str) -> None:
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(message)
        if callable(getattr(window, "refresh_menu", None)):
            window.refresh_menu()

    def _set_busy(self, busy: bool, message: str = "Đang xử lý...") -> None:
        self.btn_run.setEnabled(not busy)
        self.btn_ecb_cbc.setEnabled(not busy)
        window = self.window()
        if callable(getattr(window, "set_running", None)):
            window.set_running(busy)
        if busy:
            self.progress.start(message)
        else:
            self.progress.stop()

    @staticmethod
    def _plot_histogram(ax, image: np.ndarray, title: str) -> None:
        counts = np.arange(256)
        if image.ndim == 2:
            ax.plot(counts, np.bincount(image.ravel(), minlength=256),
                    color="#444444", lw=1.0)
        else:
            for channel, color in enumerate(("#d03b3b", "#008300", "#2a78d6")[:image.shape[2]]):
                ax.plot(counts, np.bincount(image[..., channel].ravel(), minlength=256),
                        color=color, lw=1.0, label="RGB"[channel])
            ax.legend(frameon=False, fontsize=8, ncol=3)
        ax.set_title(title, fontsize=10)
        ax.set_xlim(0, 255)
        ax.set_xlabel("Giá trị điểm ảnh", fontsize=8)
        ax.set_ylabel("Tần suất", fontsize=8)
        ax.grid(alpha=0.2)

    @staticmethod
    def _plot_correlation(ax, image: np.ndarray, title: str, color: str) -> None:
        gray = image if image.ndim == 2 else image[..., 0]
        height, width = gray.shape
        if height < 1 or width < 2:
            return
        rng = np.random.default_rng(7)
        ys = rng.integers(0, height, 3000)
        xs = rng.integers(0, width - 1, 3000)
        ax.scatter(gray[ys, xs], gray[ys, xs + 1], s=2, color=color, alpha=0.5,
                   linewidths=0)
        ax.set_title(title, fontsize=10)
        ax.set_xlim(0, 255)
        ax.set_ylim(0, 255)
        ax.set_xlabel("p(x, y)", fontsize=8)
        ax.set_ylabel("p(x, y+1)", fontsize=8)
        ax.grid(alpha=0.2)

    def _update_charts(self, original: np.ndarray, encrypted: np.ndarray) -> None:
        self.figure.clear()
        axes = self.figure.subplots(2, 2)
        self._plot_histogram(axes[0, 0], original, "Histogram — ảnh gốc")
        self._plot_histogram(axes[0, 1], encrypted, "Histogram — ảnh mã hóa")
        self._plot_correlation(axes[1, 0], original, "Tương quan ngang — ảnh gốc", "#2a78d6")
        self._plot_correlation(axes[1, 1], encrypted, "Tương quan ngang — ảnh mã hóa",
                               "#e08a2a")
        self.figure.tight_layout()
        self.canvas.draw_idle()

    @staticmethod
    def _difference_map(first: np.ndarray, second: np.ndarray) -> np.ndarray:
        """Ảnh sai khác tuyệt đối; ảnh màu lấy sai khác lớn nhất trong 3 kênh."""
        diff = np.abs(first.astype(np.int16) - second.astype(np.int16))
        return diff.max(axis=2) if diff.ndim == 3 else diff

    def _plot_mode_histograms(self, ecb: np.ndarray, cbc: np.ndarray) -> None:
        self.ecb_cbc_figure.clear()
        axes = self.ecb_cbc_figure.subplots(1, 2)
        self._plot_histogram(axes[0], ecb, "Histogram — ECB")
        self._plot_histogram(axes[1], cbc, "Histogram — CBC")
        self.ecb_cbc_canvas.draw_idle()

    def _update_sensitivity_charts(self, encrypted: np.ndarray, plaintext_changed: np.ndarray,
                                  key_changed: np.ndarray, plaintext_sens: dict,
                                  key_sens: dict) -> None:
        diff_plaintext = self._difference_map(encrypted, plaintext_changed)
        diff_key = self._difference_map(encrypted, key_changed)

        self.sens_figure.clear()
        axes = self.sens_figure.subplots(1, 2)
        panels = (
            (axes[0], diff_plaintext, "Đổi 1 bit bản rõ", plaintext_sens),
            (axes[1], diff_key, "Đổi 1 bit khóa", key_sens),
        )
        image = None
        for ax, diff, title, sens in panels:
            image = ax.imshow(diff, cmap="hot", vmin=0, vmax=255,
                              interpolation="nearest", aspect="equal")
            ax.set_title(f"{title}\nNPCR = {sens['NPCR']:.2f}%  |  UACI = {sens['UACI']:.2f}%",
                         fontsize=9)
            ax.set_xticks([])
            ax.set_yticks([])
        if image is not None:
            self.sens_figure.colorbar(image, ax=list(axes), fraction=0.03, pad=0.02,
                                      label="|Δ điểm ảnh|")
        self.sens_canvas.draw_idle()

        self.sens_note.setText(
            f"Càng sáng nghĩa là điểm ảnh thay đổi càng nhiều. Bản rõ: NPCR = "
            f"{plaintext_sens['NPCR']:.2f}%, UACI = {plaintext_sens['UACI']:.2f}% — "
            f"Khóa: NPCR = {key_sens['NPCR']:.2f}%, UACI = {key_sens['UACI']:.2f}%. "
            "Bản đồ kín đặc (gần như nhiễu trắng) chứng tỏ hiệu ứng tuyết lở tốt."
        )

    def browse_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn ảnh", last_dir(), IMAGE_FILTER)
        if path:
            remember_dir(path)
            self.input_path.setText(path)

    def _preview_input(self) -> None:
        """Xem trước ảnh ngay khi chọn hoặc kéo-thả."""
        path = self.input_path.text().strip()
        if not path:
            self.preview_original.clear()
            return
        if os.path.isfile(path):
            self.preview_original.set_path(path)

    def _validated_source(self) -> str | None:
        source = self.input_path.text().strip()
        if not source:
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng chọn ảnh cần đánh giá.")
            return None
        if not os.path.isfile(source):
            QMessageBox.critical(self, "Lỗi", f"Không tìm thấy ảnh: {source}")
            return None
        if not self.password.text():
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng nhập mật khẩu.")
            return None
        return source

    def _start_task(self, kind: str, message: str, func, *args) -> None:
        if self.runner.busy():
            return
        self._pending = {"kind": kind}
        self._set_busy(True, message)
        if not self.runner.start(func, *args):
            self._end_task()

    def _cancel_task(self) -> None:
        self.runner.cancel()

    def _end_task(self) -> None:
        self._pending = None
        self._set_busy(False)

    def _on_task_done(self, result: dict) -> None:
        kind = (self._pending or {}).get("kind")
        try:
            if kind == "benchmark":
                self._apply_benchmark(result)
            elif kind == "ecb_cbc":
                self._apply_ecb_cbc(result)
        finally:
            self._end_task()

    def _on_task_failed(self, message: str) -> None:
        kind = (self._pending or {}).get("kind")
        self._end_task()
        if kind == "ecb_cbc":
            self.ecb_cbc_report.clear()
            QMessageBox.critical(self, "Lỗi", f"Không thể so sánh ECB/CBC: {message}")
        else:
            self.report.clear()
            QMessageBox.critical(self, "Lỗi", f"Không thể đánh giá ảnh: {message}")

    def _on_task_cancelled(self) -> None:
        self._end_task()
        self._status("Đã huỷ tác vụ")

    def shutdown(self) -> None:
        self.runner.shutdown()

    def _apply_benchmark(self, result: dict) -> None:
        source = self.input_path.text().strip()
        self._last_benchmark = {"result": result, "source": source,
                                "key": self.password.text()}
        self.btn_export.setEnabled(True)
        self.btn_copy.setEnabled(True)
        self.report.setPlainText(result["report"])
        self.preview_original.set_array(result["image"])
        self.preview_encrypted.set_array(result["encrypted"])
        self.preview_decrypted.set_array(result["decrypted"])
        self._update_charts(result["image"], result["encrypted"])
        self._update_sensitivity_charts(
            result["encrypted"], result["changed_encrypted"],
            result["key_changed_encrypted"],
            result["plaintext_sensitivity"], result["key_sensitivity"],
        )
        self.result_label.setText(
            f"✔ Đã đánh giá {os.path.basename(source)} trong {result['elapsed']:.2f} s"
        )
        self.result_label.setVisible(True)
        self._status(f"Đã đánh giá: {os.path.basename(source)}")

    def _apply_ecb_cbc(self, result: dict) -> None:
        source = self.input_path.text().strip()
        self._last_ecb_cbc = {"result": result, "source": source,
                              "key": self.password.text()}
        self.btn_export_ecb.setEnabled(True)
        self.ecb_cbc_report.setPlainText(result["report"])
        self.preview_ecb.set_array(result["ecb"])
        self.preview_cbc.set_array(result["cbc"])
        self._plot_mode_histograms(result["ecb"], result["cbc"])
        self.result_label.setText(
            f"✔ Đã so sánh ECB vs CBC trong {result['elapsed']:.2f} s"
            f" — NPCR giữa hai bản mã {result['difference']['NPCR']:.2f}%"
        )
        self.result_label.setVisible(True)
        self._status(f"Đã so sánh ECB vs CBC: {os.path.basename(source)}")

    def _benchmark_table(self) -> tuple[list[str], list[list[str]]]:
        """Bảng (tiêu đề, dòng) dùng chung cho xuất báo cáo và sao chép."""
        result = self._last_benchmark["result"]
        pairs_original = image_metric_pairs(result["original_metrics"])
        pairs_encrypted = image_metric_pairs(result["encrypted_metrics"])
        plaintext_sens = result["plaintext_sensitivity"]
        key_sens = result["key_sensitivity"]
        roundtrip = "CÓ" if result["roundtrip_ok"] else "KHÔNG"

        rows = [[name, original, encrypted]
                for (name, original), (_, encrypted) in zip(pairs_original, pairs_encrypted)]
        rows += [
            ["NPCR (đổi 1 bit bản rõ)", "", f"{plaintext_sens['NPCR']:.4f}"],
            ["UACI (đổi 1 bit bản rõ)", "", f"{plaintext_sens['UACI']:.4f}"],
            ["NPCR (đổi 1 bit khóa)", "", f"{key_sens['NPCR']:.4f}"],
            ["UACI (đổi 1 bit khóa)", "", f"{key_sens['UACI']:.4f}"],
            ["Giải mã khôi phục đúng", "", roundtrip],
            ["Thời gian mã hóa (s)", "", f"{result['encrypt_time']:.3f}"],
            ["Thời gian giải mã (s)", "", f"{result['decrypt_time']:.3f}"],
        ]
        return ["Chỉ số", "Ảnh gốc", "Ảnh mã hóa"], rows

    def handle_copy(self) -> None:
        """Sao chép bảng chỉ số dạng TSV để dán vào Excel/báo cáo."""
        if not self._last_benchmark:
            QMessageBox.information(
                self, "Chưa có dữ liệu",
                "Hãy chạy “Đánh giá ảnh mã hóa” trước khi sao chép chỉ số."
            )
            return
        header, rows = self._benchmark_table()
        lines = ["\t".join(header)]
        lines += ["\t".join(str(cell) for cell in row) for row in rows]
        QApplication.clipboard().setText("\n".join(lines))
        self._status("Đã sao chép bảng chỉ số vào clipboard")

    def handle_export(self) -> bool:
        data = self._last_benchmark
        if not data:
            QMessageBox.information(
                self, "Chưa có dữ liệu",
                "Hãy chạy “Đánh giá ảnh mã hóa” trước khi xuất báo cáo."
            )
            return

        result = data["result"]
        plaintext_sens = result["plaintext_sensitivity"]
        key_sens = result["key_sensitivity"]
        header, rows = self._benchmark_table()
        text = "\n".join([
            APP_NAME,
            "BÁO CÁO ĐÁNH GIÁ ẢNH MÃ HÓA",
            f"Xuất lúc: {timestamp()}",
            f"Ảnh: {data['source']}",
            f"Khóa: {data['key']}",
            "Chế độ: CBC",
            "",
            format_table(header, rows),
        ])
        payload = {
            "phan_mem": APP_NAME,
            "loai": "benchmark_anh",
            "thoi_gian_xuat": timestamp(),
            "anh": data["source"],
            "khoa": data["key"],
            "che_do": "cbc",
            "chi_so_anh_goc": result["original_metrics"],
            "chi_so_anh_ma_hoa": result["encrypted_metrics"],
            "do_nhay": {"ban_ro": plaintext_sens, "khoa": key_sens},
            "khoi_phuc_dung": result["roundtrip_ok"],
            "thoi_gian_chay": {
                "ma_hoa": result["encrypt_time"],
                "giai_ma": result["decrypt_time"],
            },
        }
        return export_report(self, "danh_gia_anh", text=text,
                             csv_data=(header, rows), payload=payload)

    def handle_export_ecb_cbc(self) -> bool:
        data = self._last_ecb_cbc
        if not data:
            QMessageBox.information(
                self, "Chưa có dữ liệu",
                "Hãy chạy “So sánh ECB vs CBC” trước khi xuất kết quả."
            )
            return

        result = data["result"]
        pairs_ecb = image_metric_pairs(result["ecb_metrics"])
        pairs_cbc = image_metric_pairs(result["cbc_metrics"])
        rows = [[name, ecb, cbc]
                for (name, ecb), (_, cbc) in zip(pairs_ecb, pairs_cbc)]
        header = ["Chỉ số", "ECB", "CBC"]
        difference = result["difference"]
        delta = (f"Khác biệt giữa hai bản mã: NPCR = {difference['NPCR']:.2f}%, "
                 f"UACI = {difference['UACI']:.2f}%")
        text = "\n".join([
            APP_NAME,
            "BÁO CÁO SO SÁNH ECB vs CBC",
            f"Xuất lúc: {timestamp()}",
            f"Ảnh: {data['source']}",
            f"Khóa: {data['key']}",
            "",
            format_table(header, rows),
            "",
            delta,
            f"Thời gian: ECB {result['ecb_time']:.2f} s | CBC {result['cbc_time']:.2f} s",
            "",
            "ECB mã hóa từng khối độc lập nên để lộ cấu trúc ảnh; CBC dùng IV và móc xích",
            "các khối nên che cấu trúc tốt hơn.",
        ])
        payload = {
            "phan_mem": APP_NAME,
            "loai": "so_sanh_ecb_cbc",
            "thoi_gian_xuat": timestamp(),
            "anh": data["source"],
            "khoa": data["key"],
            "chi_so_ecb": result["ecb_metrics"],
            "chi_so_cbc": result["cbc_metrics"],
            "khac_biet": difference,
            "thoi_gian_chay": {"ecb": result["ecb_time"], "cbc": result["cbc_time"]},
        }
        return export_report(self, "so_sanh_ecb_cbc", text=text,
                             csv_data=(header, rows), payload=payload)

    def handle_run(self) -> None:
        if self.runner.busy():
            return
        source = self._validated_source()
        if source is None:
            return
        self._start_task("benchmark", "Đang đánh giá ảnh...",
                         benchmark_task, source, self.password.text())

    def handle_ecb_cbc(self) -> None:
        if self.runner.busy():
            return
        source = self._validated_source()
        if source is None:
            return
        self._start_task("ecb_cbc", "Đang mã hóa ECB và CBC...",
                         ecb_cbc_task, source, self.password.text())

