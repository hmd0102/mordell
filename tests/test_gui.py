"""Kiểm thử giao diện ở chế độ không hiển thị. Cấu hình ghi vào thư mục tạm, không đụng registry."""
import os
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtCore import QSettings
    from PyQt6.QtWidgets import QApplication, QMessageBox
except ImportError:
    raise unittest.SkipTest("Chưa cài PyQt6")

import numpy as np
from PIL import Image

import core.image_cipher as image_cipher
from core import decrypt_file, encrypt_file, load_image
from reference.alali2024 import printed_to_sbox

_SETTINGS_DIR = tempfile.mkdtemp(prefix="mordell_test_gui_")
QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _SETTINGS_DIR)
_APP = QApplication.instance() or QApplication([])

from gui.tabs.encryption_tab import EncryptionTab, encrypt_task
from gui.tabs.image_benchmark_tab import ImageBenchmarkTab, benchmark_task
from gui.tabs.sbox_benchmark_tab import SboxBenchmarkTab
from gui.workers import TaskCancelled

KEY = "khoa-kiem-thu"
image_cipher.KDF_ITERATIONS = 1000


class _Worker:
    """Thay cho TaskWorker khi gọi trực tiếp hàm tác vụ; hủy ở lần kiểm tra thứ `cancel_at`."""

    def __init__(self, cancel_at=None):
        self.calls = 0
        self.cancel_at = cancel_at

    def report(self, percent, message=""):
        pass

    def check_cancelled(self):
        self.calls += 1
        if self.cancel_at is not None and self.calls >= self.cancel_at:
            raise TaskCancelled


def _wait(runner, seconds=60):
    deadline = time.time() + seconds
    while runner.busy() and time.time() < deadline:
        _APP.processEvents()
        time.sleep(0.005)
    for _ in range(10):
        _APP.processEvents()


class _Base(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = folder.name
        rng = np.random.default_rng(3)
        self.source = self.path("goc.png")
        Image.fromarray(rng.integers(0, 256, (64, 64), dtype=np.uint8)).save(self.source)
        for name in ("information", "warning", "critical", "question"):
            patcher = mock.patch.object(QMessageBox, name, return_value=QMessageBox.StandardButton.Ok)
            patcher.start()
            self.addCleanup(patcher.stop)

    def path(self, name):
        return os.path.join(self.dir, name)


class TestCancel(_Base):
    def test_cancel_during_encryption_writes_nothing(self):
        out = self.path("mahoa.png")
        with self.assertRaises(TaskCancelled):
            encrypt_task(_Worker(cancel_at=2), self.source, out, KEY, "cbc")
        self.assertFalse(os.path.exists(out))
        self.assertFalse(os.path.exists(out + ".meta"))

    def test_cancel_during_decryption_writes_nothing(self):
        enc, dec = self.path("mahoa.png"), self.path("giaima.png")
        encrypt_file(self.source, enc, KEY)
        with self.assertRaises(TaskCancelled):
            decrypt_file(enc, dec, KEY, tick=_Worker(cancel_at=1).check_cancelled)
        self.assertFalse(os.path.exists(dec))


class TestDecryptMessage(_Base):
    def _decrypt(self, key, reference):
        enc, self.dec = self.path("mahoa.png"), self.path("giaima.png")
        encrypt_file(self.source, enc, KEY)
        tab = EncryptionTab()
        self.addCleanup(tab.shutdown)
        tab._reference = reference
        tab.input_path.setText(enc)
        tab.output_path.setText(self.dec)
        tab.password.setText(key)
        tab.result_label.setText("✔ kết quả của lần trước")
        tab.handle_decrypt()
        _wait(tab.runner)
        return tab.result_label.text()

    def test_wrong_key_is_refused_with_error(self):
        self.assertEqual(self._decrypt("khoa-sai", ""), "")
        QMessageBox.critical.assert_called_once()
        self.assertIn("Sai khóa", QMessageBox.critical.call_args.args[2])
        self.assertFalse(os.path.exists(self.dec))

    def test_right_key_is_confirmed_without_reference(self):
        text = self._decrypt(KEY, "")
        self.assertTrue(text.startswith("✔"), text)
        self.assertIn("đã xác thực", text)

    def test_right_key_with_reference_is_confirmed(self):
        text = self._decrypt(KEY, self.source)
        self.assertTrue(text.startswith("✔"), text)

    def test_different_reference_is_flagged(self):
        other = self.path("khac.png")
        Image.fromarray(np.zeros((64, 64), dtype=np.uint8)).save(other)
        text = self._decrypt(KEY, other)
        self.assertTrue(text.startswith("⚠"), text)


class TestHighDepthImage(_Base):
    def test_16_bit_image_is_rejected(self):
        path = self.path("sau16bit.png")
        Image.fromarray(np.full((8, 8), 40000, dtype=np.uint16)).save(path)
        with self.assertRaisesRegex(ValueError, "8 bit"):
            load_image(path)


class TestPlaintextPosition(_Base):
    def test_npcr_falls_with_position(self):
        npcr = {p: benchmark_task(_Worker(), self.source, KEY, p)["plaintext_sensitivity"]["NPCR"]
                for p in ("first", "middle", "last")}
        self.assertGreater(npcr["first"], 95)
        self.assertLess(npcr["last"], 5)
        self.assertLess(npcr["last"], npcr["middle"])
        self.assertLess(npcr["middle"], npcr["first"])

    def test_combo_is_passed_to_task(self):
        tab = ImageBenchmarkTab()
        self.addCleanup(tab.shutdown)
        tab.input_path.setText(self.source)
        tab.position_combo.setCurrentIndex(tab.position_combo.findData("last"))
        tab.handle_run()
        _wait(tab.runner)
        result = tab._last_benchmark["result"]
        self.assertEqual(result["position"], "last")
        self.assertTrue(any("cuối ảnh" in row[0] for row in tab._benchmark_table()[1]))


class TestLabels(_Base):
    def test_ampersand_is_displayed_in_tab_titles(self):
        from gui.app import MainWindow
        win = MainWindow()
        self.addCleanup(win.close)
        self.assertIn("Mã hóa && Giải mã ảnh", [win.tabs.tabText(i) for i in range(win.tabs.count())])
        benchmark = next(win.tabs.widget(i) for i in range(win.tabs.count())
                         if isinstance(win.tabs.widget(i), ImageBenchmarkTab))
        self.assertEqual(benchmark.result_tabs.tabText(0), "Ảnh && chỉ số")


class TestSboxTab(_Base):
    def _select(self, tab, data):
        for index in range(tab.source_combo.count()):
            if tab.source_combo.itemData(index) == data:
                tab.source_combo.setCurrentIndex(index)
                return
        self.fail(f"Không có nguồn {data}")

    def test_branch_sources_use_their_own_polynomials(self):
        tab = SboxBenchmarkTab()
        self._select(tab, ("branch", 10))
        self.assertEqual(tab.poly_combo.currentData(), 1315)
        self.assertEqual(tab.poly_combo.count(), 99)
        tab.handle_run()
        self.assertEqual(tab._last_sbox, printed_to_sbox(1315))
        self._select(tab, ("branch", 9))
        self.assertEqual(tab.poly_combo.currentData(), 529)
        tab.handle_run()
        self.assertEqual(len(set(tab._last_sbox)), 256)
        self._select(tab, "poly")
        self.assertEqual(tab.poly_combo.count(), 30)
        self.assertEqual(tab.poly_combo.currentData(), 0x11B)

    def test_metric_rows_report_both_nl_conventions(self):
        tab = SboxBenchmarkTab()
        self._select(tab, ("branch", 10))
        tab.handle_run()
        rows = {tab.metrics_table.item(r, 0).text(): tab.metrics_table.item(r, 1).text()
                for r in range(tab.metrics_table.rowCount())}
        self.assertTrue(rows["NL trung bình 8 bit đầu ra"].startswith("106.00"))
        self.assertTrue(rows["NL nhỏ nhất (mọi hàm thành phần)"].startswith("96"))
        self.assertNotIn("tối ưu", " ".join(rows.values()))


if __name__ == "__main__":
    unittest.main()


class TestAttackTab(_Base):
    def test_all_attacks(self):
        from gui.tabs.attack_tab import ATTACKS, attack_task
        result = attack_task(_Worker(), self.source, KEY, list(ATTACKS), 0.01)
        rows = result["rows"]
        for kind in ("black", "white"):
            self.assertTrue(np.isinf(rows[kind]["psnr"]))
            self.assertGreater(rows[kind]["metrics"]["entropy"], 7.9)
            self.assertNotIn("file", rows[kind])
        for kind, row in rows.items():
            if kind in ("black", "white"):
                continue
            self.assertTrue(row["file"]["rejected"], kind)
            self.assertFalse(row["file"]["written"], kind)
        self.assertEqual(rows["bitflip"]["blocks"], 2)
        self.assertLess(rows["wrongkey"]["psnr"], 12)
        self.assertGreater(rows["crop16"]["psnr"], rows["crop4"]["psnr"])

    def test_tab_runs_in_window(self):
        from gui.app import MainWindow
        from gui.tabs.attack_tab import AttackTab
        win = MainWindow()
        self.addCleanup(win.close)
        tab = next(win.tabs.widget(i) for i in range(win.tabs.count())
                   if isinstance(win.tabs.widget(i), AttackTab))
        tab.input_path.setText(self.source)
        tab.password.setText(KEY)
        tab.handle_run_all()
        _wait(tab.runner)
        self.assertIn("TỪ CHỐI", tab.report.toPlainText())
        tab.attack_combo.setCurrentIndex(3)
        self.assertIn("PSNR", tab.preview_decrypted.title_label.text())


class TestHomeShortcuts(_Base):
    def test_buttons_open_matching_tabs(self):
        from gui.app import MainWindow
        from gui.tabs.attack_tab import AttackTab
        win = MainWindow()
        self.addCleanup(win.close)
        home = win.tabs.widget(0)
        home.step_buttons[0].click()
        self.assertIsInstance(win.tabs.currentWidget(), EncryptionTab)
        home.step_buttons[-1].click()
        self.assertIsInstance(win.tabs.currentWidget(), AttackTab)
        self.assertEqual(len(home.step_buttons), win.tabs.count() - 1)
