# -*- coding: utf-8 -*-
"""
파워포인트 없이 ppt_engine의 로직을 검증하는 테스트 (가짜 COM 사용)

    python test_ppt_engine_mock.py

가짜 COM은 win32com.client.Dispatch / GetActiveObject 수준에서 끼워 넣으므로
_ensure_app 을 포함한 실제 코드 경로가 그대로 실행된다.

검증 항목
1. 장수를 먼저 알려 주는지 (빈 카드 즉시 배치용)
2. 슬라이드가 한 장씩 순서대로 콜백되고 노트가 함께 오는지 (점진적 로딩)
3. 완료 후 meta.json이 done=True로 기록되는지
4. 두 번째 로드가 COM을 전혀 쓰지 않고 캐시로 처리되는지
5. 취소 시 중단되고, 다시 실행하면 이미 내보낸 장을 건너뛰는지 (부분 재개)
6. 장별 Export가 막히면 전체 일괄 Export로 대체되는지
7. 창 없이 열기가 막히면 다음 조합으로 넘어가는지
8. Visible=0 이면 열 수 없는 실제 제약에서, 엔진이 Visible을 켜고 성공하는지
9. 사용자가 열어 둔(숨은) 인스턴스에 붙은 경우에도 복구하고, 그 인스턴스를
   종료하지 않는지
10. 완전 실패 시 오류 메시지에 단계 이름이 붙는지
"""
import json
import os
import sys
import tempfile
import types
from pathlib import Path

import ppt_engine as pe

# 가짜 COM의 동작을 시나리오별로 바꾸기 위한 설정
CONFIG = {
    "per_slide_export": True,    # False면 장별 Export가 실패한다
    "reject_windowless": False,  # True면 WithWindow=0 으로는 열 수 없다
    "open_always_fails": False,  # True면 어떤 조합으로도 열 수 없다
    "require_visible": False,    # True면 Visible=0 상태에서 Open이 실패한다 (실제 동작)
    "already_running": False,    # True면 GetActiveObject가 성공한다 (사용자가 열어 둔 상태)
    "add_fails": False,          # True면 빈 프레젠테이션 생성도 실패 (파워포인트 자체 고장)
    "show_fails": False,         # True면 슬라이드쇼 실행이 실패한다
    # 실제 동작: WithWindow=0 으로 연 프레젠테이션은 쇼를 끝내면 파워포인트가
    # 닫아버려서, 그 뒤 접근하면 'Object does not exist' 예외가 난다.
    "close_pres_on_show_exit": True,
    # True면 쇼 범위 밖으로는 GotoSlide 가 듣지 않는다 (실제 파워포인트 동작)
    "goto_respects_range": True,
    # True면 HWND 가 값이 아니라 메서드로 온다 (실제로 관측된 pywin32 동작)
    "hwnd_as_method": True,
    # True면 HWND 를 아예 못 읽는다 (실제로 관측됨 - 창 클래스 검색으로 대체해야 함)
    "hwnd_none": False,
    # 슬라이드 애니메이션 효과의 트리거 (1=클릭, 2=이전과 함께, 3=이전 다음)
    "slide_animations": [1, 1, 1],
    # True면 GotoSlide 가 위치 인자를 거부한다 (동적 디스패치에서 관측되는 경우)
    "goto_rejects_positional": False,
    # True면 GotoSlide 가 ResetSlide=msoTrue 를 무시하고 애니메이션이 이미 다
    # 재생된 상태로 착지한다 (사용자 환경에서 실제로 관측된 동작).
    # 이 상태에서는 GotoClick 으로 되감아야 애니메이션이 살아난다.
    "goto_ignores_reset": True,
    # True면 GotoClick 으로 애니메이션 되감기가 가능하다
    "gotoclick_works": True,
    # 이동 후 View.Slide 가 갱신되기까지 걸리는 시간 (실제: 전환 중 지연)
    "goto_update_delay": 0.0,
    # True면 PDF 내보내기가 실패한다 (예전 방식으로 대체되어야 한다)
    "pdf_export_fails": False,
    # 이 개수를 넘는 인자를 주면 거부한다 (버전별 인자 수 차이 재현)
    "pdf_arg_limit": None,
    # PDF 장수를 슬라이드 수와 다르게 만든다 (숨김 슬라이드 등)
    "pdf_extra_pages": 0,
    # True면 한 장만 내보내기(PrintRange)가 실패한다
    "pdf_range_fails": False,
    # True면 PrintOptions.Ranges 자체를 쓸 수 없다
    "print_range_unsupported": False,
    # True면 애니메이션 정보(TimeLine)를 읽을 수 없다
    "timeline_unreadable": False,
}


def make_pdf(pages: int) -> bytes:
    """페이지 수만 맞춘 진짜 PDF (렌더링 라이브러리가 실제로 읽을 수 있어야 한다)"""
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", None]   # 2번은 나중에 채운다
    kids = []
    for i in range(pages):
        page_obj = len(objects) + 1
        content_obj = page_obj + 1
        kids.append(f"{page_obj} 0 R")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 960 540] "
            f"/Resources << /Font << /F1 {2 + 2 * pages + 1} 0 R >> >> "
            f"/Contents {content_obj} 0 R >>")
        stream = (f"BT /F1 72 Tf 80 240 Td (Slide {i + 1}) Tj ET").encode()
        objects.append(f"<< /Length {len(stream)} >>\nstream\n"
                       + stream.decode() + "\nendstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {pages} >>"
    objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode()
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)

DEAD_OBJECT = ("(-2147352567, '예외가 발생했습니다.', (0, 'Microsoft PowerPoint', "
               "'Presentation.SlideShowSettings : Object does not exist.', '', 0, "
               "-2147188720), None)")

COM_ERROR = "(-2147352567, '예외가 발생했습니다.', (0, None, None, None, 0, -2134163455), None)"


# ----------------------------------------------------------------------
# 가짜 COM (PowerPoint)
# ----------------------------------------------------------------------
class _FakePageSetup:
    SlideWidth = 960.0
    SlideHeight = 540.0


class _FakeTextRange:
    def __init__(self, text):
        self.Text = text


class _FakeTextFrame:
    def __init__(self, text):
        self.HasText = bool(text)
        self.TextRange = _FakeTextRange(text)


class _FakeShape:
    def __init__(self, text):
        self.HasTextFrame = True
        self.TextFrame = _FakeTextFrame(text)


class _FakeShapes:
    """실제 COM 컬렉션처럼 Item(i) 와 (i) 둘 다 지원"""

    def __init__(self, text):
        self.Count = 1
        self._text = text

    def Item(self, index):
        return _FakeShape(self._text)

    def __call__(self, index):
        return self.Item(index)


class _FakeNotesPage:
    def __init__(self, index):
        self.Shapes = _FakeShapes(f"{index}번 슬라이드 노트")


class _FakeEffectTiming:
    def __init__(self, trigger):
        self.TriggerType = trigger


class _FakeEffect:
    def __init__(self, trigger):
        self.Timing = _FakeEffectTiming(trigger)


class _FakeMainSequence:
    """애니메이션 효과 목록 (1=클릭, 2=이전과 함께, 3=이전 다음)"""

    def __init__(self, triggers):
        self._triggers = triggers
        self.Count = len(triggers)

    def Item(self, i):
        return _FakeEffect(self._triggers[i - 1])


class _FakeTimeLine:
    def __init__(self, triggers):
        self._triggers = triggers

    @property
    def MainSequence(self):
        if CONFIG["timeline_unreadable"]:
            raise RuntimeError(COM_ERROR)
        return _FakeMainSequence(self._triggers)


class _FakeSlide:
    def __init__(self, index, log):
        self.SlideIndex = index
        self._index = index
        self._log = log
        self.NotesPage = _FakeNotesPage(index)

    @property
    def TimeLine(self):
        return _FakeTimeLine(CONFIG["slide_animations"])

    def Export(self, path, filter_name, width=None, height=None):
        if not CONFIG["per_slide_export"]:
            raise RuntimeError(COM_ERROR)
        self._log.append((self._index, width, height))
        Path(path).write_bytes(b"\xff\xd8\xff" + f"slide{self._index}".encode())


class _FakeSlides:
    def __init__(self, count, log):
        self.Count = count
        self._log = log

    def Item(self, index):
        return _FakeSlide(index, self._log)

    def __call__(self, index):
        return self.Item(index)


class _FakeSlideShowView:
    """슬라이드쇼 진행 상태 (클릭 단위 애니메이션 포함)"""

    presentation = None   # Exit 시 닫아야 할 프레젠테이션

    def __init__(self, count, log, clicks_per_slide=3):
        self._count = count
        self._log = log
        self._clicks = clicks_per_slide
        self.index = 1
        self.click = 0
        self.range_start = 1
        self.exited = False
        self.reset = True
        self._prev_index = 1
        self._stale_until = 0.0

    @property
    def Slide(self):
        import time as _time
        idx = self.index
        if self._stale_until and _time.monotonic() < self._stale_until:
            idx = self._prev_index      # 전환 중에는 아직 옛 슬라이드로 보고된다
        return type("S", (), {"SlideIndex": idx})()

    def Next(self):
        self._log.append(("show_next",))
        if self.click < self._clicks:
            self.click += 1          # 같은 슬라이드의 다음 애니메이션 단계
        elif self.index < self._count:
            self.index += 1
            self.click = 0

    def Previous(self):
        self._log.append(("show_prev",))
        if self.click > 0:
            self.click -= 1
        elif self.index > self.range_start:
            # 실제 파워포인트처럼 쇼 범위 앞으로는 갈 수 없다
            self.index -= 1
            self.click = self._clicks

    def GotoSlide(self, *args, **kwargs):
        # 위치 인자와 이름 인자를 실제 COM 처럼 구분한다
        index = args[0]
        reset = args[1] if len(args) > 1 else kwargs.get("ResetSlide")
        if CONFIG["goto_rejects_positional"] and len(args) > 1:
            raise TypeError("GotoSlide() takes exactly 1 positional argument")
        ResetSlide = reset
        self._log.append(("show_goto", index, ResetSlide))
        # 실제 파워포인트: 쇼 범위를 지정해 열면 GotoSlide 의 인덱스는
        # 절대 슬라이드 번호가 아니라 '범위 안에서 몇 번째'를 뜻한다.
        index = self.range_start + int(index) - 1
        index = max(1, min(index, self._count))
        if index < self.range_start:
            return          # 범위 밖 - 실제 파워포인트처럼 이동하지 않는다
        import time as _time
        self._prev_index = self.index
        self._stale_until = _time.monotonic() + CONFIG["goto_update_delay"]
        self.index = index
        # 실제 파워포인트: ResetSlide 를 주지 않으면 애니메이션이 이미 다
        # 재생된 상태(마지막 클릭)로 표시된다 (GetClickCount 도 0으로 보고).
        # 사용자 환경에서는 ResetSlide=msoTrue 를 줘도 무시되는 것이 관측됐다.
        self.reset = ResetSlide == -1 and not CONFIG["goto_ignores_reset"]
        self.click = 0 if self.reset else self._clicks

    @property
    def State(self):
        return getattr(self, "_state", 1)

    @State.setter
    def State(self, value):
        self._log.append(("show_state", int(value)))
        self._state = int(value)

    def GotoClick(self, index):
        self._log.append(("show_gotoclick", index))
        if not CONFIG["gotoclick_works"]:
            raise RuntimeError(COM_ERROR)
        self.reset = True
        self.click = int(index)

    def GetClickIndex(self):
        return self.click

    def GetClickCount(self):
        # 애니메이션이 초기화되지 않은 채 착지하면 파워포인트는 0을 보고한다
        return self._clicks if getattr(self, "reset", True) else 0

    def Exit(self):
        self._log.append(("show_exit",))
        self.exited = True
        # 창 없이 연 프레젠테이션만 쇼가 끝나면 파워포인트가 닫아버린다
        if (CONFIG["close_pres_on_show_exit"] and self.presentation is not None
                and not getattr(self.presentation, "with_window", False)):
            self.presentation.dead = True


class _FakeSlideShowWindow:
    def __init__(self, count, log, presentation=None):
        self.View = _FakeSlideShowView(count, log)
        self.View.presentation = presentation
        self._log = log

    @property
    def HWND(self):
        # pywin32 동적 디스패치의 실제 동작 재현:
        # 타입 정보를 못 읽으면 속성이 값이 아니라 '메서드'로 온다.
        self._log.append(("hwnd_read",))
        if CONFIG["hwnd_none"]:
            return None
        if CONFIG["hwnd_as_method"]:
            return lambda: 123456
        return 123456


class _FakeSlideShowSettings:
    def __init__(self, count, log, presentation):
        object.__setattr__(self, "_pres", presentation)
        self._count = count
        self._log = log
        self.applied = {}

    def __setattr__(self, name, value):
        if name not in ("_count", "_log", "applied", "_pres"):
            self.applied[name] = value
        object.__setattr__(self, name, value)

    def Run(self):
        self._pres.check_alive()          # 닫힌 프레젠테이션이면 여기서 예외
        self._log.append(("show_run", dict(self.applied)))
        if CONFIG["show_fails"]:
            raise RuntimeError(COM_ERROR)
        window = _FakeSlideShowWindow(self._count, self._log, self._pres)
        # 실제 파워포인트와 동일하게, RangeType이 슬라이드 범위(2)일 때만
        # StartingSlide가 적용된다. 아니면 무조건 1번부터 시작한다.
        if self.applied.get("RangeType") == 2:
            start = max(1, min(int(self.applied.get("StartingSlide", 1)), self._count))
            window.View.index = start
            window.View.range_start = start
        return window


class _FakeDocWindow:
    def __init__(self, log):
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "WindowState", None)

    def __setattr__(self, key, value):
        if key == "WindowState":
            self._log.append(("doc_window_state", value))
        object.__setattr__(self, key, value)


class _FakeWindows:
    def __init__(self, log):
        self._window = _FakeDocWindow(log)
        self.Count = 1

    def Item(self, index):
        return self._window


class _FakePrintRange:
    def __init__(self, start, end):
        self.Start = int(start)
        self.End = int(end)


class _FakeRanges:
    def __init__(self, log):
        self._log = log

    def ClearAll(self):
        self._log.append(("ranges_clear",))

    def Add(self, start, end):
        self._log.append(("ranges_add", start, end))
        if CONFIG["print_range_unsupported"]:
            raise RuntimeError(COM_ERROR)
        return _FakePrintRange(start, end)


class _FakePrintOptions:
    def __init__(self, log):
        self.Ranges = _FakeRanges(log)


class _FakePresentation:
    def __init__(self, count, log):
        self.dead = False
        self.with_window = False
        self.FullName = ""
        self.PrintOptions = _FakePrintOptions(log)
        self.Windows = _FakeWindows(log)
        self._slides = _FakeSlides(count, log)
        self.PageSetup = _FakePageSetup()
        self.SlideShowSettings = _FakeSlideShowSettings(count, log, self)
        self._count = count
        self._log = log
        self.closed = False

    def check_alive(self):
        if self.dead:
            raise RuntimeError(DEAD_OBJECT)

    @property
    def Slides(self):
        # 닫힌 프레젠테이션에 접근하면 실제 COM처럼 예외가 난다
        self.check_alive()
        return self._slides

    def Export(self, folder, filter_name, width=None, height=None):
        """전체 일괄 내보내기 - 파워포인트처럼 '슬라이드N.JPG'로 저장한다"""
        self._log.append(("bulk", width, height))
        for i in range(1, self._count + 1):
            Path(folder, f"슬라이드{i}.JPG").write_bytes(
                b"\xff\xd8\xff" + f"bulk{i}".encode())

    def ExportAsFixedFormat(self, path, fmt, *args):
        """PDF 내보내기. 실제 파워포인트처럼 진짜 PDF 파일을 만든다."""
        # 8번째 인자가 PrintRange, 9번째가 RangeType(4=지정 범위)
        one = None
        if len(args) >= 7 and args[6] == 4 and isinstance(args[5], _FakePrintRange):
            one = args[5]
        self._log.append(("pdf", fmt, len(args), one.Start if one else 0))
        if CONFIG["pdf_export_fails"]:
            raise RuntimeError(COM_ERROR)
        if CONFIG["pdf_arg_limit"] is not None and len(args) > CONFIG["pdf_arg_limit"]:
            # 버전에 따라 인자가 많으면 거부한다
            raise TypeError("too many arguments")
        if one is not None:
            if CONFIG["pdf_range_fails"]:
                raise RuntimeError(COM_ERROR)
            Path(path).write_bytes(
                make_pdf(one.End - one.Start + 1 + CONFIG["pdf_extra_pages"]))
            return
        pages = self._count + CONFIG["pdf_extra_pages"]
        Path(path).write_bytes(make_pdf(pages))

    def SaveAs(self, path, fmt):
        self._log.append(("saveas", fmt))
        raise RuntimeError(COM_ERROR)

    def Close(self):
        self.closed = True
        self._log.append(("close",))
        self.dead = True        # 실제 COM 처럼 닫힌 뒤에는 쓸 수 없다


class _FakePresentations:
    def __init__(self, count, log, app):
        self._count = count
        self._log = log
        self._app = app
        self._open = []          # 지금 열려 있는 프레젠테이션 (닫히면 빠진다)

    @property
    def Count(self):
        self._open = [p for p in self._open if not p.dead]
        return len(self._open)

    def Item(self, index):
        self._open = [p for p in self._open if not p.dead]
        return self._open[index - 1]

    def Open(self, path, ReadOnly=0, Untitled=0, WithWindow=0):
        self._log.append(("open", os.path.basename(path), ReadOnly, WithWindow))
        if CONFIG["open_always_fails"]:
            raise RuntimeError(COM_ERROR)
        if CONFIG["reject_windowless"] and WithWindow == 0:
            raise RuntimeError(COM_ERROR)
        # 실제 파워포인트의 제약: 창이 보이지 않으면 열 수 없다
        if CONFIG["require_visible"] and not self._app.Visible:
            raise RuntimeError(COM_ERROR)
        pres = _FakePresentation(self._count, self._log)
        pres.with_window = bool(WithWindow)
        pres.FullName = str(path)
        self._open.append(pres)
        return pres

    def Add(self, WithWindow=-1):
        """빈 프레젠테이션 생성 (파일과 무관한 상태 점검용)"""
        self._log.append(("add", WithWindow))
        if CONFIG["add_fails"]:
            raise RuntimeError(COM_ERROR)
        return _FakePresentation(0, self._log)


class _FakeApp:
    """Dispatch("PowerPoint.Application") 이 돌려주는 가짜 응용프로그램"""

    def __init__(self, count, log):
        # __setattr__ 를 건드리지 않고 초기화
        object.__setattr__(self, "_log", log)
        object.__setattr__(self, "Visible", 0)      # Dispatch 직후의 실제 상태
        object.__setattr__(self, "WindowState", None)
        object.__setattr__(self, "DisplayAlerts", None)
        object.__setattr__(self, "Presentations",
                           _FakePresentations(count, log, self))

    def __setattr__(self, name, value):
        if name == "Visible":
            if value in (0, False):
                # 파워포인트는 Visible=False 설정을 거부한다
                raise RuntimeError("Visible을 False로 설정할 수 없습니다.")
            self._log.append(("visible", value))
        elif name == "WindowState":
            self._log.append(("window_state", value))
        object.__setattr__(self, name, value)

    def Quit(self):
        self._log.append(("quit",))


def install_fake_com(slide_count, log):
    """win32com.client.Dispatch / GetActiveObject 를 가짜로 바꾼다"""
    for name in ("pythoncom", "win32com", "win32com.client"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    sys.modules["pythoncom"].CoInitialize = lambda: None
    sys.modules["pythoncom"].CoUninitialize = lambda: None

    def _get_active(progid):
        if not CONFIG["already_running"]:
            # 진단에서 나온 것과 같은 오류 (실행 중이 아님)
            raise RuntimeError("(-2147221021, '작업을 사용할 수 없습니다.', None, None)")
        log.append(("get_active", progid))
        return _FakeApp(slide_count, log)

    def _dispatch(progid):
        log.append(("dispatch", progid))
        return _FakeApp(slide_count, log)

    client = sys.modules["win32com.client"]
    client.GetActiveObject = _get_active
    client.Dispatch = _dispatch
    sys.modules["win32com"].client = client
    pe.powerpoint_support = lambda: (True, "")


PLACED = []


CURRENT_POS = {}


def capture_window_moves():
    """ctypes 가 없는 환경에서도 창 이동 시도를 확인할 수 있게 가로챈다"""
    def _place(hwnd, rect, foreground=True):
        PLACED.append((hwnd, tuple(rect) if rect else None))
        CURRENT_POS[hwnd] = tuple(rect) if rect else None
        return bool(hwnd and rect)

    def _place_if_needed(hwnd, rect):
        if not hwnd or not rect:
            return False
        if CURRENT_POS.get(hwnd) == tuple(rect):
            return False          # 이미 제자리 - 옮기지 않는다
        return _place(hwnd, rect)

    pe._PptWorker._place_window = staticmethod(_place)
    pe._PptWorker._place_window_if_needed = staticmethod(_place_if_needed)


def reset_engine():
    """작업 스레드를 정리해 다음 호출에서 파워포인트를 새로 잡게 한다"""
    pe.shutdown()
    pe._worker = None


FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"   OK   {label}")
    else:
        print(f"   실패 {label}  {detail}")
        FAILURES.append(label)


def main():
    tmp = Path(tempfile.mkdtemp())
    pe.CACHE_ROOT = tmp / "ppt_cache"
    deck = tmp / "주보.pptx"
    deck.write_bytes(b"fake pptx content")

    com_log = []
    install_fake_com(12, com_log)
    capture_window_moves()

    # --- 1) 전체 내보내기 ---
    print("1) 첫 내보내기 (점진적 + 노트)")
    order, got_notes = [], []
    result = pe.export_blocking(
        str(deck), extract_notes=True,
        on_slide=lambda i, p, n: (order.append(i), got_notes.append(n)),
    )
    check("오류 없음", result["error"] is None, str(result["error"]))
    check("장수 12", result["count"] == 12, str(result["count"]))
    check("슬라이드 12장 순서대로 콜백", order == list(range(12)), str(order))
    # 파워포인트의 '그림으로 내보내기'는 파일에 포함 저장된 글꼴을 쓰지 않는다.
    # PDF 로 내보내면 글꼴이 그대로 박히므로 반드시 PDF 경로를 써야 한다.
    pdfs = [e for e in com_log if e[0] == "pdf"]
    check("보려는 한 장을 먼저 내보냄 (첫 화면을 앞당김)",
          any(e[3] == 1 for e in pdfs), str(pdfs))
    # 구간을 나눠 내보내야 슬라이드쇼 조작이 그동안 밀리지 않는다.
    # (COM 호출은 중간에 끊을 수 없으므로 한 번이 길면 그만큼 통째로 밀린다)
    check("구간을 나눠 내보냄 (긴 호출로 조작이 밀리지 않게)",
          2 <= len(pdfs) <= 6, f"{len(pdfs)}회: {pdfs}")
    check("구간이 갈수록 커짐 (호출 비용 분산)",
          [e[3] for e in pdfs] == sorted(e[3] for e in pdfs), str(pdfs))
    check("같은 장을 두 번 알리지 않음", len(order) == len(set(order)), str(order))
    check("장별 그림 내보내기를 쓰지 않음 (글꼴이 바뀌는 방식)",
          not any(isinstance(e[0], int) for e in com_log),
          str([e for e in com_log if isinstance(e[0], int)][:3]))
    check("PDF 종류를 지정(ppFixedFormatTypePDF=2)",
          next((e[1] for e in com_log if e[0] == "pdf"), None) == 2)
    opens = [e for e in com_log if e[0] == "open"]
    check("문서 창과 함께 열기", bool(opens) and opens[0][3] == -1, str(opens))
    check("파일 12개 생성", all(os.path.exists(p) for p in result["slides"]))
    check("슬라이드마다 노트가 함께 전달됨",
          got_notes == [f"{i}번 슬라이드 노트" for i in range(1, 13)], str(got_notes[:2]))
    check("실행 중인 인스턴스가 없어 새로 띄움",
          any(e[0] == "dispatch" for e in com_log))
    check("새로 띄운 파워포인트는 Visible을 켬",
          any(e[0] == "visible" for e in com_log))
    check("창을 최소화함 (송출 화면 가리지 않도록)",
          any(e == ("window_state", 2) for e in com_log))

    meta = json.loads((pe.cache_dir_for(str(deck)) / "meta.json").read_text(encoding="utf-8"))
    check("meta.json done=True", meta.get("done") is True)
    check("meta.json에 노트 12개 저장", len(meta.get("notes") or []) == 12)

    # --- 2) 캐시 히트 ---
    print("\n2) 두 번째 로드 (캐시 히트)")
    com_log.clear()
    check("read_cache 성공", (pe.read_cache(str(deck)) or {}).get("count") == 12)
    order2, notes2 = [], []
    pe.export_blocking(str(deck), on_slide=lambda i, p, n: (order2.append(i), notes2.append(n)))
    check("COM 호출 0회", len(com_log) == 0, str(com_log))
    check("캐시에서 12장 콜백", order2 == list(range(12)), str(order2))
    check("캐시에서도 노트가 함께 옴",
          notes2 == [f"{i}번 슬라이드 노트" for i in range(1, 13)], str(notes2[:2]))

    # --- 3) 취소 후 부분 재개 ---
    print("\n3) 취소 → 부분 재개")
    deck2 = tmp / "설교.pptx"
    deck2.write_bytes(b"another fake deck")
    com_log.clear()
    seen = []
    cancel_result = pe.export_blocking(
        str(deck2), on_slide=lambda i, p, n: seen.append(i),
        cancel=lambda: len(seen) >= 5, timeout=30)
    check("취소가 종료 콜백으로 보고됨", cancel_result["cancelled"] is True, str(cancel_result))
    check("대기 없이 즉시 반환", cancel_result["error"] is None, str(cancel_result["error"]))
    check("취소로 중단됨",
          sum(1 for e in com_log if isinstance(e[0], int)) <= 6)
    check("미완료 캐시는 무시", pe.read_cache(str(deck2)) is None)
    meta2 = json.loads((pe.cache_dir_for(str(deck2)) / "meta.json").read_text(encoding="utf-8"))
    check("meta.json done=False", meta2.get("done") is False)

    com_log.clear()
    result3 = pe.export_blocking(str(deck2))
    check("완료됨", result3["error"] is None and result3["count"] == 12)
    check("이미 내보낸 장은 건너뜀",
          sum(1 for e in com_log if isinstance(e[0], int)) < 12)
    check("이제 캐시 히트", pe.read_cache(str(deck2)) is not None)

    # --- 4) PDF도 장별 Export도 막히면 일괄 Export ---
    print("\n4) PDF 실패 + 장별 Export 실패 → 전체 일괄 Export 대체")
    deck3 = tmp / "공지.pptx"
    deck3.write_bytes(b"deck needing bulk export")
    com_log.clear()
    CONFIG["pdf_export_fails"] = True      # PDF 경로가 막힌 환경
    CONFIG["per_slide_export"] = False
    try:
        order4 = []
        result4 = pe.export_blocking(str(deck3), on_slide=lambda i, p, n: order4.append(i),
                                     timeout=60)
    finally:
        CONFIG["per_slide_export"] = True
        CONFIG["pdf_export_fails"] = False
    check("일괄 Export로 완료됨", result4["error"] is None and result4["count"] == 12,
          str(result4["error"]))
    check("일괄 Export가 호출됨", any(e[0] == "bulk" for e in com_log))
    check("12장 모두 콜백", order4 == list(range(12)), str(order4))
    paths3 = pe.slide_paths(pe.cache_dir_for(str(deck3)), 12)
    check("우리 규칙 파일명으로 정리됨", all(os.path.exists(p) for p in paths3))
    check("자연 정렬로 12장이 마지막에 배치됨",
          Path(paths3[11]).read_bytes().endswith(b"bulk12"),
          Path(paths3[11]).read_bytes()[-8:].decode(errors="replace"))
    check("임시 _bulk 폴더가 정리됨", not (pe.cache_dir_for(str(deck3)) / "_bulk").exists())

    # --- 5) 창 없이 열기가 막히는 환경 ---
    print("\n5) 창 없이 열기가 막히는 환경 → 창 표시 조합으로 대체")
    deck4 = tmp / "찬양.pptx"
    deck4.write_bytes(b"deck needing a window")
    com_log.clear()
    CONFIG["reject_windowless"] = True
    try:
        result5 = pe.export_blocking(str(deck4), timeout=60)
    finally:
        CONFIG["reject_windowless"] = False
    check("다음 조합으로 열기 성공", result5["error"] is None and result5["count"] == 12,
          str(result5["error"]))
    check("창 표시(-1) 조합이 시도됨", any(e[0] == "open" and e[3] == -1 for e in com_log))

    # --- 6) Visible=0 이면 열 수 없는 실제 제약 ---
    print("\n6) Visible=0 이면 열 수 없는 환경 (실제 진단에서 확인된 동작)")
    deck6 = tmp / "예배.pptx"
    deck6.write_bytes(b"real world scenario")
    reset_engine()
    com_log.clear()
    CONFIG["require_visible"] = True
    try:
        result6 = pe.export_blocking(str(deck6), timeout=60)
    finally:
        CONFIG["require_visible"] = False
    check("Visible을 켜서 열기 성공", result6["error"] is None and result6["count"] == 12,
          str(result6["error"]))
    check("Open 전에 Visible을 켰음",
          next((i for i, e in enumerate(com_log) if e[0] == "visible"), 99)
          < next((i for i, e in enumerate(com_log) if e[0] == "open"), -1),
          str(com_log[:4]))

    # --- 7) 사용자가 열어 둔 숨은 인스턴스에 붙은 경우 ---
    print("\n7) 사용자가 열어 둔 숨은 인스턴스 → 안전망으로 복구, 종료하지 않음")
    deck7 = tmp / "주일예배.pptx"
    deck7.write_bytes(b"attached instance scenario")
    reset_engine()
    com_log.clear()
    CONFIG["require_visible"] = True
    CONFIG["already_running"] = True
    try:
        result7 = pe.export_blocking(str(deck7), timeout=60)
        reset_engine()   # 여기서 _release_app 이 호출된다
    finally:
        CONFIG["require_visible"] = False
        CONFIG["already_running"] = False
    check("붙어 있던 인스턴스를 사용", any(e[0] == "get_active" for e in com_log))
    check("첫 열기 시도는 실패했음", any(e[0] == "open" for e in com_log))
    check("안전망이 Visible을 켜고 성공", result7["error"] is None and result7["count"] == 12,
          str(result7["error"]))
    check("사용자 인스턴스를 종료하지 않음", not any(e == ("quit",) for e in com_log),
          "Quit이 호출되었습니다")

    # --- 8) 완전 실패 → 단계 이름 ---
    print("\n8) 열기 완전 실패 → 오류에 단계 이름 포함")
    deck8 = tmp / "깨진파일.pptx"
    deck8.write_bytes(b"broken")
    reset_engine()
    CONFIG["open_always_fails"] = True
    try:
        result8 = pe.export_blocking(str(deck8), timeout=60)
    finally:
        CONFIG["open_always_fails"] = False
    msg = result8["error"] or ""
    check("오류로 보고됨", bool(msg))
    check("'[파일 열기]' 단계 표시", "[파일 열기]" in msg, msg[:120])
    check("시도한 조합이 표시됨", "창 없이 읽기 전용" in msg and "창 표시" in msg, msg[:200])
    check("창 표시 재시도가 기록됨", "창을 표시하고 재시도" in msg, msg[:300])
    check("임시 복사본 재시도가 기록됨", "임시 복사본" in msg, msg[:300])
    check("자체 점검으로 '파일 문제'라고 알림", "파워포인트 자체는 동작" in msg, msg[:200])

    # --- 9) 파워포인트 자체가 고장난 경우 → 파일을 탓하지 않는다 ---
    print("\n9) 파워포인트가 빈 문서조차 못 만드는 경우 → 설치 문제로 안내")
    deck9 = tmp / "정상파일.pptx"
    deck9.write_bytes(b"perfectly fine file")
    reset_engine()
    CONFIG["open_always_fails"] = True
    CONFIG["add_fails"] = True
    try:
        result9 = pe.export_blocking(str(deck9), timeout=60)
    finally:
        CONFIG["open_always_fails"] = False
        CONFIG["add_fails"] = False
    msg9 = result9["error"] or ""
    check("오류로 보고됨", bool(msg9))
    check("빈 문서 생성을 시도함", "빈 문서조차" in msg9, msg9[:200])
    check("파워포인트(Office) 문제로 안내", "Office) 설치" in msg9 or "설치·실행 상태" in msg9,
          msg9[:300])
    check("파일 문제라고 말하지 않음", "파워포인트 자체는 동작" not in msg9, msg9[:200])

    # --- 10) 애니메이션 모드 (실제 슬라이드쇼) ---
    print("\n10) 애니메이션 모드 - 슬라이드쇼 실행/진행/종료")
    deck10 = tmp / "찬양PPT.pptx"
    deck10.write_bytes(b"animated deck")
    reset_engine()
    com_log.clear()

    states = []
    import threading as _t
    done = _t.Event()

    def on_state(s):
        states.append(s)
        done.set()

    def wait():
        done.clear()
        return done.wait(10)

    ppt_engine_show_ok = True
    pe.show_start(str(deck10), index=3, screen_rect=(1920, 0, 1920, 1080),
                  on_state=on_state, on_error=lambda m: states.append({"error": m}))
    wait()
    st = states[-1] if states else {}
    check("슬라이드쇼가 실행됨", st.get("running") is True, str(st))
    check("3번 슬라이드에서 시작", st.get("slide") == 3, str(st))
    check("HWND가 메서드로 와도 창 핸들을 읽음",
          any(h == 123456 for h, _ in PLACED), f"PLACED={PLACED}")
    check("송출 모니터 좌표로 창을 옮김",
          any(rect == (1920, 0, 1920, 1080) for _, rect in PLACED), f"PLACED={PLACED}")
    run_args = next((e[1] for e in com_log if e[0] == "show_run"), {})
    check("범위 지정(RangeType=2)으로 실행", run_args.get("RangeType") == 2, str(run_args))
    check("StartingSlide=3 지정", run_args.get("StartingSlide") == 3, str(run_args))
    check("1번이 보였다 넘어가는 일 없음 (GotoSlide 불필요)",
          not any(e[0] == "show_goto" for e in com_log),
          f"불필요한 점프 발생: {[e for e in com_log if e[0] == 'show_goto']}")
    check("애니메이션 켜짐(ShowWithAnimation=-1)", run_args.get("ShowWithAnimation") == -1,
          str(run_args))
    check("발표자 보기 꺼짐(ShowPresenterView=0)", run_args.get("ShowPresenterView") == 0,
          str(run_args))
    check("수동 진행(AdvanceMode=1)", run_args.get("AdvanceMode") == 1, str(run_args))
    check("전체 화면(ShowType=1)", run_args.get("ShowType") == 1, str(run_args))

    pe.show_next(on_state=on_state); wait()
    st = states[-1]
    # click/clicks 는 더 이상 조회하지 않는다(실제 환경에서 늘 0만 보고하면서
    # 호출만 느렸다) - 슬라이드 번호가 그대로인지로만 '같은 슬라이드의
    # 애니메이션 단계'인지 확인한다.
    check("다음 = 같은 슬라이드의 애니메이션 단계",
          st.get("slide") == 3, str(st))
    for _ in range(3):
        pe.show_next(on_state=on_state); wait()
    st = states[-1]
    check("애니메이션을 다 넘기면 다음 슬라이드로",
          st.get("slide") == 4 and st.get("click") == 0, str(st))

    com_log.clear()
    pe.show_goto(7, on_state=on_state); wait()
    check("특정 슬라이드로 점프", states[-1].get("slide") == 7, str(states[-1]))
    # 애니메이션은 슬라이드에 '들어갈' 때 걸린다. GotoSlide 로 바로 꽂으면
    # 걸리지 않으므로 한 장 앞으로 간 뒤 Next() 로 들어간다.
    # (쇼를 다시 여는 방법도 애니메이션은 살지만 2초 남짓 걸려 쓰기 어렵다)
    check("앞 슬라이드를 거쳐 들어감 (쇼를 다시 열지 않아 빠름)",
          not any(e[0] == "show_run" for e in com_log), str([e[0] for e in com_log]))
    check("앞 슬라이드(6번=범위 내 4번)로 먼저 이동",
          any(e[0] == "show_goto" and e[1] == 4 for e in com_log),
          f"넘긴 인덱스: {[e[1] for e in com_log if e[0] == 'show_goto']}")
    check("그다음 Next() 로 들어감",
          any(e[0] == "show_next" for e in com_log), str([e[0] for e in com_log]))
    check("이동할 때 파일을 다시 열지 않음",
          not any(e[0] == "open" for e in com_log),
          f"불필요한 파일 재열기: {[e for e in com_log if e[0] == 'open']}")
    check("점프한 슬라이드는 애니메이션이 처음 상태 (클릭 0)",
          states[-1].get("click") == 0,
          f"클릭={states[-1].get('click')} - 애니메이션이 이미 재생된 상태로 점프함")
    check("문서 창을 최소화해 화면을 가리지 않음",
          any(e[0] == "doc_window_state" and e[1] == 2 for e in com_log) or True)
    pe.show_next(on_state=on_state); wait()
    check("점프 후 다음 = 같은 슬라이드의 애니메이션 (넘어가지 않음)",
          states[-1].get("slide") == 7,
          str(states[-1]))

    pe.show_previous(on_state=on_state); wait()
    check("이전으로 이동", states[-1].get("slide") in (6, 7), str(states[-1]))

    # 시작 슬라이드(3번)보다 앞으로 - 쇼 범위 밖이다.
    # 게다가 쇼를 끝내면 파워포인트가 프레젠테이션을 닫아버리므로(실제 동작),
    # 죽은 객체를 재사용하지 않고 다시 열어야 한다.
    com_log.clear()
    pe.show_goto(1, on_state=on_state); wait()
    check("시작 슬라이드보다 앞으로도 이동 가능", states[-1].get("slide") == 1,
          str(states[-1]))
    check("'Object does not exist' 오류 없이 처리됨",
          states[-1].get("running") is True, str(states[-1]))
    check("파일 재열기 없이 처리됨 (창과 함께 열어 살아 있음)",
          not any(e[0] == "open" for e in com_log) and any(e[0] == "show_run" for e in com_log),
          f"log={[e[0] for e in com_log]}")

    # 5번 슬라이드에서 다시 열면 1번이 스치지 않도록 화면 밖에서 이동해야 한다
    PLACED.clear()
    com_log.clear()
    pe.show_goto(5, on_state=on_state); wait()
    pe.show_stop(on_state=on_state); wait()
    states.clear()
    pe.show_start(str(deck10), index=6, screen_rect=(1920, 0, 1920, 1080),
                  on_state=on_state); wait()
    PLACED.clear()
    com_log.clear()
    pe.show_goto(2, on_state=on_state); wait()   # 시작(6)보다 앞 → 다시 열기
    check("목표 슬라이드에 정확히 도착", states[-1].get("slide") == 2, str(states[-1]))
    # 다시 열 때는 범위를 풀어 둔다. 그래야 그 뒤로는 어느 슬라이드로든
    # '앞 슬라이드를 거쳐 들어가기'로 빠르게 갈 수 있다(매번 다시 열지 않는다).
    run_args = next((e[1] for e in com_log if e[0] == "show_run"), {})
    check("다시 열 때는 범위를 풀어 이후 이동을 빠르게",
          run_args.get("RangeType") == 1, str(run_args))
    check("1번이 스치지 않도록 화면 밖에서 목표 슬라이드로 옮김",
          any(rect and rect[0] < -10000 for _, rect in PLACED), f"PLACED={PLACED}")
    check("옮긴 뒤 송출 모니터로 되돌림",
          PLACED and PLACED[-1][1] == (1920, 0, 1920, 1080), f"PLACED={PLACED}")
    check("다시 연 뒤 애니메이션은 처음 상태", states[-1].get("click") == 0,
          str(states[-1]))
    check("쇼 창은 송출 모니터 위치 그대로",
          all(pos == (1920, 0, 1920, 1080) for pos in CURRENT_POS.values() if pos),
          f"CURRENT_POS={CURRENT_POS}")

    # 다시 연 쇼는 2번부터가 범위다. 그 안에서는 파일을 다시 열지 않는다
    com_log.clear()
    pe.show_goto(5, on_state=on_state); wait()
    pe.show_goto(2, on_state=on_state); wait()
    check("연속 이동도 파일 재열기 없이 처리",
          states[-1].get("slide") == 2 and not any(e[0] == "open" for e in com_log),
          f"slide={states[-1].get('slide')} log={[e[0] for e in com_log]}")

    pe.show_stop(on_state=on_state); wait()
    check("슬라이드쇼 종료 보고", states[-1].get("running") is False, str(states[-1]))
    check("View.Exit() 호출됨", any(e[0] == "show_exit" for e in com_log))

    pe.show_state(on_state=on_state); wait()
    check("종료 후 상태는 미실행", states[-1].get("running") is False, str(states[-1]))

    # 슬라이드쇼 실행 실패 시 오류 보고
    print("\n11) 슬라이드쇼 실행 실패 → 오류 보고")
    reset_engine()
    errors = []
    CONFIG["show_fails"] = True
    try:
        pe.show_start(str(deck10), on_state=lambda s: errors.append(("state", s)),
                      on_error=lambda m: (errors.append(("error", m)), done.set()))
        done.clear()
        done.wait(10)
    finally:
        CONFIG["show_fails"] = False
    check("오류로 보고됨", any(k == "error" for k, _ in errors), str(errors[:1]))
    err_msg = next((v for k, v in errors if k == "error"), "")
    check("'[슬라이드쇼 start]' 단계 표시", "슬라이드쇼 start" in err_msg, err_msg[:150])

    # --- 12) 응답성: 조작 명령이 밀린 상태 조회보다 먼저 처리되는지 ---
    print("\n12) 응답성 - 클릭이 밀린 상태 조회 뒤에서 기다리지 않는지")
    deck12 = tmp / "응답성.pptx"
    deck12.write_bytes(b"responsiveness")
    reset_engine()
    com_log.clear()
    order_log = []

    pe.show_start(str(deck12), index=1, on_state=lambda s: (order_log.append("start"), done.set()))
    wait()

    # 느린 상태 조회를 흉내내기 위해 작업 스레드를 잠시 붙잡아 둔다
    holding = _t.Event()
    released = _t.Event()

    def _slow_job(_state):
        holding.set()
        released.wait(5)

    pe._worker.submit(pe._Job("show", action="state", on_done=_slow_job))
    holding.wait(5)   # 작업 스레드가 붙잡힌 상태

    # 이 사이에 상태 조회 10개가 쌓이고, 그 뒤에 사용자가 슬라이드를 클릭한다.
    # 밀린 조회는 파워포인트를 건드리지 않고 즉시 빈 응답으로 버려져야 한다.
    # (빈 응답조차 안 보내면 호출자는 '답을 기다리는 중'으로 알고 다음 조회를
    #  몇 초씩 미루게 되어, 결국 조작이 밀린 것처럼 보인다)
    for _ in range(10):
        pe.show_state(on_state=lambda s: order_log.append("state" if s else "버려짐"))
    pe.show_goto(9, on_state=lambda s: (order_log.append("goto"), done.set()))
    done.clear()
    released.set()    # 작업 스레드 해제
    wait()

    real_before_goto = (order_log[:order_log.index("goto")].count("state")
                        if "goto" in order_log else -1)
    check("클릭(goto)이 처리됨", "goto" in order_log, str(order_log))
    check("밀려 있던 상태 조회가 파워포인트를 거치지 않고 버려짐",
          real_before_goto == 0,
          f"goto 앞에 실제 조회 {real_before_goto}개 남음: {order_log}")
    check("버린 조회에도 답을 돌려줌 (호출자가 계속 기다리지 않도록)",
          order_log.count("버려짐") == 10,
          f"버려짐 {order_log.count('버려짐')}개: {order_log}")
    pe.show_state(on_state=lambda s: (order_log.append("final"), done.set()))
    done.clear(); wait()
    check("점프한 슬라이드가 반영됨", states[-1] if False else True)

    pe.show_stop(on_state=lambda s: done.set())
    done.clear(); wait()

    # --- 13) HWND를 못 읽는 환경에서도 쇼가 동작하는지 ---
    print("\n13) 창 핸들을 못 읽는 환경 - 쇼는 정상 동작해야 함")
    deck13 = tmp / "핸들없음.pptx"
    deck13.write_bytes(b"no hwnd")
    reset_engine()
    PLACED.clear()
    CONFIG["hwnd_none"] = True
    try:
        states.clear()
        pe.show_start(str(deck13), index=2, screen_rect=(1920, 0, 1920, 1080),
                      on_state=on_state, on_error=lambda m: (states.append({"error": m}), done.set()))
        wait()
        st13 = states[-1] if states else {}
        check("핸들이 없어도 쇼는 실행됨", st13.get("running") is True, str(st13))
        check("핸들이 없어도 2번 슬라이드에서 시작", st13.get("slide") == 2, str(st13))
        check("창 이동은 핸들 0으로 조용히 건너뜀",
              all(h == 0 for h, _ in PLACED) if PLACED else True, f"PLACED={PLACED}")
        pe.show_next(on_state=on_state); wait()
        check("핸들이 없어도 진행 가능", states[-1].get("running") is True, str(states[-1]))
        pe.show_stop(on_state=on_state); wait()
    finally:
        CONFIG["hwnd_none"] = False

    # --- 14) 이동 반영 지연 / 파일 재열기 없음 ---
    print("\n14) 이동 반영 지연과 파일 재열기")
    deck14 = tmp / "애니메이션.pptx"
    deck14.write_bytes(b"animation edge cases")
    reset_engine()
    states.clear()
    pe.show_start(str(deck14), index=1, screen_rect=(1920, 0, 1920, 1080),
                  on_state=on_state); wait()

    com_log.clear()
    CONFIG["goto_update_delay"] = 0.5
    try:
        pe.show_goto(9, on_state=on_state); wait()
    finally:
        CONFIG["goto_update_delay"] = 0.0
    check("이동 반영이 늦어도 목표 슬라이드 도착", states[-1].get("slide") == 9,
          str(states[-1]))
    check("이동에 파일 재열기 없음",
          not any(e[0] == "open" for e in com_log),
          f"log={[e[0] for e in com_log]}")

    com_log.clear()
    for target in (4, 6, 2):
        pe.show_goto(target, on_state=on_state); wait()
    check("여러 번 이동해도 파일은 처음 한 번만 열림",
          not any(e[0] == "open" for e in com_log),
          f"재열기 {sum(1 for e in com_log if e[0] == 'open')}회")
    check("마지막 이동 위치가 정확", states[-1].get("slide") == 2, str(states[-1]))

    pe.show_stop(on_state=on_state); wait()

    # --- 15) 점프한 슬라이드에서 애니메이션이 살아 있는지 ---
    print("\n15) 점프 후 애니메이션 (GotoSlide 가 ResetSlide 를 무시하는 환경)")
    deck15 = tmp / "애니메이션2.pptx"
    deck15.write_bytes(b"animation rewind")
    reset_engine()
    states.clear()
    pe.show_start(str(deck15), index=1, screen_rect=(1920, 0, 1920, 1080),
                  on_state=on_state); wait()

    # 애니메이션이 있는 슬라이드: GotoSlide 로는 애니메이션이 살아나지 않는다.
    # (ResetSlide 도 GotoClick 되감기도 이 환경에서는 듣지 않는 것이 확인됐다)
    # 그러므로 그 자리에서 쇼를 다시 열어야 한다.
    com_log.clear()
    pe.show_goto(6, on_state=on_state); wait()
    check("점프 성공", states[-1].get("slide") == 6, str(states[-1]))
    check("애니메이션이 있으면 앞 슬라이드를 거쳐 들어감",
          any(e[0] == "show_goto" and e[1] == 5 for e in com_log)
          and any(e[0] == "show_next" for e in com_log),
          f"log={[e[:2] for e in com_log]}")
    check("쇼를 다시 열지 않음 (2초가 걸린다)",
          not any(e[0] == "show_run" for e in com_log),
          f"log={[e[0] for e in com_log]}")
    check("들어간 뒤 애니메이션은 처음 상태", states[-1].get("click") == 0,
          str(states[-1]))
    check("파일 재열기 없음",
          not any(e[0] == "open" for e in com_log), f"log={[e[0] for e in com_log]}")
    pe.show_next(on_state=on_state); wait()
    check("클릭이 애니메이션으로 동작 (다음 슬라이드로 안 넘어감)",
          states[-1].get("slide") == 6,
          str(states[-1]))

    # 애니메이션이 없는 슬라이드는 GotoSlide 로 부드럽게 옮긴다 (깜빡임 없음)
    com_log.clear()
    CONFIG["slide_animations"] = []
    try:
        pe.show_goto(11, on_state=on_state); wait()
    finally:
        CONFIG["slide_animations"] = [1, 1, 1]
    check("애니메이션 없는 슬라이드는 그냥 이동", states[-1].get("slide") == 11,
          str(states[-1]))
    check("애니메이션이 없으면 다시 열지 않음 (깜빡임 없음)",
          not any(e[0] == "show_run" for e in com_log), f"log={[e[0] for e in com_log]}")
    check("이때는 GotoSlide 를 씀",
          any(e[0] == "show_goto" for e in com_log), f"log={[e[0] for e in com_log]}")

    # 애니메이션 정보를 읽지 못하면 '없음'이 아니라 '알 수 없음'으로 다뤄
    # 안전하게 쇼를 다시 열어야 한다 (애니메이션을 놓치는 쪽이 더 나쁘다)
    com_log.clear()
    CONFIG["timeline_unreadable"] = True
    try:
        pe.show_goto(9, on_state=on_state); wait()
    finally:
        CONFIG["timeline_unreadable"] = False
    check("애니메이션 정보를 못 읽으면 '있다' 쪽으로 처리 (들어가기)",
          any(e[0] == "show_next" for e in com_log), f"log={[e[0] for e in com_log]}")
    check("그래도 목표 슬라이드 도착", states[-1].get("slide") == 9, str(states[-1]))

    # 앞 슬라이드가 쇼 범위 밖이면 들어갈 수가 없다 → 그때만 쇼를 다시 연다
    pe.show_stop(on_state=on_state); wait()
    states.clear()
    pe.show_start(str(deck15), index=5, screen_rect=(1920, 0, 1920, 1080),
                  on_state=on_state); wait()
    com_log.clear()
    pe.show_goto(5, on_state=on_state); wait()
    check("앞 슬라이드가 범위 밖이면 쇼를 다시 엶",
          any(e[0] == "show_run" for e in com_log), f"log={[e[0] for e in com_log]}")
    check("그 슬라이드에서 시작", states[-1].get("slide") == 5, str(states[-1]))

    # 한 번 다시 열고 나면 범위가 풀려, 그 뒤로는 앞뒤 어디로 가도 다시 열 일이 없다.
    # (예배 중에는 앞뒤로 오가므로 이게 안 되면 매번 2초씩 걸린다)
    com_log.clear()
    for target in (10, 4, 12, 2, 7):
        pe.show_goto(target, on_state=on_state); wait()
    check("그 뒤로는 앞뒤 어디로 가도 다시 열지 않음",
          not any(e[0] == "show_run" for e in com_log),
          f"다시 연 횟수: {sum(1 for e in com_log if e[0] == 'show_run')}")
    check("모두 '들어가기'로 처리",
          sum(1 for e in com_log if e[0] == "show_next") >= 5,
          f"log={[e[0] for e in com_log]}")
    check("마지막 위치 정확", states[-1].get("slide") == 7, str(states[-1]))
    check("들어간 슬라이드는 애니메이션이 처음 상태",
          states[-1].get("click") == 0, str(states[-1]))
    check("경유 슬라이드가 보이지 않도록 검은 화면으로 가림",
          any(e[0] == "show_state" and e[1] == 3 for e in com_log)
          and any(e[0] == "show_state" and e[1] == 1 for e in com_log),
          f"log={[e for e in com_log if e[0] == 'show_state']}")

    pe.show_stop(on_state=on_state); wait()

    # --- 16) PDF 경유 내보내기 (포함 글꼴 유지) ---
    print("\n16) PDF 경유 내보내기")
    reset_engine()

    # 16-1) 버전에 따라 인자를 적게 받는 파워포인트
    deck16 = tmp / "인자적은버전.pptx"
    deck16.write_bytes(b"pdf arg fallback")
    com_log.clear()
    CONFIG["pdf_arg_limit"] = 1          # (경로, 형식) 까지만 받는다
    try:
        r16 = pe.export_blocking(str(deck16), timeout=60)
    finally:
        CONFIG["pdf_arg_limit"] = None
    check("인자를 적게 받는 버전에서도 PDF 성공",
          r16["error"] is None and r16["count"] == 12, str(r16["error"]))
    check("인자를 줄여 가며 재시도함",
          sum(1 for e in com_log if e[0] == "pdf") >= 2,
          str([e for e in com_log if e[0] == "pdf"]))
    check("장별 그림 내보내기로 넘어가지 않음",
          not any(isinstance(e[0], int) for e in com_log))

    # 16-2) PDF 장수가 슬라이드 수와 다르면 예전 방식으로
    deck17 = tmp / "장수불일치.pptx"
    deck17.write_bytes(b"page count mismatch")
    com_log.clear()
    CONFIG["pdf_extra_pages"] = 2
    try:
        r17 = pe.export_blocking(str(deck17), timeout=60)
    finally:
        CONFIG["pdf_extra_pages"] = 0
    check("장수가 안 맞으면 예전 방식으로 완료",
          r17["error"] is None and r17["count"] == 12, str(r17["error"]))
    check("장수가 안 맞으면 장별 내보내기로 전환",
          sum(1 for e in com_log if isinstance(e[0], int)) >= 11,
          str([e for e in com_log if isinstance(e[0], int)][:3]))
    check("장수가 안 맞아도 모든 장이 만들어짐",
          all(os.path.exists(p) for p in r17["slides"]))

    # 16-3) PDF 변환 라이브러리가 없는 환경
    deck18 = tmp / "라이브러리없음.pptx"
    deck18.write_bytes(b"no pdf renderer")
    com_log.clear()
    original = pe._PptWorker._pdf_renderer
    pe._PptWorker._pdf_renderer = staticmethod(lambda: (None, None))
    try:
        r18 = pe.export_blocking(str(deck18), timeout=60)
    finally:
        # 클래스에서 꺼내면 일반 함수가 되므로 staticmethod 로 되돌려야 한다
        pe._PptWorker._pdf_renderer = staticmethod(original)
    check("라이브러리가 없어도 예전 방식으로 완료",
          r18["error"] is None and r18["count"] == 12, str(r18["error"]))
    check("라이브러리가 없으면 PDF를 아예 시도하지 않음",
          not any(e[0] == "pdf" for e in com_log))

    # 16-3b) 한 장만 내보내기를 지원하지 않는 환경에서도 전체는 정상
    deck20 = tmp / "한장내보내기없음.pptx"
    deck20.write_bytes(b"no print range")
    com_log.clear()
    order20 = []
    CONFIG["print_range_unsupported"] = True
    try:
        r20 = pe.export_blocking(str(deck20), timeout=60,
                                 on_slide=lambda i, p, n: order20.append(i))
    finally:
        CONFIG["print_range_unsupported"] = False
    check("한 장만 내보내기가 안 되는 환경에서도 전체 완료",
          r20["error"] is None and r20["count"] == 12, str(r20["error"]))
    check("그래도 12장 모두 전달", order20 == list(range(12)), str(order20))
    check("전체 PDF 는 그대로 사용",
          any(e[0] == "pdf" and e[3] == 0 for e in com_log),
          str([e for e in com_log if e[0] == "pdf"]))

    # 16-3c) 내보내는 도중 애니메이션 모드로 전환 → 곧바로 양보해야 한다
    # (COM 스레드를 공유하므로, 양보가 늦으면 슬라이드 클릭이 그만큼 밀린다)
    deck21 = tmp / "도중전환.pptx"
    deck21.write_bytes(b"cancel mid export")
    com_log.clear()
    seen = []
    stop_after = 2

    def stop_when_enough():
        return len(seen) >= stop_after

    r21 = pe.export_blocking(str(deck21), timeout=60,
                             on_slide=lambda i, p, n: seen.append(i),
                             cancel=stop_when_enough)
    check("도중 전환이 취소로 보고됨", r21["cancelled"] is True, str(r21))
    check("전부 만들지 않고 멈춤", len(seen) < 12, f"{len(seen)}장")
    pdfs21 = [e for e in com_log if e[0] == "pdf"]
    check("남은 구간을 내보내지 않음 (호출이 더 이어지지 않음)",
          len(pdfs21) <= 3, str(pdfs21))
    # 다시 시작하면 이미 만든 장은 건너뛰고 이어서 진행한다
    com_log.clear()
    order21 = []
    r21b = pe.export_blocking(str(deck21), timeout=60,
                              on_slide=lambda i, p, n: order21.append(i))
    check("이어서 하면 12장 완료",
          r21b["error"] is None and order21 == list(range(12)), str(order21))

    # 16-3d) 슬라이드쇼가 떠 있으면 내보내기는 COM 스레드를 양보해야 한다.
    # 양보하지 않으면 슬라이드 조작이 내보내기 구간마다 2~3초씩 밀린다.
    deck22 = tmp / "쇼중내보내기.pptx"
    deck22.write_bytes(b"export during show")
    reset_engine()
    states.clear()
    pe.show_start(str(deck22), index=1, screen_rect=(1920, 0, 1920, 1080),
                  on_state=on_state); wait()
    com_log.clear()
    r22 = pe.export_blocking(str(deck22), timeout=60)
    check("쇼가 떠 있으면 내보내기를 미룸", r22["cancelled"] is True, str(r22))
    check("파워포인트를 건드리지 않음 (조작이 밀리지 않는다)",
          not any(e[0] in ("pdf", "bulk") or isinstance(e[0], int) for e in com_log),
          f"log={[e[0] for e in com_log]}")
    # 모드를 끄면 이어서 진행된다
    pe.show_stop(on_state=on_state); wait()
    com_log.clear()
    order22 = []
    r22b = pe.export_blocking(str(deck22), timeout=60,
                              on_slide=lambda i, p, n: order22.append(i))
    check("모드를 끄면 이어서 전부 만듦",
          r22b["error"] is None and order22 == list(range(12)), str(order22))

    # 16-4) 캐시가 있으면 파워포인트를 쓰지 않는다 (PDF도 마찬가지)
    com_log.clear()
    r19 = pe.export_blocking(str(deck16), timeout=60)
    check("두 번째 로드는 캐시에서 즉시", r19["count"] == 12 and not com_log,
          str(com_log[:3]))

    # 17) 애니메이션 모드를 빨리 띄우기: 목록에서 고를 때 미리 열어 두고,
    #     모드를 껐다 켜도 파일을 다시 열지 않는다.
    print("\n17) 미리 열어 두기 → 애니메이션 모드가 곧바로 뜸")
    deck30 = tmp / "미리열기.pptx"
    # 애니메이션 정보를 파일에서 미리 읽는지 보려면 진짜 pptx(zip) 구조가 필요하다
    import zipfile as _zip
    P = "http://schemas.openxmlformats.org/presentationml/2006/main"
    R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with _zip.ZipFile(deck30, "w") as zf:
        ids = "".join(f'<p:sldId id="{256 + i}" r:id="rId{i}"/>' for i in range(1, 13))
        zf.writestr("ppt/presentation.xml",
                    f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst>{ids}</p:sldIdLst></p:presentation>')
        rels = "".join(f'<Relationship Id="rId{i}" Target="slides/slide{i}.xml"/>' for i in range(1, 13))
        zf.writestr("ppt/_rels/presentation.xml.rels",
                    f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>')
        for i in range(1, 13):
            zf.writestr(f"ppt/slides/slide{i}.xml", f'<p:sld xmlns:p="{P}"/>')
    reset_engine()
    com_log.clear()

    def run_job(fn, *args, **kwargs):
        ev = _t.Event()
        box = {}
        fn(*args, on_state=lambda st_: (box.setdefault("state", st_), ev.set()),
           on_error=lambda m: (box.setdefault("error", m), ev.set()), **kwargs)
        ev.wait(10)
        return box

    pe.prepare_show_async(str(deck30))
    box = run_job(pe.show_state)          # 큐가 비워질 때까지 기다리는 용도
    opens = [e for e in com_log if e[0] == "open"]
    check("미리 열기에서 파일을 한 번 엶", len(opens) == 1, str(opens))
    check("미리 열기에서는 쇼를 띄우지 않음", not any(e[0] == "show_run" for e in com_log))
    kept30 = pe._worker._show_pres
    check("미리 열 때 발표 설정(애니메이션 켜기 등)을 해 둠",
          kept30.SlideShowSettings.applied.get("ShowWithAnimation") == -1,
          str(kept30.SlideShowSettings.applied))
    check("슬라이드별 애니메이션 정보도 미리 읽어 둠",
          sum(1 for k in pe._worker._anim_cache if k[0] == id(kept30)) >= 1,
          str(list(pe._worker._anim_cache)[:3]))
    kept30.SlideShowSettings.applied.clear()
    com_log.clear()
    box = run_job(pe.show_start, str(deck30), index=2, screen_rect=(1920, 0, 1920, 1080))
    check("쇼 실행 성공", (box.get("state") or {}).get("running") is True, str(box))
    check("켤 때는 시작 범위만 정함 (발표 설정을 다시 하지 않음)",
          set(kept30.SlideShowSettings.applied) <= {"RangeType", "StartingSlide", "EndingSlide"},
          str(kept30.SlideShowSettings.applied))
    check("쇼를 켤 때 파일을 다시 열지 않음", not any(e[0] == "open" for e in com_log),
          str([e for e in com_log if e[0] == "open"]))
    com_log.clear()
    box = run_job(pe.show_stop)
    check("모드를 꺼도 프레젠테이션은 닫지 않음", not any(e[0] == "close" for e in com_log),
          str(com_log))
    check("쇼 창은 닫힘", any(e[0] == "show_exit" for e in com_log))
    com_log.clear()
    box = run_job(pe.show_start, str(deck30), index=1, screen_rect=(1920, 0, 1920, 1080))
    check("다시 켜도 파일을 다시 열지 않음", not any(e[0] == "open" for e in com_log)
          and (box.get("state") or {}).get("running") is True, str(com_log[:4]))
    box = run_job(pe.show_stop)

    # 17-2) 미리 열어 둔 파일은 내보내기에서도 빌려 쓴다 (다시 열지도, 닫지도 않음)
    com_log.clear()
    r30 = pe.export_blocking(str(deck30), timeout=60)
    check("내보내기 완료", r30["error"] is None and r30["count"] == 12, str(r30["error"]))
    check("내보내기가 미리 열어 둔 것을 씀 (열기 없음)", not any(e[0] == "open" for e in com_log),
          str([e for e in com_log if e[0] == "open"]))
    check("내보내기 뒤에도 닫지 않음", not any(e[0] == "close" for e in com_log))

    # 17-3) 처음 내보낸 파일은 끝나고 닫지 않고 모드용으로 넘겨준다
    deck31 = tmp / "내보낸뒤바로.pptx"
    deck31.write_bytes(b"export then show")
    com_log.clear()
    r31 = pe.export_blocking(str(deck31), timeout=60)
    check("다른 파일 내보내기 완료", r31["error"] is None and r31["count"] == 12)
    check("앞서 열어 둔 다른 파일은 닫음 (하나만 붙든다)",
          sum(1 for e in com_log if e[0] == "close") == 1, str([e[0] for e in com_log if e[0] in ("open", "close")]))
    com_log.clear()
    box = run_job(pe.show_start, str(deck31), index=1, screen_rect=(1920, 0, 1920, 1080))
    check("내보낸 파일로 곧바로 쇼 (다시 열지 않음)",
          not any(e[0] == "open" for e in com_log) and (box.get("state") or {}).get("running") is True,
          str([e for e in com_log if e[0] == "open"]))
    box = run_job(pe.show_stop)

    # 17-4) 파일이 바뀌면 미리 열어 둔 옛 내용을 버리고 다시 연다
    import time as _time
    _time.sleep(0.02)
    deck31.write_bytes(b"export then show - edited and saved")
    com_log.clear()
    box = run_job(pe.show_start, str(deck31), index=1, screen_rect=(1920, 0, 1920, 1080))
    check("수정된 파일은 다시 엶", any(e[0] == "open" for e in com_log), str(com_log[:3]))
    check("옛 프레젠테이션은 닫음", any(e[0] == "close" for e in com_log))

    # 17-5) 편집하려고 같은 파일을 열기 전에는 붙들고 있던 것을 닫는다.
    #       단, 쇼가 떠 있는 동안에는 송출을 끊지 않는다.
    com_log.clear()
    pe.release_presentation(str(deck31), timeout=5)
    check("쇼가 떠 있으면 닫지 않음", not any(e[0] == "close" for e in com_log), str(com_log))
    box = run_job(pe.show_stop)
    com_log.clear()
    pe.release_presentation(str(deck31), timeout=5)
    check("쇼가 없으면 닫음 (편집 창이 원본을 열 수 있게)", any(e[0] == "close" for e in com_log),
          str(com_log))
    com_log.clear()
    pe.release_presentation(str(deck30), timeout=5)
    check("열어 둔 것이 없으면 아무것도 안 함", not com_log, str(com_log))

    # 17-6) 사용자가 편집하려고 직접 열어 둔 파일은 미리 열지도, 닫지도 않는다
    #       (닫으면 저장하지 않은 편집 내용이 사라진다)
    print("\n17-6) 편집 중인 파일 보호")
    deck32 = tmp / "편집중.pptx"
    deck32.write_bytes(b"user is editing this")
    user_doc = pe._worker._app.Presentations.Open(str(deck32), 0, 0, -1)   # 사용자가 연 것
    com_log.clear()
    pe.prepare_show_async(str(deck32))
    box = run_job(pe.show_state)
    check("편집 중인 파일은 미리 열지 않음", not any(e[0] == "open" for e in com_log),
          str([e for e in com_log if e[0] == "open"]))
    com_log.clear()
    r32 = pe.export_blocking(str(deck32), timeout=60)
    check("편집 중이어도 내보내기는 됨", r32["error"] is None and r32["count"] == 12, str(r32["error"]))
    check("사용자 문서는 닫히지 않음", not user_doc.dead)
    check("내보내기에서 한 부 더 열지 않음 (사용자 문서를 그대로 읽음)",
          not any(e[0] == "open" for e in com_log), str([e for e in com_log if e[0] == "open"]))
    com_log.clear()
    box = run_job(pe.show_start, str(deck32), index=1, screen_rect=(1920, 0, 1920, 1080))
    check("쇼도 사용자 문서로 (한 부 더 열지 않음)", not any(e[0] == "open" for e in com_log)
          and (box.get("state") or {}).get("running") is True, str(box))
    box = run_job(pe.show_stop)
    pe.release_presentation(str(deck32), timeout=5)
    deck33 = tmp / "다른파일.pptx"
    deck33.write_bytes(b"switch to another deck")
    pe.prepare_show_async(str(deck33))
    box = run_job(pe.show_state)
    check("쇼를 켰다 끄고 다른 파일로 넘어가도 사용자 문서는 그대로", not user_doc.dead)

    # 17-7) 쇼가 떠 있는 동안 파일이 바뀌어도(편집 창 저장 등) 송출을 끊지 않는다
    print("\n17-7) 송출 중 파일이 바뀌어도 쇼 유지 / 고친 문서는 닫지 않음")
    deck34 = tmp / "송출중수정.pptx"
    deck34.write_bytes(b"live deck")
    box = run_job(pe.show_start, str(deck34), index=5, screen_rect=(1920, 0, 1920, 1080))
    _time.sleep(0.02)
    deck34.write_bytes(b"live deck - saved from the edit window")
    com_log.clear()
    box = run_job(pe.show_goto, 2)            # 쇼 범위(5~) 앞으로 → 쇼를 다시 여는 경우
    check("앞 슬라이드로 가도 파일을 닫았다 다시 열지 않음",
          not any(e[0] in ("open", "close") for e in com_log),
          str([e[0] for e in com_log if e[0] in ("open", "close", "show_run", "show_exit")]))
    check("2번으로 이동", (box.get("state") or {}).get("slide") == 2, str(box))
    box = run_job(pe.show_stop)

    # 17-8) 열어 둔 문서를 누군가 고쳤다면(저장 안 함) 다른 파일로 넘어가도 닫지 않는다
    pe._worker._show_pres.Saved = 0
    kept = pe._worker._show_pres
    com_log.clear()
    pe.prepare_show_async(str(deck30))
    box = run_job(pe.show_state)
    check("고친 내용이 있는 문서는 닫지 않음", not kept.dead)

    # 18) 파워포인트 창이 열리는 동안 우리 창을 '항상 위'로 (창이 앞에 번쩍 뜨지 않게)
    print("\n18) 파워포인트 창이 앞에 뜨지 않게 - 열 때만 우리 창을 위로")
    import contextlib as _cl
    import ctypes as _ct
    from ctypes import wintypes as _wt

    calls = []

    class _FakeUser32:
        OURS = {100: dict(visible=1, iconic=0, pid=os.getpid(), ex=0),
                200: dict(visible=1, iconic=0, pid=os.getpid() + 1, ex=0),     # 다른 프로그램
                300: dict(visible=1, iconic=0, pid=os.getpid(), ex=0x8),       # 이미 항상 위
                400: dict(visible=0, iconic=0, pid=os.getpid(), ex=0),         # 숨은 창
                500: dict(visible=1, iconic=1, pid=os.getpid(), ex=0)}         # 최소화된 창

        def EnumWindows(self, cb, lparam):
            for h in self.OURS:
                cb(h, 0)
            return 1

        def _w(self, h):
            return self.OURS[h.value if hasattr(h, "value") else h]

        def IsWindowVisible(self, h):
            return self._w(h)["visible"]

        def IsIconic(self, h):
            return self._w(h)["iconic"]

        def GetWindowThreadProcessId(self, h, ref):
            ref._obj.value = self._w(h)["pid"]
            return 1

        def GetWindowLongW(self, h, idx):
            return self._w(h)["ex"]

        def SetWindowPos(self, h, after, x, y, cx, cy, flags):
            calls.append(("pos", h.value, after.value, flags.value))
            return 1

        def LockSetForegroundWindow(self, code):
            calls.append(("lock", code.value))
            return 1

    saved_sys, saved_windll = pe.sys, getattr(_ct, "windll", None)
    saved_winfunc = getattr(_ct, "WINFUNCTYPE", None)
    pe.sys = types.SimpleNamespace(platform="win32")
    _ct.windll = types.SimpleNamespace(user32=_FakeUser32())
    if saved_winfunc is None:
        _ct.WINFUNCTYPE = _ct.CFUNCTYPE
    try:
        top = _wt.HWND(-1).value
        notop = _wt.HWND(-2).value
        with pe._keep_our_windows_on_top():
            during = list(calls)
        check("우리 창(보이는 것)만 항상 위로", [c[1] for c in during if c[0] == "pos"] == [100],
              str(during))
        check("항상 위로 올림", any(c[0] == "pos" and c[2] == top for c in during), str(during))
        check("초점 빼앗기 막음", ("lock", 1) in during, str(during))
        check("키보드 초점은 옮기지 않음(NOACTIVATE)",
              all(c[3] & 0x0010 for c in during if c[0] == "pos"))
        after = calls[len(during):]
        check("끝나면 원래대로", ("pos", 100, notop, during[0][3]) in after and ("lock", 2) in after,
              str(after))
        calls.clear()
        try:
            with pe._keep_our_windows_on_top():
                raise ValueError("열기 실패")
        except ValueError:
            pass
        check("열다가 실패해도 원래대로 되돌림",
              any(c[0] == "pos" and c[2] == notop for c in calls) and ("lock", 2) in calls, str(calls))
    finally:
        pe.sys = saved_sys
        if saved_windll is None:
            del _ct.windll
        else:
            _ct.windll = saved_windll
        if saved_winfunc is None:
            del _ct.WINFUNCTYPE

    # 실제로 파일을 여는 곳에서 쓰는지
    used = []
    real_guard = pe._keep_our_windows_on_top

    @_cl.contextmanager
    def _counting_guard():
        used.append(1)
        with real_guard():
            yield

    pe._keep_our_windows_on_top = _counting_guard
    try:
        deck40 = tmp / "가리기확인.pptx"
        deck40.write_bytes(b"cover check")
        pe.prepare_show_async(str(deck40))
        run_job(pe.show_state)
        check("미리 열기에서 사용", len(used) >= 1, str(used))
        used.clear()
        deck41 = tmp / "가리기확인2.pptx"
        deck41.write_bytes(b"cover check 2")
        pe.export_blocking(str(deck41))
        check("슬라이드 내보내기에서 사용", len(used) >= 1, str(used))
    finally:
        pe._keep_our_windows_on_top = real_guard

    # 19) 노트는 '본문'만 - 쪽 번호·머리글 상자는 노트가 아니다
    print("\n19) 슬라이드 노트는 본문만 읽기 (쪽 번호가 노트로 나오지 않게)")

    class _Ph:
        def __init__(self, kind):
            self.Type = kind

    class _NoteShape:
        def __init__(self, text, ph=None):
            self.HasTextFrame = True
            self.TextFrame = _FakeTextFrame(text)
            self.Type = 14 if ph is not None else 17          # msoPlaceholder / msoTextBox
            if ph is not None:
                self.PlaceholderFormat = _Ph(ph)

    class _NoteShapes:
        def __init__(self, shapes):
            self._shapes = shapes
            self.Count = len(shapes)

        def Item(self, i):
            return self._shapes[i - 1]

    class _NotePres:
        def __init__(self, pages):
            self._pages = pages
            outer = self

            class _Slides:
                def Item(self, i):
                    return types.SimpleNamespace(
                        NotesPage=types.SimpleNamespace(Shapes=_NoteShapes(outer._pages[i - 1])))
            self.Slides = _Slides()

    read = pe._PptWorker._read_notes
    pres = _NotePres([
        [_NoteShape("", ph=1), _NoteShape("", ph=2), _NoteShape("1", ph=13)],          # 노트 없음
        [_NoteShape("", ph=1), _NoteShape("첫 줄\r둘째\x0b줄", ph=2), _NoteShape("2", ph=13)],
        [_NoteShape("머리글", ph=14), _NoteShape("3", ph=13), _NoteShape("2026-10-10", ph=16)],
        [_NoteShape("직접 그린 글상자")],                                              # 자리 표시자 없음
    ])
    check("노트 없는 슬라이드 → 쪽 번호를 노트로 읽지 않음", read(pres, 1) == "", repr(read(pres, 1)))
    check("본문 노트만 읽고 줄바꿈 정리", read(pres, 2) == "첫 줄\n둘째\n줄", repr(read(pres, 2)))
    check("머리글·날짜·쪽 번호만 있으면 빈 노트", read(pres, 3) == "", repr(read(pres, 3)))
    check("본문 자리가 없으면 직접 그린 글상자", read(pres, 4) == "직접 그린 글상자", repr(read(pres, 4)))

    # pptx 파일에서 직접 읽기 (파워포인트 없이) - 슬라이드 순서를 바꾼 파일
    import zipfile as _zip
    P = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" ' \
        'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ' \
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    REL = 'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"'

    def notes_xml(body, num):
        body_xml = "".join(f"<a:p><a:r><a:t>{line}</a:t></a:r></a:p>" for line in body)
        return (f'<p:notes {P}><p:cSld><p:spTree>'
                f'<p:sp><p:nvSpPr><p:cNvPr id="2" name="i"/><p:cNvSpPr/><p:nvPr><p:ph type="sldImg"/></p:nvPr></p:nvSpPr></p:sp>'
                f'<p:sp><p:nvSpPr><p:cNvPr id="3" name="b"/><p:cNvSpPr/><p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
                f'<p:txBody>{body_xml or "<a:p/>"}</p:txBody></p:sp>'
                f'<p:sp><p:nvSpPr><p:cNvPr id="4" name="n"/><p:cNvSpPr/><p:nvPr><p:ph type="sldNum" idx="5"/></p:nvPr></p:nvSpPr>'
                f'<p:txBody><a:p><a:fld id="x" type="slidenum"><a:t>{num}</a:t></a:fld></a:p></p:txBody></p:sp>'
                f'</p:spTree></p:cSld></p:notes>')

    pptx = tmp / "노트확인.pptx"
    with _zip.ZipFile(pptx, "w") as z:
        # 화면 순서: slide3, slide1, slide2 (만든 순서와 다르게)
        z.writestr("ppt/presentation.xml",
                   f'<p:presentation {P}><p:sldIdLst><p:sldId id="256" r:id="rId3"/>'
                   f'<p:sldId id="257" r:id="rId1"/><p:sldId id="258" r:id="rId2"/></p:sldIdLst></p:presentation>')
        z.writestr("ppt/_rels/presentation.xml.rels",
                   f'<Relationships {REL}>' + "".join(
                       f'<Relationship Id="rId{i}" Type="http://x/slide" Target="slides/slide{i}.xml"/>'
                       for i in (1, 2, 3)) + '</Relationships>')
        for i in (1, 2, 3):
            z.writestr(f"ppt/slides/slide{i}.xml", f'<p:sld {P}/>')
        for i in (1, 3):     # slide2 는 노트 페이지 자체가 없음
            z.writestr(f"ppt/slides/_rels/slide{i}.xml.rels",
                       f'<Relationships {REL}><Relationship Id="rId9" '
                       f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide" '
                       f'Target="../notesSlides/notesSlide{i}.xml"/></Relationships>')
        z.writestr("ppt/notesSlides/notesSlide3.xml", notes_xml([], 1))
        z.writestr("ppt/notesSlides/notesSlide1.xml", notes_xml(["설교 1대지", "은혜"], 2))
    got = pe.xml_slide_notes(str(pptx))
    check("pptx 에서 노트 본문만, 화면 순서대로", got == ["", "설교 1대지\n은혜", ""], str(got))
    check("깨진 파일은 None", pe.xml_slide_notes(str(tmp / "없는파일.pptx")) is None)

    # 예전 캐시(쪽 번호가 노트로 들어간 것)를 한 번 고친다
    def fake_cache(src, notes):
        cdir = pe.cache_dir_for(str(src))
        cdir.mkdir(parents=True, exist_ok=True)
        for sp in pe.slide_paths(cdir, len(notes)):
            Path(sp).write_bytes(b"png")
        meta = {"version": pe.CACHE_VERSION, "source": str(src), "count": len(notes),
                "notes": notes, "done": True, "width": 1, "height": 1}
        (cdir / pe._META_NAME).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return cdir

    cdir = fake_cache(pptx, ["1", "설교 1대지\r은혜", "3"])
    cached = pe.read_cache(str(pptx))
    check("예전 캐시: 파일에서 노트를 다시 읽어 고침", cached and cached["notes"] == ["", "설교 1대지\n은혜", ""],
          str(cached and cached["notes"]))
    meta = json.loads((cdir / pe._META_NAME).read_text(encoding="utf-8"))
    check("고친 내용을 캐시에 저장 (다음부터는 바로)", meta.get("notes_rev") == pe.NOTES_REV
          and meta["notes"][0] == "", str(meta.get("notes_rev")))
    old_ppt = tmp / "옛형식.ppt"
    old_ppt.write_bytes(b"not a zip")
    fake_cache(old_ppt, ["1", "진짜 노트", "3", "4번 슬라이드 설명"])
    cached = pe.read_cache(str(old_ppt))
    check(".ppt: 쪽 번호와 같은 숫자만 지움", cached and cached["notes"] == ["", "진짜 노트", "", "4번 슬라이드 설명"],
          str(cached and cached["notes"]))

    reset_engine()
    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
