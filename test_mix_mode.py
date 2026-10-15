# -*- coding: utf-8 -*-
"""
묶음 화면 테스트 - python test_mix_mode.py

- 왼쪽 목록에서 한 항목을 다른 항목 위에 겹치면 묶음이 되는지
- 텍스트·이미지 폴더·PPT·동영상 카드가 한 화면에 함께 보이는지
- 카드를 누르면 종류에 맞게 송출되는지 (글자 / 사진 + 숨은 글 / 슬라이드 + 노트 / 동영상)
- 종류가 달라도 끌어서 순서를 섞을 수 있고, 다시 켜도 그 순서인지
- 화살표 키로 넘기기, 동영상은 키로 넘어와도 곧바로 재생하지 않는지
- 묶음 풀기
"""
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="bgpt_mixmode_")
os.environ["BGPT_SETTINGS_DIR"] = os.path.join(_TMP, "settings")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, Qt, QPoint
from PySide6.QtTest import QTest

import cv2
import numpy as np
from PIL import Image

import image_notes
import mix_bundle
import ppt_engine

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"   OK   {label}")
    else:
        print(f"   실패 {label}  {detail}")
        FAILURES.append(label)


def make_video(path, seconds=3.0, fps=20):
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 180))
    for i in range(int(seconds * fps)):
        frame = np.zeros((180, 320, 3), np.uint8)
        frame[:] = (30, 90, (i * 5) % 255)
        writer.write(frame)
    writer.release()


def fake_ppt_cache(pptx, notes):
    """파워포인트 없이 '이미 그림으로 만든' PPT 캐시를 만든다"""
    cdir = ppt_engine.cache_dir_for(str(pptx))
    cdir.mkdir(parents=True, exist_ok=True)
    paths = ppt_engine.slide_paths(cdir, len(notes))
    for i, sp in enumerate(paths):
        Image.new("RGB", (640, 360), (200, 120 + i * 30, 40)).save(sp)
    meta = {"version": ppt_engine.CACHE_VERSION, "source": str(pptx), "count": len(notes),
            "notes": notes, "notes_rev": ppt_engine.NOTES_REV, "done": True, "width": 640, "height": 360}
    (cdir / ppt_engine._META_NAME).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    def pump(sec=0.2):
        end = time.time() + sec
        while time.time() < end:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            time.sleep(0.01)

    media = os.path.join(_TMP, "media")
    os.makedirs(media)
    text = os.path.join(media, "찬양.txt")
    with open(text, "w", encoding="utf-8") as f:
        f.write("주 하나님 지으신 모든 세계\n\n내 영혼이 은총 입어\n\n하늘 영광 보좌")
    folder = os.path.join(media, "광고")
    os.makedirs(folder)
    arr = np.random.default_rng(2).integers(0, 255, (180, 320, 3), dtype=np.uint8)
    img1 = os.path.join(folder, "01 환영.jpg")
    img2 = os.path.join(folder, "02 행사.jpg")
    Image.fromarray(arr).save(img1)
    Image.fromarray(arr[::-1]).save(img2)
    image_notes.write_note(img1, "새가족 환영 멘트")
    pptx = os.path.join(media, "설교.pptx")
    with open(pptx, "wb") as f:
        f.write(b"fake pptx")
    fake_ppt_cache(pptx, ["", "1대지 노트"])
    video = os.path.join(media, "광고영상.mp4")
    make_video(video)

    from main_window import MainWindow
    w = MainWindow()
    w.resize(1400, 860)
    w.show()
    pump(0.3)
    for p in (text, folder, pptx, video):
        w._register_text_file(p)
    pump(0.2)

    print("1) 왼쪽 목록: 가운데에 놓으면 겹치기, 가장자리에 놓으면 순서 바꾸기")
    lst = w.list_text_files
    lst.clearSelection()
    lst.item(1).setSelected(True)                      # 이미지 폴더를 끌고 있다고 치고
    rect = lst.visualItemRect(lst.item(0))
    check("가운데 → 겹치기 대상", lst.merge_target_row(rect.center()) == 0)
    check("위쪽 가장자리 → 순서 바꾸기", lst.merge_target_row(QPoint(rect.center().x(), rect.top() + 1)) == -1)
    check("끌고 있는 항목 자신은 대상이 아님", lst.merge_target_row(lst.visualItemRect(lst.item(1)).center()) == -1)

    print("\n2) 겹쳐서 묶기")
    w._on_library_items_merged([folder], text)
    pump(0.3)
    lib = w._get_registered_text_files()
    mix_path = lib[0]
    check("텍스트 자리에 묶음이 생김", mix_bundle.is_mix_file(mix_path) and folder not in lib and text not in lib,
          str(lib))
    check("묶음 파일은 설정 폴더 안", os.path.dirname(mix_path).startswith(os.environ["BGPT_SETTINGS_DIR"]))
    check("묶음 화면으로 바뀜", w.current_source_type == "mix")
    w._on_library_items_merged([pptx, video], mix_path)
    pump(0.4)
    lib = w._get_registered_text_files()
    check("묶음에 PPT·동영상 더하기 → 목록에는 묶음 하나", lib == [mix_path], str(lib))
    kinds = [e.kind for e in w.mix_entries]
    check("글 3 + 사진 2 + 슬라이드 2 + 동영상 1", kinds == ["text"] * 3 + ["image"] * 2 + ["slide"] * 2 + ["video"],
          str(kinds))
    check("가운데에 카드 8장", w.list_paragraphs.count() == 8)
    check("왼쪽 줄 이름", "🔗" in w.list_text_files.itemWidget(w.list_text_files.item(0)).label.text())
    check("구경만 할 때는 송출하지 않음", not w.presenter.has_text() and w.mix_index == -1)

    print("\n3) 카드를 누르면 종류에 맞게 송출")
    w._present_mix_entry(1)
    pump(0.2)
    check("글 카드 → 글자 송출", w.presenter.text_overlay.text() == "내 영혼이 은총 입어",
          repr(w.presenter.text_overlay.text()))
    check("글 카드일 때는 글자 스타일 칸", w.grp_style.isVisible() and not w.grp_notes.isVisible())
    w._present_mix_entry(3)
    pump(0.2)
    check("사진 카드 → 글자는 내리고 사진", not w.presenter.has_text() and w._live_source_type == "folder")
    check("사진 카드 → 숨은 글이 노트 칸에", w.grp_notes.isVisible()
          and w.txt_slide_notes.toPlainText() == "새가족 환영 멘트", repr(w.txt_slide_notes.toPlainText()))
    check("사진 카드일 때 숨은 글 편집 단추", w.btn_image_note_edit.isVisible())
    w._present_mix_entry(6)
    pump(0.2)
    check("슬라이드 카드 → 슬라이드 노트", w.txt_slide_notes.toPlainText() == "1대지 노트",
          repr(w.txt_slide_notes.toPlainText()))
    check("슬라이드일 때는 숨은 글 편집 단추 없음", not w.btn_image_note_edit.isVisible())
    w._present_mix_entry(0)
    pump(0.2)
    check("사진 뒤에 글 → 배경을 되돌리고 글자", w.presenter.text_overlay.text().startswith("주 하나님")
          and not w._folder_replaced_bg)
    check("상태 표시줄에 묶음 위치", "1/8" in w.lbl_status.text(), w.lbl_status.text())

    print("\n4) 화살표 키로 넘기기")
    QTest.keyClick(w.list_paragraphs, Qt.Key.Key_Right)
    pump(0.2)
    check("→ 다음 카드(글) 송출", w.mix_index == 1 and w.presenter.text_overlay.text() == "내 영혼이 은총 입어")
    w._present_mix_entry(6)
    pump(0.2)
    QTest.keyClick(w.list_paragraphs, Qt.Key.Key_Right)
    pump(0.3)
    check("동영상 카드로 넘어와도 곧바로 재생하지 않음", w.mix_index == 7 and not w.presenter.content_active)
    check("동영상 조작 막대가 보임", w.video_bar.isVisible())
    QTest.keyClick(w.list_paragraphs, Qt.Key.Key_Space)
    pump(1.0)
    check("스페이스로 재생", w.presenter.content_active and w.presenter.content_state == "playing",
          w.presenter.content_state)
    w._present_mix_entry(0)
    pump(0.3)
    check("다른 카드를 송출하면 동영상은 내려감", not w.presenter.content_active)

    print("\n5) 종류가 달라도 끌어서 순서 섞기")
    view = w.list_paragraphs.viewport()
    w.spin_list_columns.setValue(4)                    # 카드 8장이 모두 보이게
    pump(0.3)

    def center(i):
        return w.list_paragraphs.visualItemRect(w.list_paragraphs.item(i)).center()

    before = [e.key for e in w.mix_entries]
    start, end = center(7), center(0)                  # 동영상 카드를 맨 앞으로
    QTest.mousePress(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    for t in (0.3, 0.6, 1.0):
        p = QPoint(int(start.x() + (end.x() - start.x()) * t), int(start.y() + (end.y() - start.y()) * t))
        QTest.mouseMove(view, p)
        pump(0.05)
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, end)
    pump(0.3)
    after = [e.key for e in w.mix_entries]
    check("동영상 카드가 맨 앞으로", w.mix_entries[0].kind == "video", str([e.kind for e in w.mix_entries]))
    check("나머지 순서는 그대로", after[1:] == before[:7], str(after))
    check("끄는 동안 송출하지 않음", not w.presenter.content_active)
    saved = mix_bundle.load_mix(mix_path)["order"]
    check("순서가 묶음 파일에 저장됨", saved == after, str(saved[:3]))
    check("송출 중이던 카드가 따라감(글 1번 → 2번째 자리)", w.mix_index == 1 and w.mix_entries[1].kind == "text")
    with open(text, encoding="utf-8") as f:
        check("원본 텍스트 파일은 그대로", f.read().startswith("주 하나님"))

    print("\n5-A) Ctrl/Shift 로 여러 장 골라 함께 옮기기")
    CTRL, SHIFT, NOMOD = (Qt.KeyboardModifier.ControlModifier, Qt.KeyboardModifier.ShiftModifier,
                          Qt.KeyboardModifier.NoModifier)

    def click(i, mods=NOMOD):
        p = center(i)
        QTest.mousePress(view, Qt.MouseButton.LeftButton, mods, p)
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, mods, p)
        pump(0.15)

    def drag(i, j, mods=NOMOD):
        a, b = center(i), center(j)
        QTest.mousePress(view, Qt.MouseButton.LeftButton, mods, a)
        for t in (0.3, 0.6, 1.0):
            QTest.mouseMove(view, QPoint(int(a.x() + (b.x() - a.x()) * t), int(a.y() + (b.y() - a.y()) * t)))
            pump(0.05)
        QTest.mouseRelease(view, Qt.MouseButton.LeftButton, mods, b)
        pump(0.3)

    def picked_rows():
        return [r for r in range(w.list_paragraphs.count()) if w.list_paragraphs.item(r).data(USER_ROLE_PICKED)]

    from main_window import USER_ROLE_PICKED
    live_before = w.mix_index
    order0 = [e.key for e in w.mix_entries]
    click(4, CTRL)
    click(6, CTRL)
    check("Ctrl 로 누르면 송출하지 않고 고르기만", w.mix_index == live_before)
    check("송출 중 카드 + Ctrl 로 누른 2장 = 3장 고름 (금색 표시)",
          sorted(picked_rows()) == sorted({live_before, 4, 6}), str(picked_rows()))
    click(4, CTRL)
    check("Ctrl 로 다시 누르면 빠짐", sorted(picked_rows()) == sorted({live_before, 6}), str(picked_rows()))
    click(4, CTRL)
    group = [order0[i] for i in sorted({live_before, 4, 6})]
    drag(6, 0)
    keys = [e.key for e in w.mix_entries]
    check("고른 카드들이 한 덩어리로 맨 앞에 (원래 순서 유지)", keys[:3] == group, str([k.split(chr(9))[0] for k in keys]))
    check("나머지 카드 순서는 그대로", keys[3:] == [k for k in order0 if k not in group])
    check("끌어 옮겨도 송출하지 않음 / 송출 중 카드가 따라감",
          w.mix_entries[w.mix_index].key == order0[live_before], str(w.mix_index))
    check("옮긴 순서가 묶음 파일에 저장됨", mix_bundle.load_mix(mix_path)["order"] == keys)
    check("옮긴 뒤에도 고른 표시 유지 (한 번 더 옮길 수 있게)", picked_rows() == [0, 1, 2], str(picked_rows()))
    drag(1, 6)
    keys2 = [e.key for e in w.mix_entries]
    check("다시 끌면 덩어리째 뒤로", keys2[4:7] == group and keys2[:4] == keys[3:7], str([k.split(chr(9))[0] for k in keys2]))

    # 그냥 누르면 고르기가 풀리고 그 카드만 송출
    target = next(i for i, e in enumerate(w.mix_entries) if e.kind in ("text", "image") and e.key not in group)
    click(target)
    check("그냥 누르면 고르기 풀림 + 송출", picked_rows() == [] and w.mix_index == target)
    # Shift: 지금 카드부터 누른 카드까지
    end_row = min(target + 2, len(w.mix_entries) - 1)
    click(end_row, SHIFT)
    check("Shift 로 누르면 범위를 고름 (송출하지 않음)",
          picked_rows() == list(range(target, end_row + 1)) and w.mix_index == target, str(picked_rows()))
    # 고르지 않은 카드를 끌면 그 카드 하나만 옮겨지고 고르기는 풀림
    single_from = next(i for i in range(len(w.mix_entries)) if i not in picked_rows())
    one_key = w.mix_entries[single_from].key
    drag(single_from, len(w.mix_entries) - 1)
    check("고르지 않은 카드를 끌면 그 카드 하나만", w.mix_entries[-1].key == one_key and picked_rows() == [],
          str(picked_rows()))
    mix_bundle.save_order(mix_path, [next(e for e in w.mix_entries if e.key == k) for k in after])
    w._load_mix(mix_path)
    pump(0.2)

    print("\n5-1) 안 보이는 자리로 끌면 목록이 저절로 굴러감")
    w.spin_list_columns.setValue(1)                    # 카드가 커져서 아래 카드들은 안 보인다
    pump(0.3)
    bar = w.list_paragraphs.verticalScrollBar()
    bar.setValue(0)
    pump(0.1)
    order_before = [e.key for e in w.mix_entries]
    start = center(0)
    bottom = QPoint(start.x(), view.height() - 5)
    QTest.mousePress(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, start)
    QTest.mouseMove(view, QPoint(start.x(), start.y() + 30))
    pump(0.05)
    QTest.mouseMove(view, bottom)
    pump(1.2)
    scrolled = bar.value()
    QTest.mouseRelease(view, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, bottom)
    pump(0.3)
    check("아래 가장자리에서 저절로 굴러감", scrolled > 0, str(scrolled))
    check("첫 카드가 아래쪽으로 옮겨짐",
          [e.key for e in w.mix_entries].index(order_before[0]) > 0,
          str([e.kind for e in w.mix_entries]))
    mix_bundle.save_order(mix_path, [next(e for e in w.mix_entries if e.key == k) for k in after])
    w._load_mix(mix_path)
    w.spin_list_columns.setValue(2)
    pump(0.2)

    print("\n5-2) 직접 입력 송출 / ESC 뒤에도 묶음은 그대로")
    w._present_mix_entry(1)
    pump(0.2)
    w._broadcast_direct_text("잠시 광고 말씀")
    pump(0.2)
    check("직접 입력해도 묶음 화면 유지", w.current_source_type == "mix" and w.mix_index == -1)
    check("상태 표시줄은 직접 입력 송출", w.t("status_direct_presenting").strip("| ") in w.lbl_status.text(),
          w.lbl_status.text())
    w._present_mix_entry(2)
    pump(0.2)
    check("그 뒤에도 카드를 누르면 송출", w.presenter.text_overlay.text() == w.mix_entries[2].title,
          repr(w.presenter.text_overlay.text()))
    w._on_escape_action()
    pump(0.1)
    w._on_escape_action()
    pump(0.2)
    check("ESC 로 내리면 '송출 중' 표시가 사라짐", "송출 중" not in w.lbl_status.text() and w.mix_index == -1,
          w.lbl_status.text())

    print("\n5-3) 애니메이션 모드 중에는 묶음 안 PPT 그림 만들기를 미룸 (되풀이 없음)")
    calls = []
    real_export = ppt_engine.export_async
    ppt_engine.export_async = lambda *a, **k: calls.append(a[0])
    real_load = w._load_mix
    loads = []
    w._load_mix = lambda *a, **k: (loads.append(1), real_load(*a, **k))[1]
    try:
        other_ppt = os.path.join(media, "아직안됨.pptx")
        with open(other_ppt, "wb") as f:
            f.write(b"not exported yet")
        mix_bundle.add_sources(mix_path, [other_ppt])
        w._show_mode_active = True
        real_load(mix_path)
        check("슬라이드쇼 중에는 그림 만들기를 시작하지 않음", calls == [], str(calls))
        w._on_mix_ppt_ready(other_ppt)         # (중단 알림이 와도) 그림이 없으면 다시 읽지 않는다
        pump(0.1)
        check("그림이 없으면 묶음을 다시 읽지 않음 (되풀이 없음)", loads == [], str(loads))
        w._show_mode_active = False
        w._mix_start_ppt_exports()
        check("슬라이드쇼가 끝나면 그림 만들기 시작", calls == [other_ppt], str(calls))
    finally:
        ppt_engine.export_async = real_export
        w._load_mix = real_load
        data = mix_bundle.load_mix(mix_path)
        data["sources"] = [x for x in data["sources"] if x != other_ppt]
        mix_bundle.save_mix(mix_path, data)
        w._mix_exporting.clear()
        real_load(mix_path)

    print("\n5-4) 섞어 둔 묶음을 다른 묶음에 겹쳐도 각자 순서 유지")
    t2 = os.path.join(media, "말씀.txt")
    with open(t2, "w", encoding="utf-8") as f:
        f.write("가\n\n나")
    w._register_text_file(t2)
    w._register_text_file(video)
    w._on_library_items_merged([video], t2)           # 새 묶음: 말씀(가, 나) + 동영상 (섞지 않음)
    pump(0.2)
    small = w.current_source_path
    w._on_library_items_merged([mix_path], small)     # 섞어 둔 큰 묶음을 겹침
    pump(0.3)
    keys = [e.key for e in w.mix_entries]
    check("겹친 대상의 카드가 먼저, 그 뒤에 끌어 온 묶음의 섞인 순서",
          keys[:2] == [f"text\t{t2}\t0", f"text\t{t2}\t1"] and keys[3:] == [k for k in after if k not in keys[:3]],
          str([e.kind for e in w.mix_entries]))

    print("\n6) 다시 켜도 묶음과 순서가 되살아남")
    w.close()
    pump(0.2)
    w2 = MainWindow()
    w2.show()
    pump(0.3)
    check("묶음 화면으로 시작", w2.current_source_type == "mix" and w2.current_source_path == small)
    check("섞은 순서 그대로", [e.key for e in w2.mix_entries] == keys)
    check("시작할 때 송출하지 않음", not w2.presenter.has_text())

    print("\n7) 묶음 풀기")
    w2._ungroup_mix(small)
    pump(0.3)
    lib = w2._get_registered_text_files()
    check("원래 파일들이 그 자리에", lib == [t2, video, text, folder, pptx], str(lib))
    check("첫 파일(텍스트)을 보여 줌", w2.current_source_type == "text" and w2.text_file_path == t2)
    check("텍스트 화면으로 돌아오면 편집 칸이 보임", w2.grp_edit.isVisible())
    w2.close()
    pump(0.2)

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
