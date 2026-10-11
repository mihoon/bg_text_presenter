# -*- coding: utf-8 -*-
"""동영상 재생목록 반복(마지막 -> 처음) 로직 테스트"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from presenter_window import PresenterWindow

app = QApplication(sys.argv)
w = PresenterWindow()

# 실제 파일 존재 검사 통과용 임시 파일 (미디어 로드는 하지 않음)
import tempfile
v1 = os.path.join(tempfile.gettempdir(), "bg_playlist_a.mp4")
v2 = os.path.join(tempfile.gettempdir(), "bg_playlist_b.mp4")
v3 = os.path.join(tempfile.gettempdir(), "bg_playlist_c.mp4")
for p in (v1, v2, v3):
    with open(p, "wb") as f:
        f.write(b"dummy")
VIDS = [v1, v2, v3]

# 실제 미디어 로드 없이 재생목록 회전만 검증
played = []
w._load_current_video = lambda: played.append(w.playlist_index)

w.play_playlist(VIDS, 0)
assert played == [0], f"첫 재생 인덱스 오류: {played}"

w._advance_playlist()
w._advance_playlist()
assert played == [0, 1, 2], f"재생목록 진행 오류: {played}"

# 마지막 영상 종료 -> 다시 처음부터 (반복)
w._advance_playlist()
assert played == [0, 1, 2, 0], f"반복(처음 복귀) 오류: {played}"

# 중간부터 시작 테스트
played.clear()
w.play_playlist(VIDS, 1)
assert played == [1], f"중간 시작 오류: {played}"

# 단일 영상 반복 테스트
played.clear()
w.play_playlist([v1], 0)
w._advance_playlist()
assert played == [0, 0], f"단일 영상 반복 오류: {played}"

# 빈 목록은 무시
played.clear()
w.play_playlist([], 0)
assert played == [], f"빈 목록 처리 오류: {played}"

print("All playlist tests passed!")
sys.exit(0)