# -*- coding: utf-8 -*-
"""왼쪽 '송출할 목록'의 목록 폴더 화면 테스트 - python test_library_folders.py

교사 예배 / 어른 예배 폴더를 만들고, 파일을 끌어다 넣고(옮기기·Ctrl 함께 넣기),
같은 파일을 두 폴더에 넣고, 접기·펼치기, 폴더 안에서 순서 바꾸기·묶기·묶음 풀기,
다시 켜도 그대로인지 확인한다.
"""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="bgpt_libfolders_")
os.environ["BGPT_SETTINGS_DIR"] = os.path.join(_TMP, "settings")
os.environ["BGPT_NO_UPDATE_CHECK"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import QEventLoop, QPoint

FAILURES = []


def check(label, condition, detail=""):
    print(f"   {'OK  ' if condition else '실패'} {label}  {'' if condition else detail}")
    if not condition:
        FAILURES.append(label)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    from main_window import MainWindow, USER_ROLE_GROUP, USER_ROLE_KIND, USER_ROLE_PATH
    from library_model import LOOSE
    import mix_bundle

    def pump(sec=0.1):
        end = time.time() + sec
        while time.time() < end:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 30)
            time.sleep(0.01)

    media = os.path.join(_TMP, "media")
    os.makedirs(media)
    hymn = os.path.join(media, "찬양.txt")
    open(hymn, "w", encoding="utf-8").write("주 하나님\n\n내 영혼이")
    notice = os.path.join(media, "광고.txt")
    open(notice, "w", encoding="utf-8").write("광고 1\n\n광고 2")
    prayer = os.path.join(media, "기도.txt")
    open(prayer, "w", encoding="utf-8").write("기도")
    pics = os.path.join(media, "사진")
    os.makedirs(pics)
    Image.new("RGB", (320, 180), (200, 50, 50)).save(os.path.join(pics, "01.jpg"))

    w = MainWindow()
    w.show()
    pump(0.3)
    lst = w.list_text_files
    for p in (hymn, notice, prayer, pics):
        w._register_text_file(p)
    lst.clearSelection()
    pump()

    def rows():
        out = []
        for r in range(lst.count()):
            it = lst.item(r)
            out.append((it.data(USER_ROLE_KIND), it.data(USER_ROLE_GROUP),
                        os.path.basename(it.data(USER_ROLE_PATH) or "")))
        return out

    def row_of(path, group):
        for r in range(lst.count()):
            it = lst.item(r)
            if it.data(USER_ROLE_PATH) == path and it.data(USER_ROLE_GROUP) == group:
                return r
        return -1

    def header_row(group):
        for r in range(lst.count()):
            it = lst.item(r)
            if it.data(USER_ROLE_KIND) == "group" and it.data(USER_ROLE_GROUP) == group:
                return r
        return -1

    def drop(src_rows, target_row, mode, copy=False):
        lst.clearSelection()
        for r in src_rows:
            lst.item(r).setSelected(True)
        w._on_library_drop(src_rows, target_row, mode, copy)
        pump()

    print("1) 폴더 만들기")
    check("단추가 있음", w.btn_new_lib_folder.text().startswith("📂"))
    t = w._new_library_folder("교사 예배")
    a = w._new_library_folder("어른 예배")
    lib = w._library()
    check("폴더 2개가 목록 위쪽에", [f["name"] for f in lib.folders] == ["교사 예배", "어른 예배"]
          and rows()[0][0] == "group", str(rows()))
    check("빈 폴더 안내 줄", any(k == "empty" for k, g, n in rows()))

    print("\n2) 끌어서 폴더에 넣기 (옮기기)")
    lst.clearSelection()
    lst.item(row_of(hymn, LOOSE)).setSelected(True)
    hint = lst.drop_hint(lst.visualItemRect(lst.item(header_row(t))).center())
    check("폴더 머리 위에 놓으면 '안으로'", hint == (header_row(t), "into"), str(hint))
    drop([row_of(hymn, LOOSE), row_of(notice, LOOSE)], header_row(t), "into")
    lib = w._library()
    check("교사 예배에 찬양·광고", lib.folders[t]["items"] == [hymn, notice], str(lib.folders[t]["items"]))
    check("폴더 밖에서는 빠짐 (덜 복잡해짐)", hymn not in lib.loose and notice not in lib.loose, str(lib.loose))
    check("옮겼다는 안내", "교사 예배" in w.statusBar().currentMessage())

    print("\n3) 같은 파일을 다른 폴더에도 (Ctrl 을 누른 채 놓기)")
    drop([row_of(hymn, t)], header_row(a), "into", copy=True)
    lib = w._library()
    check("찬양이 두 폴더 모두에", hymn in lib.folders[t]["items"] and hymn in lib.folders[a]["items"])
    drop([row_of(hymn, t)], header_row(a), "into", copy=True)
    check("같은 폴더에는 두 번 들어가지 않음", w._library().folders[a]["items"].count(hymn) == 1)
    check("목록에 두 줄로 보임", row_of(hymn, t) >= 0 and row_of(hymn, a) >= 0)

    print("\n4) 폴더 안 줄을 누르면 그 파일이 열림 · 그때 더하는 파일은 그 폴더로")
    lst.setCurrentRow(row_of(notice, t))
    w._on_text_file_library_clicked(lst.item(row_of(notice, t)))
    pump(0.2)
    check("광고가 열림", w.current_source_type == "text" and w.text_file_path == notice)
    lst.setCurrentRow(row_of(notice, t))
    w._register_text_file(prayer)                     # 이미 폴더 밖에 있는 파일
    lib = w._library()
    check("이미 목록에 있는 파일을 열면 더하지 않음", prayer in lib.loose and prayer not in lib.folders[t]["items"],
          str(lib.folders[t]["items"]))
    new_txt = os.path.join(media, "교사 기도.txt")
    open(new_txt, "w", encoding="utf-8").write("교사 기도")
    lst.setCurrentRow(row_of(notice, t))
    w._register_text_file(new_txt)
    lib = w._library()
    check("새 파일은 고른 폴더(교사 예배)에 들어감", new_txt in lib.folders[t]["items"] and new_txt not in lib.loose,
          str(lib.folders[t]["items"]))

    print("\n5) 폴더 안 순서 바꾸기 · 폴더 밖으로 꺼내기")
    drop([row_of(new_txt, t)], row_of(hymn, t), "before")
    check("교사 기도를 맨 앞으로", w._library().folders[t]["items"][0] == new_txt, str(w._library().folders[t]["items"]))
    drop([row_of(new_txt, t)], row_of(prayer, LOOSE), "after")
    lib = w._library()
    check("폴더 밖 줄 뒤에 놓으면 폴더에서 꺼내짐", new_txt in lib.loose and new_txt not in lib.folders[t]["items"])
    drop([row_of(new_txt, LOOSE)], header_row(t), "into")

    print("\n6) 휴지통은 그 폴더에서만 빼기")
    w._remove_one_text_file(hymn, a)
    pump()
    lib = w._library()
    check("어른 예배에서만 빠지고 교사 예배에는 남음", hymn not in lib.folders[a]["items"] and hymn in lib.folders[t]["items"])
    check("실제 파일은 그대로", os.path.exists(hymn))

    print("\n7) 접기 · 펼치기")
    n_before = lst.count()
    w._on_text_file_library_clicked(lst.item(header_row(t)))
    w._on_text_file_library_clicked(lst.item(header_row(t)))     # 같은 누름이 두 번 와도 한 번만
    pump()
    check("접으면 안의 줄이 숨음", lst.count() == n_before - 3 and row_of(hymn, t) == -1, f"{n_before}->{lst.count()}")
    check("머리에 ▶ 표시", lst.itemWidget(lst.item(header_row(t))).label.text().startswith("▶"))
    time.sleep(0.45)
    w._on_text_file_library_clicked(lst.item(header_row(t)))
    pump()
    check("다시 펼침", row_of(hymn, t) >= 0)

    print("\n8) 폴더 안에서 겹쳐서 묶기 · 묶음 풀기")
    drop([row_of(pics, LOOSE)], header_row(t), "into", copy=True)
    hint_rect = lst.visualItemRect(lst.item(row_of(hymn, t)))
    lst.clearSelection()
    lst.item(row_of(pics, t)).setSelected(True)
    check("파일 가운데에 놓으면 '묶기'", lst.drop_hint(hint_rect.center())[1] == "merge")
    hymn_at = w._library().folders[t]["items"].index(hymn)
    drop([row_of(pics, t)], row_of(hymn, t), "merge")
    lib = w._library()
    mixes = [p for p in lib.folders[t]["items"] if mix_bundle.is_mix_file(p)]
    check("교사 예배 안 찬양 자리에 묶음이 생김", len(mixes) == 1 and lib.folders[t]["items"].index(mixes[0]) == hymn_at
          and hymn not in lib.folders[t]["items"] and pics not in lib.folders[t]["items"], str(lib.folders[t]["items"]))
    check("폴더 밖의 사진은 그대로 (복사해 넣었던 것)", pics in lib.loose)
    check("묶음 화면이 열림", w.current_source_type == "mix")
    w._ungroup_mix(mixes[0])
    pump(0.2)
    lib = w._library()
    check("묶음 풀기: 그 자리에 원래 파일들", lib.folders[t]["items"][hymn_at:hymn_at + 2] == [hymn, pics],
          str(lib.folders[t]["items"]))

    print("\n9) 폴더 순서 바꾸기")
    lst.clearSelection()
    lst.item(header_row(a)).setSelected(True)
    check("폴더를 끌면 앞·뒤로", lst.drop_hint(lst.visualItemRect(lst.item(header_row(t))).topLeft() + QPoint(5, 2))[1] == "before")
    drop([header_row(a)], header_row(t), "before")
    check("어른 예배가 위로", [f["name"] for f in w._library().folders] == ["어른 예배", "교사 예배"])

    print("\n10) 다시 켜도 그대로")
    saved = w._library()
    w.close()
    pump(0.2)
    w2 = MainWindow()
    w2.show()
    pump(0.3)
    again = w2._library()
    check("폴더·안의 파일·순서 그대로", again.folders == saved.folders and again.loose == saved.loose)
    lst = w2.list_text_files
    check("목록에 폴더 머리가 보임", any(lst.item(r).data(USER_ROLE_KIND) == "group" for r in range(lst.count())))

    print("\n11) 폴더 지우기 (Delete) - 안의 파일은 지워지지 않음")
    orig_q = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    try:
        first_header = next(r for r in range(lst.count()) if lst.item(r).data(USER_ROLE_KIND) == "group")
        lst.clearSelection()
        lst.setCurrentRow(first_header)
        w2._remove_text_file_from_library()
        pump()
    finally:
        QMessageBox.question = orig_q
    lib = w2._library()
    check("폴더가 하나 남음", [f["name"] for f in lib.folders] == ["교사 예배"], str([f["name"] for f in lib.folders]))
    check("실제 파일은 그대로", all(os.path.exists(p) for p in (hymn, notice, prayer, new_txt)))

    print("\n12) 실제 놓기 동작 (끌어 놓기 이벤트)")
    from PySide6.QtCore import QMimeData, Qt as _Qt
    from PySide6.QtGui import QDropEvent

    class FakeDrop(QDropEvent):
        def source(self):
            return lst

    loose_row = next(r for r in range(lst.count()) if lst.item(r).data(USER_ROLE_GROUP) == LOOSE)
    moving = lst.item(loose_row).data(USER_ROLE_PATH)
    head = next(r for r in range(lst.count()) if lst.item(r).data(USER_ROLE_KIND) == "group")
    lst.clearSelection()
    lst.item(loose_row).setSelected(True)
    mime = QMimeData()
    ev = FakeDrop(lst.visualItemRect(lst.item(head)).center().toPointF(), _Qt.DropAction.MoveAction, mime,
                  _Qt.MouseButton.LeftButton, _Qt.KeyboardModifier.ControlModifier)
    lst.dropEvent(ev)
    pump()
    lib = w2._library()
    check("Ctrl 놓기 = 함께 넣기 (폴더 밖에도 그대로)", moving in lib.folders[0]["items"] and moving in lib.loose)
    check("놓은 뒤 원래 줄이 지워지지 않음 (목록을 새로 그림)", ev.dropAction() == _Qt.DropAction.IgnoreAction)

    w2.close()
    shutil.rmtree(_TMP, ignore_errors=True)
    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
