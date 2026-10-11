# -*- coding: utf-8 -*-
"""
슬라이드 노트 칸 크기 조절 테스트 - python test_notes_resize.py

- 오른쪽 칸을 넓혀도 아래 미리보기가 위아래로 커지면서 노트를 밀어내지 않는지
- 노트와 미리보기 사이 경계를 끌어 노트를 위아래로 넓힐 수 있는지
- 미리보기는 남은 자리 안에서 송출 화면 비율(16:9)을 그대로 지키는지
- 텍스트 모드로 돌아와도 미리보기가 제대로 보이는지
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BGPT_SETTINGS_DIR", tempfile.mkdtemp(prefix="bgpt_notes_resize_"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"   OK   {label}")
    else:
        print(f"   실패 {label}  {detail}")
        FAILURES.append(label)


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    def pump(sec=0.2):
        end = time.time() + sec
        while time.time() < end:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            time.sleep(0.01)

    from main_window import MainWindow
    w = MainWindow()
    w.resize(1500, 900)
    w.show()
    pump(0.3)
    w.preview.set_screen_aspect(1920, 1080)

    # PPT 모드 (노트 칸이 보이는 상태)
    w.current_source_type = "folder"
    w.media_source_kind = "pptx"
    w._update_side_panel_mode()
    w.txt_slide_notes.setPlainText("노트 " * 400)
    pump(0.3)
    check("PPT 모드에서 노트 칸이 보임", w.grp_notes.isVisible())

    def aspect_ok():
        pw, ph = w.preview.width(), w.preview.height()
        return ph > 0 and abs(pw / ph - 16 / 9) < 0.03, f"{pw}x{ph}"

    print("1) 오른쪽 칸을 넓게")
    total = sum(w.main_splitter.sizes())
    w.main_splitter.setSizes([220, total - 220 - 800, 800])
    pump(0.3)
    right_w = w.main_splitter.sizes()[2]
    check("오른쪽 칸이 넓어짐", right_w >= 700, str(w.main_splitter.sizes()))

    print("\n2) 노트를 위아래로 넓히기 (경계를 아래로)")
    rs = w.right_splitter
    before_notes = w.txt_slide_notes.height()
    rs_total = sum(rs.sizes())
    rs.setSizes([rs_total - 160, 160])
    pump(0.3)
    sizes = rs.sizes()
    print(f"   (오른쪽 위/아래 크기: {sizes}, 노트 높이 {before_notes} → {w.txt_slide_notes.height()},"
          f" 미리보기 {w.preview.width()}x{w.preview.height()})")
    check("미리보기 칸을 작게 줄일 수 있음", sizes[1] <= 200, str(sizes))
    check("노트 칸이 위아래로 커짐", w.txt_slide_notes.height() > before_notes + 150,
          f"{before_notes} → {w.txt_slide_notes.height()}")
    ok, detail = aspect_ok()
    check("작아진 미리보기도 16:9 비율 유지", ok, detail)
    check("미리보기가 칸 밖으로 넘치지 않음",
          w.preview.height() <= sizes[1] and w.preview.width() <= right_w, detail)

    print("\n3) 다시 미리보기를 크게")
    rs.setSizes([260, rs_total - 260])
    pump(0.3)
    ok, detail = aspect_ok()
    check("미리보기가 넓은 칸에 맞춰 커짐", w.preview.width() > 600, detail)
    check("비율 유지", ok, detail)

    print("\n4) 송출 모니터 비율이 바뀌면 (4:3)")
    w.preview.set_screen_aspect(1024, 768)
    pump(0.2)
    pw, ph = w.preview.width(), w.preview.height()
    check("4:3 비율로 바뀜", ph > 0 and abs(pw / ph - 4 / 3) < 0.03, f"{pw}x{ph}")
    w.preview.set_screen_aspect(1920, 1080)

    print("\n5) 텍스트 모드로 돌아오기")
    w.current_source_type = "text"
    w.media_source_kind = "folder"
    w._update_side_panel_mode()
    pump(0.3)
    ok, detail = aspect_ok()
    check("텍스트 모드에서도 미리보기 비율 유지", ok, detail)
    check("미리보기가 보임", w.preview.isVisible() and w.preview.width() > 100, detail)

    w.close()
    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
