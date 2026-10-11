# -*- coding: utf-8 -*-
"""GUI 초기화 스모크 테스트 (1.5초 후 자동 종료)"""
import sys
import os
import tempfile
import shutil
import atexit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 실제 앱 설정(%APPDATA%/BgTextPresenter)을 오염시키지 않도록 별도 설정 폴더 사용
_TEST_SETTINGS = os.path.join(tempfile.gettempdir(), "bg_presenter_test_settings_gui")
os.environ["BGPT_SETTINGS_DIR"] = _TEST_SETTINGS
atexit.register(lambda: shutil.rmtree(_TEST_SETTINGS, ignore_errors=True))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor
from main_window import MainWindow

app = QApplication(sys.argv)
win = MainWindow()
win.show()

# 색상 배경 전환 테스트
win._set_color_bg(QColor("#1E88E5"), "파랑")
assert not win.presenter.is_transparent

# 투명 배경 테스트
win._set_transparent_bg()
assert win.presenter.is_transparent, "투명 배경 전환 실패"
win._set_color_bg(QColor("#000000"), "검정")

# 문단 처리 테스트용 샘플 텍스트 파일 생성 후 로드
sample_txt = os.path.join(tempfile.gettempdir(), "bg_presenter_test_paragraphs.txt")
with open(sample_txt, "w", encoding="utf-8") as f:
    f.write("첫 번째 문단입니다.\n\n두 번째 문단입니다.\n\n세 번째 문단입니다.")
win._load_text_file(sample_txt)  # 기본: 첫 문단 송출
assert win.presenter.text_overlay._text == "첫 번째 문단입니다.", "첫 문단 기본 송출 오류"

# 문단 목록에 전체 내용이 표시되어야 함 (잘리지 않고)
assert win.list_paragraphs.item(1).text() == "두 번째 문단입니다.", \
    f"문단 목록 전체 내용 표시 오류: {win.list_paragraphs.item(1).text()!r}"

# 문단 클릭 시 해당 문단만 송출
win._broadcast_paragraph(1)
assert win.presenter.text_overlay._text == "두 번째 문단입니다.", "문단 송출 내용 오류"

# 편집 모드 켜고 적용 테스트 (송출 중 즉시 반영)
win.btn_edit_toggle.setChecked(True)
win._toggle_edit_mode(True)
win.txt_editor.setPlainText("수정된 문단이 송출에 즉시 반영됩니다.")
win._apply_edit()
assert win.presenter.text_overlay._text == "수정된 문단이 송출에 즉시 반영됩니다.", "편집 적용 즉시 반영 오류"
assert win.list_paragraphs.item(1).text().startswith("수정된 문단이"), "편집 후 목록 갱신 오류"

print("색상/투명/문단/편집 모드 테스트 통과")
QTimer.singleShot(1500, lambda: (print("GUI Init Test Passed!"), app.quit()))
sys.exit(app.exec())