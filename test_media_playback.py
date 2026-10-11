# -*- coding: utf-8 -*-
"""
동영상 배경 실재생 테스트 (2초짜리 동영상 2개를 생성해 재생목록 반복 검증)
"""
import os
import sys
import tempfile
import shutil
import atexit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 실제 앱 설정(%APPDATA%/BgTextPresenter)을 오염시키지 않도록 별도 설정 폴더 사용
_TEST_SETTINGS = os.path.join(tempfile.gettempdir(), "bg_presenter_test_settings_media")
os.environ["BGPT_SETTINGS_DIR"] = _TEST_SETTINGS
atexit.register(lambda: shutil.rmtree(_TEST_SETTINGS, ignore_errors=True))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtMultimedia import QMediaPlayer

import cv2
import numpy as np
from PIL import Image


def make_test_video(path, color, seconds=2.0, fps=24):
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 180))
    b, g, r = color
    for i in range(int(fps * seconds)):
        frame = ((i * 3) % 255, g, r)  # 살짝 변화하는 색
        img = Image.new("RGB", (320, 180), frame)
        writer.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))
    writer.release()


app = QApplication(sys.argv)

tmp = tempfile.gettempdir()
v1 = os.path.join(tmp, "bg_test_red.mp4")
v2 = os.path.join(tmp, "bg_test_blue.mp4")
make_test_video(v1, (60, 60, 220))
make_test_video(v2, (220, 120, 60))

from main_window import MainWindow
from PySide6.QtGui import QColor

win = MainWindow()
win.show()

# 이미지 배경 전환 테스트 (임시 이미지)
img_path = os.path.join(tmp, "bg_test_image.png")
Image.new("RGB", (640, 360), (20, 90, 160)).save(img_path)
win._set_image_bg(img_path)
assert win.presenter.bg_image_path == img_path, "이미지 배경 설정 실패"

# 동영상 2개 재생목록 반복 재생
win._add_video_item(v1, checked=True)
win._add_video_item(v2, checked=True)
win._play_selected_videos()
assert win.presenter.playlist == [v1, v2], f"재생목록 오류: {win.presenter.playlist}"

result = {"ok": False}


def check_playback():
    state = win.presenter.player.playbackState()
    status = win.presenter.player.mediaStatus()
    if state == QMediaPlayer.PlaybackState.PlayingState and win.presenter.playlist_index == 1:
        # 첫 영상 종료 후 두 번째 영상으로 넘어감 = 반복 재생목록 동작 확인
        result["ok"] = True
        print(f"Media playback PASS (playlist_index={win.presenter.playlist_index})")
        app.quit()
        return
    if status == QMediaPlayer.MediaStatus.InvalidMedia:
        print("Media playback FAIL: InvalidMedia (코덱 부족?)")
        app.exit(1)
        return


timer = QTimer()
timer.timeout.connect(check_playback)
timer.start(500)
QTimer.singleShot(15000, lambda: (print("Media playback FAIL: timeout"), app.exit(1)))
sys.exit(app.exec())