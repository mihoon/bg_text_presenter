# -*- coding: utf-8 -*-
"""
회귀 테스트 (오프스크린, 자동 종료)

검증 항목:
 1. 대화상자 안에서 Enter/Esc 가 전역 이벤트 필터에 먹히지 않는다.
 2. "파일로 저장" 경로에서 쓰는 _register_text_file 이 라이브러리에 등록한다.
 3. 실시간 직접 입력 송출 중 키 입력마다 동영상 배경이 재시작되지 않는다.
    (이미지 폴더 모드에서 빠져나올 때는 여전히 배경을 복원한다)
 4. 선택한 배경이 재시작 후에도 설정에 남고 복원된다.
 5. 띄어쓰기 없는 긴 문자열이 화면 폭 안에서 줄바꿈된다.
"""
import os
import sys
import shutil
import tempfile
import atexit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_TEST_SETTINGS = os.path.join(tempfile.gettempdir(), "bg_presenter_test_settings_regress")
shutil.rmtree(_TEST_SETTINGS, ignore_errors=True)
os.environ["BGPT_SETTINGS_DIR"] = _TEST_SETTINGS
atexit.register(lambda: shutil.rmtree(_TEST_SETTINGS, ignore_errors=True))

from PIL import Image
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QVBoxLayout
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFontMetrics

from main_window import MainWindow
from presenter_window import wrap_text_lines, TextStyle

app = QApplication(sys.argv)
tmp = tempfile.mkdtemp(prefix="bgpt_regress_")
atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))

NL = chr(10)
txt = os.path.join(tmp, "paras.txt")
with open(txt, "w", encoding="utf-8") as f:
    f.write("문단 하나" + NL + NL + "문단 둘" + NL + NL + "문단 셋")

win = MainWindow()
win.show()
win._load_text_file(txt)
assert win.paragraph_index == 0

# ---------------------------------------------------------------- 1. 대화상자 키 입력
dlg = QDialog(win)
lay = QVBoxLayout(dlg)
btn = QPushButton("OK", dlg)
btn.setDefault(True)
lay.addWidget(btn)
clicked = []
btn.clicked.connect(lambda: clicked.append(1))
dlg.show()
btn.setFocus()
app.processEvents()

QTest.keyClick(btn, Qt.Key.Key_Return)
app.processEvents()
assert clicked, "대화상자에서 Enter 가 버튼을 누르지 못함 (전역 필터가 가로챔)"
assert win.paragraph_index == 0, f"대화상자 Enter 가 문단을 넘김: {win.paragraph_index}"

QTest.keyClick(btn, Qt.Key.Key_Escape)
app.processEvents()
assert not dlg.isVisible(), "대화상자에서 Esc 로 창이 닫히지 않음"

# 메인 창에서는 여전히 Enter/Space 로 문단이 넘어가야 함
win.list_paragraphs.setFocus()
app.processEvents()
QTest.keyClick(win.list_paragraphs, Qt.Key.Key_Return)
app.processEvents()
assert win.paragraph_index == 1, f"메인 창 문단 넘김 회귀: {win.paragraph_index}"
win._broadcast_paragraph(0)

# ---------------------------------------------------------------- 2. _register_text_file
other = os.path.join(tmp, "direct.txt")
with open(other, "w", encoding="utf-8") as f:
    f.write("직접 작성")
win._register_text_file(other)
registered = win._get_registered_text_files()
assert other in registered, f"라이브러리 등록 실패: {registered}"
cur = win.list_text_files.currentItem()
assert cur is not None and cur.data(Qt.ItemDataRole.UserRole) == other, "등록 후 목록 선택 실패"
win._register_text_file(other)
assert win._get_registered_text_files().count(other) == 1, "중복 등록됨"

# ---------------------------------------------------------------- 3. 실시간 송출 + 동영상 배경
calls = []
orig_play = win.presenter.play_playlist
win.presenter.play_playlist = lambda paths, start_index=0: calls.append(list(paths))
win.settings.setValue("bg/type", "video")
win.settings.setValue("bg/value", txt)   # 존재하는 파일이면 충분 (실제 재생은 스텁)

win.para_tab.setCurrentIndex(1)
win.chk_direct_realtime.setChecked(True)
win.txt_direct_input.setFocus()
QTest.keyClicks(win.txt_direct_input, "abcde")
app.processEvents()
assert len(calls) == 0, f"직접 입력 5회에 동영상이 {len(calls)}번 재시작됨"
assert win.presenter.text_overlay._text == "abcde", "실시간 송출 텍스트 반영 실패"
win.chk_direct_realtime.setChecked(False)
win.txt_direct_input.clear()

# 이미지 폴더 모드 -> 직접 입력: 이 경우에는 배경을 복원해야 함
folder = os.path.join(tmp, "imgs")
os.makedirs(folder)
Image.new("RGB", (64, 36), (200, 40, 40)).save(os.path.join(folder, "a.jpg"))
win.settings.setValue("bg/type", "color")
win.settings.setValue("bg/value", "#1e88e5")
win._load_image_folder(folder)
assert win.current_source_type == "folder" and win.presenter.bg_image_path.endswith("a.jpg")
win._broadcast_direct_text("폴더에서 전환")
assert win.presenter.bg_image_path == "", "폴더 모드 이탈 시 슬라이드 배경이 남음"
assert win.presenter.bg_color.name() == "#1e88e5", f"폴더 모드 이탈 시 배경 미복원: {win.presenter.bg_color.name()}"

# 이미지 폴더 모드 -> 텍스트 파일 열기(문단 송출) 도 동일
win._load_image_folder(folder)
win._load_text_file(txt)
assert win.paragraph_index == 0 and win.presenter.text_overlay._text == "문단 하나"
assert win.presenter.bg_image_path == "" and win.presenter.bg_color.name() == "#1e88e5", "폴더->문단 배경 미복원"
win.presenter.play_playlist = orig_play

# ---------------------------------------------------------------- 4. 배경 설정 재시작 후 유지/복원
# 시작 직후: 화면은 투명 + 빈 텍스트, 설정은 유지. 첫 송출 때 저장된 배경이 적용된다.
win._set_color_bg(QColor("#43A047"), "초록")
win.settings.sync()
win2 = MainWindow()
assert win2.settings.value("bg/type") == "color", f"재시작 시 bg/type 덮어씀: {win2.settings.value('bg/type')!r}"
assert str(win2.settings.value("bg/value")).lower() == "#43a047"
assert win2.presenter.is_transparent, "시작 직후 화면은 투명이어야 함"
assert win2.presenter.text_overlay._text == "", "재시작 시 텍스트가 비어 있어야 함"
assert win2.paragraphs, "마지막 텍스트 파일이 다시 열려야 함"
win2._broadcast_paragraph(0)
assert not win2.presenter.is_transparent and win2.presenter.bg_color.name() == "#43a047",     f"첫 송출 시 저장된 배경 미복원: transparent={win2.presenter.is_transparent} color={win2.presenter.bg_color.name()}"
assert win2.settings.value("bg/type") == "color", "복원 과정에서 설정이 바뀜"
win2.close()

# 직접 입력으로 첫 송출해도 동일
win2b = MainWindow()
assert win2b.presenter.is_transparent
win2b._broadcast_direct_text("첫 송출")
assert win2b.presenter.bg_color.name() == "#43a047" and not win2b.presenter.is_transparent, "직접 입력 첫 송출 시 배경 미복원"
win2b.close()

# 시작 직후 사용자가 배경을 직접 고르면 그 선택이 유지되어야 함 (첫 송출 때 덮어쓰지 않음)
win2c = MainWindow()
win2c._set_color_bg(QColor("#E53935"), "빨강")
win2c._broadcast_paragraph(0)
assert win2c.presenter.bg_color.name() == "#e53935", "시작 후 직접 고른 배경이 첫 송출 때 덮어써짐"
win2c.close()

# 저장된 배경이 없으면(첫 실행) 투명이 기본
shutil.rmtree(_TEST_SETTINGS, ignore_errors=True)
win3 = MainWindow()
assert win3.presenter.is_transparent, "첫 실행 기본 배경은 투명이어야 함"
win3.close()

# ---------------------------------------------------------------- 5. 긴 단어 줄바꿈
font = TextStyle(size=48).make_font()
fm = QFontMetrics(font)
for sample in ("가" * 80, "http://example.com/" + "a" * 120, "짧은 말 " + "나" * 60 + " 뒤에 붙는 말"):
    lines = wrap_text_lines(font, sample, 800)
    widest = max(fm.horizontalAdvance(l) for l in lines)
    assert widest <= 800, f"줄 폭 초과: {widest}px > 800px ({sample[:12]}…)"
    assert "".join(lines).replace(" ", "") == sample.replace(" ", ""), "줄바꿈 중 글자 유실"
assert wrap_text_lines(font, "hello world", 10_000) == ["hello world"], "일반 문장 줄바꿈 회귀"
assert wrap_text_lines(font, "a" + NL + "b", 10_000) == ["a", "b"], "하드 줄바꿈 유지 회귀"

win.close()
print("All regression tests passed!")
sys.exit(0)
