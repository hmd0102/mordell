"""Chạy tác vụ nặng trong luồng nền để giao diện không bị đóng băng.

Cách dùng::

    runner = TaskRunner(self)
    runner.progress.connect(progress_widget.set_progress)
    runner.start(ham_xu_ly, tham_so_1, tham_so_2)

Hàm xử lý nhận **worker** làm tham số đầu tiên và chỉ được trả về dữ liệu
(mảng numpy, dict, chuỗi...). Mọi thao tác với widget/matplotlib phải làm trong
slot nhận tín hiệu ``finished``/``failed``/``cancelled`` — tức là ở luồng UI.
"""
from __future__ import annotations

from typing import Any, Callable

from PyQt6.QtCore import QObject, QThread, pyqtSignal

# Giữ tham chiếu tới luồng chưa kịp dừng khi đóng cửa sổ, tránh Qt huỷ QThread
# đang chạy (nguyên nhân làm chương trình abort).
_ORPHAN_THREADS: list[tuple[QThread, "TaskWorker"]] = []


class TaskCancelled(Exception):
    """Tác vụ tự ném ra khi thấy người dùng đã bấm Huỷ."""


class TaskWorker(QObject):
    """Đối tượng thực thi trong QThread; tác vụ dùng nó để báo tiến trình."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self._func = func
        self._args = args
        self._kwargs = kwargs
        self._cancel = False

    def report(self, percent: int, message: str = "") -> None:
        self.progress.emit(max(0, min(100, int(percent))), message)

    def is_cancelled(self) -> bool:
        return self._cancel

    def check_cancelled(self) -> None:
        """Dừng tác vụ nếu đã có yêu cầu huỷ (gọi giữa các bước)."""
        if self._cancel:
            raise TaskCancelled

    def request_cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            result = self._func(self, *self._args, **self._kwargs)
        except TaskCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - chuyển lỗi cho giao diện
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.finished.emit(result)


class TaskRunner(QObject):
    """Quản lý một QThread + worker; phát lại tín hiệu cho giao diện."""

    progress = pyqtSignal(int, str)
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._thread: QThread | None = None
        self._worker: TaskWorker | None = None

    def busy(self) -> bool:
        return self._thread is not None

    def start(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> bool:
        """Chạy ``func(worker, *args, **kwargs)`` ở luồng nền. Trả về False nếu đang bận."""
        if self._thread is not None:
            return False

        thread = QThread()
        worker = TaskWorker(func, *args, **kwargs)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self.progress)
        worker.finished.connect(self._relay_finished)
        worker.failed.connect(self._relay_failed)
        worker.cancelled.connect(self._relay_cancelled)
        for signal in (worker.finished, worker.failed, worker.cancelled):
            signal.connect(thread.quit)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._thread = thread
        self._worker = worker
        thread.start()
        return True

    def cancel(self) -> None:
        if self._worker is not None:
            self._worker.request_cancel()

    def shutdown(self, timeout_ms: int = 3000) -> None:
        """Huỷ và chờ luồng kết thúc (dùng khi đóng cửa sổ)."""
        thread, worker = self._thread, self._worker
        if thread is None:
            return
        self.cancel()
        if thread.isRunning():
            thread.quit()
            if not thread.wait(timeout_ms):
                _ORPHAN_THREADS.append((thread, worker))
        self._thread = None
        self._worker = None

    def _relay_finished(self, result: object) -> None:
        self.finished.emit(result)

    def _relay_failed(self, message: str) -> None:
        self.failed.emit(message)

    def _relay_cancelled(self) -> None:
        self.cancelled.emit()

    def _thread_finished(self) -> None:
        self._thread = None
        self._worker = None
