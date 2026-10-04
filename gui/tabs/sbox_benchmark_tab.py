"""Tab benchmark chất lượng S-box."""
from __future__ import annotations

import time

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import DEGREE_8_IRREDUCIBLES, build_sbox, key_to_polynomial, poly_to_str, properties
from metrics import sbox_metrics as sm
from reference import REFERENCE_SBOXES
from .. import theme
from ..export import APP_NAME, export_report, format_table, timestamp

DEFAULT_KEY = "day-la-mot-khoa-bi-mat-vi-du"
REFERENCE_NAMES = {"aes": "AES", "weierstrass": "Weierstrass", "chaos": "Hỗn loạn"}


class SboxBenchmarkTab(QWidget):
    """Bảng thế S-box 16x16 và các chỉ số NL, SAC, BIC, LAP, DAP."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_sbox: list[int] | None = None
        self._last_result: dict | None = None
        self._last_title = ""
        self._build_ui()
        self._sync_controls()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        row = QHBoxLayout()
        row.addWidget(QLabel("Nguồn S-box:"))
        self.source_combo = QComboBox()
        self.source_combo.addItem("Mordell — từ khóa", "key")
        self.source_combo.addItem("Mordell — theo đa thức", "poly")
        for name in ("aes", "weierstrass", "chaos"):
            self.source_combo.addItem(f"{REFERENCE_NAMES[name]} (tham chiếu)", ("ref", name))
        self.source_combo.currentIndexChanged.connect(self._sync_controls)
        row.addWidget(self.source_combo, 1)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("Khóa:"))
        self.key_edit = QLineEdit(DEFAULT_KEY)
        self.key_edit.setPlaceholderText("Khóa bí mật dùng để dẫn xuất đa thức f(x)")
        row.addWidget(self.key_edit, 1)
        row.addWidget(QLabel("Đa thức bậc 8:"))
        self.poly_combo = QComboBox()
        for poly in DEGREE_8_IRREDUCIBLES:
            self.poly_combo.addItem(f"0x{poly:03X}   {poly_to_str(poly)}", poly)
        index = self.poly_combo.findData(0x11B)
        if index >= 0:
            self.poly_combo.setCurrentIndex(index)
        row.addWidget(self.poly_combo, 1)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.btn_run = QPushButton("Chạy Benchmark S-box")
        self.btn_run.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_run.clicked.connect(self.handle_run)
        theme.mark_primary(self.btn_run)
        row.addWidget(self.btn_run)
        self.btn_export = QPushButton("Xuất kết quả...")
        self.btn_export.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.btn_export.setToolTip("Xuất chỉ số và bảng S-box ra TXT/CSV/JSON")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.handle_export)
        row.addWidget(self.btn_export)
        self.info_label = QLabel("Chọn nguồn S-box rồi bấm chạy để xem chỉ số.")
        self.info_label.setWordWrap(True)
        row.addWidget(self.info_label, 1)
        layout.addLayout(row)

        tables = QSplitter(Qt.Orientation.Horizontal)
        tables.setChildrenCollapsible(False)

        group_sbox = QGroupBox("Bảng thế S-box (16x16)")
        group_sbox_layout = QVBoxLayout(group_sbox)

        table_controls = QHBoxLayout()
        table_controls.addWidget(QLabel("Định dạng:"))
        self.format_combo = QComboBox()
        self.format_combo.addItem("Hex (00–FF)", "hex")
        self.format_combo.addItem("Thập phân (0–255)", "dec")
        self.format_combo.currentIndexChanged.connect(self._refresh_sbox_table)
        table_controls.addWidget(self.format_combo)
        table_controls.addStretch(1)
        self.btn_copy = QPushButton("Sao chép bảng")
        self.btn_copy.setToolTip("Sao chép dạng bảng TSV để dán vào Excel/báo cáo")
        self.btn_copy.clicked.connect(self.handle_copy)
        table_controls.addWidget(self.btn_copy)
        group_sbox_layout.addLayout(table_controls)

        self.sbox_table = QTableWidget(16, 16)
        self.sbox_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sbox_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.sbox_table.setHorizontalHeaderLabels([f"{c:X}" for c in range(16)])
        self.sbox_table.setVerticalHeaderLabels([f"{r:X}" for r in range(16)])
        self.sbox_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sbox_table.verticalHeader().setDefaultSectionSize(24)
        group_sbox_layout.addWidget(self.sbox_table)

        group_metrics = QGroupBox("Chỉ số đánh giá")
        group_metrics_layout = QVBoxLayout(group_metrics)
        self.metrics_table = QTableWidget(0, 2)
        self.metrics_table.setHorizontalHeaderLabels(["Chỉ số", "Giá trị"])
        self.metrics_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.metrics_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        header = self.metrics_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.metrics_table.verticalHeader().setVisible(False)
        group_metrics_layout.addWidget(self.metrics_table)

        tables.addWidget(group_sbox)
        tables.addWidget(group_metrics)
        tables.setStretchFactor(0, 3)
        tables.setStretchFactor(1, 2)
        tables.setSizes([620, 420])
        layout.addWidget(tables, 1)

    def _sync_controls(self) -> None:
        data = self.source_combo.currentData()
        self.key_edit.setEnabled(data == "key")
        self.poly_combo.setEnabled(data == "poly")

    def _status(self, message: str) -> None:
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(message)
        if callable(getattr(window, "refresh_menu", None)):
            window.refresh_menu()

    def _current_sbox(self) -> tuple[str, list[int]]:
        data = self.source_combo.currentData()
        if data == "key":
            key = self.key_edit.text()
            if not key:
                raise ValueError("Vui lòng nhập khóa bí mật.")
            poly = key_to_polynomial(key)
            return (f"Mordell từ khóa — f(x) = {poly_to_str(poly)} (0x{poly:03X})",
                    build_sbox(key=key))
        if data == "poly":
            poly = int(self.poly_combo.currentData())
            return (f"Mordell theo đa thức — f(x) = {poly_to_str(poly)} (0x{poly:03X})",
                    build_sbox(poly=poly))
        _, name = data
        return f"S-box tham chiếu: {REFERENCE_NAMES[name]}", REFERENCE_SBOXES[name]()

    def _fill_sbox_table(self, sbox: list[int]) -> None:
        self._last_sbox = list(sbox)
        hexa = self.format_combo.currentData() == "hex"
        for r in range(16):
            for c in range(16):
                value = sbox[r * 16 + c]
                item = QTableWidgetItem(f"{value:02X}" if hexa else str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.sbox_table.setItem(r, c, item)

    def _refresh_sbox_table(self) -> None:
        if self._last_sbox is not None:
            self._fill_sbox_table(self._last_sbox)

    def handle_copy(self) -> None:
        if self._last_sbox is None:
            QMessageBox.information(self, "Chưa có dữ liệu",
                                    "Hãy chạy benchmark trước khi sao chép bảng S-box.")
            return
        hexa = self.format_combo.currentData() == "hex"
        fmt = (lambda v: f"{v:02X}") if hexa else str
        lines = ["\t" + "\t".join(f"{c:X}" for c in range(16))]
        for r in range(16):
            row = self._last_sbox[r * 16:(r + 1) * 16]
            lines.append(f"{r:X}\t" + "\t".join(fmt(v) for v in row))
        QApplication.clipboard().setText("\n".join(lines))
        self._status("Đã sao chép bảng S-box 16×16 vào clipboard")

    def _fill_metrics_table(self, sbox: list[int], result: dict) -> None:
        rows = self._metric_rows(sbox, result)
        self.metrics_table.setRowCount(len(rows))
        for row, (name, value) in enumerate(rows):
            name_item = QTableWidgetItem(name)
            value_item = QTableWidgetItem(value)
            self.metrics_table.setItem(row, 0, name_item)
            self.metrics_table.setItem(row, 1, value_item)

    @staticmethod
    def _metric_rows(sbox: list[int], result: dict) -> list[tuple[str, str]]:
        props = properties(sbox)
        return [
            ("Song ánh", "Có" if props["bijective"] else "Không"),
            ("Tự nghịch đảo", "Có" if props["involution"] else "Không"),
            ("Điểm bất động", str(len(props["fixed_points"]))),
            ("NL (phi tuyến)", f"{result['NL']}   (tối ưu 112)"),
            ("SAC trung bình",
             f"{result['SAC_avg']:.4f}   (lý tưởng 0.5; lệch max {result['SAC_max_dev']:.4f})"),
            ("BIC-NL trung bình",
             f"{result['BIC_NL_avg']:.2f}   (min {result['BIC_NL_min']})"),
            ("BIC-SAC", f"{result['BIC_SAC']:.4f}   (lý tưởng 0.5)"),
            ("LAP", f"{result['LAP']:.4f}   (tối ưu 0.0625)"),
            ("DAP", f"{result['DAP']:.4f} = {result['DAP_count']}/256   (tối ưu 4/256)"),
        ]

    def handle_export(self) -> bool:
        if self._last_sbox is None or self._last_result is None:
            QMessageBox.information(self, "Chưa có dữ liệu",
                                    "Hãy chạy benchmark trước khi xuất báo cáo.")
            return

        sbox, result = self._last_sbox, self._last_result
        props = properties(sbox)
        rows = [list(row) for row in self._metric_rows(sbox, result)]
        sbox_table = format_table(
            ["#"] + [f"{c:X}" for c in range(16)],
            [[f"{r:X}"] + [f"{sbox[r * 16 + c]:02X}" for c in range(16)] for r in range(16)],
        )
        text = "\n".join([
            APP_NAME,
            "BÁO CÁO ĐÁNH GIÁ S-BOX",
            f"Xuất lúc: {timestamp()}",
            f"Nguồn: {self._last_title}",
            "",
            "CHỈ SỐ",
            format_table(["Chỉ số", "Giá trị"], rows),
            "",
            "BẢNG S-BOX (HEX)",
            sbox_table,
        ])
        payload = {
            "phan_mem": APP_NAME,
            "loai": "sbox_benchmark",
            "thoi_gian": timestamp(),
            "nguon": self._last_title,
            "sbox": sbox,
            "chi_so": result,
            "thuoc_tinh": {
                "song_anh": props["bijective"],
                "tu_nghich_dao": props["involution"],
                "diem_bat_dong": props["fixed_points"],
            },
        }
        return export_report(self, "danh_gia_sbox", text=text,
                             csv_data=(["Chỉ số", "Giá trị"], rows), payload=payload)

    def handle_run(self) -> None:
        self.btn_run.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            title, sbox = self._current_sbox()
            self.info_label.setText(f"{title} — đang tính chỉ số...")
            self._fill_sbox_table(sbox)
            QApplication.processEvents()

            started = time.perf_counter()
            result = sm.evaluate(sbox)
            elapsed = time.perf_counter() - started
            self._fill_metrics_table(sbox, result)
            self._last_result = result
            self._last_title = title
            self.btn_export.setEnabled(True)
            self.info_label.setText(f"{title} — đánh giá trong {elapsed:.2f} s")
            self._status(f"Đã đánh giá: {title}")
        except Exception as exc:  # noqa: BLE001 - hiển thị mọi lỗi cho người dùng
            self.info_label.setText("Chưa có dữ liệu benchmark.")
            QMessageBox.critical(self, "Lỗi", f"Không thể đánh giá S-box: {exc}")
        finally:
            QApplication.restoreOverrideCursor()
            self.btn_run.setEnabled(True)
