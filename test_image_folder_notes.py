# -*- coding: utf-8 -*-
"""
이미지 폴더의 '사진 속 숨은 글' 화면 테스트 - python test_image_folder_notes.py

- 이미지 폴더를 열면 오른쪽 칸이 PPT 처럼 노트 칸으로 바뀌는지
- 숨은 글이 있는 사진 카드에 📝 표시
- 사진을 송출하면 그 사진의 숨은 글이 노트 칸에 보이는지
- '✏ 숨은 글 편집'으로 넣은 글이 사진 파일에 저장되고, 송출은 바뀌지 않는지
- GIF 처럼 넣을 수 없는 형식은 안내만 하고 파일을 건드리지 않는지
- 텍스트 / PPT 모드로 돌아가면 원래 칸이 보이는지
"""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="bgpt_imgfolder_notes_")
os.environ["BGPT_SETTINGS_DIR"] = os.path.join(_TMP, "settings")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QPixmap

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

    def answer_next_dialog(action):
        def poll():
            box = QApplication.activeModalWidget()
            if box is None:
                QTimer.singleShot(30, poll)
                return
            action(box)
        QTimer.singleShot(30, poll)

    def write_in_dialog(text):
        def act(dlg):
            dlg._editor.setPlainText(text)
            dlg.accept()
        return act

    folder = os.path.join(_TMP, "주일광고")
    os.makedirs(folder)
    rng = np.random.default_rng(3)
    arr = rng.integers(0, 255, (180, 320, 3), dtype=np.uint8)
    p1 = os.path.join(folder, "01 환영.jpg")
    p2 = os.path.join(folder, "02 광고.png")
    p3 = os.path.join(folder, "03 움짤.gif")
    Image.fromarray(arr).save(p1, quality=90)
    Image.fromarray(arr).save(p2)
    Image.fromarray(arr).save(p3)
    image_notes.write_note(p1, "새가족 환영 멘트\n- 이름 불러 주기")
    gif_size = os.path.getsize(p3)

    from main_window import MainWindow
    w = MainWindow()
    w.resize(1400, 860)
    w.show()
    pump(0.3)

    print("1) 이미지 폴더 열기 - 오른쪽이 노트 칸으로")
    w._load_image_folder(folder, broadcast=False)
    pump(0.4)
    check("노트 칸이 보임", w.grp_notes.isVisible())
    check("제목이 '사진 노트'", w.grp_notes.title() == w.t("image_notes_group"), w.grp_notes.title())
    check("텍스트 편집/글자 스타일은 숨김", not w.grp_edit.isVisible() and not w.grp_style.isVisible())
    check("'숨은 글 편집' 단추가 보임", w.btn_image_note_edit.isVisible())
    check("숨은 글 있는 사진 카드에 📝", w.list_paragraphs.item(0).text().startswith("📝"),
          w.list_paragraphs.item(0).text())
    check("없는 사진 카드에는 표시 없음", not w.list_paragraphs.item(1).text().startswith("📝"),
          w.list_paragraphs.item(1).text())
    check("사진 카드에는 풍선 도움말이 없음",
          all(not w.list_paragraphs.item(i).toolTip() for i in range(w.list_paragraphs.count())))
    from main_window import ParagraphCardDelegate
    font = w.list_paragraphs.font()
    item0 = w.list_paragraphs.item(0)
    card_h, icon_w, thumb_h = ParagraphCardDelegate.media_card_size(item0.sizeHint().width(), font)
    title_h = ParagraphCardDelegate.media_title_height(font)
    check("카드 높이 = 그림 칸 + 이름 칸 (겹치지 않음)",
          item0.sizeHint().height() == card_h
          and card_h >= thumb_h + title_h + 2 * ParagraphCardDelegate.MEDIA_PAD,
          f"{item0.sizeHint()} / {thumb_h} + {title_h}")
    w.spin_list_font_size.setValue(22)
    pump(0.3)
    big_h = w.list_paragraphs.item(0).sizeHint().height()
    check("글자를 키우면 이름 칸도 커짐", big_h > card_h, f"{card_h} → {big_h}")
    w.spin_list_font_size.setValue(13)
    pump(0.2)
    check("구경만 할 때는 송출하지 않음", w.media_slide_index == -1)

    print("\n2) 사진 송출 → 숨은 글이 노트 칸에")
    w._present_media_slide(0)
    pump(0.2)
    check("숨은 글이 보임", w.txt_slide_notes.toPlainText() == "새가족 환영 멘트\n- 이름 불러 주기",
          repr(w.txt_slide_notes.toPlainText()))
    check("몇 번째 사진인지 표시", w.lbl_notes_slide.text().startswith(f"{w.t('image_prefix')} 1/3"),
          w.lbl_notes_slide.text())
    check("사진 이름은 풍선 도움말에", "01 환영.jpg" in w.lbl_notes_slide.toolTip())
    w._present_media_slide(1)
    pump(0.2)
    check("숨은 글 없는 사진은 빈 칸", w.txt_slide_notes.toPlainText() == "")
    check("빈 칸 안내 글", w.txt_slide_notes.placeholderText() == w.t("image_notes_empty"))

    print("\n3) 송출 중이 아닌 사진에 숨은 글 넣기 - 송출은 그대로")
    w._present_media_slide(0)
    pump(0.2)
    live_before = w.presenter.current_bg_desc if hasattr(w.presenter, "current_bg_desc") else None
    answer_next_dialog(write_in_dialog("광고 순서\n1. 수요예배\n2. 구역모임"))
    w._edit_image_note(1)
    pump(0.3)
    check("사진 파일에 저장됨", image_notes.read_note(p2) == "광고 순서\n1. 수요예배\n2. 구역모임",
          repr(image_notes.read_note(p2)))
    check("송출 중인 사진은 그대로 (0번)", w.media_slide_index == 0, str(w.media_slide_index))
    if live_before is not None:
        check("송출 화면 그대로", w.presenter.current_bg_desc == live_before)
    check("노트 칸은 송출 중인 사진 것 그대로",
          w.txt_slide_notes.toPlainText().startswith("새가족 환영"), repr(w.txt_slide_notes.toPlainText()))
    check("편집한 카드에 📝 표시", w.list_paragraphs.item(1).text().startswith("📝"),
          w.list_paragraphs.item(1).text())
    check("저장한 PNG 를 Qt 가 정상으로 읽음", not QPixmap(p2).isNull())

    print("\n4) 송출 중인 사진의 숨은 글 고치기 → 노트 칸 바로 반영")
    w.list_paragraphs.setCurrentRow(0)
    answer_next_dialog(write_in_dialog("고친 환영 멘트"))
    w.btn_image_note_edit.click()
    pump(0.3)
    check("파일에 저장", image_notes.read_note(p1) == "고친 환영 멘트")
    check("노트 칸에 바로 반영", w.txt_slide_notes.toPlainText() == "고친 환영 멘트",
          repr(w.txt_slide_notes.toPlainText()))
    check("저장한 JPG 를 Qt 가 정상으로 읽음", not QPixmap(p1).isNull())

    print("\n5) 지우기")
    answer_next_dialog(write_in_dialog(""))
    w._edit_image_note(0)
    pump(0.3)
    check("숨은 글이 지워짐", image_notes.read_note(p1) == "")
    check("노트 칸도 빈 칸", w.txt_slide_notes.toPlainText() == "")
    check("📝 표시가 사라짐", not w.list_paragraphs.item(0).text().startswith("📝"),
          w.list_paragraphs.item(0).text())

    print("\n6) 넣을 수 없는 형식 (GIF)")
    seen = []

    def close_box(box):
        seen.append(box.text() if isinstance(box, QMessageBox) else type(box).__name__)
        box.accept()
    answer_next_dialog(close_box)
    w._edit_image_note(2)
    pump(0.3)
    check("안내 창이 뜸", seen and ".gif" in seen[0], str(seen))
    check("GIF 파일은 그대로", os.path.getsize(p3) == gif_size)

    print("\n7) 취소하면 아무것도 바뀌지 않음")
    mtime = os.path.getmtime(p2)

    def cancel(dlg):
        dlg._editor.setPlainText("저장하면 안 되는 글")
        dlg.reject()
    answer_next_dialog(cancel)
    w._edit_image_note(1)
    pump(0.3)
    check("취소 - 파일 그대로", os.path.getmtime(p2) == mtime and
          image_notes.read_note(p2).startswith("광고 순서"))

    print("\n8) 영어 화면")
    idx_en = w.combo_lang.findData("en")
    w.combo_lang.setCurrentIndex(idx_en)
    pump(0.2)
    check("영어 제목", w.grp_notes.title() == w.t("image_notes_group") and "Image" in w.grp_notes.title(),
          w.grp_notes.title())
    check("영어 단추", w.btn_image_note_edit.text() == "✏ Edit Hidden Note")
    w.combo_lang.setCurrentIndex(w.combo_lang.findData("ko"))
    pump(0.2)

    print("\n8-1) 폴더를 연 채로 다른 프로그램(ppt2jpg 노트 편집 등)이 노트를 바꾼 경우")
    import struct as _st
    raw = "ppt2jpg 에서 넣은 노트".encode("utf-8")
    with open(p1, "ab") as f:
        f.write(b"PPT_NOTE_V1" + _st.pack("<i", len(raw)) + raw + b"PPT_NOTE_END")
    w._present_media_slide(0)
    pump(0.2)
    check("다시 열지 않아도 송출할 때 새 노트가 보임",
          w.txt_slide_notes.toPlainText() == "ppt2jpg 에서 넣은 노트", repr(w.txt_slide_notes.toPlainText()))
    check("카드에도 📝 표시가 생김", w.list_paragraphs.item(0).text().startswith("📝"),
          w.list_paragraphs.item(0).text())

    print("\n8-2) 저장하다 남은 임시 파일은 목록에 넣지 않음")
    import shutil as _sh
    _sh.copy(p1, p1 + ".tmp.jpg")
    _sh.copy(p1, os.path.join(folder, ".bgpt_note_abc.tmp"))
    w._load_image_folder(folder, broadcast=False)
    pump(0.2)
    names = [os.path.basename(x) for x in w.media_slides]
    check("임시 파일 제외", not any(".tmp" in n for n in names), str(names))
    os.remove(p1 + ".tmp.jpg")
    os.remove(os.path.join(folder, ".bgpt_note_abc.tmp"))

    print("\n9) 다른 모드로 돌아가기")
    text_file = os.path.join(_TMP, "찬양.txt")
    with open(text_file, "w", encoding="utf-8") as f:
        f.write("첫째\n\n둘째")
    w._register_text_file(text_file)
    w._load_text_file(text_file, broadcast=False)
    pump(0.3)
    check("텍스트 모드: 노트 칸 숨김", not w.grp_notes.isVisible())
    check("텍스트 모드: 편집/스타일 보임", w.grp_edit.isVisible() and w.grp_style.isVisible())
    w.current_source_type = "folder"
    w.media_source_kind = "pptx"
    w._update_side_panel_mode()
    pump(0.1)
    check("PPT 모드: 제목은 '슬라이드 노트'", w.grp_notes.title() == w.t("notes_group"), w.grp_notes.title())
    check("PPT 모드: 숨은 글 단추는 숨김", not w.btn_image_note_edit.isVisible())
    check("PPT 모드: 사진 노트가 남아 있지 않음", w.txt_slide_notes.toPlainText() == "")

    w.close()
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
