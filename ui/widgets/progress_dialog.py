"""下载进度对话框 — 取消会真正中断任务。

库里所有下载/安装都通过 callback["setStatus"] 推进进度，
因此在回调里抛 TaskCancelled 就能在下一个文件边界中断整个安装。
取消后对话框保持打开直到线程真正结束，避免"窗口关了但还在写同一目录"。
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                              QProgressBar, QPushButton)
from PyQt6.QtCore import Qt, QThread, pyqtSignal


class TaskCancelled(Exception):
    """任务被用户取消。"""


class WorkerThread(QThread):
    progress_status = pyqtSignal(str)
    progress_value = pyqtSignal(int)
    progress_max = pyqtSignal(int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, task_func, parent=None):
        super().__init__(parent)
        self.task_func = task_func
        self._cancelled = False
        self.was_cancelled = False

    # ── 取消 ──

    def cancel(self):
        self._cancelled = True

    def _guard(self):
        if self._cancelled:
            raise TaskCancelled()

    # ── 回调（库每完成一个文件调用一次） ──

    def _on_status(self, text):
        self._guard()
        self.progress_status.emit(str(text))

    def _on_progress(self, value):
        self._guard()
        self.progress_value.emit(int(value))

    def _on_max(self, value):
        self.progress_max.emit(int(value))

    def run(self):
        cb = {
            "setStatus": self._on_status,
            "setProgress": self._on_progress,
            "setMax": self._on_max,
            # 让长任务（大文件下载）能自己查询是否被取消 —— 只靠抛 TaskCancelled
            # 的话，卡在 read() 里的下载根本收不到信号。
            "isCancelled": lambda: bool(self._cancelled),
        }
        try:
            self.task_func(cb)
            if self._cancelled:
                self.was_cancelled = True
                self.finished_signal.emit(False, "已取消")
            else:
                self.finished_signal.emit(True, "")
        except TaskCancelled:
            self.was_cancelled = True
            self.finished_signal.emit(False, "已取消")
        except Exception as e:
            if self._cancelled:
                self.was_cancelled = True
                self.finished_signal.emit(False, "已取消")
            else:
                self.finished_signal.emit(False, str(e))


class ProgressDialog(QDialog):
    """模态进度对话框。用法：

        d = ProgressDialog(title, task_func, parent)
        d.start()                       # 阻塞直到完成/取消
        if d.was_cancelled: ...
        elif d.success: ...
        else: 显示 d.error_msg
    """

    def __init__(self, title, task_func, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedSize(480, 140)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        self.title_lbl = QLabel(title)
        self.title_lbl.setObjectName("sectionLabel")
        lay.addWidget(self.title_lbl)

        self.status_lbl = QLabel("准备中…")
        self.status_lbl.setObjectName("statusLabel")
        self.status_lbl.setWordWrap(True)
        lay.addWidget(self.status_lbl)

        self.bar = QProgressBar()
        self.bar.setValue(0)
        self.bar.setFixedHeight(6)
        self.bar.setTextVisible(False)
        lay.addWidget(self.bar)

        br = QHBoxLayout()
        br.addStretch()
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedHeight(36)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel)
        br.addWidget(self.cancel_btn)
        lay.addLayout(br)

        self.worker = WorkerThread(task_func)
        self.worker.progress_status.connect(lambda t: self.status_lbl.setText(t))
        self.worker.progress_value.connect(self._set_value)
        self.worker.progress_max.connect(self._set_max)
        self.worker.finished_signal.connect(self._done)

        self.success = False
        self.was_cancelled = False
        self.error_msg = ""

    # ── 进度 ──

    def _set_max(self, value):
        self.bar.setMaximum(max(1, value))

    def _set_value(self, value):
        self.bar.setValue(value)

    # ── 生命周期 ──

    def start(self):
        self.worker.start()
        self.exec()

    def _cancel(self):
        if not self.worker.isRunning():
            self.reject()
            return
        # 只发取消请求：真正的关闭由 finished_signal 触发，
        # 保证用户无法在旧任务还在写盘时再开一个新任务。
        self.worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setText("正在取消…")
        self.status_lbl.setText("正在停止当前任务，请稍候…")

    def _done(self, ok, msg):
        self.success = ok
        self.error_msg = msg
        self.was_cancelled = self.worker.was_cancelled
        if self.was_cancelled:
            self.error_msg = "已取消"
        self.accept()

    def closeEvent(self, event):
        # 关窗口等于取消，但先等任务停下
        if self.worker.isRunning():
            self._cancel()
            event.ignore()
            return
        event.accept()

    def reject(self):
        if self.worker.isRunning():
            self._cancel()
            return
        super().reject()
