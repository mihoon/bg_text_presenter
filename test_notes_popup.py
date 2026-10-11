# -*- coding: utf-8 -*-
"""
노트 따로 보기(언제나 맨 위 창) 테스트 - python test_notes_popup.py

- '🗗 노트 따로 보기'로 창이 뜨고, 본 창에 딸린 도구 창인지
  (본 창 앞에는 늘 있지만 '항상 위'가 아니라서 다른 프로그램을 가리지 않는다)
- 송출하는 슬라이드/사진에 따라 노트가 바뀌는지 (PPT 노트, 사진 속 숨은 글)
- 노트 창에서 →/← 를 눌러도 슬라이드가 넘어가는지, Ctrl+C 는 가로채지 않는지
- 창을 닫으면 단추가 꺼지고, 글자 크기·위치가 다음에도 유지되는지
- 켜 두면 노트가 없는 슬라이드·사진에서는 저절로 숨고, 있으면 다시 뜨는지
- 꺼 두면 노트가 있어도 뜨지 않는지
"""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="bgpt_notes_popup_")
os.environ["BGPT_SETTINGS_DIR"] = os.path.join(_TMP, "settings")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtTest import QTest

import numpy as np
from PIL import Image

import image_notes

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

    folder = os.path.join(_TMP, "사진들")
    os.makedirs(folder)
    arr = np.random.default_rng(5).integers(0, 255, (90, 160, 3), dtype=np.uint8)
    paths = []
    for i in range(3):
        p = os.path.join(folder, f"{i + 1:02d}.jpg")
        Image.fromarray(arr).save(p)
        paths.append(p)
    image_notes.write_note(paths[0], "첫째 사진 노트")
    image_notes.write_note(paths[2], "셋째 사진 노트")

    from main_window import MainWindow, NotesPopup
    w = MainWindow()
    w.resize(1300, 820)
    w.show()
    pump(0.3)
    w._load_image_folder(folder, broadcast=False)
    pump(0.3)

    print("0) 꺼 둔 상태에서는 노트가 있어도 뜨지 않음")
    w._present_media_slide(0)
    pump(0.2)
    check("창이 없음", getattr(w, "notes_popup", None) is None)

    print("\n1) 노트 따로 보기 창")
    check("단추가 보임", w.btn_notes_popup.isVisible())
    w.btn_notes_popup.click()
    pump(0.3)
    pop = getattr(w, "notes_popup", None)
    check("노트가 있는 사진이 송출 중 → 창이 뜸", isinstance(pop, NotesPopup) and pop.isVisible())
    flags = pop.windowFlags()
    check("'항상 위'가 아님 (다른 프로그램을 가리지 않음)",
          not (flags & Qt.WindowType.WindowStaysOnTopHint))
    check("작업 표시줄에 안 나오는 도구 창", (flags & Qt.WindowType.Tool) == Qt.WindowType.Tool)
    check("본 창에 딸린 창 (본 창 뒤로 넘어가지 않음)", pop.parent() is w and pop.isWindow())
    check("띄울 때 키보드 초점을 빼앗지 않음",
          pop.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))
    check("맨 위로 다시 끌어올리는 동작 없음", not hasattr(pop, "_top_timer"))

    print("\n2) 송출하는 사진을 따라 노트가 바뀜")
    w._present_media_slide(0)
    pump(0.2)
    check("첫째 사진 노트", pop.text.toPlainText() == "첫째 사진 노트", repr(pop.text.toPlainText()))
    check("몇 번째 사진인지 + 이름", pop.lbl_where.text().startswith(f"{w.t('image_prefix')} 1/3")
          and "01.jpg" in pop.lbl_where.text(), pop.lbl_where.text())
    w._present_media_slide(1)
    pump(0.2)
    check("노트 없는 사진 → 창이 저절로 숨음", not pop.isVisible())
    check("숨어도 노트 따로 보기는 켜진 채", w.btn_notes_popup.isChecked())
    w._present_media_slide(2)
    pump(0.2)
    check("노트 있는 사진 → 다시 뜸", pop.isVisible() and pop.text.toPlainText() == "셋째 사진 노트",
          repr(pop.text.toPlainText()))
    w._present_media_slide(1)
    pump(0.2)

    print("\n3) 노트 창에서 키를 눌러 슬라이드 넘기기")
    w._present_media_slide(0)
    pump(0.2)
    pop.activateWindow()
    pop.text.setFocus()
    QTest.keyClick(pop.text, Qt.Key.Key_Right)
    pump(0.2)
    check("→ 로 다음 사진", w.media_slide_index == 1, str(w.media_slide_index))
    check("노트 없는 사진으로 넘어가면 숨음", not pop.isVisible())
    w._present_media_slide(2)
    pump(0.2)
    pop.activateWindow()
    QTest.keyClick(pop, Qt.Key.Key_PageUp)
    pump(0.2)
    check("PageUp 으로 앞 사진", w.media_slide_index == 1, str(w.media_slide_index))
    w._present_media_slide(2)
    pump(0.2)
    before = w.media_slide_index
    QTest.keyClick(pop.text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    pump(0.1)
    check("Ctrl+C 는 가로채지 않음 (슬라이드 그대로)", w.media_slide_index == before)

    print("\n4) 숨은 글을 고치면 노트 창에도 바로")
    w._present_media_slide(1)              # 노트 없는 사진 송출 중 (창은 숨어 있음)
    pump(0.2)
    w.list_paragraphs.setCurrentRow(1)
    from PySide6.QtCore import QTimer

    def answer():
        dlg = QApplication.activeModalWidget()
        if dlg is None:
            QTimer.singleShot(30, answer)
            return
        dlg._editor.setPlainText("새로 넣은 노트")
        dlg.accept()
    QTimer.singleShot(30, answer)
    w._edit_image_note(1)
    pump(0.3)
    check("숨은 글을 넣으면 창이 뜨고 반영", pop.isVisible() and pop.text.toPlainText() == "새로 넣은 노트",
          repr(pop.text.toPlainText()))

    print("\n5) PPT 노트")
    w.current_source_type = "folder"
    w.media_source_kind = "pptx"
    w.media_slides = [os.path.join(_TMP, "s1.png"), os.path.join(_TMP, "s2.png")]
    w.media_notes = ["설교 1대지: 은혜", "설교 2대지: 순종"]
    w._update_side_panel_mode()
    w._show_slide_notes(1)
    pump(0.1)
    check("PPT 노트가 보임", pop.isVisible() and pop.text.toPlainText() == "설교 2대지: 순종",
          repr(pop.text.toPlainText()))
    check("슬라이드 번호", pop.lbl_where.text() == f"{w.t('slide_prefix')} 2/2", pop.lbl_where.text())
    w.media_notes = ["설교 1대지: 은혜", ""]
    w.media_slides.append(os.path.join(_TMP, "s3.png"))
    w.media_notes.append("   ")
    w._show_slide_notes(1)
    pump(0.1)
    check("노트 없는 슬라이드 → 숨음", not pop.isVisible())
    w._show_slide_notes(2)
    pump(0.1)
    check("빈칸뿐인 노트도 없는 것으로 → 숨음", not pop.isVisible())
    w._show_slide_notes(0)
    pump(0.1)
    check("노트 있는 슬라이드 → 다시 뜸", pop.isVisible() and pop.text.toPlainText() == "설교 1대지: 은혜")

    print("\n6) 노트가 없는 모드 (텍스트)")
    text_file = os.path.join(_TMP, "찬양.txt")
    with open(text_file, "w", encoding="utf-8") as f:
        f.write("첫째\n\n둘째")
    w._register_text_file(text_file)
    w._load_text_file(text_file, broadcast=False)
    pump(0.2)
    check("노트가 없는 모드 → 숨음", not pop.isVisible())
    check("그래도 켜진 채", w.btn_notes_popup.isChecked())

    print("\n7) 글자 크기 / 닫기 / 다시 열기")
    w._load_image_folder(folder, broadcast=False)
    w._present_media_slide(0)
    pump(0.2)
    check("이미지 폴더로 돌아와 노트 있는 사진 → 다시 뜸", pop.isVisible())
    pop.btn_bigger.click()
    pop.btn_bigger.click()
    check("A+ 로 글자 키우기", pop.text.font().pointSize() == 24, str(pop.text.font().pointSize()))
    pop.move(pop.x() + 30, pop.y() + 20)
    pump(0.1)
    pos_before = pop.pos()
    pop.close()
    pump(0.2)
    check("창을 닫으면(X) 단추가 꺼짐", not w.btn_notes_popup.isChecked())
    w._present_media_slide(2)
    pump(0.2)
    check("끈 뒤에는 노트가 있어도 뜨지 않음", not pop.isVisible())
    w._present_media_slide(0)
    pump(0.2)
    w.btn_notes_popup.click()
    pump(0.2)
    check("다시 열면 같은 창", w.notes_popup is pop and pop.isVisible())
    check("단추를 다시 누르면 닫힘", (w.btn_notes_popup.click(), pump(0.2), not pop.isVisible())[2])
    w.close()
    pump(0.2)

    w2 = MainWindow()
    w2.show()
    pump(0.2)
    w2._load_image_folder(folder, broadcast=False)
    w2._present_media_slide(0)
    w2.btn_notes_popup.click()
    pump(0.3)
    pop2 = w2.notes_popup
    check("다음에 켜도 글자 크기 유지", pop2.text.font().pointSize() == 24, str(pop2.text.font().pointSize()))
    check("다음에 켜도 위치 유지", (pop2.pos() - pos_before).manhattanLength() < 40,
          f"{pop2.pos()} vs {pos_before}")
    w2.close()
    pump(0.2)
    check("본 창을 닫으면 노트 창도 닫힘", not pop2.isVisible())

    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    code = main()
    shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
