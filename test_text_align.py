# -*- coding: utf-8 -*-
"""
글자 세로 위치(위/가운데/아래)와 위·아래 여백 테스트 - python test_text_align.py

송출 창을 실제로 그려서 글자가 있는 줄의 위치를 재어 본다.
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BGPT_SETTINGS_DIR", tempfile.mkdtemp(prefix="bgpt_align_"))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop
from PySide6.QtGui import QColor

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
    w.show()
    w.paragraphs = ["주님의 사랑이\n우리를 새롭게 하시니"]
    w.current_source_type = "text"
    w._rebuild_paragraph_list()
    w._set_color_bg(QColor("#123456"), "test")
    w._broadcast_paragraph(0)
    w.presenter.resize(960, 540)
    pump()
    height = 540

    def text_rows():
        img = w.presenter.grab().toImage()
        rows = [y for y in range(img.height())
                if any(img.pixelColor(x, y).lightness() > 200 for x in range(0, img.width(), 4))]
        return (rows[0], rows[-1]) if rows else (None, None)

    w.spin_margin_top.setValue(5)
    w.spin_margin_bottom.setValue(5)
    w._set_text_valign("top")
    pump()
    top = text_rows()
    w._set_text_valign("center")
    pump()
    mid = text_rows()
    w._set_text_valign("bottom")
    pump()
    bottom = text_rows()
    print(f"   (글자 줄 위치: 위 {top}, 가운데 {mid}, 아래 {bottom})")
    check("위 정렬은 위쪽 여백(5%) 바로 아래", top[0] is not None and height * 0.05 <= top[0] < height * 0.15, str(top))
    check("가운데 정렬은 가운데", mid[0] is not None and abs((mid[0] + mid[1]) / 2 - height / 2) < height * 0.06, str(mid))
    check("아래 정렬은 아래쪽 여백(5%) 바로 위", bottom[1] is not None and height * 0.85 < bottom[1] <= height * 0.95, str(bottom))

    w._set_text_valign("center")
    check("가운데 정렬에서는 여백 칸을 감춤",
          not w.spin_margin_top.isVisible() and not w.spin_margin_bottom.isVisible())
    w.spin_margin_top.setValue(40)
    pump()
    check("가운데 정렬은 여백과 상관없이 화면 한가운데", text_rows() == mid, f"{text_rows()} vs {mid}")
    w.spin_margin_top.setValue(5)
    w._set_text_valign("bottom")
    pump()
    check("위/아래 정렬에서는 여백 칸이 보임", w.spin_margin_top.isVisible() and w.spin_margin_bottom.isVisible())
    w.spin_margin_bottom.setValue(30)
    pump()
    raised = text_rows()
    check("아래 여백 30% → 글자가 화면 70% 위에서 끝남",
          raised[1] is not None and height * 0.6 < raised[1] <= height * 0.70, str(raised))
    w.spin_margin_top.setValue(20)
    w._set_text_valign("top")
    pump()
    lowered = text_rows()
    check("위 여백 20% → 글자가 화면 20% 아래에서 시작",
          lowered[0] is not None and height * 0.20 <= lowered[0] < height * 0.30, str(lowered))
    check("미리보기에도 같은 설정", w.preview._style.valign == "top" and w.preview._style.margin_top == 20)

    w.close()
    pump()
    w2 = MainWindow()
    pump()
    check("다시 켜도 세로 위치 유지", w2._text_valign == "top"
          and w2.valign_buttons["top"].isChecked(), w2._text_valign)
    check("다시 켜도 여백 유지", w2.spin_margin_top.value() == 20 and w2.spin_margin_bottom.value() == 30,
          f"{w2.spin_margin_top.value()} / {w2.spin_margin_bottom.value()}")
    check("송출 창에도 되살아난 설정 적용", w2.presenter.text_overlay._style.valign == "top")
    w2.close()

    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
