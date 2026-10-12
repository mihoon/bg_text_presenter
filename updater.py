# -*- coding: utf-8 -*-
"""
새 버전 확인 · 내려받기 · 바꿔 끼우기 (화면 없는 부분)

- GitHub Releases 의 가장 최근 버전(tag 'v1.2.3')을 지금 버전(version.APP_VERSION)과 비교한다.
- 릴리스에 붙은 zip(BgTextPresenter-win64.zip, 안에 BgTextPresenter 폴더)을 내려받아
  임시 폴더에 푼다.
- 프로그램이 켜져 있는 동안에는 exe 와 _internal 폴더의 파일을 바꿀 수 없으므로,
  작은 배치 파일(update.bat)을 띄워 두고 프로그램을 끈다. 배치 파일은 프로그램이
  완전히 꺼지기를 기다렸다가 새 파일을 덮어쓰고 프로그램을 다시 켠다.

배치 파일 안에는 영어만 쓴다. 폴더 이름(사용자 이름이 한글일 수 있음)은 환경 변수로
넘기므로 글자가 깨지지 않는다.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

from version import APP_VERSION

REPO = "mihoon/bg_text_presenter"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
EXE_NAME = "BgTextPresenter.exe"
WORK_DIR_NAME = "BgTextPresenter_update"


class UpdateCancelled(Exception):
    pass


class UpdateError(Exception):
    pass


# ----------------------------------------------------------------------
# 버전 비교
# ----------------------------------------------------------------------
def parse_version(text) -> tuple:
    """'v1.2.3' → (1, 2, 3). 숫자가 없으면 ()"""
    m = re.search(r"(\d+(?:\.\d+)*)", str(text or ""))
    if not m:
        return ()
    return tuple(int(x) for x in m.group(1).split("."))


def is_newer(remote, local=APP_VERSION) -> bool:
    r, l = parse_version(remote), parse_version(local)
    if not r:
        return False
    n = max(len(r), len(l))
    return r + (0,) * (n - len(r)) > l + (0,) * (n - len(l))


# ----------------------------------------------------------------------
# 릴리스 정보
# ----------------------------------------------------------------------
class ReleaseInfo:
    def __init__(self, version, tag="", notes="", page_url=RELEASES_PAGE,
                 asset_url="", asset_name="", asset_size=0):
        self.version = version          # '1.2.3'
        self.tag = tag or f"v{version}"
        self.notes = notes or ""        # 릴리스 설명 (마크다운)
        self.page_url = page_url or RELEASES_PAGE
        self.asset_url = asset_url      # 내려받을 zip ("" 이면 페이지만 열 수 있음)
        self.asset_name = asset_name
        self.asset_size = int(asset_size or 0)

    def __repr__(self):
        return f"ReleaseInfo({self.version}, {self.asset_name or 'no zip'})"


def _request(url, timeout):
    req = urllib.request.Request(url, headers={
        "User-Agent": f"BgTextPresenter/{APP_VERSION}",
        "Accept": "application/vnd.github+json",
    })
    return urllib.request.urlopen(req, timeout=timeout)


def _pick_asset(assets):
    zips = [a for a in assets or [] if str(a.get("name", "")).lower().endswith(".zip")]
    for a in zips:                       # 윈도우용이라고 적힌 것을 먼저
        if "win" in a["name"].lower():
            return a
    return zips[0] if zips else None


def fetch_latest(timeout=8, url=None):
    """가장 최근 릴리스 정보 (없거나 읽을 수 없으면 예외)"""
    with _request(url or LATEST_API, timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    tag = str(data.get("tag_name") or "")
    version = ".".join(str(x) for x in parse_version(tag))
    if not version:
        raise UpdateError(f"버전 번호를 알 수 없는 릴리스: {tag!r}")
    asset = _pick_asset(data.get("assets"))
    return ReleaseInfo(
        version=version, tag=tag, notes=str(data.get("body") or ""),
        page_url=str(data.get("html_url") or RELEASES_PAGE),
        asset_url=str(asset.get("browser_download_url", "")) if asset else "",
        asset_name=str(asset.get("name", "")) if asset else "",
        asset_size=asset.get("size", 0) if asset else 0,
    )


def check_for_update(timeout=8, url=None, local=APP_VERSION):
    """새 버전이 있으면 ReleaseInfo, 없으면 None"""
    try:
        info = fetch_latest(timeout=timeout, url=url)
    except urllib.error.HTTPError as e:
        if e.code == 404:           # 아직 릴리스가 하나도 없음
            return None
        raise
    return info if is_newer(info.version, local) else None


# ----------------------------------------------------------------------
# 내려받기 · 풀기
# ----------------------------------------------------------------------
def work_dir() -> str:
    return os.path.join(tempfile.gettempdir(), WORK_DIR_NAME)


def cleanup_work_dir():
    shutil.rmtree(work_dir(), ignore_errors=True)


def download(url, dest, progress=None, cancelled=None, timeout=30, chunk=256 * 1024):
    """url → dest. progress(받은 바이트, 전체 바이트 또는 0). cancelled() 가 참이면 멈춘다."""
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    part = dest + ".part"
    try:
        with _request(url, timeout) as resp, open(part, "wb") as f:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            if progress:
                progress(0, total)
            while True:
                if cancelled and cancelled():
                    raise UpdateCancelled()
                block = resp.read(chunk)
                if not block:
                    break
                f.write(block)
                done += len(block)
                if progress:
                    progress(done, total)
        if total and done != total:
            raise UpdateError(f"내려받다가 끊겼습니다 ({done}/{total} 바이트)")
        os.replace(part, dest)
    finally:
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
    return dest


def extract_package(zip_path, dest_dir) -> str:
    """zip 을 dest_dir 에 풀고, BgTextPresenter.exe 가 들어 있는 폴더를 돌려준다."""
    shutil.rmtree(dest_dir, ignore_errors=True)
    os.makedirs(dest_dir, exist_ok=True)
    root = os.path.realpath(dest_dir)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():      # 폴더 밖으로 나가는 이름은 거부
                target = os.path.realpath(os.path.join(root, name))
                if target != root and not target.startswith(root + os.sep):
                    raise UpdateError(f"잘못된 파일 이름이 들어 있습니다: {name}")
            zf.extractall(root)
    except zipfile.BadZipFile as e:
        raise UpdateError(f"내려받은 파일이 망가졌습니다: {e}")
    for folder, _dirs, files in os.walk(root):
        if EXE_NAME in files:
            return folder
    raise UpdateError(f"내려받은 파일에 {EXE_NAME} 가 없습니다")


# ----------------------------------------------------------------------
# 바꿔 끼우기
# ----------------------------------------------------------------------
def installed_dir():
    """exe 로 실행 중이면 exe 가 있는 폴더, 파이썬으로 실행 중이면 None"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return None


def can_self_update(target=None) -> bool:
    """이 자리에서 바로 바꿔 끼울 수 있는지 (윈도우 exe + 폴더에 쓸 수 있음)"""
    target = target or installed_dir()
    if not target or os.name != "nt":
        return False
    probe = os.path.join(target, ".bgpt_write_test")
    try:
        with open(probe, "w") as f:
            f.write("x")
        os.remove(probe)
        return True
    except OSError:
        return False


UPDATER_BAT = r"""@echo off
rem BgTextPresenter updater - waits for the app to exit, copies the new files, restarts it.
rem Paths come from environment variables so non-ASCII folder names stay intact.
rem Safety: the old files are backed up first and put back if anything goes wrong,
rem so a failed update never leaves a half-new program folder.
setlocal
set "LOG=%BGPT_WORK%\update_log.txt"
set "OLD=%BGPT_EXE%.old"
set "BAK=%BGPT_WORK%\backup"
echo update start > "%LOG%"
set /a N=0
:wait
tasklist /FI "PID eq %BGPT_PID%" /NH 2>nul | find "%BGPT_PID%" >nul
if errorlevel 1 goto closed
set /a N+=1
if %N% GEQ 60 goto force
ping -n 2 127.0.0.1 >nul
goto wait
:force
echo app did not exit - closing it >> "%LOG%"
taskkill /PID %BGPT_PID% /F >> "%LOG%" 2>&1
ping -n 4 127.0.0.1 >nul
:closed
ping -n 2 127.0.0.1 >nul
if exist "%BGPT_DST%\%OLD%" del /f /q "%BGPT_DST%\%OLD%" >nul 2>&1
rem If the exe cannot be renamed it is still in use - stop before touching anything.
ren "%BGPT_DST%\%BGPT_EXE%" "%OLD%" >> "%LOG%" 2>&1
if errorlevel 1 goto failed
if exist "%BAK%" rmdir /s /q "%BAK%"
robocopy "%BGPT_DST%" "%BAK%" /E /R:2 /W:1 /NP >> "%LOG%" 2>&1
if errorlevel 8 goto undo_rename
robocopy "%BGPT_NEW%" "%BGPT_DST%" /E /IS /IT /R:10 /W:1 /NP >> "%LOG%" 2>&1
if errorlevel 8 goto rollback
del /f /q "%BGPT_DST%\%OLD%" >nul 2>&1
echo done >> "%LOG%"
if "%BGPT_RESTART%"=="0" exit /b 0
start "" /D "%BGPT_DST%" "%BGPT_DST%\%BGPT_EXE%" --updated
exit /b 0
:rollback
echo copy failed - restoring the previous version >> "%LOG%"
robocopy "%BAK%" "%BGPT_DST%" /E /IS /IT /R:10 /W:1 /NP >> "%LOG%" 2>&1
:undo_rename
if exist "%BGPT_DST%\%BGPT_EXE%" del /f /q "%BGPT_DST%\%BGPT_EXE%" >nul 2>&1
ren "%BGPT_DST%\%OLD%" "%BGPT_EXE%" >> "%LOG%" 2>&1
:failed
echo failed >> "%LOG%"
if "%BGPT_RESTART%"=="0" exit /b 1
start "" /D "%BGPT_DST%" "%BGPT_DST%\%BGPT_EXE%" --update-failed
exit /b 1
"""


def write_updater_script(folder) -> str:
    path = os.path.join(folder, "update.bat")
    with open(path, "w", encoding="ascii", newline="\r\n") as f:
        f.write(UPDATER_BAT)
    return path


def launch_updater(new_dir, target_dir, pid=None, folder=None, restart=None, popen=subprocess.Popen):
    """배치 파일을 띄운다. 이 함수가 돌아온 뒤 프로그램을 꺼야 바꿔 끼우기가 시작된다.

    restart=False 면 바꾼 뒤 다시 켜지 않는다 (프로그램을 끌 때 바꾸기).
    """
    folder = folder or work_dir()
    bat = write_updater_script(folder)
    env = dict(os.environ)
    env.update({
        "BGPT_NEW": os.path.abspath(new_dir),
        "BGPT_DST": os.path.abspath(target_dir),
        "BGPT_PID": str(pid or os.getpid()),
        "BGPT_WORK": os.path.abspath(folder),
        "BGPT_EXE": EXE_NAME,
    })
    if restart is not None:
        env["BGPT_RESTART"] = "1" if restart else "0"
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    return popen(["cmd.exe", "/d", "/c", bat], env=env, cwd=folder,
                 creationflags=flags, close_fds=True)


def update_log_path() -> str:
    return os.path.join(work_dir(), "update_log.txt")


def last_update_result() -> str:
    """지난번 바꿔 끼우기 결과: 'done' / 'failed' / '' (기록 없음)"""
    try:
        with open(update_log_path(), "r", encoding="ascii", errors="ignore") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
    except OSError:
        return ""
    for ln in reversed(lines):
        if ln in ("done", "failed"):
            return ln
    return ""
