"""Xuất kết quả đánh giá ra tệp TXT / CSV / JSON.

CSV được ghi bằng UTF-8 có BOM để Excel hiển thị đúng tiếng Việt; JSON giữ nguyên
dấu tiếng Việt (``ensure_ascii=False``) cho dễ đọc.
"""
from __future__ import annotations

import csv
import io
import json
import os
import time

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from .settings import last_dir, remember_dir

APP_NAME = "Mordell S-box — Mã hóa ảnh & Benchmark"


def timestamp() -> str:
    """Thời điểm hiện tại dạng dd/mm/YYYY HH:MM:SS."""
    return time.strftime("%d/%m/%Y %H:%M:%S")


def file_stamp() -> str:
    """Thời điểm dùng cho tên tệp: YYYYMMDD_HHMM."""
    return time.strftime("%Y%m%d_%H%M")


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Bảng văn bản canh cột bằng khoảng trắng."""
    widths = [len(str(h)) for h in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    lines = ["  ".join(str(h).ljust(widths[i]) for i, h in enumerate(headers)).rstrip()]
    lines.append("  ".join("-" * width for width in widths))
    for row in rows:
        lines.append("  ".join(str(cell).ljust(widths[i])
                               for i, cell in enumerate(row)).rstrip())
    return "\n".join(lines)


def image_metric_pairs(metrics: dict) -> list[tuple[str, str]]:
    """Chuyển dict chỉ số ảnh thành các cặp (tên, giá trị) để in/xuất."""
    corr, glcm = metrics["corr"], metrics["glcm"]
    return [
        ("Entropy", f"{metrics['entropy']:.4f}"),
        ("Chi-square", f"{metrics['chi2']:.2f}"),
        ("Tương quan ngang", f"{corr['horizontal']:.4f}"),
        ("Tương quan dọc", f"{corr['vertical']:.4f}"),
        ("Tương quan chéo", f"{corr['diagonal']:.4f}"),
        ("GLCM contrast", f"{glcm['contrast']:.2f}"),
        ("GLCM homogeneity", f"{glcm['homogeneity']:.4f}"),
        ("GLCM energy", f"{glcm['energy']:.2e}"),
    ]


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip() + "\n")


def _write_csv(path: str, header: list[str], rows: list[list[object]]) -> None:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    # utf-8-sig: thêm BOM để Excel nhận đúng bảng mã tiếng Việt
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        handle.write(buffer.getvalue())


def _write_json(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def _extension_from_filter(selected: str) -> str:
    for token in selected.replace("(", " ").replace(")", " ").split():
        if token.startswith("*."):
            return token[1:]
    return ".txt"


def export_report(parent, default_stem: str, *, text: str,
                  csv_data: tuple[list[str], list[list[object]]] | None = None,
                  payload: dict | None = None) -> bool:
    """Hỏi đường dẫn rồi ghi báo cáo. Trả về True nếu đã ghi tệp."""
    filters = ["Văn bản (*.txt)"]
    if csv_data is not None:
        filters.append("Bảng CSV (*.csv)")
    if payload is not None:
        filters.append("JSON (*.json)")
    filters.append("Tất cả tệp (*)")

    default_name = f"{default_stem}_{file_stamp()}.txt"
    folder = last_dir()
    if folder:
        default_name = os.path.join(folder, default_name)
    path, selected = QFileDialog.getSaveFileName(
        parent, "Xuất báo cáo", default_name, ";;".join(filters)
    )
    if not path:
        return False

    extension = os.path.splitext(path)[1].lower()
    if not extension:
        extension = _extension_from_filter(selected)
        path += extension
    if extension not in (".txt", ".csv", ".json"):
        QMessageBox.warning(
            parent, "Định dạng không hỗ trợ",
            f"Chỉ xuất được .txt, .csv hoặc .json (bạn chọn: {extension}).",
        )
        return False

    try:
        if extension == ".csv":
            if csv_data is None:
                raise ValueError("Dữ liệu này không xuất được dạng CSV.")
            _write_csv(path, csv_data[0], csv_data[1])
        elif extension == ".json":
            if payload is None:
                raise ValueError("Dữ liệu này không xuất được dạng JSON.")
            _write_json(path, payload)
        else:
            _write_text(path, text)
    except Exception as exc:  # noqa: BLE001 - hiển thị mọi lỗi cho người dùng
        QMessageBox.critical(parent, "Lỗi", f"Không ghi được tệp:\n{path}\n\n{exc}")
        return False

    message = f"Đã xuất báo cáo: {os.path.basename(path)}"
    window = parent.window() if parent is not None else None
    if window is not None and hasattr(window, "statusBar"):
        window.statusBar().showMessage(message)
    elif parent is not None and hasattr(parent, "statusBar"):
        parent.statusBar().showMessage(message)
    if window is not None and hasattr(window, "remember_output"):
        window.remember_output(path)
    remember_dir(path)
    return True
