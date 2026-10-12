# -*- coding: utf-8 -*-
"""새 버전 확인·내려받기·업데이트 창 테스트 - python test_updater.py

GitHub 대신 이 컴퓨터 안에 작은 웹 서버를 띄워 릴리스 정보와 zip 을 내려준다.
"""
import http.server
import io
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import updater
import version

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"   OK   {label}")
    else:
        print(f"   실패 {label}  {detail}")
        FAILURES.append(label)


def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


class Server:
    def __init__(self):
        self.files = {}
        files = self.files

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = files.get(self.path)
                if body is None:
                    self.send_response(404)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def release(self, tag, zip_bytes=None, body="- 고친 점"):
        assets = []
        if zip_bytes is not None:
            self.files["/pkg.zip"] = zip_bytes
            assets.append({"name": "BgTextPresenter-win64.zip", "size": len(zip_bytes),
                           "browser_download_url": self.url + "/pkg.zip"})
        self.files["/latest"] = json.dumps({
            "tag_name": tag, "body": body, "html_url": self.url + "/page", "assets": assets,
        }).encode("utf-8")
        return self.url + "/latest"


def test_logic(srv, tmp):
    print("1) 버전 비교")
    check("v1.0.1 > 1.0.0", updater.is_newer("v1.0.1", "1.0.0"))
    check("1.10 > 1.9", updater.is_newer("1.10", "1.9"))
    check("1.0 == 1.0.0 (새 버전 아님)", not updater.is_newer("1.0", "1.0.0"))
    check("낮은 버전은 아님", not updater.is_newer("v0.9.9", "1.0.0"))
    check("숫자 없는 태그는 무시", not updater.is_newer("latest", "1.0.0"))
    check("지금 버전 숫자", updater.parse_version(version.APP_VERSION) >= (1, 0, 0))

    print("\n2) 릴리스 정보 읽기")
    pkg = make_zip({"BgTextPresenter/BgTextPresenter.exe": b"EXE" * 1000,
                    "BgTextPresenter/_internal/a.dll": b"DLL"})
    url = srv.release("v9.1.0", pkg)
    info = updater.check_for_update(url=url, timeout=5)
    check("새 버전 찾음", info is not None and info.version == "9.1.0", repr(info))
    check("zip 주소", info.asset_url.endswith("/pkg.zip") and info.asset_size == len(pkg))
    check("설명", info.notes == "- 고친 점")
    same = srv.release("v" + version.APP_VERSION, pkg)
    check("같은 버전이면 None", updater.check_for_update(url=same, timeout=5) is None)
    check("릴리스가 하나도 없으면(404) None", updater.check_for_update(url=srv.url + "/none", timeout=5) is None)

    print("\n3) 내려받기 · 풀기")
    seen = []
    dest = os.path.join(tmp, "dl", "pkg.zip")
    updater.download(info.asset_url, dest, progress=lambda d, t: seen.append((d, t)), chunk=1024)
    check("파일 받음", os.path.getsize(dest) == len(pkg))
    check("진행 상황 알림", seen and seen[-1] == (len(pkg), len(pkg)), str(seen[-1:]))
    check("임시 .part 파일 없음", not os.path.exists(dest + ".part"))
    new_dir = updater.extract_package(dest, os.path.join(tmp, "new"))
    check("exe 가 든 폴더", os.path.basename(new_dir) == "BgTextPresenter"
          and os.path.exists(os.path.join(new_dir, "_internal", "a.dll")))

    try:
        updater.download(info.asset_url, os.path.join(tmp, "dl", "x.zip"), cancelled=lambda: True)
        check("취소", False)
    except updater.UpdateCancelled:
        check("취소하면 멈춤 (받던 파일 지움)", not os.path.exists(os.path.join(tmp, "dl", "x.zip.part")))

    bad = os.path.join(tmp, "bad.zip")
    with open(bad, "wb") as f:
        f.write(make_zip({"../evil.txt": b"x", "BgTextPresenter/BgTextPresenter.exe": b"E"}))
    try:
        updater.extract_package(bad, os.path.join(tmp, "bad"))
        check("폴더 밖으로 나가는 이름 거부", False)
    except updater.UpdateError:
        check("폴더 밖으로 나가는 이름 거부", not os.path.exists(os.path.join(tmp, "evil.txt")))
    noexe = os.path.join(tmp, "noexe.zip")
    with open(noexe, "wb") as f:
        f.write(make_zip({"readme.txt": b"x"}))
    try:
        updater.extract_package(noexe, os.path.join(tmp, "noexe"))
        check("exe 없는 zip 거부", False)
    except updater.UpdateError:
        check("exe 없는 zip 거부", True)

    print("\n4) 바꿔 끼우는 배치 파일")
    calls = []
    work = os.path.join(tmp, "work")
    os.makedirs(work)
    updater.launch_updater(new_dir, os.path.join(tmp, "설치 폴더"), pid=4321, folder=work,
                           restart=False, popen=lambda *a, **k: calls.append((a, k)))
    bat = open(os.path.join(work, "update.bat"), "rb").read()
    check("배치 파일은 영어만 (한글 폴더도 안전)", all(b < 128 for b in bat))
    check("윈도우 줄바꿈", b"\r\n" in bat and b"\n\n" not in bat.replace(b"\r\n", b"\n\r"))
    env = calls[0][1]["env"]
    check("폴더는 환경 변수로", env["BGPT_DST"].endswith("설치 폴더") and env["BGPT_PID"] == "4321"
          and env["BGPT_NEW"] == os.path.abspath(new_dir) and env["BGPT_RESTART"] == "0")
    check("프로그램이 꺼지길 기다렸다 덮어쓰고 다시 켬",
          b"tasklist" in bat and b"robocopy" in bat and b"--updated" in bat and b'"%BGPT_RESTART%"=="0"' in bat)
    check("덮어쓰기 전에 예전 파일 보관, 실패하면 되돌림",
          bat.index(b'robocopy "%BGPT_DST%" "%BAK%"') < bat.index(b'robocopy "%BGPT_NEW%"')
          and b":rollback" in bat and b'robocopy "%BAK%" "%BGPT_DST%"' in bat)
    check("exe 를 못 바꾸면(아직 켜져 있음) 아무것도 건드리지 않음",
          bat.index(b'ren "%BGPT_DST%\\%BGPT_EXE%"') < bat.index(b'robocopy "%BGPT_DST%" "%BAK%"'))
    check("끌 때 바꾸기가 실패해도 다시 켜지 않음",
          bat.split(b":failed")[1].index(b'"%BGPT_RESTART%"=="0"') < bat.split(b":failed")[1].index(b"start"))
    check("cmd 자동 실행 무시 (/d)", calls[0][0][0][:3] == ["cmd.exe", "/d", "/c"])

    print("\n4-1) 지난번 바꿔 끼우기 결과 읽기")
    old_tmp = updater.tempfile.tempdir
    updater.tempfile.tempdir = tmp
    try:
        os.makedirs(updater.work_dir(), exist_ok=True)
        with open(updater.update_log_path(), "w") as f:
            f.write("update start\r\nrobocopy...\r\nfailed\r\n")
        check("실패 기록", updater.last_update_result() == "failed")
        with open(updater.update_log_path(), "w") as f:
            f.write("update start\r\ndone\r\n")
        check("성공 기록", updater.last_update_result() == "done")
        os.remove(updater.update_log_path())
        check("기록 없음", updater.last_update_result() == "")
    finally:
        updater.tempfile.tempdir = old_tmp


def test_gui(srv, tmp):
    print("\n5) 프로그램 화면에서")
    os.environ["BGPT_SETTINGS_DIR"] = os.path.join(tmp, "settings")
    os.environ["BGPT_NO_UPDATE_CHECK"] = "1"
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    from main_window import MainWindow
    w = MainWindow()
    u = w.updates

    def wait(cond, sec=5):
        end = time.time() + sec
        while time.time() < end and not cond():
            app.processEvents()
            time.sleep(0.01)
        return cond()

    check("창 제목에 버전", f"v{version.APP_VERSION}" in w.windowTitle(), w.windowTitle())
    check("상단 단추", w.btn_update.text().startswith("🔄"))

    pkg = make_zip({"BgTextPresenter/BgTextPresenter.exe": b"NEW", "BgTextPresenter/_internal/b.dll": b"B"})
    url = srv.release("v9.2.0", pkg, body="**새 기능**")
    u.fetch = lambda: updater.check_for_update(url=url, timeout=5)
    shown = []
    u.show_dialog = lambda info: shown.append(info.version)

    # (가) 송출 중이 아니면 창이 뜬다
    u.check(manual=False)
    check("새 버전이면 업데이트 창", wait(lambda: shown == ["9.2.0"]), str(shown))
    check("단추가 금색 '새 버전'", "9.2.0" in w.btn_update.text() and "ffd866" in w.btn_update.styleSheet())

    # (나) 송출 중이면 창 대신 단추·상태 표시만
    shown.clear()
    u.pending = None
    w.presenter.set_text("송출 중인 가사")
    check("송출 중으로 판단", w._is_presenting_now())
    u.check(manual=False)
    wait(lambda: u.pending is not None)
    app.processEvents()
    check("송출 중이면 창을 띄우지 않음", shown == [], str(shown))
    check("상태 표시줄 안내", "9.2.0" in w.statusBar().currentMessage(), w.statusBar().currentMessage())
    w.presenter.set_text("")
    w.btn_update.click()
    check("금색 단추를 누르면 창", shown == ["9.2.0"])

    # (다) 건너뛴 버전은 자동으로는 알리지 않음, 직접 확인하면 보여 줌
    shown.clear()
    u.pending = None
    u.settings.setValue(u.SETTINGS_SKIP, "9.2.0")
    u.check(manual=False)
    wait(lambda: u.pending is not None)
    app.processEvents()
    check("건너뛴 버전은 조용히", shown == [])
    u.pending = None
    u.check(manual=True)
    check("직접 확인하면 보여 줌", wait(lambda: shown == ["9.2.0"]))

    # (라) 업데이트 창 자체
    del u.show_dialog
    dlg = u.make_dialog(updater.ReleaseInfo("9.2.0", notes="**새 기능**", asset_url="x"))
    check("바뀐 점 표시", "새 기능" in dlg.notes.toPlainText())
    check("자동 확인 체크", dlg.chk_auto.isChecked())

    # (마) 지금 업데이트 → 내려받기 → 지금 다시 켜기
    install_dir = os.path.join(tmp, "installed")
    os.makedirs(install_dir)
    launched, quit_called = [], []
    u.installed_dir = lambda: install_dir
    u.can_self_update = lambda: True
    u.launch_func = lambda new, target, restart=None: launched.append((new, target, restart))
    u.quit_app = lambda: quit_called.append(1)
    answers = []
    u._on_downloaded_orig = u._on_downloaded

    def fake_ready(new_dir):           # "지금 다시 켜기" 를 누른 것으로
        u._close_progress()
        u.ready_dir, u.ready_version = new_dir, "9.2.0"
        answers.append(new_dir)
        u.apply_now()
    u.download_done.disconnect(u._on_downloaded)
    u.download_done.connect(fake_ready)
    old_tmp = updater.tempfile.tempdir
    updater.tempfile.tempdir = tmp
    try:
        info = updater.check_for_update(url=url, timeout=5)
        u.start_install(info)
        check("내려받아 풀기", wait(lambda: answers, 10), str(answers))
        check("새 exe 가 풀림", answers and open(os.path.join(answers[0], "BgTextPresenter.exe"), "rb").read() == b"NEW")
        check("바꿔 끼우기 시작 + 프로그램 끔",
              launched and launched[0][1] == install_dir and launched[0][2] is True and quit_called == [1],
              str(launched))
        check("진행 창 닫힘", u._progress is None)

        # (바) 끌 때 바꾸기
        launched.clear()
        u.ready_dir = answers[0]
        w.close()
        check("끌 때 바꾸기 (다시 켜지 않음)", launched and launched[0][2] is False, str(launched))
    finally:
        updater.tempfile.tempdir = old_tmp

    # (아-1) 취소한 내려받기가 아직 멈추는 중이면 새로 시작하지 않음
    blocker = threading.Event()
    u.download_func = lambda *a, **k: blocker.wait(5)
    started = []
    u.download_failed.disconnect(u._on_download_failed)
    u.download_failed.connect(lambda e: (u._close_progress(), started.append(("failed", e))))
    u.extract_func = lambda *a, **k: (_ for _ in ()).throw(updater.UpdateError("x"))
    u.start_install(info)
    first = u._download_thread
    u._on_cancel()
    u.start_install(info)
    check("취소 뒤 바로 다시 눌러도 내려받기가 겹치지 않음", u._download_thread is first)
    check("취소 표시가 그 내려받기에만", u._cancel_event.is_set())
    blocker.set()
    wait(lambda: not first.is_alive())
    app.processEvents()
    u.download_func = updater.download
    u.extract_func = updater.extract_package
    u.download_failed.disconnect()
    u.download_failed.connect(u._on_download_failed)

    # (아-2) 윈도우를 끄는 중이면 '끌 때 바꾸기' 하지 않음
    launched.clear()
    u.ready_dir = answers[0] if answers else tmp
    u._on_session_ending()
    u.apply_on_exit()
    check("윈도우 종료 중에는 바꾸지 않음", launched == [])
    u._session_ending = False
    u.ready_dir = ""

    # (사) 내려받기 실패
    failed = []
    u.download_failed.disconnect(u._on_download_failed)
    u.download_failed.connect(lambda e: (u._close_progress(), failed.append(e)))
    srv.files.pop("/pkg.zip")
    u.start_install(info)
    check("받을 파일이 없으면 실패 알림", wait(lambda: failed, 10) and "404" in failed[0], str(failed))

    # (아) exe 가 아니면(파이썬 실행) 자동 확인 안 함
    os.environ.pop("BGPT_NO_UPDATE_CHECK", None)
    u.installed_dir = lambda: None
    check("파이썬으로 실행 중이면 자동 확인 안 함", u.start_auto_check() is False)
    u.installed_dir = lambda: install_dir
    u.set_auto_check(False)
    check("설정을 끄면 자동 확인 안 함", u.start_auto_check() is False)
    u.set_auto_check(True)
    check("exe + 설정 켬 → 자동 확인 예약", u.start_auto_check(delay_ms=60000) is True)
    os.environ["BGPT_NO_UPDATE_CHECK"] = "1"

    # (자) 영어
    w.current_lang = "en"
    u.pending = None
    u.retranslate()
    check("영어 단추", w.btn_update.text() == "🔄 Check for updates")


def main():
    tmp = tempfile.mkdtemp(prefix="bgpt_upd_")
    srv = Server()
    try:
        test_logic(srv, tmp)
        test_gui(srv, tmp)
    finally:
        srv.httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)
    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
