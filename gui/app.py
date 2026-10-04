"""Cửa sổ chính của ứng dụng PyQt6."""
from __future__ import annotations

import os
import sys

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStyle,
    QTabWidget,
)

from .settings import settings
from .tabs.encryption_tab import EncryptionTab
from .tabs.home_tab import HomeTab
from .tabs.image_benchmark_tab import ImageBenchmarkTab
from .tabs.sbox_benchmark_tab import SboxBenchmarkTab
from .tabs.sbox_compare_tab import SboxCompareTab
from .theme import apply_theme, build_app_icon

SHORTCUT_HELP = """\
Tệp
  Ctrl+O            Mở ảnh
  Ctrl+S            Lưu ảnh thành...
  Ctrl+E            Xuất báo cáo kết quả
  Ctrl+Q            Thoát

Chạy
  Ctrl+Enter        Mã hóa ảnh
  Ctrl+Shift+Enter  Giải mã ảnh
  Ctrl+B            Đánh giá ảnh mã hóa

Hiển thị
  F11               Bật/tắt toàn màn hình
  Esc               Thu nhỏ khi đang toàn màn hình
  Ctrl+H            Về trang chủ
  Ctrl+Tab          Chuyển tab
"""


class MainWindow(QMainWindow):
    """Cửa sổ chính chứa 4 tab: mã hóa ảnh, benchmark và so sánh S-box, benchmark ảnh."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mordell S-box — Mã hóa ảnh")
        self.setWindowIcon(build_app_icon())
        # Kích thước dự phòng, dùng khi người dùng thoát chế độ toàn màn hình.
        self.resize(1360, 860)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)
        home = HomeTab()
        self.tabs.addTab(home, "Trang chủ")
        self.tabs.addTab(EncryptionTab(), "Mã hóa & Giải mã ảnh")
        self.tabs.addTab(SboxBenchmarkTab(), "Benchmark S-box")
        self.tabs.addTab(SboxCompareTab(), "So sánh S-box")
        self.tabs.addTab(ImageBenchmarkTab(), "Benchmark ảnh mã hóa")

        self.statusBar().showMessage("Sẵn sàng")

        self._output_folder: str | None = None
        self.hint_status = QLabel("F11: toàn màn hình · Esc: thu nhỏ")
        self.hint_status.setStyleSheet("color: #555555; padding-right: 10px;")
        self.statusBar().addPermanentWidget(self.hint_status)
        self.btn_open_folder = QPushButton("Mở thư mục")
        self.btn_open_folder.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self.btn_open_folder.setToolTip("Mở thư mục chứa tệp vừa lưu hoặc vừa xuất")
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.clicked.connect(self._open_output_folder)
        self.statusBar().addPermanentWidget(self.btn_open_folder)

        self._settings = settings()
        self._running = False
        self._build_menu()
        self.tabs.currentChanged.connect(self._sync_menu)
        for index in range(self.tabs.count()):
            sub_tabs = getattr(self.tabs.widget(index), "result_tabs", None)
            if sub_tabs is not None:
                sub_tabs.currentChanged.connect(self._sync_menu)
        self._sync_menu()
        self._restore_settings()

    def _add_action(self, menu, text: str, shortcut: str, slot) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _build_menu(self) -> None:
        bar = self.menuBar()

        file_menu = bar.addMenu("&Tệp")
        self.act_open = self._add_action(file_menu, "Mở ảnh...", "Ctrl+O", self._open_image)
        self.act_save = self._add_action(file_menu, "Lưu ảnh thành...", "Ctrl+S", self._save_image)
        file_menu.addSeparator()
        self.act_export = self._add_action(file_menu, "Xuất báo cáo...", "Ctrl+E", self._export)
        file_menu.addSeparator()
        self._add_action(file_menu, "Thoát", "Ctrl+Q", self.close)

        run_menu = bar.addMenu("&Chạy")
        self.act_encrypt = self._add_action(run_menu, "Mã hóa ảnh", "Ctrl+Return", self._encrypt)
        self.act_decrypt = self._add_action(
            run_menu, "Giải mã ảnh", "Ctrl+Shift+Return", self._decrypt
        )
        self.act_benchmark = self._add_action(
            run_menu, "Đánh giá ảnh mã hóa", "Ctrl+B", self._benchmark
        )
        run_menu.addSeparator()
        self.act_run_sbox = self._add_action(
            run_menu, "Chạy Benchmark S-box", "", self._run_sbox
        )
        self.act_run_compare = self._add_action(
            run_menu, "Chạy so sánh S-box", "", self._run_compare
        )
        run_menu.addSeparator()
        self.act_ecb_cbc = self._add_action(
            run_menu, "So sánh ECB vs CBC", "", self._ecb_cbc
        )

        view_menu = bar.addMenu("&Hiển thị")
        self._add_action(view_menu, "Trang chủ", "Ctrl+H", self._navigate_home)
        view_menu.addSeparator()
        self._add_action(view_menu, "Toàn màn hình", "F11", self._toggle_fullscreen)
        self._add_action(
            view_menu, "Đưa về kích thước 1360×860", "", lambda: self.showNormal()
        )

        help_menu = bar.addMenu("&Trợ giúp")
        self._add_action(help_menu, "Phím tắt", "F1", self._show_shortcuts)
        self._add_action(help_menu, "Giới thiệu", "", self._show_about)

    def _sync_menu(self) -> None:
        """Bật/tắt mục menu theo tab đang mở và theo dữ liệu đã có."""
        tab = self.tabs.currentWidget()
        self.act_open.setEnabled(hasattr(tab, "browse_image"))
        self.act_save.setEnabled(hasattr(tab, "browse_output"))
        self.act_export.setEnabled(
            hasattr(tab, "handle_export") and self._export_available(tab)
        )

    def refresh_menu(self) -> None:
        """Cập nhật trạng thái menu (gọi sau khi có kết quả mới)."""
        if hasattr(self, "act_open"):
            self._sync_menu()

    def set_running(self, running: bool) -> None:
        """Khoá/mở các lệnh chạy khi đang có tác vụ nền."""
        self._running = running
        for action in (
            self.act_encrypt, self.act_decrypt, self.act_benchmark,
            self.act_run_sbox, self.act_run_compare, self.act_ecb_cbc,
        ):
            action.setEnabled(not running)
        self.hint_status.setText(
            "Đang chạy tác vụ nền..." if running else "F11: toàn màn hình · Esc: thu nhỏ"
        )

    @staticmethod
    def _export_available(tab) -> bool:
        """Chỉ bật “Xuất báo cáo...” khi tab đang mở đã có kết quả."""
        sub_tabs = getattr(tab, "result_tabs", None)
        if sub_tabs is not None and sub_tabs.currentIndex() == 2:
            return getattr(tab, "_last_ecb_cbc", None) is not None
        if hasattr(tab, "_last_benchmark"):
            return tab._last_benchmark is not None
        if hasattr(tab, "_last_result"):
            return tab._last_result is not None
        if hasattr(tab, "_rows"):
            return bool(tab._rows)
        return hasattr(tab, "handle_export")

    def _open_image(self) -> None:
        tab = self.tabs.currentWidget()
        method = getattr(tab, "browse_image", None)
        if callable(method):
            method()

    def _save_image(self) -> None:
        tab = self.tabs.currentWidget()
        method = getattr(tab, "browse_output", None)
        if callable(method):
            method()

    def _export(self) -> None:
        tab = self.tabs.currentWidget()
        # Tab Benchmark ảnh: đang ở tab con ECB vs CBC thì xuất báo cáo ECB/CBC
        result_tabs = getattr(tab, "result_tabs", None)
        if result_tabs is not None and result_tabs.currentIndex() == 2:
            method = getattr(tab, "handle_export_ecb_cbc", None)
        else:
            method = getattr(tab, "handle_export", None)
        if callable(method):
            method()

    def _encrypt(self) -> None:
        tab = self._tab(EncryptionTab)
        if self.tabs.currentWidget() is not tab:
            self.tabs.setCurrentWidget(tab)
            if not tab.input_path.text().strip():
                return          # chỉ chuyển tab, chưa có ảnh thì không báo lỗi
        tab.handle_encrypt()

    def _decrypt(self) -> None:
        tab = self._tab(EncryptionTab)
        if self.tabs.currentWidget() is not tab:
            self.tabs.setCurrentWidget(tab)
            if not tab.input_path.text().strip():
                return
        tab.handle_decrypt()

    def _benchmark(self) -> None:
        tab = self._tab(ImageBenchmarkTab)
        if self.tabs.currentWidget() is not tab:
            self.tabs.setCurrentWidget(tab)
            if not tab.input_path.text().strip():
                return
        tab.handle_run()

    def _run_sbox(self) -> None:
        tab = self._tab(SboxBenchmarkTab)
        self.tabs.setCurrentWidget(tab)
        tab.handle_run()

    def _run_compare(self) -> None:
        tab = self._tab(SboxCompareTab)
        self.tabs.setCurrentWidget(tab)
        tab.handle_run()

    def _ecb_cbc(self) -> None:
        tab = self._tab(ImageBenchmarkTab)
        if self.tabs.currentWidget() is not tab:
            self.tabs.setCurrentWidget(tab)
            if not tab.input_path.text().strip():
                return
        tab.handle_ecb_cbc()

    def _tab(self, kind):
        """Trả về tab theo lớp (không phụ thuộc thứ tự tab)."""
        for index in range(self.tabs.count()):
            widget = self.tabs.widget(index)
            if isinstance(widget, kind):
                return widget
        raise LookupError(f"Không tìm thấy tab {kind.__name__}")

    def _navigate_home(self) -> None:
        self.tabs.setCurrentIndex(0)

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def keyPressEvent(self, event):  # noqa: N802 - API của Qt
        # Esc chỉ thu nhỏ khi đang toàn màn hình (ở maximized thì không làm gì
        # để tránh thoát nhầm); F11 do action trong menu Hiển thị xử lý.
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showMaximized()
            return
        super().keyPressEvent(event)

    def _show_shortcuts(self) -> None:
        QMessageBox.information(self, "Phím tắt", SHORTCUT_HELP)

    def _show_about(self) -> None:
        QMessageBox.about(
            self,
            "Giới thiệu",
            "<b>Mordell S-box — Mã hóa ảnh &amp; Benchmark</b><br><br>"
            "Sinh S-box động từ đường cong Mordell và khóa bí mật, dùng để mã hóa "
            "ảnh (AES-256, CBC/ECB), kèm bộ đánh giá S-box và ảnh mã hóa.<br><br>"
            "PyQt6 · NumPy · Pillow · Matplotlib",
        )

    def remember_output(self, path: str) -> None:
        """Ghi nhớ thư mục của tệp vừa lưu để nút “Mở thư mục” mở đúng chỗ."""
        folder = os.path.dirname(os.path.abspath(path))
        if not os.path.isdir(folder):
            return
        self._output_folder = folder
        self.btn_open_folder.setEnabled(True)
        self.btn_open_folder.setToolTip(f"Mở thư mục: {folder}")

    def _open_output_folder(self) -> None:
        if self._output_folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._output_folder))

    def _restore_settings(self) -> None:
        """Khôi phục tab đang mở và tỉ lệ các khung kéo (không lưu mật khẩu)."""
        # Lưu theo tên tab để thêm/bớt tab không làm lệch vị trí.
        name = self._settings.value("ui/tab_name", "", type=str)
        if name:
            for index in range(self.tabs.count()):
                if self.tabs.tabText(index) == name:
                    self.tabs.setCurrentIndex(index)
                    break
        for tab_index in range(self.tabs.count()):
            tab = self.tabs.widget(tab_index)
            for split_index, splitter in enumerate(tab.findChildren(QSplitter)):
                value = self._settings.value(f"ui/splitter/{tab_index}/{split_index}")
                if not value:
                    continue
                try:
                    sizes = [int(size) for size in value]
                except (TypeError, ValueError):
                    continue
                if len(sizes) == splitter.count() and sum(sizes) > 0:
                    splitter.setSizes(sizes)

    def _save_settings(self) -> None:
        self._settings.setValue("ui/tab_name", self.tabs.tabText(self.tabs.currentIndex()))
        for tab_index in range(self.tabs.count()):
            tab = self.tabs.widget(tab_index)
            for split_index, splitter in enumerate(tab.findChildren(QSplitter)):
                sizes = splitter.sizes()
                if sum(sizes) > 0:
                    self._settings.setValue(f"ui/splitter/{tab_index}/{split_index}", sizes)
        self._settings.sync()

    def closeEvent(self, event):  # noqa: N802 - API của Qt
        # Dừng các tác vụ nền trước khi đóng để Qt không huỷ QThread đang chạy.
        self._save_settings()
        for index in range(self.tabs.count()):
            stop = getattr(self.tabs.widget(index), "shutdown", None)
            if callable(stop):
                stop()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MainWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
