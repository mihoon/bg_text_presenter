# -*- coding: utf-8 -*-
"""이미지 폴더 다시 만들기 테스트 - python test_folder_watch.py

PPT 를 사진으로 내보낸 폴더를 지우고 같은 이름으로 다시 만들거나(다시 내보내기),
구글 드라이브가 파일을 나중에 써 넣는 경우에도
- 목록·썸네일이 새 사진으로 저절로 바뀌는지
- 송출 중이던 사진이 새 그림으로 바뀌는지
- 아직 다 써지지 않은(읽을 수 없는) 사진을 눌러도 까만 화면을 내보내지 않는지
"""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="bgpt_watch_")
os.environ["BGPT_SETTINGS_DIR"] = os.path.join(_TMP, "settings")
os.environ["BGPT_NO_UPDATE_CHECK"] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop
from thumbnail_utils import scan_folder_images as scan_folder

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"   OK   {label}")
    else:
        print(f"   실패 {label}  {detail}")
        FAILURES.append(label)


def write_slides(folder, colors):
    os.makedirs(folder, exist_ok=True)
    for i, c in enumerate(colors):
        Image.new("RGB", (1600, 900), c).save(os.path.join(folder, f"Slide_{i + 1:02d}.jpg"), quality=90)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    from main_window import MainWindow, USER_ROLE_THUMB

    def pump(sec):
        end = time.time() + sec
        while time.time() < end:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            time.sleep(0.02)

    def wait(cond, sec=8):
        end = time.time() + sec
        while time.time() < end and not cond():
            pump(0.05)
        return cond()

    def screen_color():
        pm = w.presenter._bg_pixmap
        if pm is None or pm.isNull():
            return None
        c = pm.toImage().pixelColor(pm.width() // 2, pm.height() // 2)
        return (c.red() // 32, c.green() // 32, c.blue() // 32)

    def thumbs():
        lst = w.list_paragraphs
        return [bool(lst.item(r).data(USER_ROLE_THUMB)) for r in range(lst.count())]

    folder = os.path.join(_TMP, "예배 사진", "FRIDAY WORSHIP")
    write_slides(folder, [(200, 0, 0), (0, 200, 0), (0, 0, 200)])

    w = MainWindow()
    w.show()
    pump(0.3)

    print("1) 폴더 불러오기")
    w._load_image_folder(folder, select_index=1)
    check("3장", len(w.media_slides) == 3)
    check("썸네일 모두 나옴", wait(lambda: all(thumbs()) and len(thumbs()) == 3), str(thumbs()))
    check("2번 사진 송출(초록)", screen_color() == (200 // 32, 0, 0) or screen_color() == (0, 200 // 32, 0), str(screen_color()))
    green = screen_color()

    print("\n2) 폴더를 지우고 같은 이름으로 다시 만들기 (사진이 바뀌고 한 장 늘어남)")
    shutil.rmtree(folder)
    pump(0.3)
    write_slides(folder, [(250, 250, 0), (0, 200, 200), (200, 0, 200), (250, 250, 250)])
    check("목록이 4장으로 저절로 바뀜", wait(lambda: len(w.media_slides) == 4 and w.list_paragraphs.count() == 4),
          str(len(w.media_slides)))
    check("새 썸네일이 모두 나옴", wait(lambda: len(thumbs()) == 4 and all(thumbs())), str(thumbs()))
    check("송출 중이던 2번 자리는 새 그림(청록)으로", wait(lambda: screen_color() == (0, 200 // 32, 200 // 32)),
          str(screen_color()))
    check("고른 카드 자리 유지", w.media_slide_index == 1 and w.list_paragraphs.currentRow() == 1)

    print("\n3) 아직 다 써지지 않은 사진")
    broken = os.path.join(folder, "Slide_03.jpg")
    with open(broken, "wb") as f:
        f.write(b"")                                  # 동기화 프로그램이 막 만든 빈 파일
    pump(2.0)
    before = screen_color()
    w._present_media_slide(2)
    pump(0.2)
    check("읽을 수 없는 사진을 눌러도 화면은 그대로 (까만 화면 X)", screen_color() == before and w.media_slide_index == 1,
          str(screen_color()))
    check("안내 문구", "읽을 수 없습니다" in w.statusBar().currentMessage(), w.statusBar().currentMessage())
    Image.new("RGB", (1600, 900), (0, 0, 250)).save(broken, quality=90)   # 이제 다 써짐
    check("다 써지면 썸네일이 저절로 다시 나옴", wait(lambda: all(thumbs()), 10), str(thumbs()))
    w._present_media_slide(2)
    pump(0.2)
    check("이제 누르면 송출", w.media_slide_index == 2 and screen_color() == (0, 0, 250 // 32), str(screen_color()))

    print("\n4) 폴더가 잠시 없어졌다가 다시 생김")
    shutil.rmtree(folder)
    check("없어지면 안내 (목록은 그대로)", wait(lambda: "찾을 수 없습니다" in w.statusBar().currentMessage(), 5)
          and len(w.media_slides) == 4, w.statusBar().currentMessage())
    write_slides(folder, [(250, 0, 0), (0, 250, 0)])
    check("다시 생기면 저절로 읽음 (2장)", wait(lambda: len(w.media_slides) == 2 and all(thumbs()) and len(thumbs()) == 2),
          str(len(w.media_slides)))

    print("\n5) 이름·크기·수정 시각이 똑같은 새 파일도 다른 파일로 봄 (썸네일 저장분을 다시 쓰지 않음)")
    import thumbnail_utils as tu
    p1 = os.path.join(folder, "Slide_01.jpg")
    st = os.stat(p1)
    key_before = tu._get_cache_path(p1, 480, 270)
    data = open(p1, "rb").read()
    os.remove(p1)
    with open(p1, "wb") as f:                     # 같은 크기, 같은 이름
        f.write(data[:-3] + b"\x00\x00\xd9" if data.endswith(b"\xff\xd9") else data)
    os.utime(p1, ns=(st.st_atime_ns, st.st_mtime_ns))  # 수정 시각까지 똑같이
    check("다시 만든 파일은 썸네일 저장 이름이 다름", tu._get_cache_path(p1, 480, 270) != key_before)

    print("\n6) Qt 가 못 읽는 그림은 PIL 로 대신 읽어 송출")
    orig_qt = tu.qt_read_image
    tu.qt_read_image = lambda *a, **k: (None, "시험용 실패")
    tu._DISPLAY_CACHE.clear()
    try:
        w._present_media_slide(0)
        pump(0.2)
        check("Qt 실패해도 화면에 나옴", w.media_slide_index == 0 and screen_color() == (250 // 32, 0, 0),
              str(screen_color()))
    finally:
        tu.qt_read_image = orig_qt

    print("\n7) 큰 사진은 송출 화면 크기로 줄여서 읽음")
    big = os.path.join(folder, "Slide_03.jpg")
    Image.new("RGB", (5867, 3300), (0, 120, 250)).save(big, quality=85)
    check("새 그림 반영", wait(lambda: len(w.media_slides) == 3, 6))
    w._present_media_slide(2)
    pump(0.3)
    pm = w.presenter._bg_pixmap
    lim = w.presenter._display_limit()
    check("송출 그림은 화면 크기 이하", pm is not None and pm.width() <= lim[0] and pm.height() <= lim[1],
          f"{pm.width() if pm else None} / {lim}")
    check("미리보기는 1920 이하", w.preview._bg_pixmap is not None and w.preview._bg_pixmap.width() <= 1920)

    print("\n8) 썸네일 일꾼이 모두 붙잡혀도 다른 카드 그림은 나옴 + 사진 다시 읽기(F5)")
    import threading
    gate = threading.Event()
    orig_get = tu.get_thumbnail
    stuck = set()

    def slow_get(path, *a, **k):
        if len(stuck) < 4 and path not in stuck:
            stuck.add(path)
            gate.wait(30)                         # 동기화 중인 파일처럼 오래 붙잡힘
            return ""
        return orig_get(path, *a, **k)
    tu.get_thumbnail = slow_get
    try:
        for i in range(6):
            Image.new("RGB", (800, 450), (40 * i, 100, 200)).save(os.path.join(folder, f"Extra_{i}.jpg"))
        removed = tu.forget_thumbnails(scan_folder(folder), [(480, 270)])
        w._reload_image_folder_fresh()
        check("다시 읽기: 사진 9장", len(w.media_slides) == 9, str(len(w.media_slides)))
        check("일꾼이 붙잡혀도 결국 모든 카드에 그림", wait(lambda: all(thumbs()) and len(thumbs()) == 9, 25), str(thumbs()))
        check("붙잡힌 일꾼은 새 일꾼으로 바꿈", len(w._old_card_pools) >= 1)
    finally:
        gate.set()
        tu.get_thumbnail = orig_get

    w.close()
    shutil.rmtree(_TMP, ignore_errors=True)
    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
