"""Tab so sánh S-box Mordell với các S-box tham chiếu."""
from __future__ import annotations

import time

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import build_sbox, key_to_polynomial, poly_to_str
from metrics import sbox_metrics as sm
from reference import REFERENCE_SBOXES
from .. import theme
from ..export import APP_NAME, export_report, format_table, timestamp
from ..widgets import TaskProgress
from ..workers import TaskRunner

DEFAULT_KEY = "day-la-mot-khoa-bi-mat-vi-du"
REFERENCE_NAMES = {"aes": "AES", "weierstrass": "Weierstrass", "chaos": "Hỗn loạn"}
COLUMNS = ["S-box", "NL", "SAC", "BIC-NL", "BIC-SAC", "LAP", "DAP"]

#: Tooltip giải thích từng cột chỉ số
COLUMN_HINTS = {
    "NL": "Phi tuyến — cao hơn tốt hơn (tối ưu 112)",
    "SAC": "SAC trung bình — lý tưởng 0,5",
    "BIC-NL": "BIC phi tuyến trung bình — cao hơn tốt hơn (tối ưu 112)",
    "BIC-SAC": "BIC-SAC — lý tưởng 0,5",
    "LAP": "LAP — thấp hơn tốt hơn (tối ưu 0,0625)",
    "DAP": "DAP — thấp hơn tốt hơn (tối ưu 4/256)",
}

# (tên khóa trong kết quả evaluate, chỉ số cột, hàm chọn "tốt nhất")
# NL/BIC-NL càng cao càng tốt; SAC/BIC-SAC gần 0.5; LAP/DAP càng thấp càng tốt.
_METRICS = (
    ("NL", lambda v: v),
    ("SAC_avg", lambda v: -abs(v - 0.5)),
    ("BIC_NL_avg", lambda v: v),
    ("BIC_SAC", lambda v: -abs(v - 0.5)),
    ("LAP", lambda v: -v),
    ("DAP", lambda v: -v),
)

# (khóa chỉ số, tiêu đề biểu đồ, định dạng nhãn, giá trị lý tưởng để vẽ đường tham chiếu)
_CHART_SPECS = (
    ("NL", "NL — cao hơn tốt hơn", "{:.0f}", 112.0),
    ("BIC_NL_avg", "BIC-NL trung bình — cao hơn tốt hơn", "{:.2f}", 112.0),
    ("LAP", "LAP — thấp hơn tốt hơn", "{:.4f}", 0.0625),
    ("DAP", "DAP — thấp hơn tốt hơn", "{:.4f}", 4 / 256),
)


def compare_task(worker, key: str) -> tuple[int, list[tuple[str, dict]]]:
    """Sinh 4 S-box và đánh giá chỉ số (chạy ở luồng nền)."""
    worker.report(5, "Đang dẫn xuất đa thức từ khóa...")
    poly = key_to_polynomial(key)
    worker.check_cancelled()

    entries = [("Mordell (đề xuất)", build_sbox(key=key))]
    for name, factory in REFERENCE_SBOXES.items():
        entries.append((REFERENCE_NAMES[name], factory()))

    rows = []
    for index, (label, sbox) in enumerate(entries):
        worker.check_cancelled()
        worker.report(15 + int(75 * index / len(entries)), f"Đang đánh giá {label}...")
        rows.append((label, sm.evaluate(sbox)))
    worker.report(95, "Đang vẽ biểu đồ...")
    return poly, rows


class SboxCompareTab(QWidget):
    """Đánh giá 4 S-box trên cùng bộ chỉ số và hiển thị cạnh nhau."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._started = 0.0
        self._rows: list[tuple[str, dict]] | None = None
        self._poly: int | None = None
        self._key = ""
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
        title = QLabel("So sánh S-box đề xuất (Mordell) với AES, Weierstrass và Hỗn loạn")
        title.setStyleSheet(f"color: {theme.BRAND}; font-size: 11pt; font-weight: 600;")
        layout.addWidget(title)

        row = QHBoxLayout()
        row.addWidget(QLabel("Khóa (sinh S-box Mordell):"))
        self.key_edit = QLineEdit(DEFAULT_KEY)
        self.key_edit.setPlaceholderText("Khóa bí mật dùng để dẫn xuất đa thức f(x)")
        row.addWidget(self.key_edit, 1)
        self.btn_run = QPushButton("Chạy so sánh")
        self.btn_run.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.btn_run.clicked.connect(self.handle_run)
        theme.mark_primary(self.btn_run)
        row.addWidget(self.btn_run)
        self.btn_export = QPushButton("Xuất báo cáo...")
        self.btn_export.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)
        )
        self.btn_export.setToolTip("Xuất bảng so sánh ra TXT/CSV/JSON")
        self.btn_export.setEnabled(False)
        self.btn_export.clicked.connect(self.handle_export)
        row.addWidget(self.btn_export)
        self.btn_copy = QPushButton("Sao chép bảng")
        self.btn_copy.setToolTip("Sao chép bảng so sánh dạng TSV để dán vào Excel/báo cáo")
        self.btn_copy.setEnabled(False)
        self.btn_copy.clicked.connect(self.handle_copy)
        row.addWidget(self.btn_copy)
        layout.addLayout(row)

        self.progress = TaskProgress()
        self.progress.cancel_requested.connect(self.runner_cancel)
        layout.addWidget(self.progress)

        self.info_label = QLabel("Bấm chạy để đánh giá 4 S-box (có thể mất vài giây).")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        for column in range(1, len(COLUMNS)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)
        for column, name in enumerate(COLUMNS):
            item = self.table.horizontalHeaderItem(column)
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                if column == 0
                else Qt.AlignmentFlag.AlignCenter
            )
            if name in COLUMN_HINTS:
                item.setToolTip(COLUMN_HINTS[name])
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        # Bảng chỉ có 4 dòng: cao vừa đủ, nhường chỗ cho biểu đồ
        self.table.setFixedHeight(
            self.table.horizontalHeader().sizeHint().height() + 4 * 36 + 8
        )

        self.figure = Figure(figsize=(7.5, 4.6), dpi=100, layout="constrained")
        self.figure.text(0.5, 0.5, "Chạy so sánh để xem biểu đồ cột...",
                         ha="center", va="center", color=theme.PLACEHOLDER)
        self.canvas = FigureCanvasQTAgg(self.figure)
        chart_panel = QWidget()
        chart_panel.setMinimumHeight(430)
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.addWidget(NavigationToolbar2QT(self.canvas, chart_panel))
        chart_layout.addWidget(self.canvas, 1)

        chart_scroll = QScrollArea()
        chart_scroll.setWidgetResizable(True)
        chart_scroll.setFrameShape(QFrame.Shape.NoFrame)
        chart_scroll.setWidget(chart_panel)

        layout.addWidget(self.table)
        layout.addWidget(chart_scroll, 1)

        self.note_label = QLabel("")
        self.note_label.setWordWrap(True)
        self.note_label.setStyleSheet(f"color: {theme.NOTE};")
        layout.addWidget(self.note_label)

    def _status(self, message: str) -> None:
        window = self.window()
        if hasattr(window, "statusBar"):
            window.statusBar().showMessage(message)
        if callable(getattr(window, "refresh_menu", None)):
            window.refresh_menu()

    def _fill_table(self, rows: list[tuple[str, dict]]) -> None:
        self.table.setRowCount(len(rows))

        # Chỉ số tốt nhất của từng cột (có thể đồng hạng)
        best_values = {}
        column_scores = {}
        for column, (metric, score) in enumerate(_METRICS, start=1):
            scores = [score(result[metric]) for _, result in rows]
            column_scores[column] = scores
            best_values[column] = max(scores)

        green = QColor("#1b5e20")
        mordell_bg = QColor("#e8f5e9")
        for row_index, (label, result) in enumerate(rows):
            values = [
                label,
                f"{result['NL']}",
                f"{result['SAC_avg']:.4f}",
                f"{result['BIC_NL_avg']:.2f}",
                f"{result['BIC_SAC']:.4f}",
                f"{result['LAP']:.4f}",
                f"{result['DAP']:.4f}",
            ]
            for column, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                    if column == 0
                    else Qt.AlignmentFlag.AlignCenter
                )
                if row_index == 0:
                    item.setBackground(mordell_bg)
                if column > 0 and column_scores[column][row_index] == best_values[column]:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(green)
                    item.setToolTip("Tốt nhất trong 4 S-box")
                self.table.setItem(row_index, column, item)

    def _update_chart(self, rows: list[tuple[str, dict]]) -> None:
        short_labels = {
            "Mordell (đề xuất)": "Mordell",
            "AES": "AES",
            "Weierstrass": "Weierstrass",
            "Hỗn loạn": "Hỗn loạn",
        }
        labels = [short_labels.get(label, label) for label, _ in rows]
        colors = ["#2e7d32" if index == 0 else "#90a4ae"
                  for index in range(len(labels))]

        self.figure.clear()
        axes = self.figure.subplots(2, 2).ravel()
        for ax, (metric, title, fmt, ideal) in zip(axes, _CHART_SPECS):
            values = [result[metric] for _, result in rows]
            bars = ax.bar(range(len(values)), values, color=colors, width=0.58)
            best = max(values) if metric in ("NL", "BIC_NL_avg") else min(values)
            for bar, value in zip(bars, values):
                if value == best:
                    bar.set_edgecolor("#1b5e20")
                    bar.set_linewidth(2.0)
            for bar, value in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2, value, fmt.format(value),
                        ha="center", va="bottom", fontsize=8)
            ax.axhline(ideal, color="#e53935", linestyle="--", linewidth=0.9)
            ax.set_title(f"{title} (tối ưu {ideal:g})", fontsize=9)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, fontsize=8)
            ax.tick_params(axis="y", labelsize=8)
            ax.set_ylim(0, max(max(values), ideal) * 1.18)
            ax.grid(axis="y", alpha=0.2)
            ax.set_axisbelow(True)
        self.canvas.draw_idle()

    def runner_cancel(self) -> None:
        self.runner.cancel()

    def _set_busy(self, busy: bool) -> None:
        self.btn_run.setEnabled(not busy)
        window = self.window()
        if callable(getattr(window, "set_running", None)):
            window.set_running(busy)
        if busy:
            self.progress.start("Đang so sánh 4 S-box...")
        else:
            self.progress.stop()

    def _on_task_done(self, result) -> None:
        poly, rows = result
        try:
            self._fill_table(rows)
            self._update_chart(rows)
            self._rows = rows
            self._poly = poly
            self._key = self.key_edit.text()
            self.btn_export.setEnabled(True)
            self.btn_copy.setEnabled(True)
            self.info_label.setText(
                f"S-box Mordell: f(x) = {poly_to_str(poly)} (0x{poly:03X})"
                f" — so sánh trong {time.perf_counter() - self._started:.2f} s"
            )
            self.note_label.setText(
                "NL, BIC-NL: cao hơn tốt · SAC, BIC-SAC lý tưởng 0,5 · LAP, DAP: thấp hơn tốt"
                " · Ô xanh đậm = tốt nhất, cột xanh lá = Mordell, đường đứt đỏ = tối ưu."
            )
            self._status("Đã so sánh 4 S-box")
        finally:
            self._set_busy(False)

    def _on_task_failed(self, message: str) -> None:
        self._set_busy(False)
        self.info_label.setText("Chưa có dữ liệu so sánh.")
        QMessageBox.critical(self, "Lỗi", f"Không thể so sánh S-box: {message}")

    def _on_task_cancelled(self) -> None:
        self._set_busy(False)
        self._status("Đã huỷ so sánh S-box")

    def shutdown(self) -> None:
        self.runner.shutdown()

    def handle_export(self) -> bool:
        if not self._rows or self._poly is None:
            QMessageBox.information(self, "Chưa có dữ liệu",
                                    "Hãy chạy so sánh trước khi xuất báo cáo.")
            return

        table_rows = [
            [label, str(result["NL"]), f"{result['SAC_avg']:.4f}",
             f"{result['BIC_NL_avg']:.2f}", f"{result['BIC_SAC']:.4f}",
             f"{result['LAP']:.4f}", f"{result['DAP']:.4f}"]
            for label, result in self._rows
        ]
        note = ("NL, BIC-NL càng cao càng tốt; SAC, BIC-SAC lý tưởng 0.5;"
                " LAP, DAP càng thấp càng tốt.")
        text = "\n".join([
            APP_NAME,
            "BÁO CÁO SO SÁNH S-BOX",
            f"Xuất lúc: {timestamp()}",
            f"Khóa: {self._key}",
            f"Đa thức: f(x) = {poly_to_str(self._poly)} (0x{self._poly:03X})",
            "",
            format_table(COLUMNS, table_rows),
            "",
            f"Ghi chú: {note}",
        ])
        payload = {
            "phan_mem": APP_NAME,
            "loai": "so_sanh_sbox",
            "thoi_gian": timestamp(),
            "khoa": self._key,
            "poly": self._poly,
            "poly_str": poly_to_str(self._poly),
            "ghi_chu": note,
            "rows": [{"ten": label, "chi_so": result} for label, result in self._rows],
        }
        return export_report(self, "so_sanh_sbox", text=text,
                             csv_data=(COLUMNS, table_rows), payload=payload)

    def handle_copy(self) -> None:
        if not self._rows:
            QMessageBox.information(self, "Chưa có dữ liệu",
                                    "Hãy chạy so sánh trước khi sao chép bảng.")
            return
        lines = ["\t".join(COLUMNS)]
        for label, result in self._rows:
            lines.append("\t".join([
                label, str(result["NL"]), f"{result['SAC_avg']:.4f}",
                f"{result['BIC_NL_avg']:.2f}", f"{result['BIC_SAC']:.4f}",
                f"{result['LAP']:.4f}", f"{result['DAP']:.4f}",
            ]))
        QApplication.clipboard().setText("\n".join(lines))
        self._status("Đã sao chép bảng so sánh vào clipboard")

    def handle_run(self) -> None:
        key = self.key_edit.text()
        if not key:
            QMessageBox.warning(self, "Thiếu dữ liệu", "Vui lòng nhập khóa bí mật.")
            return
        if self.runner.busy():
            return
        self._started = time.perf_counter()
        self._set_busy(True)
        if not self.runner.start(compare_task, key):
            self._set_busy(False)
