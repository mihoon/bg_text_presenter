# -*- coding: utf-8 -*-
"""
텍스트 슬라이드 카드의 ✏(편집) / 🗑(삭제) 단추 테스트 - python test_card_buttons.py

- 🗑 를 누르면 확인 창이 뜨고, '취소'면 그대로, '삭제'면 지워지는지
- ✏ 로 편집해도 화면(송출)에는 아무것도 나가지 않는지 (지금 나가 있는 것도 그대로)
- 편집한 뒤 그 카드를 눌러야 비로소 송출되는지
- '+' 로 새 슬라이드를 만들어도 바로 송출되지 않는지
- 단추가 아닌 카드 본문을 누르면 예전처럼 송출되는지
"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("BGPT_SETTINGS_DIR", tempfile.mkdtemp(prefix="bgpt_cardbtn_"))

from PySide6.QtWidgets import QApplication, QMessageBox, QDialog
from PySide6.QtCore import QEventLoop, QTimer, Qt, QPoint
from PySide6.QtTest import QTest

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

    def answer_next_dialog(action):
        """다음에 뜨는 모달 창에 action(창)을 실행한다"""
        def poll():
            box = QApplication.activeModalWidget()
            if box is None:
                QTimer.singleShot(30, poll)
                return
            action(box)
        QTimer.singleShot(30, poll)

    def click_message_button(label):
        def act(box):
            for btn in box.buttons():
                if btn.text() == label:
                    btn.click()
                    return
        return act

    def edit_dialog(text, mode_all=False):
        def act(dlg):
            if mode_all:
                dlg.rad_all.setChecked(True)
            dlg.editor.setPlainText(text)
            dlg.accept()
        return act

    tmp = tempfile.mkdtemp()
    text_file = os.path.join(tmp, "찬양.txt")
    with open(text_file, "w", encoding="utf-8") as f:
        f.write("첫째 슬라이드\n\n둘째 슬라이드\n\n셋째 슬라이드")

    from main_window import MainWindow, ParagraphCardDelegate
    w = MainWindow()
    w.resize(1360, 800)
    w.show()
    w._register_text_file(text_file)
    w._load_text_file(text_file, broadcast=False)
    pump(0.5)
    view = w.list_paragraphs.viewport()

    def button_center(idx, which):
        item = w.list_paragraphs.item(idx)
        edit_rect, delete_rect = ParagraphCardDelegate.card_button_rects(
            w.list_paragraphs.visualItemRect(item))
        return (edit_rect if which == "edit" else delete_rect).center()

    def click(point):
        QTest.mouseClick(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)

    print("1) 단추 위치")
    check("카드 오른쪽 위 구석에 편집·삭제 단추 자리가 있음",
          w._card_button_at(button_center(0, "delete")) == (0, "delete")
          and w._card_button_at(button_center(0, "edit")) == (0, "edit"))
    check("'+' 카드에는 단추 없음", w._card_button_at(button_center(3, "delete")) is None)

    print("\n2) 🗑 삭제 - 확인 창")
    answer_next_dialog(click_message_button(w.t("btn_cancel_plain")))
    click(button_center(1, "delete"))
    pump(0.5)
    check("'취소'를 누르면 그대로", w.paragraphs == ["첫째 슬라이드", "둘째 슬라이드", "셋째 슬라이드"], str(w.paragraphs))
    answer_next_dialog(click_message_button(w.t("btn_delete_confirm")))
    click(button_center(1, "delete"))
    pump(0.5)
    check("'삭제'를 누르면 지워짐", w.paragraphs == ["첫째 슬라이드", "셋째 슬라이드"], str(w.paragraphs))
    check("삭제 단추가 송출하지 않음", not w.presenter.has_text())

    print("\n3) ✏ 편집 - 송출하지 않음")
    answer_next_dialog(edit_dialog("고친 첫째 슬라이드"))
    click(button_center(0, "edit"))
    pump(0.5)
    check("내용이 고쳐짐", w.paragraphs[0] == "고친 첫째 슬라이드", str(w.paragraphs))
    check("편집해도 화면에 나가지 않음", not w.presenter.has_text() and w.preview._text == "",
          repr(w.presenter.text_overlay.text()))
    check("저장 전 표시(●)", w._paragraphs_dirty)

    print("\n4) 카드를 눌러야 송출")
    item_rect = w.list_paragraphs.visualItemRect(w.list_paragraphs.item(0))
    click(item_rect.center() + QPoint(0, 15))
    pump(0.3)
    check("카드 본문을 누르면 송출", w.presenter.text_overlay.text() == "고친 첫째 슬라이드",
          repr(w.presenter.text_overlay.text()))

    print("\n5) 다른 슬라이드가 나가 있는 중에 편집")
    answer_next_dialog(edit_dialog("고친 셋째 슬라이드"))
    click(button_center(1, "edit"))
    pump(0.5)
    check("나가 있던 화면은 그대로", w.presenter.text_overlay.text() == "고친 첫째 슬라이드",
          repr(w.presenter.text_overlay.text()))
    check("편집한 슬라이드는 목록에서만 바뀜", w.paragraphs[1] == "고친 셋째 슬라이드")
    answer_next_dialog(edit_dialog("화면에 나가 있는 것을 고침"))
    click(button_center(0, "edit"))
    pump(0.5)
    check("지금 나가 있는 슬라이드를 고쳐도 화면은 그대로 (눌러야 반영)",
          w.presenter.text_overlay.text() == "고친 첫째 슬라이드", repr(w.presenter.text_overlay.text()))

    print("\n6) '+' 새 슬라이드도 바로 송출하지 않음")
    w._clear_text()
    answer_next_dialog(edit_dialog("새로 만든 슬라이드"))
    w._add_new_paragraph_card()
    pump(0.3)
    check("새 슬라이드가 목록에 추가됨", w.paragraphs[-1] == "새로 만든 슬라이드", str(w.paragraphs))
    check("만들어도 화면에 나가지 않음", not w.presenter.has_text())

    print("\n7) 오른쪽 편집기 - 화면에 아무것도 없을 때는 띄우지 않음")
    count_before = len(w.paragraphs)
    answer_next_dialog(edit_dialog("편집기로 쓴 글"))
    w._open_edit_dialog()
    pump(0.3)
    check("화면에 아무것도 띄우지 않음", not w.presenter.has_text())
    check("기존 슬라이드를 지우지 않고 덧붙임", len(w.paragraphs) == count_before + 1, str(w.paragraphs))

    w.close()
    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
