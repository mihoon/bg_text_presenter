# -*- coding: utf-8 -*-
import sys
import os
import time
import ctypes
import tempfile
import threading

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt

from main_window import MainWindow


class _LogTee:
    """print() 출력을 로그 파일에도 남긴다 (exe 는 콘솔이 없어 출력이 사라지기 때문).

    %LOCALAPPDATA%\\BgTextPresenter\\logs\\app.log - 1MB 가 넘으면 app.old.log 로 넘긴다.
    파워포인트 애니메이션 모드가 어디서 느린지 같은 문제를 나중에 확인하는 데 쓴다.
    """

    def __init__(self, original, log_file, lock):
        self._original = original
        self._file = log_file
        self._lock = lock
        self._line_start = True

    def write(self, text):
        if self._original is not None:
            try:
                self._original.write(text)
            except Exception:
                pass
        if not text:
            return 0
        with self._lock:
            try:
                out = []
                for piece in text.splitlines(keepends=True):
                    if self._line_start:
                        out.append(time.strftime("%H:%M:%S "))
                    out.append(piece)
                    self._line_start = piece.endswith("\n")
                self._file.write("".join(out))
                self._file.flush()
            except Exception:
                pass
        return len(text)

    def flush(self):
        if self._original is not None:
            try:
                self._original.flush()
            except Exception:
                pass


def _setup_log_file():
    try:
        log_dir = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(),
                               "BgTextPresenter", "logs")
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "app.log")
        if os.path.exists(path) and os.path.getsize(path) > 1_000_000:
            os.replace(path, os.path.join(log_dir, "app.old.log"))
        log_file = open(path, "a", encoding="utf-8")
        log_file.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} 프로그램 시작 =====\n")
        lock = threading.Lock()
        sys.stdout = _LogTee(sys.stdout, log_file, lock)
        sys.stderr = _LogTee(sys.stderr, log_file, lock)
    except Exception:
        pass    # 로그를 못 남겨도 프로그램은 그대로 동작해야 한다


def main():
    started = time.perf_counter()
    _setup_log_file()
    # Windows 작업표시줄 고유 앱 ID
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("bgtextpresenter.dualmonitor.1.0")
    except Exception:
        pass

    # 고해상도 모니터 지원
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("배경 텍스트 프리젠터")
    app.setOrganizationName("BgTextPresenter")

    base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    icon_path = os.path.join(base_dir, "app_icon.png")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    if os.path.exists(icon_path):
        window.setWindowIcon(QIcon(icon_path))
    window.show()
    print(f"[시작] 창 표시까지 {time.perf_counter() - started:.1f}초")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()