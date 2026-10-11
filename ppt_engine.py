# -*- coding: utf-8 -*-
"""
파워포인트(.pptx/.ppt) 슬라이드를 이미지로 내보내는 엔진 (Windows + PowerPoint 필요)

로딩 시간을 줄이기 위한 설계 요점
1. 캐시 우선: 경로+수정시각+크기 해시로 캐시 폴더를 만든다. 캐시가 완전하면
   COM(파워포인트)을 아예 띄우지 않으므로 두 번째 로드부터는 즉시 열린다.
2. 점진적 내보내기: 슬라이드를 한 장씩 내보내며 콜백으로 알린다. 전체 완료를
   기다리지 않고 첫 장이 준비되는 즉시 송출할 수 있다.
3. 전용 작업 스레드: COM은 스레드 친화적이므로 한 스레드에서만 사용하고,
   파워포인트 인스턴스를 살려 둔 채 재사용한다 → 두 번째 파일부터 실행 비용이 없다.
4. 워밍업: 파일 선택 대화상자를 여는 동안 파워포인트를 미리 띄워 첫 로드에서
   2~5초를 줄인다.
5. 부분 캐시 재개: 중간에 취소되면 이미 내보낸 장은 건너뛰고 이어서 진행한다.
6. 사용자가 직접 열어 둔 파워포인트는 절대 종료하지 않는다(우리가 띄운 경우만 정리).

이 모듈은 Qt에 의존하지 않는다(순수 콜백). GUI 스레드로의 전달은 호출자가
Qt 시그널로 감싼다. pywin32는 함수 안에서만 import 하므로 이 모듈 자체는
어느 OS에서나 안전하게 import 된다.
"""
import contextlib
import hashlib
import json
import os
import queue
import shutil
import sys
import tempfile
import threading
import time
import uuid
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

PPT_EXTS = {".pptx", ".ppt", ".pptm", ".ppsx", ".pps"}

# 5: 슬라이드 그림을 PDF 를 거쳐 만들도록 바꿈 (파일에 포함 저장된 글꼴 유지).
#    이 번호를 올려야 예전 방식으로 만든 이미지 캐시가 버려지고 다시 만들어진다.
CACHE_VERSION = 5
CACHE_ROOT = (Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir())
              / "BgTextPresenter" / "ppt_cache")

DEFAULT_EXPORT_WIDTH = 1920   # 송출 해상도(1080p)에 맞춘 기본 내보내기 폭
MAX_EXPORT_SCALE = 3          # 원본 크기의 최대 몇 배까지 내보낼지 (용량·시간 제한)
MAX_CACHED_DECKS = 20         # 캐시 폴더가 무한정 늘지 않도록 보관 개수 제한
# 한 번에 PDF 로 내보낼 장수. 처음엔 작게(빨리 보이게), 뒤로 갈수록 크게
# (COM 호출은 중간에 끊을 수 없으므로, 한 번이 길수록 조작이 밀린다)
# 10~12장을 실제 파일(포함 글꼴·이미지가 많은 46장짜리)로 재 보니 한 번에
# 4~5초씩 걸려 애니메이션 모드 조작이 그만큼 밀렸다. 최대 장수를 낮춰
# 한 번의 호출이 2초를 크게 넘지 않도록 한다(총 소요 시간은 조금 늘어도
# 실시간 조작이 훨씬 중요하다).
_CHUNK_SPANS = (2, 3, 4, 5)

# 슬라이드 XML(OOXML)의 presentationml 네임스페이스 - 애니메이션 유무를
# 파워포인트 COM 대신 파일에서 직접 읽을 때 쓴다 (아래 _xml_animation_count 참고)
_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

_META_NAME = "meta.json"
_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
# 노트를 읽는 방식이 바뀐 차례. 예전(1)에는 노트 페이지의 '첫 글상자'를 읽어서,
# 노트가 없는 슬라이드는 쪽 번호 상자의 숫자("1", "3" …)가 노트처럼 들어갔다.
NOTES_REV = 2
_OOXML_EXTS = (".pptx", ".pptm", ".ppsx", ".ppsm", ".potx", ".potm")
_MSO_PLACEHOLDER = 14            # msoPlaceholder
_PP_PLACEHOLDER_BODY = 2         # ppPlaceholderBody (노트 본문)

# "취소됨"을 None(=이 방식을 쓸 수 없음)과 구분하기 위한 표식
_CANCELLED = object()

# PowerPoint 상수
_PP_ALERTS_NONE = 1
_PP_WINDOW_MINIMIZED = 2
_PP_SHOW_ALL = 1              # ppShowAll (전체 슬라이드)
# 슬라이드쇼를 잠시 숨겨 둘 화면 밖 위치 (1번 슬라이드가 스치는 것을 막는다)
_OFFSCREEN_RECT = (-32000, -32000, 1280, 720)
_PP_SHOW_SLIDE_RANGE = 2      # ppShowSlideRange (StartingSlide가 적용되는 범위 지정)
_PP_FIXED_FORMAT_PDF = 2      # ppFixedFormatTypePDF
_PP_INTENT_PRINT = 2          # ppFixedFormatIntentPrint (화면용보다 품질이 높다)
_PP_HANDOUT_ORDER = 1         # ppPrintHandoutVerticalFirst
_PP_OUTPUT_SLIDES = 1         # ppPrintOutputSlides
_PP_SAVE_AS_PDF = 32          # ppSaveAsPDF
_PP_PRINT_SLIDE_RANGE = 4     # ppPrintSlideRange (PrintRange 가 적용되는 범위 지정)
_PP_SHOW_RUNNING = 1          # ppSlideShowRunning
_PP_SHOW_BLACK = 3            # ppSlideShowBlackScreen ('B' 키를 누른 상태)
_MSO_TRUE = -1
_MSO_FALSE = 0


def is_ppt_file(path) -> bool:
    """확장자로 파워포인트 파일인지 판별"""
    if not path:
        return False
    return os.path.splitext(str(path))[1].lower() in PPT_EXTS


def pdf_render_support():
    """PDF 를 거쳐 슬라이드를 그릴 수 있는지 (불가하면 안내 메시지)

    파워포인트의 '그림으로 내보내기'는 파일에 포함 저장된 글꼴을 쓰지 않아
    글꼴이 바뀐다. PDF 를 거치면 글꼴이 유지되지만 변환 라이브러리가 필요하다.
    """
    kind, _ = _PptWorker._pdf_renderer()
    if kind:
        return True, ""
    return False, (
        "슬라이드 글꼴이 원본과 다르게 보일 수 있습니다. "
        "원본 글꼴을 유지하려면 명령 프롬프트에서 pip install pypdfium2 를 실행해 주세요."
    )


def powerpoint_support():
    """(사용 가능 여부, 안내 메시지) 반환. 메시지는 사용 불가일 때만 채워진다."""
    if os.name != "nt":
        return False, "파워포인트 슬라이드 불러오기는 Windows에서만 지원됩니다."
    try:
        import win32com.client  # noqa: F401
        import pythoncom  # noqa: F401
    except ImportError:
        return False, (
            "파워포인트 슬라이드를 불러오려면 pywin32 패키지가 필요합니다.\n\n"
            "명령 프롬프트에서 다음을 실행해 주세요:\n"
            "    pip install pywin32"
        )
    return True, ""


# ----------------------------------------------------------------------
# 캐시
# ----------------------------------------------------------------------
def _fingerprint(path: str) -> str:
    """파일 내용이 바뀌면 달라지는 캐시 키"""
    p = os.path.abspath(path)
    try:
        st = os.stat(p)
        raw = f"{p}|{st.st_mtime_ns}|{st.st_size}|v{CACHE_VERSION}"
    except OSError:
        raw = f"{p}|missing|v{CACHE_VERSION}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def cache_dir_for(path: str) -> Path:
    return CACHE_ROOT / _fingerprint(path)


def slide_paths(cache_dir, count: int) -> list:
    """슬라이드 이미지 경로 목록(결정적). 아직 만들어지지 않은 파일도 포함한다.

    경로가 미리 정해지므로, 장수만 알면 곧바로 빈 카드를 배치해 둘 수 있다.
    """
    d = Path(cache_dir)
    return [str(d / f"slide_{i:04d}.jpg") for i in range(1, int(count) + 1)]


def read_cache(path: str):
    """완전한 캐시가 있으면 {'slides', 'notes', 'count'}, 없으면 None

    COM을 전혀 쓰지 않으므로 매우 빠르다.
    """
    cache_dir = cache_dir_for(path)
    meta_file = cache_dir / _META_NAME
    if not meta_file.exists():
        return None
    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception:
        return None
    if not meta.get("done"):
        return None
    if int(meta.get("version", 0)) != CACHE_VERSION:
        return None
    count = int(meta.get("count", 0))
    if count <= 0:
        return None
    paths = slide_paths(cache_dir, count)
    if not all(os.path.exists(p) for p in paths):
        return None
    notes = list(meta.get("notes") or [])
    if int(meta.get("notes_rev", 1)) < NOTES_REV:
        # 예전 방식으로 읽은 노트 - 쪽 번호가 노트로 들어가 있을 수 있다. 한 번 고쳐 둔다.
        notes = _repair_old_notes(path, notes, count)
        meta["notes"] = notes
        meta["notes_rev"] = NOTES_REV
        try:
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False)
        except OSError:
            pass
    try:
        os.utime(meta_file, None)   # 최근 사용 표시 (오래된 캐시 정리 기준)
    except OSError:
        pass
    return {"slides": paths, "notes": notes, "count": count}


def _repair_old_notes(path, notes, count):
    """예전에 저장한 노트 목록을 바로잡는다.

    pptx 처럼 zip 형식이면 파일에서 노트 본문만 다시 읽는다(파워포인트 없이, 빠르다).
    그렇지 못하면(.ppt 등) 슬라이드 번호와 똑같은 숫자만 들어 있는 노트를 지운다.
    """
    if str(path).lower().endswith(_OOXML_EXTS):
        fresh = xml_slide_notes(path)
        if fresh is not None and len(fresh) == count:
            return fresh
    fixed = []
    for i in range(count):
        note = notes[i] if i < len(notes) else ""
        if (note or "").strip() == str(i + 1):
            note = ""
        fixed.append(note or "")
    return fixed


def _xml_paragraph_text(p_elem) -> str:
    parts = []
    for child in p_elem:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag in ("r", "fld"):
            t = child.find(f"{{{_NS_A}}}t")
            if t is not None and t.text:
                parts.append(t.text)
        elif tag == "br":
            parts.append("\n")
    return "".join(parts)


def xml_slide_notes(pptx_path):
    """pptx 파일에서 슬라이드 순서대로 '노트 본문'만 읽는다 (파워포인트 없이).

    노트 페이지에는 본문 말고도 쪽 번호·머리글·날짜 상자가 있는데, 그것들은 읽지
    않는다. 읽을 수 없으면 None.
    """
    try:
        order = _pptx_slide_parts(pptx_path)
        result = []
        with zipfile.ZipFile(pptx_path) as zf:
            names = set(zf.namelist())
            for part in order:
                folder, name = part.rsplit("/", 1)
                rels_name = f"{folder}/_rels/{name}.rels"
                note_part = None
                if rels_name in names:
                    for rel in ET.fromstring(zf.read(rels_name)):
                        if (rel.get("Type") or "").endswith("/notesSlide"):
                            target = rel.get("Target") or ""
                            note_part = "ppt/" + target.split("../")[-1] if "../" in target \
                                else f"{folder}/{target}"
                            break
                if not note_part or note_part not in names:
                    result.append("")
                    continue
                root = ET.fromstring(zf.read(note_part))
                texts = []
                for sp in root.iter(f"{{{_NS_P}}}sp"):
                    ph = sp.find(f"./{{{_NS_P}}}nvSpPr/{{{_NS_P}}}nvPr/{{{_NS_P}}}ph")
                    if ph is None or ph.get("type") != "body":
                        continue
                    body = sp.find(f"./{{{_NS_P}}}txBody")
                    if body is None:
                        continue
                    paras = [_xml_paragraph_text(p) for p in body.findall(f"{{{_NS_A}}}p")]
                    text = "\n".join(paras).strip()
                    if text:
                        texts.append(text)
                result.append("\n".join(texts))
        return result
    except Exception:
        return None


def prune_cache(max_decks: int = MAX_CACHED_DECKS):
    """오래 쓰지 않은 캐시 폴더부터 삭제"""
    try:
        if not CACHE_ROOT.exists():
            return
        dirs = [d for d in CACHE_ROOT.iterdir() if d.is_dir()]
        if len(dirs) <= max_decks:
            return

        def _used_at(d):
            meta = d / _META_NAME
            try:
                return (meta if meta.exists() else d).stat().st_mtime
            except OSError:
                return 0.0

        for d in sorted(dirs, key=_used_at)[: len(dirs) - max_decks]:
            shutil.rmtree(d, ignore_errors=True)
    except Exception as e:
        print(f"[ppt_engine] 캐시 정리 실패: {e}")


def clear_cache():
    """캐시 전체 삭제 (설정 초기화용)"""
    shutil.rmtree(CACHE_ROOT, ignore_errors=True)


# ----------------------------------------------------------------------
# 작업 스레드 (COM 전용)
# ----------------------------------------------------------------------
def _natural_key(name: str):
    """'슬라이드10.JPG'가 '슬라이드2.JPG' 뒤에 오도록 숫자를 수치로 비교"""
    import re
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", name)]


def _com_get(obj, name, default=None):
    """COM 속성 읽기.

    pywin32 동적 디스패치는 타입 정보를 못 읽으면 속성을 '메서드'로 노출한다.
    (예: SlideShowWindow.HWND 가 값이 아니라 bound method 로 온다)
    그래서 값이 호출 가능하면 한 번 호출해서 실제 값을 꺼낸다.
    """
    try:
        value = getattr(obj, name)
    except Exception:
        return default
    if callable(value):
        try:
            value = value()
        except Exception:
            return default
    return default if value is None else value



@contextlib.contextmanager
def _keep_our_windows_on_top():
    """파워포인트 창이 잠깐 떴다 최소화되는 동안 우리 창이 그 위에 있도록 한다.

    파워포인트는 파일을 '문서 창과 함께' 열어야 슬라이드쇼를 끝내도 파일이 닫히지
    않는다. 그런데 문서 창은 열리는 순간 화면에 나타났다가, 우리가 최소화하기까지
    잠깐 이 프로그램(과 송출 화면) 앞에 보인다. 그 짧은 동안만 우리 창들을 '항상 위'로
    올려 두어 파워포인트 창이 뒤에서 열리게 하고, 파워포인트가 키보드 초점을 가져가지
    못하게 막는다. 끝나면 원래대로 되돌린다. (윈도우가 아니면 아무 일도 하지 않는다)
    """
    changed = []
    user32 = None
    locked = False
    flags = 0x0001 | 0x0002 | 0x0010 | 0x4000   # NOSIZE | NOMOVE | NOACTIVATE | ASYNCWINDOWPOS
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            pid = os.getpid()
            found = []
            proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

            def _collect(hwnd, _lparam):
                try:
                    h = wintypes.HWND(hwnd)
                    if user32.IsWindowVisible(h) and not user32.IsIconic(h):
                        owner = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(h, ctypes.byref(owner))
                        if owner.value == pid:
                            exstyle = user32.GetWindowLongW(h, -20)         # GWL_EXSTYLE
                            if not exstyle & 0x00000008:                     # WS_EX_TOPMOST
                                found.append(hwnd)
                except Exception:
                    pass
                return True

            user32.EnumWindows(proc_type(_collect), 0)
            for hwnd in found:
                if user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(-1),
                                       0, 0, 0, 0, wintypes.UINT(flags)):      # HWND_TOPMOST
                    changed.append(hwnd)
            locked = bool(user32.LockSetForegroundWindow(wintypes.UINT(1)))        # LSFW_LOCK
        except Exception as e:
            print(f"[ppt_engine] 창 가리기 준비 실패(무시): {e}")
    try:
        yield
    finally:
        if user32 is not None:
            try:
                from ctypes import wintypes
                for hwnd in changed:
                    user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(-2),
                                        0, 0, 0, 0, wintypes.UINT(flags))     # HWND_NOTOPMOST
                if locked:
                    user32.LockSetForegroundWindow(wintypes.UINT(2))                   # LSFW_UNLOCK
            except Exception:
                pass

def _safe(fn, *args):
    if fn is None:
        return
    try:
        fn(*args)
    except Exception as e:
        print(f"[ppt_engine] 콜백 오류: {e}")


def _pptx_slide_parts(pptx_path):
    """pptx(zip)에서 '표시 순서 → 실제 슬라이드 XML 파일' 목록을 만든다.

    슬라이드 파일 이름(slideN.xml)은 만들어진 순서일 뿐이다 - 파워포인트에서
    슬라이드 순서를 바꿔도 파일 이름은 그대로이고, presentation.xml의
    sldIdLst 순서 + 관계(rels) 파일로만 실제 화면 순서를 알 수 있다.
    .ppt(옛 바이너리 형식)처럼 zip이 아니면 예외가 나서 빈 목록을 준다.
    """
    with zipfile.ZipFile(pptx_path) as zf:
        pres_xml = zf.read("ppt/presentation.xml")
        rels_xml = zf.read("ppt/_rels/presentation.xml.rels")
    rel_map = {}
    for rel in ET.fromstring(rels_xml):
        rid = rel.get("Id")
        target = rel.get("Target")
        if rid and target and "slides/" in target:
            rel_map[rid] = "ppt/" + target.split("../")[-1]
    order = []
    root = ET.fromstring(pres_xml)
    sld_id_lst = root.find(f"{{{_NS_P}}}sldIdLst")
    if sld_id_lst is not None:
        for sld_id in sld_id_lst:
            rid = sld_id.get(f"{{{_NS_R}}}id")
            part = rel_map.get(rid)
            if part:
                order.append(part)
    return order


def _xml_animation_count(pptx_path, part_name):
    """슬라이드 XML을 직접 읽어 애니메이션 효과 수를 센다 (COM 없이).

    <p:timing> 안의 메인 시퀀스(첫 p:seq) 바로 아래 있는 p:par 개수를
    센다. 파워포인트가 TimeLine.MainSequence.Count로 세는 것과 정확히
    같지 않을 수 있지만(트리거로 묶인 별도 시퀀스 등 드문 경우), '효과가
    있다/없다' 판단과 대략적인 개수 표시에는 충분하고 실제로 필요한 건
    그게 전부다. 실패하면 -1(알 수 없음 - 호출한 쪽에서 COM 방식으로
    대체해야 한다).
    """
    try:
        with zipfile.ZipFile(pptx_path) as zf:
            data = zf.read(part_name)
        root = ET.fromstring(data)
    except Exception:
        return -1
    seq = root.find(f".//{{{_NS_P}}}timing//{{{_NS_P}}}seq")
    if seq is None:
        return 0
    child_list = seq.find(f"./{{{_NS_P}}}cTn/{{{_NS_P}}}childTnLst")
    if child_list is None:
        return 0
    return len(child_list.findall(f"./{{{_NS_P}}}par"))


class _Job:
    __slots__ = ("kind", "path", "on_count", "on_slide", "on_done", "on_error",
                 "on_cancelled", "cancel", "width", "extract_notes",
                 "action", "payload", "first_index", "queued_at")

    def __init__(self, kind, path=None, on_count=None, on_slide=None, on_done=None,
                 on_error=None, on_cancelled=None, cancel=None, width=None,
                 extract_notes=False, action="", payload=None, first_index=1):
        self.kind = kind
        self.path = path
        self.action = action
        self.payload = payload or {}
        self.on_count = on_count
        self.on_slide = on_slide
        self.on_done = on_done
        self.on_error = on_error
        self.on_cancelled = on_cancelled
        self.cancel = cancel
        self.width = width
        self.extract_notes = extract_notes
        self.first_index = max(1, int(first_index or 1))   # 가장 먼저 필요한 슬라이드
        self.queued_at = time.time()      # 큐에서 얼마나 기다렸는지 재기 위해


class _PptWorker(threading.Thread):
    """파워포인트 COM 작업을 처리하는 단일 스레드

    COM 객체는 생성한 스레드에서만 써야 하므로 모든 작업을 이 스레드에 모으고,
    파워포인트 인스턴스를 살려 둔 채 재사용한다.
    """

    def __init__(self):
        super().__init__(name="ppt-engine", daemon=True)
        self._queue = queue.Queue()
        self._app = None
        self._we_launched = False   # 우리가 띄운 파워포인트인지 (종료 여부 판단)
        # 슬라이드쇼(애니메이션 모드) 상태 - COM 객체는 이 스레드에서만 쓴다
        self._show_pres = None
        self._show_window = None
        self._last_render_size = None   # PDF 로 만든 그림의 실제 크기
        self._show_temp = None
        self._show_total = 0        # 쇼 도중 바뀌지 않으므로 캐시 (COM 호출 절약)
        self._show_source = ""      # 현재 쇼의 원본 파일 (재사용/재시작용)
        # 열어 둔 프레젠테이션을 만든 시점의 원본 파일 지문 - 파일이 바뀌었으면
        # 미리 열어 둔 것을 버리고 다시 연다 (옛 내용으로 쇼가 뜨지 않도록)
        self._show_fingerprint = ""
        # 사용자가 파워포인트에서 직접 열어 둔 것을 받은 경우 - 우리가 닫으면
        # 저장하지 않은 편집 내용이 사라지므로 절대 Close 하지 않는다
        self._show_pres_foreign = False
        # 발표 방식 고정 설정(애니메이션 켜기 등)을 이미 해 둔 프레젠테이션
        self._show_settings_ready_for = None
        self._show_rect = None      # 슬라이드쇼를 올릴 모니터 영역
        self._show_range_start = 1  # 현재 쇼 범위의 첫 슬라이드
        self._anim_cache = {}       # (프레젠테이션id, 슬라이드번호) → (효과수, 설명)
        self._slide_xml_parts = None      # 표시 순서 → 슬라이드 XML 파일 경로
        self._slide_xml_parts_src = ""    # 위 목록을 만든 원본 파일 경로

    # 슬라이드쇼 조작 명령 (사용자가 기다리는 명령)
    _SHOW_COMMANDS = ("start", "next", "prev", "goto", "stop")

    def submit(self, job: _Job):
        # 조작 명령이 들어오면 대기 중인 상태 조회를 버린다.
        # (COM 호출은 이 스레드 하나로 직렬 처리되므로, 밀린 조회가 앞에 있으면
        #  클릭이 몇 초 뒤에야 반영된다)
        if job.kind == "show" and job.action in self._SHOW_COMMANDS:
            self._drop_pending(drop_goto=(job.action == "goto"))
        self._queue.put(job)

    def _drop_pending(self, drop_goto=False):
        """대기 중인 상태 조회(및 밀린 슬라이드 점프)를 큐에서 제거한다"""
        kept = []
        try:
            while True:
                job = self._queue.get_nowait()
                if job.kind == "show":
                    if job.action == "state":
                        # 조회는 언제든 버려도 되지만, 버렸다는 것은 알려야 한다.
                        # 아무 답도 안 가면 호출자는 '아직 기다리는 중'으로 알고
                        # 다음 조회를 미루다가, 결국 몇 초 뒤에야 다시 보낸다.
                        _safe(job.on_done, {})   # show 작업은 on_done 이 상태 콜백
                        continue
                    if drop_goto and job.action == "goto":
                        continue                      # 더 최근 점프로 대체된다
                kept.append(job)
        except queue.Empty:
            pass
        for job in kept:
            self._queue.put(job)

    def stop(self):
        self._queue.put(_Job("stop"))

    # --- 스레드 본체 ---
    def run(self):
        com_ready = False
        try:
            import pythoncom
        except ImportError:
            print("[ppt_engine] pythoncom을 불러올 수 없습니다.")
            return
        try:
            pythoncom.CoInitialize()
            com_ready = True
        except Exception as e:
            print(f"[ppt_engine] CoInitialize 실패: {e}")

        try:
            while True:
                job = self._queue.get()
                if job is None or job.kind == "stop":
                    break
                try:
                    if job.kind == "warmup":
                        self._ensure_app()
                    elif job.kind == "export":
                        self._do_export(job)
                    elif job.kind == "show":
                        waited = time.time() - job.queued_at
                        if waited > 0.3:
                            print(f"[ppt_engine] 조작({job.action})이 큐에서 "
                                  f"{waited:.1f}초 기다렸습니다 "
                                  f"(앞 작업이 COM 스레드를 쓰고 있었습니다)")
                        ran_at = time.time()
                        self._do_show(job)
                        ran = time.time() - ran_at
                        # '조작이 밀렸다'는 앞 작업의 대기시간으로 알 수 있지만,
                        # 그 앞 작업 자체가 무엇이었는지(state 조회 자체가 느렸는지,
                        # 다른 조작이 느렸는지)는 이 실행시간을 봐야 알 수 있다.
                        if ran > 0.3:
                            print(f"[ppt_engine] 조작({job.action}) 실행에 "
                                  f"{ran:.1f}초 걸렸습니다")
                except Exception as e:
                    message = str(e) or e.__class__.__name__
                    print(f"[ppt_engine] {job.kind} 작업 실패: {message}")
                    _safe(job.on_error, message)
        finally:
            self._release_app()
            if com_ready:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    # --- 파워포인트 인스턴스 ---
    def _ensure_app(self):
        if self._app is not None:
            try:
                _ = self._app.Presentations.Count   # 아직 살아있는지 확인
                return self._app
            except Exception:
                self._app = None
                self._we_launched = False

        import win32com.client
        try:
            # 이미 실행 중인 파워포인트에 붙는다 (매우 빠름)
            app = win32com.client.GetActiveObject("PowerPoint.Application")
            self._we_launched = False
        except Exception:
            # 없으면 새로 띄운다 (2~5초)
            app = win32com.client.Dispatch("PowerPoint.Application")
            self._we_launched = True

        try:
            app.DisplayAlerts = _PP_ALERTS_NONE
        except Exception:
            pass
        if self._we_launched:
            self._make_ready(app)
        self._app = app
        return app

    @staticmethod
    def _make_ready(app):
        """우리가 띄운 파워포인트를 자동화가 가능한 상태로 만든다.

        파워포인트는 Word/Excel과 달리 창이 보이지 않는 상태(Visible=0)에서는
        Presentations.Open 이 -2147352567(DISP_E_EXCEPTION)으로 실패한다.
        그래서 Visible을 켜되, 송출 화면을 가리지 않도록 창은 최소화해 둔다.
        (사용자가 직접 열어 둔 파워포인트에는 이 처리를 하지 않는다.)

        반환: 진단용 상태 문자열 (오류 메시지에 함께 표시한다)
        """
        note = "Visible 설정 시도 안 함"
        try:
            # 보이게 하기 전에 먼저 최소화해 두면 창이 화면에 펼쳐지지 않는다
            app.WindowState = _PP_WINDOW_MINIMIZED
        except Exception:
            pass
        for value in (_MSO_TRUE, 1, True):
            try:
                app.Visible = value
                note = f"Visible={value} 설정"
                break
            except Exception as e:
                note = f"Visible 설정 실패({e})"
        try:
            app.WindowState = _PP_WINDOW_MINIMIZED
        except Exception:
            pass
        try:
            note += f", 현재 Visible={app.Visible}"
        except Exception:
            pass
        return note

    def _release_app(self):
        self._show_stop()
        app, launched = self._app, self._we_launched
        self._app = None
        self._we_launched = False
        if app is None or not launched:
            return   # 사용자가 직접 열어 둔 파워포인트는 건드리지 않는다
        try:
            if int(app.Presentations.Count) > 0:
                # 우리가 띄운 파워포인트라도 사용자가 그 안에서 문서를 열어
                # 편집 중이면 끄지 않는다 (저장하지 않은 내용이 사라진다)
                print("[ppt_engine] 열려 있는 문서가 있어 파워포인트는 그대로 둡니다")
                return
        except Exception:
            pass
        try:
            app.Quit()
        except Exception:
            pass

    # --- 내보내기 ---
    def _do_export(self, job: _Job):
        src = os.path.abspath(job.path)
        if not os.path.exists(src):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {src}")

        # 캐시 히트: COM 없이 즉시 응답
        cached = read_cache(src)
        if cached:
            _safe(job.on_count, cached["count"], cached["slides"])
            cached_notes = cached.get("notes") or []
            for i, slide_path in enumerate(cached["slides"]):
                if job.cancel and job.cancel():
                    _safe(job.on_cancelled, i)
                    return
                note = cached_notes[i] if i < len(cached_notes) else ""
                _safe(job.on_slide, i, slide_path, note)
            _safe(job.on_done, cached["count"])
            return

        if self._show_window is not None:
            # 애니메이션 모드가 켜져 있다. COM 스레드를 넘겨주고, 모드를 끄면
            # 호출자가 이어서 요청한다(_resume_ppt_export).
            print("[ppt_engine] 슬라이드쇼가 실행 중이라 내보내기를 미룹니다")
            _safe(job.on_cancelled, 0)
            return

        cache_dir = cache_dir_for(src)
        cache_dir.mkdir(parents=True, exist_ok=True)

        # COM 오류(-2147352567 등)는 어느 단계에서 났는지 알려 주지 않으므로
        # 단계 이름을 붙여서 올린다.
        step = "파워포인트 실행"
        pres = None
        temp_copy = None
        borrowed = False     # 쇼용으로 미리 열어 둔 것을 빌려 쓰는지 (그러면 닫지 않는다)
        keep = False         # 다 쓴 뒤 쇼용으로 넘겨줄지
        foreign = False      # 사용자가 편집하려고 열어 둔 파일인지 (그러면 절대 닫지 않는다)
        saved_before = None
        try:
            if self._primed_for(src):
                pres = self._show_pres
                borrowed = True
            else:
                if (self._show_source and self._show_window is None
                        and os.path.normcase(self._show_source) == os.path.normcase(src)):
                    # 같은 파일의 수정 전 사본을 붙들고 있다 - 닫고 새로 연다
                    self._show_stop()
                with _keep_our_windows_on_top():
                    app = self._ensure_app()
                    found = self._find_open(app, src)
                    if found is not None:
                        # 사용자가 편집 중인 문서 - 한 부 더 열지 않고 그대로 읽기만 한다
                        pres, foreign = found, True
                    else:
                        step = "파일 열기"
                        # 문서 창과 함께 연다 (창 없이 열면 슬라이드쇼가 끝날 때 닫혀 버린다)
                        pres, temp_copy = self._open_presentation(app, src, with_window=True)
                        self._minimize_document_window(pres)
            saved_before = self._get_saved(pres)

            step = "슬라이드 수 확인"
            count = int(pres.Slides.Count)
            if count <= 0:
                raise ValueError("슬라이드가 없는 파일입니다.")

            step = "슬라이드 크기 확인"
            width, height = self._export_size(pres, job.width)
            paths = slide_paths(cache_dir, count)
            # 장수를 먼저 알려 주면 호출자가 빈 카드를 즉시 배치할 수 있다
            _safe(job.on_count, count, paths)

            step = "슬라이드 내보내기"
            # 여기까지 왔으면 파일은 제대로 열린 것 - 끝나면 닫지 않고 애니메이션
            # 모드용으로 넘겨준다 (모드를 켤 때 파일을 다시 열지 않아도 된다)
            keep = not borrowed and not foreign and self._show_window is None
            notes = self._export_through_pdf(pres, cache_dir, paths, count, job)
            if notes is _CANCELLED:
                return   # 취소됨 (콜백은 내부에서 처리)
            if notes is None:
                # PDF 경로를 쓸 수 없는 환경 → 예전 방식(장별 그림 내보내기)
                notes = self._export_slides(pres, paths, width, height, count,
                                            job, cache_dir, src)
                if notes is None:
                    return
            else:
                width, height = self._last_render_size or (width, height)

            self._write_meta(cache_dir, src, count, notes, True, width, height)
            _safe(job.on_done, count)
        except Exception as e:
            keep = False
            raise RuntimeError(f"[{step}] {e}") from e
        finally:
            if pres is not None and (borrowed or foreign or keep):
                # 인쇄 범위를 바꾼 것만으로 '수정됨'이 되지 않게 원래 표시로 되돌린다
                self._set_saved(pres, saved_before)
            if borrowed or foreign:
                pass                      # 쇼용으로 열어 둔 것 / 사용자가 편집 중인 것 - 그대로 둔다
            elif keep and pres is not None and self._show_window is None and self._pres_alive(pres):
                self._keep_presentation(pres, temp_copy, src)
            else:
                if pres is not None:
                    try:
                        pres.Close()
                    except Exception:
                        pass
                if temp_copy:
                    try:
                        os.remove(temp_copy)
                    except Exception:
                        pass
        prune_cache()

    @staticmethod
    def _minimize_document_window(pres):
        """문서 창을 최소화한다 (창은 있어야 하지만 화면을 가리면 안 된다)"""
        try:
            pres.Windows.Item(1).WindowState = _PP_WINDOW_MINIMIZED
            return True
        except Exception:
            return False

    def _open_presentation(self, app, src, with_window=False):
        """프레젠테이션 열기. 환경에 따라 막히는 조합이 있어 차례로 시도한다.

        with_window=True 로 열면 문서 창이 생겨 슬라이드쇼를 끝내도 프레젠테이션이
        닫히지 않는다(창 없이 열면 파워포인트가 닫아버린다). 슬라이드를 옮길 때마다
        파일을 다시 여는 것을 막기 위해 슬라이드쇼에서는 이 방식을 쓴다.

        반환: (presentation, 임시 복사본 경로 또는 None)
        """
        # (설명, (ReadOnly, Untitled, WithWindow)) - 이름 대신 위치 인자를 쓴다
        if with_window:
            attempts = (
                ("창 표시 읽기 전용", (_MSO_TRUE, _MSO_FALSE, _MSO_TRUE)),
                ("창 없이 읽기 전용", (_MSO_TRUE, _MSO_FALSE, _MSO_FALSE)),
                ("기본 옵션", None),
            )
        else:
            attempts = (
                ("창 없이 읽기 전용", (_MSO_TRUE, _MSO_FALSE, _MSO_FALSE)),
                ("창 표시 읽기 전용", (_MSO_TRUE, _MSO_FALSE, _MSO_TRUE)),
                ("기본 옵션", None),
            )
        errors = []

        def _try(path):
            for label, args in attempts:
                try:
                    if args is None:
                        return app.Presentations.Open(path)
                    return app.Presentations.Open(path, *args)
                except Exception as e:
                    errors.append(f"{label}: {e}")
            return None

        pres = _try(src)
        if pres is not None:
            return pres, None

        # 파워포인트가 보이지 않는 상태면 열기가 실패한다 → 창을 켜고 재시도
        # (붙어 있던 인스턴스가 숨은 상태였던 경우의 안전망)
        errors.append(f"→ 파워포인트 창을 표시하고 재시도 ({self._make_ready(app)})")
        pres = _try(src)
        if pres is not None:
            return pres, None

        # 인터넷에서 받은 파일은 '보호된 보기'로 열려 자동화가 막힌다.
        # 임시 폴더로 복사하면 표식(Zone.Identifier)이 떨어져 열리는 경우가 많다.
        temp_copy = self._temp_copy(src)
        if temp_copy:
            errors.append("→ 임시 복사본으로 재시도")
            pres = _try(temp_copy)
            if pres is not None:
                return pres, temp_copy
            try:
                os.remove(temp_copy)
            except Exception:
                pass

        # 파일 문제인지 파워포인트 자체 문제인지 구분해서 알린다
        health = self._powerpoint_health(app)
        raise RuntimeError(f"파워포인트가 파일을 열지 못했습니다.\n{health}\n  "
                           + "\n  ".join(errors))

    @staticmethod
    def _powerpoint_health(app):
        """파일을 전혀 건드리지 않고 빈 프레젠테이션을 만들어 파워포인트 상태를 본다.

        이것마저 실패하면 파일·경로·보호된 보기와 무관하게 파워포인트 자체가
        문서를 다루지 못하는 상태다.
        """
        last_error = None
        for args in ((0,), (-1,), ()):
            try:
                blank = app.Presentations.Add(*args)
                try:
                    blank.Close()
                except Exception:
                    pass
                return "→ 파워포인트 자체는 동작합니다. 이 파일의 문제로 보입니다."
            except Exception as e:
                last_error = e
        return ("→ 파워포인트가 빈 문서조차 만들지 못합니다. 파일 문제가 아니라\n"
                "  파워포인트(Office) 설치·실행 상태의 문제입니다.\n"
                f"  ({last_error})")

    @staticmethod
    def _temp_copy(src):
        """임시 폴더로 복사 (대체 데이터 스트림이 복사되지 않아 보호된 보기를 피한다)"""
        try:
            tmp_dir = Path(tempfile.gettempdir()) / "BgTextPresenter_ppt"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            # 쇼용으로 열어 둔 복사본은 오래 잠겨 있으므로 매번 고유한 이름을 쓴다
            # (같은 이름이면 다음 파일을 복사하다 '다른 프로세스가 사용 중'으로 실패한다)
            for old in tmp_dir.glob(f"open_{os.getpid()}_*"):
                try:
                    old.unlink()          # 안 쓰는 것만 지워진다 (잠긴 것은 그냥 넘어감)
                except Exception:
                    pass
            dest = tmp_dir / f"open_{os.getpid()}_{uuid.uuid4().hex[:8]}{os.path.splitext(src)[1]}"
            shutil.copyfile(src, dest)
            return str(dest)
        except Exception as e:
            print(f"[ppt_engine] 임시 복사 실패: {e}")
            return ""

    # ------------------------------------------------------------------
    # PDF 를 거쳐 그림 만들기 (글꼴이 포함 저장된 파일 때문에 필요하다)
    # ------------------------------------------------------------------
    @staticmethod
    def _pdf_renderer():
        """PDF 를 그림으로 바꿀 수 있는 라이브러리 (없으면 (None, None))"""
        try:
            import pypdfium2
            return "pypdfium2", pypdfium2
        except Exception:
            pass
        try:
            import fitz          # PyMuPDF
            return "fitz", fitz
        except Exception:
            pass
        return None, None

    @staticmethod
    def _slide_range(pres, start, end):
        """지정 구간만 내보내기 위한 PrintRange (못 만들면 None)"""
        try:
            ranges = pres.PrintOptions.Ranges
            try:
                ranges.ClearAll()
            except Exception:
                pass
            return ranges.Add(start, end)
        except Exception:
            return None

    @classmethod
    def _export_pdf(cls, pres, pdf_path, only_range=None) -> str:
        """PDF 로 내보낸다. only_range=(시작, 끝)이면 그 구간만.

        구간을 나눠 내보내는 이유: 전체를 한 번에 내보내면 그 COM 호출이 끝날
        때까지 아무것도 끼어들 수 없다. 슬라이드쇼도 같은 스레드를 쓰므로,
        장수가 많은 파일에서는 애니메이션 모드 클릭이 수십 초씩 밀린다.
        구간으로 끊으면 사이사이에 취소를 확인하고 조작을 받아 줄 수 있다.
        """
        try:
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
        except Exception:
            pass
        errors = []
        # 인자 개수는 버전마다 달라서 많은 쪽부터 줄여 가며 시도한다.
        # 숨김 슬라이드까지 포함해야 장수가 원본과 맞는다.
        if only_range:
            slide_range = cls._slide_range(pres, only_range[0], only_range[1])
            if slide_range is None:
                return "구간 내보내기를 지원하지 않습니다"
            attempts = (
                ("구간", (pdf_path, _PP_FIXED_FORMAT_PDF, _PP_INTENT_PRINT,
                        _MSO_FALSE, _PP_HANDOUT_ORDER, _PP_OUTPUT_SLIDES, _MSO_TRUE,
                        slide_range, _PP_PRINT_SLIDE_RANGE)),
            )
        else:
            attempts = (
                ("전체 인자", (pdf_path, _PP_FIXED_FORMAT_PDF, _PP_INTENT_PRINT,
                            _MSO_FALSE, _PP_HANDOUT_ORDER, _PP_OUTPUT_SLIDES, _MSO_TRUE)),
                ("품질 지정", (pdf_path, _PP_FIXED_FORMAT_PDF, _PP_INTENT_PRINT)),
                ("기본", (pdf_path, _PP_FIXED_FORMAT_PDF)),
            )
        for label, args in attempts:
            try:
                pres.ExportAsFixedFormat(*args)
                if os.path.exists(pdf_path):
                    return ""
                errors.append(f"{label}: 파일이 만들어지지 않음")
            except Exception as e:
                errors.append(f"{label}: {e}")
        if only_range:
            return "; ".join(errors)
        try:
            pres.SaveAs(pdf_path, _PP_SAVE_AS_PDF)
            if os.path.exists(pdf_path):
                return ""
        except Exception as e:
            errors.append(f"SaveAs: {e}")
        return "; ".join(errors)

    def _export_through_pdf(self, pres, cache_dir, paths, count, job):
        """PDF 를 거쳐 슬라이드 그림을 만든다.

        파워포인트의 '그림으로 내보내기'는 파일에 포함 저장된 글꼴
        (Raleway, Playlist Script 처럼 PC 에 설치되지 않고 파일에 딸려 온 글꼴)을
        쓰지 않고 설치된 글꼴로 바꿔 버린다. 그래서 편집 화면·슬라이드쇼는
        멀쩡한데 내보낸 그림만 글꼴이 달라진다.
        PDF 로 내보내면 글꼴이 PDF 안에 그대로 박히므로 원본 모양이 유지된다.

        한 번에 전부 내보내지 않고 구간을 나눠 내보낸다. COM 호출은 중간에
        끊을 수 없어서, 한 번의 긴 호출이 돌고 있으면 같은 스레드를 쓰는
        슬라이드쇼 조작이 그동안 통째로 밀린다. 구간 사이에서 취소를 확인하면
        애니메이션 모드로 전환했을 때 곧바로 양보할 수 있고, 슬라이드도
        구간마다 화면에 채워진다.

        돌려주는 값: 노트 목록 / 취소면 _CANCELLED / 쓸 수 없으면 None
        """
        self._last_render_size = None
        kind, _ = self._pdf_renderer()
        if not kind:
            print("[ppt_engine] PDF 변환 라이브러리가 없어 예전 방식으로 내보냅니다. "
                  "글꼴이 포함 저장된 파일은 글꼴이 달라질 수 있습니다 "
                  "(해결: pip install pypdfium2)")
            return None

        width = max(640, int(job.width or DEFAULT_EXPORT_WIDTH))
        started = time.time()
        collected = []          # (슬라이드 인덱스, 노트) - 만들어진 순서
        state = {"size": (0, 0), "made": 0, "pdf_seconds": 0.0, "ranged": True}
        chunk_pdf = str(Path(cache_dir) / "chunk.pdf")

        def cancel_now():
            """취소를 기록하고 알린다.

            종료 콜백(on_cancelled)을 빠뜨리면 호출자가 끝없이 기다리게 된다.
            """
            self._write_meta(cache_dir, job.path, count,
                             self._ordered_notes(collected, count), False, width, 0)
            _safe(job.on_cancelled, state["made"])
            return _CANCELLED

        def cancelled():
            # 슬라이드쇼가 떠 있으면 내보내기는 무조건 양보한다.
            # 같은 COM 스레드를 쓰기 때문에, 내보내기가 한 구간이라도 더 돌면
            # 그동안 슬라이드 조작이 통째로 밀린다(실제로 2~3초씩 밀렸다).
            # 호출자의 취소 조건과 별개로 엔진 안에서도 지키는 안전장치다.
            if self._show_window is not None:
                print("[ppt_engine] 슬라이드쇼가 실행 중이라 내보내기를 멈춥니다 "
                      "(모드를 끄면 이어서 진행합니다)")
                return True
            return bool(job.cancel and job.cancel())

        def run(start, end):
            """[start, end] 구간을 PDF 로 뽑아 그림으로 만든다.

            돌려주는 값: True 계속 / False 이 방식 포기 / None 취소됨
            """
            targets = paths[start - 1:end]
            if all(os.path.exists(p) for p in targets):
                # 이어받기: 이미 만들어진 구간은 노트만 채우고 알린다
                for slide_no, out_path in zip(range(start, end + 1), targets):
                    note = self._read_notes(pres, slide_no) if job.extract_notes else ""
                    collected.append((slide_no - 1, note))
                    _safe(job.on_slide, slide_no - 1, out_path, note)
                    state["made"] += 1
                return True

            at = time.time()
            span = (start, end) if state["ranged"] and (start, end) != (1, count) else None
            problem = self._export_pdf(pres, chunk_pdf, only_range=span)
            if problem and span:
                print(f"[ppt_engine] 구간 내보내기를 쓸 수 없어 전체를 한 번에 "
                      f"내보냅니다 ({problem})")
                state["ranged"] = False
                return "retry"
            if problem:
                print(f"[ppt_engine] PDF 내보내기 실패 → 예전 방식으로 대체합니다: "
                      f"{problem}")
                return False
            state["pdf_seconds"] += time.time() - at

            try:
                part, part_size = self._render_pdf_pages(
                    chunk_pdf, targets, width, job, pres, collected,
                    base_index=start - 1)
            except Exception as e:
                print(f"[ppt_engine] PDF를 그림으로 바꾸지 못했습니다 → 예전 방식으로 "
                      f"대체합니다: {e}")
                return False
            finally:
                try:
                    os.remove(chunk_pdf)
                except Exception:
                    pass
            if part is None:
                return None
            state["made"] += part
            if part_size and part_size[0]:
                state["size"] = part_size
            return True

        # 1) 지금 보려는 한 장을 먼저 (송출까지의 대기를 장수와 무관하게 만든다)
        first = min(max(1, job.first_index), count)
        done = set()
        if cancelled():
            return cancel_now()
        outcome = run(first, first)
        if outcome == "retry":
            outcome = run(1, count)         # 구간을 못 쓰는 환경
            if outcome is True:
                done = set(range(1, count + 1))
        if outcome is None:
            return cancel_now()
        if outcome is False:
            return None
        done.add(first)

        # 2) 나머지를 앞에서부터 구간으로. 구간은 점점 키워 호출 비용을 줄인다.
        #
        # 주의: step(구간 크기 단계)은 '실제로 내보낸 구간'에만 올려야 한다.
        # 이미 캐시에 있어 건너뛴(continue) 구간까지 step을 올리면, 캐시가
        # 많이 남아 있는 파일에서는 앞부분을 스킵하며 순식간에 step이
        # 최대치(12장)까지 올라가 버려서 정작 처음 실제로 내보내는 구간이
        # 곧바로 12장짜리 거대한 한 번의 COM 호출이 되어 버린다(그동안
        # 슬라이드쇼 조작이 4~5초씩 밀리는 원인이었다). 실제로 내보낸
        # 구간 수만큼만 단계를 올려야 처음 몇 번은 작게 시작한다.
        position, step = 1, 0
        while position <= count:
            span = _CHUNK_SPANS[min(step, len(_CHUNK_SPANS) - 1)]
            end = min(position + span - 1, count)
            block = [i for i in range(position, end + 1) if i not in done]
            position = end + 1
            if not block:
                continue
            step += 1
            if cancelled():
                return cancel_now()
            chunk_at = time.time()
            outcome = run(block[0], block[-1])
            print(f"[ppt_engine] PDF 구간 내보내기 {block[0]}~{block[-1]}"
                  f"({len(block)}장) - {time.time() - chunk_at:.1f}초")
            if outcome is None:
                return cancel_now()
            if outcome is False:
                return None
            if outcome == "retry":
                outcome = run(1, count)
                if outcome is None:
                    return cancel_now()
                if outcome is not True:
                    return None
                break

        self._last_render_size = state["size"] if state["size"][0] else None
        total = time.time() - started
        print(f"[ppt_engine] PDF 경유로 {state['made']}장 준비 "
              f"({state['size'][0]}x{state['size'][1]}, 글꼴 유지, {kind}) - "
              f"전체 {total:.1f}초 (PDF {state['pdf_seconds']:.1f}초 + "
              f"변환 {total - state['pdf_seconds']:.1f}초)")
        return self._ordered_notes(collected, count)

    @staticmethod
    def _ordered_notes(collected, count):
        """(인덱스, 노트) 목록을 슬라이드 순서대로 된 목록으로"""
        notes = [""] * count
        for index, note in collected:
            if 0 <= index < count:
                notes[index] = note
        return notes

    @staticmethod
    def _pdf_page_width(page) -> float:
        """PDF 한 장의 가로 크기 (라이브러리 버전에 따라 부르는 이름이 다르다)"""
        for get in (lambda: page.get_width(),
                    lambda: page.get_size()[0],
                    lambda: page.width):
            try:
                value = float(get())
                if value > 0:
                    return value
            except Exception:
                continue
        return 960.0

    def _render_pdf_pages(self, pdf_path, paths, width, job, pres, notes_out,
                          base_index=0, skip_notify=()):
        """PDF 각 장을 그림으로 저장하면서 준비되는 대로 알려 준다.

        돌려주는 값: (만든 장수, 실제 그림 크기) / 취소되면 (None, None)
        """
        kind, lib = self._pdf_renderer()
        if not kind:
            raise RuntimeError("PDF를 그림으로 바꿀 라이브러리가 없습니다 "
                               "(pip install pypdfium2)")
        from PIL import Image

        made = 0
        size = (0, 0)
        if kind == "pypdfium2":
            doc = lib.PdfDocument(pdf_path)
            total = len(doc)
        else:
            doc = lib.open(pdf_path)
            total = doc.page_count

        try:
            if total != len(paths):
                raise RuntimeError(f"PDF 장수({total})가 슬라이드 수({len(paths)})와 "
                                   f"다릅니다")
            for i in range(total):
                if self._show_window is not None or (job.cancel and job.cancel()):
                    return None, None
                out_path = paths[i]
                if not os.path.exists(out_path):
                    if kind == "pypdfium2":
                        page = doc[i]
                        scale = width / max(1.0, self._pdf_page_width(page))
                        rendered = page.render(scale=scale)
                        # 버전에 따라 PdfBitmap 을 주기도 하고 그림을 바로 주기도 한다
                        image = (rendered.to_pil() if hasattr(rendered, "to_pil")
                                 else rendered).convert("RGB")
                        try:
                            page.close()
                        except Exception:
                            pass
                    else:
                        page = doc[i]
                        zoom = width / max(1.0, float(page.rect.width))
                        pix = page.get_pixmap(matrix=lib.Matrix(zoom, zoom), alpha=False)
                        image = Image.frombytes("RGB", (pix.width, pix.height),
                                                pix.samples)
                    image.save(out_path, "JPEG", quality=88, subsampling=0)
                    size = image.size
                elif not size[0]:
                    try:
                        with Image.open(out_path) as done:
                            size = done.size
                    except Exception:
                        pass
                made += 1
                index = base_index + i
                note = self._read_notes(pres, index + 1) if job.extract_notes else ""
                notes_out.append((index, note))
                if index not in skip_notify:
                    _safe(job.on_slide, index, out_path, note)
        finally:
            try:
                doc.close()
            except Exception:
                pass
        return made, size

    def _export_slides(self, pres, paths, width, height, count, job, cache_dir, src):
        """슬라이드를 한 장씩 내보낸다. 취소되면 None 반환."""
        notes = []
        bulk_tried = False
        for i in range(1, count + 1):
            if self._show_window is not None or (job.cancel and job.cancel()):
                # 다음에 이어서 진행할 수 있도록 미완료 상태로 기록
                self._write_meta(cache_dir, src, count, notes, False, width, height)
                _safe(job.on_cancelled, i - 1)
                return None

            out_path = paths[i - 1]
            if not os.path.exists(out_path):
                try:
                    self._export_one(pres, i, out_path, width, height)
                except Exception as e:
                    if bulk_tried:
                        raise
                    # 장별 내보내기가 막히는 환경 → 전체 일괄 내보내기로 대체
                    print(f"[ppt_engine] {i}장 내보내기 실패({e}) → 일괄 내보내기 시도")
                    self._export_bulk(pres, paths, width, height)
                    bulk_tried = True
                    if not os.path.exists(out_path):
                        raise

            note = self._read_notes(pres, i) if job.extract_notes else ""
            notes.append(note)
            _safe(job.on_slide, i - 1, out_path, note)
        return notes

    @staticmethod
    def _export_one(pres, index, out_path, width, height):
        slide = pres.Slides.Item(index)
        try:
            slide.Export(out_path, "JPG", width, height)
        except Exception:
            slide.Export(out_path, "JPG")   # 크기 지정 없이 재시도

    @staticmethod
    def _export_bulk(pres, paths, width, height):
        """프레젠테이션 전체를 한 번에 내보낸 뒤 우리 규칙의 파일명으로 옮긴다.

        파워포인트는 '슬라이드1.JPG'(한국어) / 'Slide1.JPG'(영어)처럼 저장하므로
        자연 정렬해 순서대로 대응시킨다.
        """
        out_dir = Path(paths[0]).parent / "_bulk"
        shutil.rmtree(out_dir, ignore_errors=True)
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            try:
                pres.Export(str(out_dir), "JPG", width, height)
            except Exception:
                pres.Export(str(out_dir), "JPG")
            produced = sorted((p for p in out_dir.iterdir() if p.is_file()),
                              key=lambda p: _natural_key(p.name))
            for target, made in zip(paths, produced):
                if not os.path.exists(target):
                    shutil.move(str(made), target)
        finally:
            shutil.rmtree(out_dir, ignore_errors=True)

    # --- 슬라이드쇼 (애니메이션 모드) ---
    def _do_show(self, job: _Job):
        """실제 파워포인트 슬라이드쇼를 조작한다.

        이미지로 내보낸 슬라이드에는 애니메이션이 남지 않으므로, 애니메이션이
        필요할 때는 파워포인트에게 화면을 넘기고 우리는 리모컨 역할만 한다.
        """
        step = job.action
        try:
            if job.action == "start":
                self._show_start(job)
            elif job.action == "prepare":
                self._show_prepare(job)
            elif job.action == "release":
                self._show_release(job)
            elif job.action == "next":
                self._show_view(lambda view: view.Next())
            elif job.action == "prev":
                self._show_step_back()
            elif job.action == "goto":
                self._show_goto(max(1, int(job.payload.get("index", 1))))
            elif job.action == "stop":
                # 쇼 창만 닫고 프레젠테이션은 열어 둔다 - 애니메이션 모드를 다시 켜면
                # 파일을 다시 열지 않아 곧바로 뜬다 (다른 파일로 넘어가면 그때 닫는다)
                self._show_end()
            elif job.action == "state":
                pass
        except Exception as e:
            raise RuntimeError(f"[슬라이드쇼 {step}] {e}") from e
        if step == "goto":
            # 검은 화면으로 가리는 것은 슬라이드 점프(_enter_slide)뿐이다 - 다음/이전
            # 단계마다 화면 상태를 한 번 더 묻던 것을 없애 한 번의 호출을 아낀다
            self._ensure_show_visible(step)
        status_at = time.time()
        status = self._show_status()
        status_took = time.time() - status_at
        if status_took > 0.2:
            print(f"[ppt_engine] 조작({step}) 뒤 상태 조회 자체에 "
                  f"{status_took:.1f}초 걸렸습니다")
        _safe(job.on_done, status)

    def _show_start(self, job: _Job):
        began = time.time()
        src = os.path.abspath(job.path) if job.path else self._show_source
        if not src or not os.path.exists(src):
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {src}")

        # 같은 파일이면 이미 열려 있는 프레젠테이션을 재사용한다.
        # (큰 파일은 다시 여는 데만 몇 초가 걸린다)
        pres = None
        # 쇼가 떠 있는 중(앞 슬라이드로 가려고 다시 여는 경우 등)에는 파일이 바뀌었어도
        # 열려 있는 것을 그대로 쓴다 - 다시 열면 송출 중인 화면이 몇 초간 끊긴다
        restarting = self._show_window is not None or bool(job.payload.get("restart"))
        reusable = (self._primed_for(src) if not restarting else
                    (self._show_source == src and self._pres_alive(self._show_pres)))
        if reusable:
            self._exit_show_window()
            # 주의: 창 없이(WithWindow=0) 연 프레젠테이션은 슬라이드쇼를 끝내면
            #       파워포인트가 그대로 닫아버린다. 살아 있을 때만 재사용한다.
            if self._pres_alive(self._show_pres):
                pres = self._show_pres

        if pres is None:
            self._show_stop()
            with _keep_our_windows_on_top():
                app = self._ensure_app()
                found = self._find_open(app, src)
                if found is not None:
                    # 사용자가 편집하려고 열어 둔 문서 - 따로 한 부 더 열지 않고 그대로
                    # 쓴다 (절대 닫지 않고, 창도 최소화하지 않는다)
                    pres, temp_copy = found, None
                else:
                    # 문서 창과 함께 열어야 쇼를 끝내도 닫히지 않아, 슬라이드를 옮길 때마다
                    # 파일을 다시 여는 일이 없다. 창은 곧바로 최소화한다.
                    pres, temp_copy = self._open_presentation(app, src, with_window=True)
                    self._minimize_document_window(pres)
            self._keep_presentation(pres, temp_copy, src, foreign=found is not None)

        try:
            total = int(pres.Slides.Count)
        except Exception:
            total = 0
        self._show_total = total
        start = max(1, int(job.payload.get("index", 1)))
        if total:
            start = min(start, total)

        saved_before = self._get_saved(pres)
        if self._show_settings_ready_for is pres:
            # 미리 열 때 이미 해 두었다 - 파워포인트 호출 6번을 아낀다
            settings = pres.SlideShowSettings
        else:
            settings = self._apply_fixed_show_settings(pres)

        # 누른 슬라이드에서 바로 시작하려면 RangeType을 '슬라이드 범위'로 둬야 한다.
        # 기본값(ppShowAll)에서는 StartingSlide가 무시되어 1번부터 시작하고,
        # 그 뒤에 이동시키면 1번 슬라이드가 잠깐 보였다가 넘어간다.
        # full_range: 뒤로 이동하려고 다시 여는 경우. 범위를 제한하지 않아야
        #             이후로는 앞뒤 이동에 다시 열 필요가 없다.
        full_range = bool(job.payload.get("full_range"))
        self._show_range_start = 1
        ranged = False
        if total and start > 1 and not full_range:
            try:
                settings.RangeType = _PP_SHOW_SLIDE_RANGE
                settings.StartingSlide = start
                settings.EndingSlide = total
                self._show_range_start = start
                ranged = True
            except Exception as e:
                print(f"[ppt_engine] 슬라이드 범위 지정 실패 → 1번부터 시작하게 됩니다: {e}")
                self._show_range_start = 1
        else:
            try:
                settings.RangeType = _PP_SHOW_ALL
            except Exception:
                pass

        self._show_rect = job.payload.get("screen_rect") or self._show_rect
        self._set_saved(pres, saved_before)     # 쇼 설정만 바꾼 것은 '수정'이 아니다
        setup_done = time.time()
        window = settings.Run()
        ran = time.time()
        self._show_window = window
        hwnd = self._window_handle(window)

        # 범위 지정이 먹으면 쇼가 목표 슬라이드에서 바로 시작하므로 숨길 것이 없다.
        # 그때 창을 화면 밖으로 뺐다 넣으면 오히려 깜빡임이 한 번 더 생긴다.
        # 범위 지정이 안 된 경우에만(1번부터 시작) 화면 밖에서 이동시킨다.
        hidden = False
        if start > 1 and not ranged:
            hidden = self._place_window(hwnd, _OFFSCREEN_RECT, foreground=False)

        if start > 1:
            here = -1
            try:
                here = int(window.View.Slide.SlideIndex)
            except Exception as e:
                print(f"[ppt_engine] 시작 슬라이드 확인 실패: {e}")
            if here != start:
                # 범위를 안 걸고 열어 1번에서 시작한 경우. 화면 밖에 있는 동안
                # 목표 슬라이드로 '들어가' 애니메이션까지 살린다.
                # (GotoSlide 로 바로 꽂으면 애니메이션이 걸리지 않는다)
                took = self._enter_slide(window.View, start)
                if not took:
                    self._goto(window.View, self._relative_index(start))
                    print(f"[ppt_engine] {start}번으로 바로 이동했습니다 "
                          f"(이 경우 애니메이션은 재생되지 않습니다)")

        # 전환이 끝나 실제로 그 슬라이드에 있게 된 뒤에 화면으로 올린다
        landed = self._wait_for_slide(window.View, start)
        self._place_window_if_needed(hwnd, self._show_rect)
        if landed != start:
            print(f"[ppt_engine] 시작 슬라이드가 {start}이 아닌 {landed}입니다")

        done = time.time()
        print(f"[ppt_engine] 슬라이드쇼 시작: {start}/{total}장, "
              f"범위지정={'예' if ranged else '아니오'}, "
              f"창핸들={hwnd or '없음'}, "
              f"화면밖처리={'예' if hidden else '아니오'}, "
              f"위치={self._show_rect}")
        fast = self._animation_lookup_fast(start)
        print(f"[ppt_engine] {start}번 슬라이드 애니메이션: "
              f"{fast[1] if fast else '확인 생략'} / "
              f"걸린 시간 {done - began:.1f}초 "
              f"(준비 {setup_done - began:.1f} + 실행 {ran - setup_done:.1f} + "
              f"마무리 {done - ran:.1f})")

    def _restart_show_at(self, index: int, full_range=True):
        """그 슬라이드에서 쇼를 다시 연다 (창을 새로 만들므로 2초 남짓 걸린다)

        기본값이 full_range=True 인 이유: 범위를 목표 슬라이드부터로 제한하면
        그보다 앞 슬라이드로 갈 때마다 또 다시 열어야 한다(매번 2초). 범위를
        풀어 두면 그 뒤로는 어느 슬라이드로든 '앞 슬라이드를 거쳐 들어가기'로
        빠르게 갈 수 있다. 여는 순간에는 1번에서 시작하지만, 화면 밖에서
        목표 슬라이드까지 옮긴 뒤 화면에 올리므로 1번이 보이지는 않는다.
        """
        if not self._show_source:
            raise RuntimeError("슬라이드쇼가 실행 중이 아닙니다.")
        self._show_start(_Job("show", path=self._show_source, action="start",
                              payload={"index": index, "screen_rect": self._show_rect,
                                       "full_range": full_range, "restart": True}))

    @staticmethod
    def _animation_lookup_raw(pres, index: int):
        """슬라이드의 애니메이션 효과 수와 설명을 '한 번'에 조회한다.

        Slides.Item→TimeLine→MainSequence 로 이어지는 체인 자체가 이
        환경에서는 호출마다 꽤 걸린다(단순 속성 하나 읽기와는 다르다).
        예전에는 효과 '개수'만 확인하는 함수와 '설명 문자열'을 만드는
        함수가 따로 있어서, 애니메이션이 있는 슬라이드로 이동할 때마다
        (분기 판단용으로 한 번 + 로그 표시용으로 한 번) 이 느린 체인을
        두 번 타고 있었다. 하나로 합쳐서 한 번만 탄다.

        돌려주는 값: (효과 수, 설명 문자열). 읽지 못하면 (-1, ...) —
        '없음'이 아니라 '알 수 없음'으로 다뤄야 한다(애니메이션이 있는데
        없다고 판단하면 그 슬라이드의 애니메이션이 통째로 재생되지 않는다).
        """
        try:
            sequence = pres.Slides.Item(index).TimeLine.MainSequence
            count = int(sequence.Count)
        except Exception as e:
            return -1, f"확인 실패({e.__class__.__name__}: {e})"
        if not count:
            return 0, "없음"
        names = {1: "클릭", 2: "이전과 함께", 3: "이전 다음"}
        kinds = {}
        for i in range(1, min(count, 20) + 1):
            try:
                trigger = int(sequence.Item(i).Timing.TriggerType)
            except Exception:
                trigger = -1
            key = names.get(trigger, f"기타({trigger})")
            kinds[key] = kinds.get(key, 0) + 1
        detail = ", ".join(f"{k} {v}개" for k, v in kinds.items())
        return count, f"효과 {count}개 ({detail})"

    def _animation_lookup(self, pres, index: int):
        """애니메이션 효과 수/설명을 찾는다. 슬라이드별로 캐싱도 한다.

        같은 슬라이드를 다시 찾아갈 때(예배 중 앞뒤로 오갈 때 흔하다)
        매번 다시 확인하지 않고 처음 한 번만 확인한다. 처음 확인할 때도
        가능하면 파워포인트(COM) 대신 파일 XML을 직접 읽는다 - COM 체인
        (Slides.Item→TimeLine→MainSequence)이 이 환경에서 1~2초씩 걸려서,
        여러 슬라이드를 옮겨 다니는 동안(캐시가 아직 안 쌓인 새 슬라이드
        마다) 실제 이동보다 이 확인이 더 오래 걸리고 있었다.
        """
        key = (id(pres), index)
        cached = self._anim_cache.get(key)
        if cached is not None:
            return cached
        result = self._animation_lookup_fast(index)
        if result is None:
            result = self._animation_lookup_raw(pres, index)
        self._anim_cache[key] = result
        return result

    def _animation_lookup_fast(self, index: int):
        """파일 XML로 애니메이션 효과 수를 확인한다 (COM 없이, 수 밀리초).

        실패하면(.ppt 옛 형식, 예상과 다른 구조 등) None - 호출한 쪽에서
        COM 방식으로 대체한다.
        """
        src = self._show_source
        if not src:
            return None
        if self._slide_xml_parts is None or self._slide_xml_parts_src != src:
            try:
                self._slide_xml_parts = _pptx_slide_parts(src)
            except Exception:
                self._slide_xml_parts = []
            self._slide_xml_parts_src = src
        parts = self._slide_xml_parts
        if not (1 <= index <= len(parts)):
            return None
        count = _xml_animation_count(src, parts[index - 1])
        if count < 0:
            return None
        return (0, "없음") if count == 0 else (count, f"효과 {count}개")

    @staticmethod
    def _goto(view, index: int) -> str:
        """슬라이드로 이동하면서 애니메이션을 처음 상태로 되돌린다.

        ResetSlide 를 주지 않으면 애니메이션이 이미 다 재생된 상태로 착지해서
        (GetClickCount 가 0으로 보고된다) 그 뒤 클릭이 애니메이션이 아니라
        다음 슬라이드로 넘어가 버린다. 동적 디스패치에서 인자 전달이 통하지
        않는 경우가 있어 여러 방식을 차례로 시도하고, 어떤 방식이 통했는지 돌려준다.
        """
        attempts = (
            ("위치인자", lambda: view.GotoSlide(index, _MSO_TRUE)),
            ("이름인자", lambda: view.GotoSlide(index, ResetSlide=_MSO_TRUE)),
            ("인자없음", lambda: view.GotoSlide(index)),
        )
        errors = []
        for label, call in attempts:
            try:
                call()
                if errors:
                    print(f"[ppt_engine] GotoSlide 대체 방식 사용({label}): {'; '.join(errors)}")
                return label
            except Exception as e:
                errors.append(f"{label}({e.__class__.__name__})")
        print(f"[ppt_engine] GotoSlide({index}) 모든 방식 실패: {'; '.join(errors)}")
        return ""

    @staticmethod
    def _wait_for_slide(view, index: int, timeout: float = 1.5) -> int:
        """이동이 반영될 때까지 잠시 기다린다.

        화면 전환·애니메이션이 도는 동안에는 View.Slide 가 곧바로 갱신되지 않는다.
        기다리지 않고 실패로 판단하면 쇼를 통째로 다시 열게 되어(빈 화면 → 1번
        슬라이드 → 목표 슬라이드) 훨씬 나쁘다.
        """
        deadline = time.monotonic() + timeout
        current = -1
        while True:
            try:
                current = int(view.Slide.SlideIndex)
            except Exception:
                current = -1
            if current == index or time.monotonic() >= deadline:
                return current
            time.sleep(0.02)

    def _relative_index(self, absolute: int) -> int:
        """GotoSlide 에 넘길 순번.

        쇼 범위를 지정해서 열면(StartingSlide=S) GotoSlide 의 인덱스는 절대
        슬라이드 번호가 아니라 '범위 안에서 몇 번째'인지를 뜻한다.
        (범위가 14부터일 때 GotoSlide(11) 은 24번 슬라이드로 간다)
        """
        start = self._show_range_start or 1
        return absolute - start + 1 if start > 1 else absolute

    def _show_goto(self, index: int):
        """지정 슬라이드로 이동한다.

        이 환경에서 확인된 사실:
        GotoSlide 로 옮긴 슬라이드는 애니메이션이 재생되지 않는다. ResetSlide 를
        줘도, 그 뒤에 GotoClick(0) 으로 되감아도 마찬가지였다. 게다가
        GetClickIndex/GetClickCount 가 늘 0을 보고해서 되감기가 통했는지
        프로그램으로 확인할 방법도 없다.

        반면 그 슬라이드에서 쇼를 '다시 열면' 애니메이션이 항상 정상 동작한다.
        그래서 애니메이션이 있는 슬라이드는 다시 열고, 애니메이션이 없는
        슬라이드만 GotoSlide 로 부드럽게 옮긴다. 가사처럼 애니메이션이 없는
        슬라이드가 많은 파일에서는 대부분의 이동이 그대로 부드럽다.
        """
        lookup_at = time.time()
        effects, effects_info = self._animation_lookup(self._show_pres, index)
        lookup_took = time.time() - lookup_at
        if lookup_took > 0.2:
            print(f"[ppt_engine] 슬라이드 {index} 애니메이션 확인 조회에 "
                  f"{lookup_took:.1f}초 걸렸습니다 (캐시 미스 - 파워포인트에 새로 물어봄)")
        window = self._show_window
        if window is not None:
            view = window.View
            if effects == 0:
                target = self._relative_index(index)
                if target >= 1:
                    try:
                        how = self._goto(view, target)
                        landed = self._wait_for_slide(view, index)
                        if landed == index:
                            print(f"[ppt_engine] 슬라이드 {index} 이동 "
                                  f"(방식={how or '없음'}, 애니메이션 없음)")
                            return
                        print(f"[ppt_engine] 슬라이드 {index} 이동 실패(현재 {landed}) "
                              f"→ 쇼를 다시 엽니다")
                    except Exception as e:
                        print(f"[ppt_engine] GotoSlide({index}) 실패: {e}")
            else:
                # 애니메이션이 있는 슬라이드: 앞 슬라이드로 간 뒤 '다음'으로 넘어간다.
                # 슬라이드쇼에서 다음 슬라이드로 '들어가는' 동작이라야 애니메이션이
                # 처음부터 걸린다. GotoSlide 로 바로 꽂으면 걸리지 않는다.
                # 쇼를 다시 여는 것(2초)보다 훨씬 빠르고, 앞 슬라이드가 지금 보고
                # 있는 슬라이드인 경우(순서대로 넘길 때)에는 화면 변화도 없다.
                at = time.time()
                took = self._enter_slide(view, index)
                if took:
                    print(f"[ppt_engine] 슬라이드 {index} 이동 "
                          f"({took}, {time.time() - at:.1f}초, "
                          f"애니메이션 {effects_info})")
                    return
                print(f"[ppt_engine] 슬라이드 {index}로 '들어가기'가 안 돼 "
                      f"쇼를 다시 엽니다")
        # 다시 열 때는 범위를 그 슬라이드부터로 지정한다. 그래야 쇼가 목표
        # 슬라이드에서 '처음부터' 시작해 애니메이션이 정상적으로 걸린다.
        # (범위를 풀면 1번에서 시작해 GotoSlide 로 옮겨가게 되어 같은 문제가 난다)
        self._restart_show_at(index)

    def _enter_slide(self, view, index: int) -> str:
        """앞 슬라이드에서 '다음'으로 넘어가 목표 슬라이드에 들어간다.

        애니메이션은 슬라이드에 들어갈 때 걸린다. GotoSlide 로 바로 꽂으면
        걸리지 않으므로, 한 장 앞으로 간 다음 Next() 로 들어간다.

        성공하면 어떻게 했는지(로그용, Next 누른 횟수·구간별 시간 포함),
        실패하면 빈 문자열.
        """
        floor = self._show_range_start or 1
        if index - 1 < floor:
            return ""           # 앞 슬라이드가 쇼 범위 밖 - 다시 여는 수밖에 없다
        t0 = time.monotonic()
        try:
            current = int(view.Slide.SlideIndex)
        except Exception:
            current = -1

        how = "바로 다음"
        blanked = False
        try:
            if current != index - 1:
                target = self._relative_index(index - 1)
                if target < 1:
                    return ""
                # 경유하는 슬라이드가 화면에 스치지 않도록 잠깐 검은 화면으로 가린다
                # (발표자가 'B' 키를 누른 것과 같은 상태. 0.3초 남짓이다)
                blanked = self._set_show_state(view, _PP_SHOW_BLACK)
                try:
                    self._goto(view, target)
                except Exception as e:
                    print(f"[ppt_engine] 앞 슬라이드({index - 1})로 이동 실패: {e}")
                    return ""
                # 도착 확인은 짧게만 한다. 확인이 안 돼도 그냥 Next() 로 넘어가
                # 목표에 도착했는지로 판단하는 편이 빠르다(확인만 1초씩 기다리면
                # 이동 한 번이 2~3초가 된다).
                self._wait_for_slide(view, index - 1, timeout=0.4)
                how = f"{index - 1}번 경유{'(가림)' if blanked else ''}"
            t1 = time.monotonic()

            # 앞 슬라이드에 애니메이션이 남아 있으면 Next() 가 그것부터 소비한다.
            # 슬라이드가 실제로 바뀔 때까지 몇 번 더 눌러 준다.
            deadline = time.monotonic() + 1.5
            presses = 0
            while True:
                presses += 1
                try:
                    view.Next()
                except Exception as e:
                    print(f"[ppt_engine] 다음으로 넘기기 실패: {e}")
                    return ""
                if self._wait_for_slide(view, index, timeout=0.25) == index:
                    t2 = time.monotonic()
                    return (f"{how}, Next {presses}회, "
                            f"경유{t1 - t0:.2f}초+진입{t2 - t1:.2f}초")
                if time.monotonic() >= deadline:
                    return ""
        finally:
            if blanked:
                # 화면을 검은 화면으로 가렸다면 반드시 되돌려야 한다 - 이 호출이
                # 조용히 실패하면(드문 COM 오류) 사용자 화면이 검은 화면에
                # 갇힌 채로 남는데, 내부적으로는 슬라이드 이동 자체는 계속
                # '성공'으로 보고되어 알아채기 어렵다. 몇 번 재시도한다.
                for attempt in range(3):
                    if self._set_show_state(view, _PP_SHOW_RUNNING):
                        break
                    print(f"[ppt_engine] 화면 복구 재시도 {attempt + 1}/3")

    @staticmethod
    def _set_show_state(view, state) -> bool:
        """슬라이드쇼 화면 상태 (검은 화면 <-> 정상). 안 되면 False"""
        try:
            view.State = state
            return True
        except Exception as e:
            print(f"[ppt_engine] 화면 상태 변경 실패: {e}")
            return False

    def _show_step_back(self):
        """이전 단계로. 쇼 범위의 처음이라 더 못 가면 앞 슬라이드에서 다시 연다.

        GetClickIndex() 는 부르지 않는다 - 이 환경에서는 늘 0을 보고해서
        슬라이드 번호만 비교해도 결과는 같은데, 호출 자체가 느렸다.
        """
        window = self._show_window
        if window is None:
            raise RuntimeError("슬라이드쇼가 실행 중이 아닙니다.")
        view = window.View
        try:
            before = int(view.Slide.SlideIndex)
        except Exception:
            before = None
        view.Previous()
        if before is None:
            return
        try:
            after = int(view.Slide.SlideIndex)
        except Exception:
            return
        if after == before and before > 1:
            # 아무 변화가 없다 = 쇼 범위의 맨 앞
            self._restart_show_at(before - 1)

    @staticmethod
    def _pres_alive(pres) -> bool:
        """COM 프레젠테이션 참조가 아직 살아 있는지 (닫힌 객체를 쓰면
        'Object does not exist' 예외가 난다)"""
        if pres is None:
            return False
        try:
            _ = pres.Slides.Count
            return True
        except Exception:
            return False

    def _exit_show_window(self):
        """프레젠테이션은 열어 둔 채 슬라이드쇼 창만 닫는다"""
        window, self._show_window = self._show_window, None
        if window is not None:
            try:
                window.View.Exit()
            except Exception:
                pass

    @staticmethod
    def _window_handle(window):
        """슬라이드쇼 창 핸들

        1) SlideShowWindow.HWND (동적 디스패치에서 메서드로 오는 경우까지 처리)
        2) 그래도 못 얻으면 창 클래스로 직접 찾는다.
           파워포인트 전체화면 슬라이드쇼 창의 클래스 이름은 "screenClass" 이다.
        """
        value = _com_get(window, "HWND")
        try:
            hwnd = int(value)
            if hwnd:
                return hwnd
        except (TypeError, ValueError):
            pass

        try:
            import ctypes
            found = ctypes.windll.user32.FindWindowW("screenClass", None)
            if found:
                return int(found)
        except Exception as e:
            print(f"[ppt_engine] 슬라이드쇼 창 검색 실패: {e}")

        print(f"[ppt_engine] 슬라이드쇼 창 핸들을 얻지 못했습니다 (HWND={value!r})")
        return 0

    @classmethod
    def _place_window_if_needed(cls, hwnd, rect):
        """이미 그 위치·크기라면 옮기지 않는다.

        같은 자리로 다시 옮겨도 화면이 한 번 깜빡이므로, 필요할 때만 옮긴다.
        """
        if not hwnd or not rect:
            return False
        try:
            import ctypes
            from ctypes import wintypes
            current = wintypes.RECT()
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(current)):
                x, y, w, h = (int(v) for v in rect)
                if (current.left == x and current.top == y
                        and current.right - current.left == w
                        and current.bottom - current.top == h):
                    return False            # 이미 제자리
        except Exception:
            pass
        return cls._place_window(hwnd, rect)

    @staticmethod
    def _place_window(hwnd, rect, foreground=True):
        """슬라이드쇼 창을 지정한 영역으로 옮긴다 (픽셀 좌표)"""
        if not hwnd or not rect:
            return False
        try:
            import ctypes
            x, y, w, h = (int(v) for v in rect)
            HWND_TOP = 0
            SWP_FRAMECHANGED = 0x0020
            SWP_SHOWWINDOW = 0x0040
            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOP, x, y, w, h, SWP_FRAMECHANGED | SWP_SHOWWINDOW)
            if foreground:
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            print(f"[ppt_engine] 슬라이드쇼 창 이동 실패: {e}")
            return False

    def _show_view(self, action):
        window = self._show_window
        if window is None:
            raise RuntimeError("슬라이드쇼가 실행 중이 아닙니다.")
        action(window.View)

    def _ensure_show_visible(self, step):
        """조작(goto/next/prev) 뒤, 화면이 검은 화면에 갇혀 있지 않은지 확인한다.

        경유 슬라이드를 가릴 때(_enter_slide) view.State 를 검은 화면으로
        바꿨다가 끝나면 되돌리는데, 되돌리는 호출 자체가 실패하면(드문 COM
        오류) 슬라이드 이동은 내부적으로 계속 '성공'으로 보고되는데 실제
        송출 화면만 검은 채로 남는다 - 사용자 쪽에서는 "파워포인트 화면이
        아예 안 뜬다"로 보인다. _enter_slide 안의 재시도로 대부분 막히지만,
        혹시 놓친 경우를 잡는 안전망이다.
        """
        window = self._show_window
        if window is None:
            return
        try:
            state = int(window.View.State)
        except Exception:
            return
        if state != _PP_SHOW_BLACK:
            return
        print(f"[ppt_engine] 조작({step}) 뒤 화면이 검은 화면에 갇혀 있어 되돌립니다")
        for attempt in range(3):
            if self._set_show_state(window.View, _PP_SHOW_RUNNING):
                return
            print(f"[ppt_engine] 화면 복구 재시도 {attempt + 1}/3")
        print("[ppt_engine] 화면 복구에 실패했습니다 - 슬라이드를 다시 눌러 보세요")

    def _show_status(self):
        """현재 슬라이드쇼 상태 (사용자가 직접 끝냈는지도 여기서 감지된다)

        GetClickIndex/GetClickCount 는 부르지 않는다. 이 환경에서는 항상 0만
        보고해서(실제로 몇 번째 클릭인지 알 방법이 없어 rewind 판단에도 못
        썼었다) 쓸모가 없는데, 실측해 보니 호출 자체가 느렸다 - 이 조회가
        모든 슬라이드쇼 조작(goto/next/prev/start) 끝에 매번 따라붙다 보니
        조작마다 몇 초씩 더 걸리고 있었다(전체 지연의 대부분이 여기였다).
        쓸모없고 느린 호출이라 아예 없앤다.
        """
        idle = {"running": False, "slide": 0, "total": 0, "click": 0, "clicks": 0}
        window = self._show_window
        if window is None:
            return idle
        try:
            view = window.View
            slide = int(view.Slide.SlideIndex)
            return {"running": True, "slide": slide, "total": self._show_total,
                    "click": 0, "clicks": 0,
                    "range_start": self._show_range_start}
        except Exception:
            # 사용자가 슬라이드쇼를 직접 종료한 경우 (프레젠테이션은 열어 둔다)
            self._show_window = None
            self._show_end()
            return idle

    def _show_stop(self):
        self._exit_show_window()
        self._show_source = ""
        self._show_fingerprint = ""
        self._show_range_start = 1
        pres, self._show_pres = self._show_pres, None
        foreign, self._show_pres_foreign = self._show_pres_foreign, False
        self._show_settings_ready_for = None
        if pres is not None and not foreign:
            if self._pres_alive(pres) and self._modified(pres):
                print("[ppt_engine] 열어 둔 문서에 고친 내용이 있어 닫지 않습니다")
            else:
                try:
                    pres.Close()
                except Exception:
                    pass
        temp, self._show_temp = self._show_temp, None
        if temp:
            try:
                os.remove(temp)
            except Exception:
                pass

    # --- 미리 열어 두기 (애니메이션 모드를 빨리 띄우기 위해) ---
    def _primed_for(self, src: str) -> bool:
        """그 파일이 (바뀌지 않은 채로) 이미 열려 있는지"""
        return (bool(src) and self._show_source == src
                and self._show_fingerprint == _fingerprint(src)
                and self._pres_alive(self._show_pres))

    def _keep_presentation(self, pres, temp_copy, src, foreign=False):
        """이 프레젠테이션을 쇼용으로 붙들어 둔다 (전에 붙들던 다른 것은 닫는다)"""
        if self._show_pres is not None and self._show_pres is not pres:
            old, self._show_pres = self._show_pres, None
            if not self._show_pres_foreign and not (self._pres_alive(old) and self._modified(old)):
                try:
                    old.Close()
                except Exception:
                    pass
            old_temp, self._show_temp = self._show_temp, None
            if old_temp and old_temp != temp_copy:
                try:
                    os.remove(old_temp)
                except Exception:
                    pass
        self._show_pres = pres
        self._show_temp = temp_copy
        self._show_source = src
        self._show_fingerprint = _fingerprint(src)
        self._show_pres_foreign = bool(foreign)
        self._show_settings_ready_for = None
        self._anim_cache = {}

    def _find_open(self, app, src):
        """그 파일이 우리 말고 (사용자가 편집하려고) 파워포인트에 이미 열려 있으면 그 문서"""
        target = os.path.normcase(os.path.abspath(src))
        if (self._show_pres is not None and self._show_source
                and os.path.normcase(self._show_source) == target):
            return None         # 우리가 붙들고 있는 것
        try:
            count = int(app.Presentations.Count)
        except Exception:
            return None
        for i in range(1, count + 1):
            try:
                pres = app.Presentations.Item(i)
                name = str(pres.FullName)
            except Exception:
                continue
            if name and os.path.normcase(os.path.abspath(name)) == target:
                return pres
        return None

    @staticmethod
    def _get_saved(pres):
        try:
            return int(pres.Saved)
        except Exception:
            return None

    @staticmethod
    def _set_saved(pres, value):
        """쇼 설정/인쇄 범위를 바꾸면 '수정됨'으로 표시될 수 있어 원래 표시로 되돌린다
        (사용자 문서라면 저장하라는 질문이 뜨지 않게, 우리 것이라면 아래
        '수정된 문서는 닫지 않는다' 판단이 흐려지지 않게)"""
        if value is None:
            return
        try:
            pres.Saved = value
        except Exception:
            pass

    def _modified(self, pres) -> bool:
        """누군가 이 문서를 고쳤는지 - 고친 문서는 우리가 닫지 않는다 (편집 내용 보호)"""
        saved = self._get_saved(pres)
        return saved is not None and saved == 0

    # 애니메이션과 화면 전환을 살리고, 발표자 보기는 끈다 (프레젠테이션마다 한 번이면 된다)
    _FIXED_SHOW_SETTINGS = (("ShowType", 1),                  # ppShowTypeSpeaker
                            ("ShowWithAnimation", _MSO_TRUE),
                            ("ShowWithNarration", _MSO_TRUE),
                            ("AdvanceMode", 1),               # 수동 진행
                            ("LoopUntilStopped", _MSO_FALSE),
                            ("ShowPresenterView", _MSO_FALSE))

    def _apply_fixed_show_settings(self, pres):
        settings = pres.SlideShowSettings
        failed = []
        for attr, value in self._FIXED_SHOW_SETTINGS:
            try:
                setattr(settings, attr, value)
            except Exception as e:
                failed.append(f"{attr}({e.__class__.__name__})")   # 버전에 따라 없는 속성
        if failed:
            print(f"[ppt_engine] 적용하지 못한 슬라이드쇼 설정: {', '.join(failed)}")
        self._show_settings_ready_for = pres
        return settings

    def _warm_for_show(self, pres, src):
        """애니메이션 모드를 켜기 전에 미리 해 둘 수 있는 일을 해 둔다.

        - 발표 방식 설정(켤 때마다 하던 파워포인트 호출 6번)
        - 슬라이드별 애니메이션 유무 (슬라이드를 처음 옮길 때마다 파일을 읽던 것)
        """
        began = time.time()
        saved = self._get_saved(pres)
        try:
            self._apply_fixed_show_settings(pres)
        except Exception as e:
            print(f"[ppt_engine] 발표 설정 미리 적용 실패: {e}")
        self._set_saved(pres, saved)
        try:
            total = int(pres.Slides.Count)
        except Exception:
            total = 0
        for index in range(1, min(total, 400) + 1):
            key = (id(pres), index)
            if key in self._anim_cache:
                continue
            fast = self._animation_lookup_fast(index)
            if fast is None:
                break          # 옛 형식(.ppt) 등 - 그때그때 확인한다
            self._anim_cache[key] = fast
        took = time.time() - began
        if took > 0.3:
            print(f"[ppt_engine] 애니메이션 모드 사전 준비 {took:.1f}초")

    def _show_prepare(self, job: _Job):
        """파워포인트를 띄우고 파일을 미리 열어 둔다 (쇼는 띄우지 않는다).

        애니메이션 모드를 켤 때 드는 시간의 대부분은 파워포인트 실행(2~5초)과
        파일 열기(큰 파일은 몇 초)다. 목록에서 파일을 고르는 순간 미리 해 두면
        모드를 켤 때는 쇼 실행만 남는다.
        """
        src = os.path.abspath(job.path) if job.path else ""
        if not src or not os.path.exists(src):
            return
        if self._show_window is not None:
            return          # 쇼가 떠 있는 동안에는 건드리지 않는다
        if self._primed_for(src):
            if not self._show_pres_foreign:
                self._minimize_document_window(self._show_pres)
            if self._show_settings_ready_for is not self._show_pres:
                self._warm_for_show(self._show_pres, src)   # 내보내기가 넘겨준 경우
            return
        began = time.time()
        # 붙들고 있던 것(다른 파일, 또는 같은 파일의 수정 전 내용)은 먼저 닫는다 -
        # 같은 파일을 한 번 더 열면 파워포인트가 옛 사본을 그대로 돌려줄 수 있다
        self._show_stop()
        with _keep_our_windows_on_top():
            app = self._ensure_app()
            if self._find_open(app, src) is not None:
                # 사용자가 편집 중인 파일 - 건드리지 않는다 (모드를 켤 때 그때 연다)
                print(f"[ppt_engine] 편집 중인 파일이라 미리 열지 않습니다: {os.path.basename(src)}")
                return
            pres, temp_copy = self._open_presentation(app, src, with_window=True)
            self._minimize_document_window(pres)
        self._keep_presentation(pres, temp_copy, src)
        self._warm_for_show(pres, src)
        print(f"[ppt_engine] 애니메이션 모드 준비(미리 열기): {os.path.basename(src)} "
              f"- {time.time() - began:.1f}초")

    def _show_end(self):
        """쇼 창만 닫고 프레젠테이션은 열어 둔다"""
        self._exit_show_window()
        self._show_range_start = 1
        if self._show_pres is None:
            return
        if self._pres_alive(self._show_pres):
            if not self._show_pres_foreign:
                self._minimize_document_window(self._show_pres)
        else:
            self._show_stop()

    def _show_release(self, job: _Job):
        """열어 둔 프레젠테이션을 닫는다 (편집하려고 같은 파일을 열기 전 등).

        쇼가 실제로 떠 있을 때는 닫지 않는다 - 송출 중인 화면을 끊으면 안 된다.
        """
        if self._show_window is not None:
            return
        src = os.path.abspath(job.path) if job.path else ""
        if src and self._show_source and os.path.normcase(self._show_source) != os.path.normcase(src):
            return
        if self._show_pres is not None:
            print("[ppt_engine] 미리 열어 둔 프레젠테이션을 닫습니다")
        self._show_stop()

    @staticmethod
    def _native_size(pres):
        """슬라이드의 원래 픽셀 크기 (포인트를 96dpi 픽셀로: 1pt = 4/3px)"""
        slide_w = slide_h = 0.0
        try:
            slide_w = float(pres.PageSetup.SlideWidth)
            slide_h = float(pres.PageSetup.SlideHeight)
        except Exception:
            pass
        if slide_w <= 0 or slide_h <= 0:
            slide_w, slide_h = 960.0, 540.0       # 16:9 기본값
        return int(round(slide_w * 4 / 3)), int(round(slide_h * 4 / 3))

    @classmethod
    def _export_size(cls, pres, target_width=None):
        """내보내기 크기 - 슬라이드 원래 크기의 정수 배수로 맞춘다.

        파워포인트는 슬라이드 원래 크기를 기준으로 글자를 배치한 뒤 요청한 크기로
        맞춘다. 배수가 아닌 크기(예: 1280 기준에 1920 = 1.5배)를 요청하면 글자
        크기와 자간이 다시 계산되면서 글꼴이 원본과 다르게 보이고 줄바꿈도 달라진다.
        그래서 목표 폭 이상인 가장 작은 정수 배수를 쓰고, 화면에는 그림을 줄여서
        올린다(줄이는 것은 화질이 상하지 않는다).
        """
        native_w, native_h = cls._native_size(pres)
        target = max(640, int(target_width or DEFAULT_EXPORT_WIDTH))
        scale = max(1, min(MAX_EXPORT_SCALE, -(-target // max(1, native_w))))
        return native_w * scale, native_h * scale

    @staticmethod
    def _read_notes(pres, index: int) -> str:
        """슬라이드 노트의 '본문'만 읽는다.

        노트 페이지에는 본문 말고도 쪽 번호·머리글·바닥글·날짜 상자가 있다. 예전에는
        글이 든 첫 상자를 읽어서, 노트가 없는 슬라이드는 쪽 번호("3")가 노트처럼 나왔다.
        본문 자리가 없으면(직접 그린 글상자만 있는 경우) 자리 표시자가 아닌 글상자를 읽는다.
        """
        body, loose = [], []
        try:
            shapes = pres.Slides.Item(index).NotesPage.Shapes
            for j in range(1, int(shapes.Count) + 1):
                shape = shapes.Item(j)
                try:
                    if not (shape.HasTextFrame and shape.TextFrame.HasText):
                        continue
                    text = str(shape.TextFrame.TextRange.Text)
                except Exception:
                    continue
                is_placeholder = False
                try:
                    is_placeholder = int(shape.Type) == _MSO_PLACEHOLDER
                except Exception:
                    pass
                if is_placeholder:
                    try:
                        if int(shape.PlaceholderFormat.Type) == _PP_PLACEHOLDER_BODY:
                            body.append(text)
                    except Exception:
                        pass
                else:
                    loose.append(text)
        except Exception:
            pass
        text = "\n".join(body or loose)
        # 파워포인트의 줄바꿈(\r 문단, \x0b 줄 나눔)을 보통 줄바꿈으로
        return text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0b", "\n").strip()

    @staticmethod
    def _write_meta(cache_dir, src, count, notes, done, width, height):
        meta = {
            "version": CACHE_VERSION,
            "source": src,
            "count": int(count),
            "notes": notes,
            "notes_rev": NOTES_REV,
            "width": width,
            "height": height,
            "done": bool(done),
            "updated": time.time(),
        }
        try:
            with open(Path(cache_dir) / _META_NAME, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print(f"[ppt_engine] meta.json 기록 실패: {e}")


# ----------------------------------------------------------------------
# 모듈 API
# ----------------------------------------------------------------------
_worker = None
_worker_lock = threading.Lock()


def _ensure_worker():
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            available, _msg = powerpoint_support()
            if not available:
                return None
            _worker = _PptWorker()
            _worker.start()
        return _worker


def prepare_show_async(path):
    """애니메이션 모드를 빨리 띄우도록 파워포인트에 그 파일을 미리 열어 둔다.

    이미 열려 있으면(파일이 바뀌지 않았으면) 아무것도 하지 않는다.
    결과를 기다릴 필요가 없는 준비 작업이라 콜백이 없다.
    """
    if not path or not is_ppt_file(path):
        return
    worker = _ensure_worker()
    if worker is not None:
        worker.submit(_Job("show", path=path, action="prepare"))


def release_presentation(path=None, timeout=15.0):
    """미리 열어 둔 프레젠테이션을 닫고, 닫힐 때까지 (최대 timeout초) 기다린다.

    같은 파일을 편집하려고 열 때 부른다. 붙들어 둔 읽기 전용 사본이 있으면
    파워포인트가 그 사본을 돌려줘 저장이 막히기 때문이다. 슬라이드쇼가 실제로
    떠 있으면 닫지 않는다. 작업 스레드가 없으면(파워포인트를 쓴 적이 없으면)
    곧바로 돌아온다.
    """
    with _worker_lock:
        worker = _worker
    if worker is None or not worker.is_alive():
        return
    done = threading.Event()
    worker.submit(_Job("show", path=path, action="release",
                       on_done=lambda *_: done.set(), on_error=lambda *_: done.set()))
    done.wait(timeout)


def warmup_async():
    """파워포인트를 미리 띄워 둔다 (파일 선택 대화상자를 여는 동안 호출하면 좋다)"""
    worker = _ensure_worker()
    if worker is not None:
        worker.submit(_Job("warmup"))


def export_async(path, on_count=None, on_slide=None, on_done=None, on_error=None,
                 on_cancelled=None, cancel=None, width=None, extract_notes=False,
                 first_index=1):
    """슬라이드를 백그라운드에서 한 장씩 내보낸다.

    콜백(작업 스레드에서 호출됨). on_done / on_error / on_cancelled 중 하나는
    반드시 호출되므로 호출자가 무한정 기다리는 일은 없다.
      on_count(count, paths)      장수와 (아직 없는 파일까지 포함한) 경로 목록
      on_slide(index, path, note) 한 장이 준비됨 (0부터 시작하는 인덱스, 슬라이드 노트)
      on_done(count)          전부 완료
      on_error(message)       실패
      on_cancelled(exported)  cancel() 요청으로 중단됨
      cancel() -> bool        True를 반환하면 중단 (이미 내보낸 장은 캐시에 남는다)
    """
    worker = _ensure_worker()
    if worker is None:
        _available, message = powerpoint_support()
        _safe(on_error, message or "파워포인트를 사용할 수 없습니다.")
        return
    worker.submit(_Job("export", path=path, on_count=on_count, on_slide=on_slide,
                       on_done=on_done, on_error=on_error, on_cancelled=on_cancelled,
                       cancel=cancel, width=width, extract_notes=extract_notes,
                       first_index=first_index))


def export_blocking(path, width=None, extract_notes=False, on_slide=None,
                    cancel=None, timeout=900):
    """테스트/CLI용 동기 내보내기. {'count', 'slides', 'error', 'cancelled'} 반환"""
    finished = threading.Event()
    result = {"count": 0, "slides": [], "error": None, "cancelled": False}

    def _count(count, paths):
        result["count"] = count
        result["slides"] = list(paths)

    def _slide(index, slide_path, note=""):
        result.setdefault("notes", []).append(note)
        if on_slide is not None:
            on_slide(index, slide_path, note)

    def _done(count):
        result["count"] = count
        finished.set()

    def _error(message):
        result["error"] = message
        finished.set()

    def _cancelled(exported):
        result["cancelled"] = True
        result["count"] = exported
        finished.set()

    export_async(path, on_count=_count, on_slide=_slide, on_done=_done,
                 on_error=_error, on_cancelled=_cancelled, cancel=cancel,
                 width=width, extract_notes=extract_notes)
    if not finished.wait(timeout):
        result["error"] = "시간이 초과되었습니다."
    return result


def _submit_show(action, path=None, on_state=None, on_error=None, **payload):
    worker = _ensure_worker()
    if worker is None:
        _available, message = powerpoint_support()
        _safe(on_error, message or "파워포인트를 사용할 수 없습니다.")
        return
    worker.submit(_Job("show", path=path, action=action, payload=payload,
                       on_done=on_state, on_error=on_error))


def show_start(path, index=1, screen_rect=None, on_state=None, on_error=None):
    """실제 파워포인트 슬라이드쇼를 띄운다 (애니메이션·화면 전환이 그대로 재생된다).

    screen_rect: 슬라이드쇼를 올릴 모니터 영역 (x, y, width, height) - 픽셀
    on_state(dict): {'running', 'slide', 'total', 'click', 'clicks'}
    """
    _submit_show("start", path=path, on_state=on_state, on_error=on_error,
                 index=index, screen_rect=screen_rect)


def show_next(on_state=None, on_error=None):
    """다음 단계로 (애니메이션이 있으면 한 단계씩 진행된다)"""
    _submit_show("next", on_state=on_state, on_error=on_error)


def show_previous(on_state=None, on_error=None):
    _submit_show("prev", on_state=on_state, on_error=on_error)


def show_goto(index, on_state=None, on_error=None):
    _submit_show("goto", on_state=on_state, on_error=on_error, index=index)


def show_stop(on_state=None, on_error=None):
    _submit_show("stop", on_state=on_state, on_error=on_error)


def show_state(on_state=None, on_error=None):
    """현재 상태 조회 (사용자가 슬라이드쇼를 직접 끝냈는지 확인용)"""
    _submit_show("state", on_state=on_state, on_error=on_error)


def shutdown():
    """작업 스레드를 정리한다 (우리가 띄운 파워포인트만 종료)"""
    global _worker
    with _worker_lock:
        worker = _worker
        _worker = None
    if worker is not None and worker.is_alive():
        worker.stop()
        worker.join(timeout=5)


def _unblock_file(path: str):
    """윈도우가 인터넷에서 받은 파일에 붙이는 표식(Zone.Identifier 대체 데이터
    스트림)을 지운다 - 파일 속성 창의 '차단 해제' 체크박스와 같은 동작이다.

    이 표식이 있으면 파워포인트가 자동화로 열 때 '보호된 보기'가 자동화 열기를
    막아 DISP_E_EXCEPTION(-2147352567, 안쪽 코드 -2147024893 경로를 찾을 수
    없음)으로 실패한다. Downloads 폴더 등에 있는 파일은 대부분 이 표식이 붙어
    있다. 실패해도(표식이 애초에 없었거나 지울 권한이 없거나) 조용히 넘어간다.
    """
    try:
        os.remove(str(path) + ":Zone.Identifier")
        return True
    except Exception:
        return False


def _wait_ppt_ready(app, timeout=6.0):
    """막 새로 띄운 파워포인트 프로세스가 자동화 호출을 받을 준비가 될 때까지
    짧게 기다린다.

    스플래시 화면/추가 기능 로딩이 끝나기 전에 곧바로 Presentations.Open 을
    부르면 같은 DISP_E_EXCEPTION 으로 실패하는 경우가 있어, 아주 가벼운
    속성(Presentations.Count) 하나가 응답할 때까지 짧게 재시도한다.
    """
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            _ = app.Presentations.Count
            return True
        except Exception as e:
            last_err = e
            time.sleep(0.25)
    print(f"[ppt_engine] 파워포인트 준비 대기 시간 초과: {last_err}")
    return False


def open_for_edit(path: str, slide_index: int = 0, on_error=None, on_notice=None, on_synced=None):
    """지정한 슬라이드가 바로 보이도록 파워포인트를 새 창으로 열어 편집할 수 있게 한다.

    캐시 내보내기/슬라이드쇼 자동화에 쓰는 내부 파워포인트 인스턴스(위의 작업
    스레드가 붙들고 있는 것)와는 완전히 별개의 새 파워포인트 프로세스를 띄운다.
    같은 인스턴스를 건드리면 자동화 중이던 내보내기나 슬라이드쇼가 꼬일 수
    있으므로, 사용자가 수동으로 파워포인트를 하나 더 켠 것과 똑같이 동작한다.

    on_error: 아예 열지 못했을 때(문자열 메시지 하나).
    on_notice: 열리긴 했지만 원본이 아니라 임시 복사본이 열렸을 때 최초 1회 알림.
    on_synced: 임시 복사본으로 열었을 때, 그 복사본에 저장(수정 시각 변경)할
        때마다 원본 파일에 자동으로 반영한 직후 호출된다(원본 경로 하나만
        받는다) - 호출자가 화면의 썸네일/캐시를 새로고침하는 데 쓸 수 있다.
        원본을 직접 열었을 때는(임시 복사본을 쓰지 않았을 때는) 저장이 이미
        원본에 곧바로 반영되므로 호출되지 않는다.

    주의(위 _open_presentation과 같은 이유로 겪는 문제들 - 되도록 같은 방식으로 막는다):
    - 파워포인트는 Word/Excel과 달리 창이 보이지 않는 상태에서는
      Presentations.Open 이 DISP_E_EXCEPTION(-2147352567)으로 실패하므로
      Visible을 먼저 켠다.
    - 막 새로 띄운 프로세스는 준비되기 전에 명령을 받으면 같은 오류를 낼 수
      있어 짧게 준비를 기다린다.
    - Open에 이름 붙은 인자(WithWindow=...)를 쓰면 동적 디스패치에서 인자
      전달이 어긋나는 경우가 있어 위치 인자만 쓴다.
    - Downloads 폴더 등 인터넷에서 받은 파일 표식이 있으면 '보호된 보기'가
      자동화로 여는 것 자체를 막는다 - 원본 파일에서 그 표식을 미리 지운다.
    - 그래도 막혀 있으면(회사 보안 정책 등) 마지막 수단으로 임시 복사본을
      열어서라도 슬라이드를 보고 수정할 수 있게 한다. 이때는 편집 창이 열려
      있는 동안 복사본이 저장될 때마다 원본에도 자동으로 복사해 넣어서,
      '다른 이름으로 저장'을 따로 하지 않아도 원본이 계속 최신 상태를
      유지하게 한다.
    """
    def _sync_temp_to_original(temp_copy, original):
        try:
            shutil.copyfile(temp_copy, original)
            print(f"[ppt_engine] 편집 내용을 원본 파일에 자동 반영했습니다: {original}")
            if on_synced:
                on_synced(str(original))
            return True
        except Exception as e:
            print(f"[ppt_engine] 원본 파일에 자동 반영 실패: {e}")
            return False

    def _watch_and_sync(pres, temp_copy, original, poll_interval=2.0, max_duration=6 * 3600):
        """편집 창이 열려 있는 동안 임시 복사본을 지켜보다가 저장될 때마다
        원본에 자동으로 반영한다. 창이 닫히거나 시간이 오래 지나면 멈춘다."""
        def _mtime():
            try:
                return os.path.getmtime(temp_copy)
            except Exception:
                return None

        last_mtime = _mtime()
        start_time = time.time()
        while time.time() - start_time < max_duration:
            time.sleep(poll_interval)
            closed = False
            try:
                _ = pres.Name   # 창이 닫히면 여기서 예외가 난다
            except Exception:
                closed = True
            mtime = _mtime()
            if mtime is not None and mtime != last_mtime:
                _sync_temp_to_original(temp_copy, original)
                last_mtime = mtime
            if closed:
                break
        print(f"[ppt_engine] 편집 창 감시를 마칩니다: {temp_copy}")

    def _run():
        try:
            import pythoncom
            import win32com.client
        except ImportError:
            if on_error:
                on_error("파워포인트 자동화 모듈(pywin32)을 찾을 수 없습니다.")
            return
        pythoncom.CoInitialize()
        step = "파워포인트 실행"
        temp_copy = None
        try:
            # 애니메이션 모드용으로 같은 파일을 읽기 전용으로 열어 둔 것이 있으면
            # 먼저 닫는다 - 남아 있으면 파워포인트가 그 읽기 전용 사본을 돌려줘서
            # 편집한 내용을 원래 이름으로 저장할 수 없다
            release_presentation(path)
            _unblock_file(path)
            app = win32com.client.DispatchEx("PowerPoint.Application")

            step = "창 표시"
            for value in (_MSO_TRUE, 1, True):
                try:
                    app.Visible = value
                    break
                except Exception:
                    continue

            step = "파워포인트 준비 대기"
            _wait_ppt_ready(app)

            step = "파일 열기"
            src = str(path)
            pres = None
            last_err = None
            # (ReadOnly, Untitled, WithWindow) - 이름 대신 위치 인자를 쓴다
            for args in ((False, False, True), (False, False, False), None):
                try:
                    pres = app.Presentations.Open(src, *args) if args else app.Presentations.Open(src)
                    break
                except Exception as e:
                    last_err = e

            if pres is None:
                # 원본이 계속 막히면(회사 보안 정책의 보호된 보기 등) 임시
                # 복사본으로 한 번 더 시도한다 - 내부 내보내기 파이프라인이 같은
                # 파일에서 이미 이 방법으로 성공한 적이 있을 수 있다.
                step = "임시 복사본으로 열기"
                try:
                    tmp_dir = Path(tempfile.gettempdir()) / "BgTextPresenter_ppt_edit"
                    tmp_dir.mkdir(parents=True, exist_ok=True)
                    # 이전에 만든 복사본 중 더 이상 안 쓰는 것은 정리한다(아직 열려
                    # 있어 잠긴 것은 지워지지 않고 조용히 넘어간다 - 문제 없음).
                    try:
                        for old in tmp_dir.glob("edit_*"):
                            try:
                                old.unlink()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    # pid만 쓰면 같은 프로그램 실행 중에 두 번째로 편집을 열 때
                    # 앞서 여전히 열려 있는(잠긴) 첫 번째 복사본과 이름이 겹쳐
                    # PermissionError 로 실패한다 - 매번 고유한 이름을 만든다.
                    unique = uuid.uuid4().hex[:8]
                    temp_copy = str(tmp_dir / f"edit_{os.getpid()}_{unique}{os.path.splitext(src)[1]}")
                    shutil.copyfile(src, temp_copy)
                    for args in ((False, False, True), None):
                        try:
                            pres = (app.Presentations.Open(temp_copy, *args) if args
                                    else app.Presentations.Open(temp_copy))
                            break
                        except Exception as e:
                            last_err = e
                except Exception as e:
                    last_err = e

            if pres is None:
                raise last_err or RuntimeError("파일을 열 수 없습니다.")

            step = "슬라이드 이동"
            try:
                total = pres.Slides.Count
                idx = max(1, min(total, int(slide_index) + 1))
                win = pres.Windows(1)
                win.View.GotoSlide(idx)
                win.Activate()
            except Exception as e:
                print(f"[ppt_engine] 편집 창에서 슬라이드 이동 실패: {e}")

            if temp_copy:
                if on_notice:
                    on_notice(str(path))
                # 편집 창이 열려 있는 동안, 복사본이 저장될 때마다 원본에 자동
                # 반영한다 (이 스레드에서 계속 - COM은 만든 스레드에서만 써야 한다).
                _watch_and_sync(pres, temp_copy, str(path))
        except Exception as e:
            print(f"[ppt_engine] 편집용 파워포인트 열기 실패 [{step}]: {e}")
            if on_error:
                hint = ""
                if step in ("파일 열기", "임시 복사본으로 열기"):
                    hint = ("\n(윈도우 탐색기에서 이 파일 우클릭 → 속성 → 맨 아래 "
                            "'차단 해제' 체크 → 확인 후 다시 시도해 보세요.)")
                on_error(f"[{step}] {e}{hint}")
        finally:
            pythoncom.CoUninitialize()

    threading.Thread(target=_run, daemon=True, name="ppt-edit-open").start()
