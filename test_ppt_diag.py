# -*- coding: utf-8 -*-
"""
파워포인트 COM 진단 - 원인을 세 갈래로 가른다.

사용법:
    python test_ppt_diag.py "C:\\경로\\문제파일.pptx"

판별 방법
  1) Presentations.Add()  - 파일을 전혀 건드리지 않고 빈 프레젠테이션 생성
       실패하면 → 파워포인트 자동화 자체가 막힌 것 (정품 인증/첫 실행/추가 기능)
  2) 프로젝트의 sample_test.pptx 열기 - 작고 단순한 파일
       성공하고 문제 파일만 실패하면 → 그 파일 고유의 문제
  3) 둘 다 실패하면 → 파일 열기 경로 전반의 문제

출력 전체를 그대로 복사해 보내 주세요.
"""
import os
import shutil
import sys
import tempfile
import traceback

RESULTS = []
VERDICT = {}


def step(label, fn, fatal=False, quiet_ok=False):
    """한 단계를 실행하고 성공/실패를 기록. 성공 시 반환값을 돌려준다."""
    try:
        value = fn()
        shown = f"  → {value!r}" if _short(value) else ""
        if not quiet_ok:
            print(f"  [성공] {label}{shown}")
        RESULTS.append((label, True, ""))
        return value
    except Exception as e:
        detail = f"{type(e).__name__}: {e}"
        print(f"  [실패] {label}\n         {detail}")
        RESULTS.append((label, False, detail))
        if fatal:
            print("\n이 단계가 실패하면 더 진행할 수 없습니다.")
            _summary()
            sys.exit(1)
        return None


def _short(value):
    return isinstance(value, (str, int, float, bool)) and len(str(value)) < 70


def _summary():
    print("\n" + "=" * 70)
    print("요약")
    print("=" * 70)
    for label, ok, detail in RESULTS:
        print(f"  {'O' if ok else 'X'}  {label}")
        if detail:
            print(f"        {detail}")
    print(f"\n  성공 {sum(1 for r in RESULTS if r[1])} / 전체 {len(RESULTS)}")


def _verdict():
    print("\n" + "=" * 70)
    print("판정")
    print("=" * 70)
    add_ok = VERDICT.get("add")
    sample_ok = VERDICT.get("sample")
    target_ok = VERDICT.get("target")

    if target_ok:
        print("  문제 파일이 열렸습니다. 아래 '동작한 방법'을 알려 주세요.")
    elif add_ok is False:
        print("  ▶ 파워포인트 자동화 자체가 막혀 있습니다.")
        print("    빈 프레젠테이션조차 만들지 못했습니다 (파일과 무관).")
        print("    확인할 것:")
        print("      • 파워포인트를 직접 실행했을 때 '정품 인증 필요' 같은 배너가 있는지")
        print("      • 파워포인트를 한 번도 대화형으로 실행하지 않았다면 실행해 초기 설정을 마칠 것")
        print("      • [파일]-[옵션]-[추가 기능]의 COM 추가 기능을 모두 끄고 다시 시도")
        print("      • Office 온라인 복구: 설정-앱-Microsoft 365-수정-온라인 복구")
    elif sample_ok and target_ok is False:
        print("  ▶ 그 파일에만 있는 문제입니다.")
        print("    단순한 파일(sample_test.pptx)은 열렸지만 문제 파일은 열리지 않았습니다.")
        print("    확인할 것:")
        print("      • 파워포인트에서 그 파일을 직접 열 때 복구/링크 업데이트 같은 창이 뜨는지")
        print("      • 파워포인트에서 열어 [다른 이름으로 저장]으로 새 .pptx로 저장한 뒤 그 파일로 시도")
        print("      • 파일이 암호로 보호되어 있거나 편집 제한(IRM)이 걸려 있는지")
    elif sample_ok is False and add_ok:
        print("  ▶ 파일 열기 경로 전반의 문제입니다.")
        print("    빈 프레젠테이션은 만들 수 있는데 어떤 파일도 열 수 없습니다.")
        print("    확인할 것:")
        print("      • 파워포인트 [파일]-[옵션]-[보안 센터]-[보안 센터 설정]-[보호된 보기]에서")
        print("        세 가지 체크를 모두 해제한 뒤 다시 시도")
        print("      • COM 추가 기능 모두 끄기")
    else:
        print("  판정할 만큼 정보가 모이지 않았습니다. 위 요약을 보내 주세요.")


def main(path):
    here = os.path.dirname(os.path.abspath(__file__))

    print("=" * 70)
    print("파워포인트 COM 진단")
    print("=" * 70)
    print(f"문제 파일: {path}")
    print(f"크기: {os.path.getsize(path):,} bytes")
    print(f"윈도우: {sys.getwindowsversion() if os.name == 'nt' else 'N/A'}")
    print(f"파이썬: {sys.version.split()[0]} ({'64bit' if sys.maxsize > 2**32 else '32bit'})")

    zone = path + ":Zone.Identifier"
    try:
        with open(zone, "r", encoding="utf-8", errors="ignore") as f:
            print(f"인터넷 파일 표식: 있음 → {f.read().strip().replace(chr(10), ' ')}")
    except OSError:
        print("인터넷 파일 표식(Zone.Identifier): 없음")

    print("\n--- 1. pywin32 / COM ---")
    step("pythoncom import", lambda: __import__("pythoncom").__file__, fatal=True)
    step("win32com.client import",
         lambda: __import__("win32com.client", fromlist=["client"]).__name__, fatal=True)
    import pythoncom
    import win32com.client
    step("CoInitialize", lambda: pythoncom.CoInitialize() or "ok", fatal=True)

    print("\n--- 2. 파워포인트 연결 ---")
    app = step("실행 중인 파워포인트에 연결 (GetActiveObject)",
               lambda: win32com.client.GetActiveObject("PowerPoint.Application"))
    already_running = app is not None
    if app is None:
        app = step("파워포인트 새로 실행 (Dispatch)",
                   lambda: win32com.client.Dispatch("PowerPoint.Application"), fatal=True)
    print(f"  (원래 실행 중이었나: {already_running})")
    step("버전", lambda: str(app.Version))
    step("빌드", lambda: str(app.Build))
    step("DisplayAlerts = 1", lambda: setattr(app, "DisplayAlerts", 1) or "ok")
    step("Visible 값 (설정 전)", lambda: str(app.Visible))

    print("\n--- 3. 추가 기능 목록 (문서 열기를 방해할 수 있음) ---")
    def _com_addins():
        items = []
        for i in range(1, int(app.COMAddIns.Count) + 1):
            a = app.COMAddIns.Item(i)
            items.append(f"{a.Description}({'켜짐' if a.Connect else '꺼짐'})")
        return "; ".join(items) if items else "없음"
    got = step("COM 추가 기능", _com_addins)
    if got and not _short(got):
        print(f"         {got}")

    def _addins():
        items = []
        for i in range(1, int(app.AddIns.Count) + 1):
            a = app.AddIns.Item(i)
            items.append(f"{a.Name}({'켜짐' if a.Loaded else '꺼짐'})")
        return "; ".join(items) if items else "없음"
    got = step("파워포인트 추가 기능", _addins)
    if got and not _short(got):
        print(f"         {got}")

    # ------------------------------------------------------------------
    print("\n--- 4. 판별 1: 파일 없이 빈 프레젠테이션 만들기 ---")
    print("  (실패하면 파일과 무관하게 자동화 자체가 막힌 것입니다)")
    blank = step("Presentations.Add(0)  창 없이", lambda: app.Presentations.Add(0))
    if blank is None:
        blank = step("Presentations.Add(-1) 창 표시", lambda: app.Presentations.Add(-1))
    if blank is None:
        blank = step("Presentations.Add()   기본", lambda: app.Presentations.Add())

    if blank is None:
        # Visible 을 켜고 다시
        print("\n  Visible=True 로 전환하고 재시도")
        step("Visible = -1 설정", lambda: setattr(app, "Visible", -1) or "ok")
        step("Visible 값 (설정 후)", lambda: str(app.Visible))
        step("창 최소화 (WindowState=2)", lambda: setattr(app, "WindowState", 2) or "ok")
        # 동적 디스패치에서는 속성이 메서드로 오기도 한다
        step("주 창 핸들 HWND",
             lambda: str(app.HWND() if callable(app.HWND) else app.HWND))
        blank = step("Visible 후 Presentations.Add(0)", lambda: app.Presentations.Add(0))
    else:
        step("Visible = -1 설정", lambda: setattr(app, "Visible", -1) or "ok")
        step("Visible 값 (설정 후)", lambda: str(app.Visible))
        step("창 최소화 (WindowState=2)", lambda: setattr(app, "WindowState", 2) or "ok")

    VERDICT["add"] = blank is not None
    if blank is not None:
        step("빈 프레젠테이션 슬라이드 추가", lambda: str(blank.Slides.Add(1, 12).SlideIndex))
        tmp_jpg = os.path.join(tempfile.gettempdir(), "bgtp_blank.jpg")
        step("빈 슬라이드 내보내기 Export",
             lambda: blank.Slides.Item(1).Export(tmp_jpg, "JPG", 1920, 1080) or _size(tmp_jpg))
        step("빈 프레젠테이션 닫기", lambda: blank.Close() or "ok")

    # ------------------------------------------------------------------
    combos = [
        ("읽기전용·창없음 (-1,0,0)", (-1, 0, 0)),
        ("읽기전용·창표시 (-1,0,-1)", (-1, 0, -1)),
        ("쓰기가능·창없음 (0,0,0)", (0, 0, 0)),
        ("옵션 없이 Open(path)", None),
    ]

    def try_open(target, title):
        print(f"\n--- {title} ---")
        print(f"  {target}")
        if not os.path.exists(target):
            print("  [건너뜀] 파일이 없습니다")
            return None, ""
        pres = None
        used = ""
        for label, args in combos:
            if pres is not None:
                break

            def _open(a=args, t=target):
                return app.Presentations.Open(t) if a is None else app.Presentations.Open(t, *a)

            pres = step(label, _open)
            if pres is not None:
                used = label
        return pres, used

    sample = os.path.join(here, "sample_test.pptx")
    sample_pres, sample_used = try_open(sample, "5. 판별 2: 단순한 파일(sample_test.pptx) 열기")
    VERDICT["sample"] = sample_pres is not None
    if sample_pres is not None:
        step("sample 슬라이드 수", lambda: int(sample_pres.Slides.Count))
        step("sample 닫기", lambda: sample_pres.Close() or "ok")

    target_pres, target_used = try_open(path, "6. 판별 3: 문제 파일 열기")

    # 임시 복사본으로도 시도
    temp_copy = ""
    if target_pres is None:
        tmp_dir = os.path.join(tempfile.gettempdir(), "BgTextPresenter_diag")
        os.makedirs(tmp_dir, exist_ok=True)
        temp_copy = os.path.join(tmp_dir, "diag" + os.path.splitext(path)[1])
        if step("임시 폴더로 복사", lambda: shutil.copyfile(path, temp_copy) and "ok"):
            target_pres = step("복사본 열기 (-1,0,0)",
                               lambda: app.Presentations.Open(temp_copy, -1, 0, 0))
            if target_pres is not None:
                target_used = "임시 복사본"
    VERDICT["target"] = target_pres is not None

    if target_pres is not None:
        print(f"\n  ==> 동작한 방법: {target_used}")
        print("\n--- 7. 문제 파일 정보 및 내보내기 ---")
        step("슬라이드 수", lambda: int(target_pres.Slides.Count))
        step("슬라이드 폭(pt)", lambda: float(target_pres.PageSetup.SlideWidth))
        step("슬라이드 높이(pt)", lambda: float(target_pres.PageSetup.SlideHeight))
        out = os.path.join(tempfile.gettempdir(), "bgtp_diag_one.jpg")
        step("1번 슬라이드 Export(1920x1080)",
             lambda: target_pres.Slides.Item(1).Export(out, "JPG", 1920, 1080) or _size(out))

        def _note():
            shapes = target_pres.Slides.Item(1).NotesPage.Shapes
            n = sum(1 for j in range(1, int(shapes.Count) + 1)
                    if shapes.Item(j).HasTextFrame and shapes.Item(j).TextFrame.HasText)
            return f"텍스트 있는 도형 {n}개"
        step("1번 슬라이드 노트 읽기", _note)
        step("닫기", lambda: target_pres.Close() or "ok")

    print("\n--- 8. 정리 ---")
    if not already_running:
        step("파워포인트 종료", lambda: app.Quit() or "ok")
    else:
        print("  (원래 실행 중이었으므로 종료하지 않습니다)")
    if temp_copy and os.path.exists(temp_copy):
        step("임시 복사본 삭제", lambda: os.remove(temp_copy) or "ok")

    _summary()
    _verdict()
    return 0


def _size(p):
    return f"{os.path.getsize(p):,} bytes" if os.path.exists(p) else "파일이 생성되지 않음"


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
    else:
        target_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_test.pptx")
    if not os.path.exists(target_path):
        print(f"파일이 없습니다: {target_path}")
        print('사용법: python test_ppt_diag.py "C:\\경로\\파일.pptx"')
        sys.exit(1)
    try:
        sys.exit(main(os.path.abspath(target_path)))
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        _summary()
        _verdict()
        sys.exit(1)
