"""슬라이드를 그림으로 내보낼 때 글꼴이 왜 달라지는지 찾는 진단 도구

같은 슬라이드를 여러 조건으로 내보내서 font_test 폴더에 모아 둔다.
어느 조건에서 글꼴이 원본대로 나오는지 눈으로 비교하면 원인이 바로 좁혀진다.

사용법:
    python test_ppt_font.py                     (폴더에서 pptx 자동 선택, 1번 슬라이드)
    python test_ppt_font.py "C:\\경로\\파일.pptx" 3
"""

import os
import sys
import glob
import time
import zipfile

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "font_test")

MSO_TRUE = -1
MSO_FALSE = 0
PP_WINDOW_MINIMIZED = 2
PP_WINDOW_NORMAL = 1

REPORT = os.path.join(OUT_DIR, "진단결과.txt")
_LINES = []


def log(message=""):
    """화면에도 보여 주고 파일로도 남긴다 (콘솔 글자가 깨져도 파일은 멀쩡하다)"""
    text = str(message)
    _LINES.append(text)
    try:
        print(text)
    except Exception:
        print(text.encode("ascii", "replace").decode("ascii"))


def save_report():
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
        with open(REPORT, "w", encoding="utf-8") as f:
            f.write("\n".join(_LINES) + "\n")
        print(f"\n진단 결과를 저장했습니다: {REPORT}")
    except Exception as e:
        print(f"결과 저장 실패: {e}")


def pick_file(argv):
    if len(argv) > 1 and argv[1].lower().endswith((".pptx", ".ppt", ".pptm")):
        return os.path.abspath(argv[1])
    here = os.path.dirname(os.path.abspath(__file__))
    found = sorted(glob.glob(os.path.join(here, "*.pptx")))
    if not found:
        log("이 폴더에 pptx 파일이 없습니다. 파일 경로를 인자로 넘겨 주세요.")
        print('예: python test_ppt_font.py "C:\\Users\\mihoon\\Desktop\\예배.pptx"')
        return ""
    return found[0]


def pick_index(argv):
    for a in argv[1:]:
        if a.isdigit():
            return int(a)
    return 1


# ----------------------------------------------------------------------
# 파일 자체 정보 (파워포인트 없이 읽는다)
# ----------------------------------------------------------------------
def inspect_file(path):
    log("\n[1] 파일 안을 들여다봅니다")
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
    except Exception as e:
        log(f"    (pptx 압축을 열지 못했습니다: {e})")
        return
    embedded = [n for n in names if n.startswith("ppt/fonts/")]
    if embedded:
        log(f"    글꼴 포함 저장: 예 ({len(embedded)}개)")
        log("    → 파워포인트 화면에는 제대로 보이지만 내보낼 때 다른 글꼴로")
        log("      바뀔 수 있는 대표적인 경우입니다.")
    else:
        log("    글꼴 포함 저장: 아니오")
        log("    → 이 컴퓨터에 설치된 글꼴로 그려집니다.")

    # 파일 안에서 실제로 지정된 글꼴 이름을 모두 긁어 온다 (파워포인트 없이)
    used = set()
    try:
        import re
        with zipfile.ZipFile(path) as z:
            for name in names:
                if not name.endswith(".xml"):
                    continue
                slide_like = (name.startswith("ppt/slides/slide")
                              or name.startswith("ppt/slideMasters/")
                              or name.startswith("ppt/slideLayouts/"))
                if not (slide_like or name.startswith("ppt/theme/")):
                    continue
                try:
                    xml = z.read(name).decode("utf-8", "ignore")
                except Exception:
                    continue
                if slide_like:
                    chunks = [xml]
                else:
                    # 테마는 제목/본문 글꼴만 본다. 뒤에 붙는 언어별 대체 글꼴
                    # 목록(<a:font script=...>)까지 세면 수십 개가 잡혀 의미가 없다.
                    chunks = re.findall(r"<a:(?:major|minor)Font>(.*?)</a:(?:major|minor)Font>",
                                        xml, re.S)
                    chunks = [re.split(r"<a:font\s", c)[0] for c in chunks]
                for chunk in chunks:
                    for m in re.findall(r'typeface="([^"]+)"', chunk):
                        if m and not m.startswith("+"):
                            used.add(m)
    except Exception as e:
        log(f"    (글꼴 이름을 읽지 못했습니다: {e})")

    if used:
        have = installed_fonts()
        log(f"\n    파일에 지정된 글꼴 {len(used)}개 (설치 여부)")
        missing = []
        for name in sorted(used):
            ok = font_installed(name, have)
            log(f"      - {name}   [{'설치됨' if ok else '설치 안 됨?'}]")
            if not ok:
                missing.append(name)
        if missing:
            log("\n    → 설치되지 않은 글꼴이 있습니다. 슬라이드쇼가 멀쩡하다면")
            log("      파일에 포함된 글꼴을 쓰고 있다는 뜻입니다.")


def slide_fonts(pres, index):
    """슬라이드에 실제로 쓰인 글꼴 이름"""
    names = []
    try:
        shapes = pres.Slides.Item(index).Shapes
        for i in range(1, int(shapes.Count) + 1):
            shape = shapes.Item(i)
            try:
                if not (shape.HasTextFrame and shape.TextFrame.HasText):
                    continue
                font = shape.TextFrame.TextRange.Font
                latin = str(font.Name)
                try:
                    east = str(font.NameFarEast)
                except Exception:
                    east = ""
                label = latin if not east or east == latin else f"{latin} / 한글:{east}"
                if label not in names:
                    names.append(label)
            except Exception:
                continue
    except Exception as e:
        return [f"(읽기 실패: {e})"]
    return names


_INSTALLED = None


def installed_fonts():
    """이 컴퓨터에 설치된 글꼴 이름 (레지스트리에 등록된 정식 이름)"""
    global _INSTALLED
    if _INSTALLED is not None:
        return _INSTALLED
    found = set()
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(root, key_path) as key:
                    count = winreg.QueryInfoKey(key)[1]
                    for i in range(count):
                        name = winreg.EnumValue(key, i)[0]
                        # "맑은 고딕 (TrueType)" → "맑은 고딕"
                        name = name.split(" (")[0]
                        for part in name.split("&"):
                            found.add(_norm(part))
            except Exception:
                pass
    except Exception:
        pass
    # 레지스트리를 못 읽으면 파일 이름으로라도 본다
    for folder in (os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
                   os.path.join(os.environ.get("LOCALAPPDATA", ""),
                                "Microsoft", "Windows", "Fonts")):
        try:
            for name in os.listdir(folder):
                found.add(_norm(os.path.splitext(name)[0]))
        except Exception:
            pass
    _INSTALLED = found
    return found


def _norm(name):
    """비교용으로 공백·대소문자를 없앤 이름"""
    return "".join(str(name).lower().split())


def font_installed(name, have=None):
    """글꼴이 설치되어 있는지 (굵게/기울임 변형 이름까지 감안)"""
    have = installed_fonts() if have is None else have
    key = _norm(name)
    if not key:
        return True
    if key in have:
        return True
    # "Noto Sans KR Bold" 처럼 굵기가 붙은 이름은 앞부분으로도 확인
    return any(h.startswith(key) or key.startswith(h) for h in have if len(h) > 3)


# ----------------------------------------------------------------------
# 내보내기 조건별 비교
# ----------------------------------------------------------------------
def export_variants(app, path, index):
    import pythoncom  # noqa: F401  (COM 초기화 확인용)

    os.makedirs(OUT_DIR, exist_ok=True)
    for old in glob.glob(os.path.join(OUT_DIR, "*.*")):
        try:
            os.remove(old)
        except Exception:
            pass

    # (설명, ReadOnly, WithWindow, 창상태, 배율(None=크기지정안함), 형식)
    variants = [
        ("1_지금방식_창있음_읽기전용_2배", MSO_TRUE, MSO_TRUE, PP_WINDOW_MINIMIZED, 2, "JPG"),
        ("2_창없음_읽기전용_2배",          MSO_TRUE, MSO_FALSE, None, 2, "JPG"),
        ("3_창있음_쓰기가능_2배",          MSO_FALSE, MSO_TRUE, PP_WINDOW_MINIMIZED, 2, "JPG"),
        ("4_창있음_창을_보통크기로_2배",    MSO_TRUE, MSO_TRUE, PP_WINDOW_NORMAL, 2, "JPG"),
        ("5_창있음_원본크기_1배",          MSO_TRUE, MSO_TRUE, PP_WINDOW_MINIMIZED, 1, "JPG"),
        ("6_창있음_크기지정안함",          MSO_TRUE, MSO_TRUE, PP_WINDOW_MINIMIZED, None, "JPG"),
        ("7_창있음_PNG_2배",               MSO_TRUE, MSO_TRUE, PP_WINDOW_MINIMIZED, 2, "PNG"),
        ("8_창있음_쓰기가능_PNG_원본크기",  MSO_FALSE, MSO_TRUE, PP_WINDOW_MINIMIZED, 1, "PNG"),
    ]

    fonts_reported = False
    results = []
    for label, read_only, with_window, win_state, scale, fmt in variants:
        pres = None
        try:
            pres = app.Presentations.Open(path, read_only, MSO_FALSE, with_window)
            if with_window == MSO_TRUE and win_state is not None:
                try:
                    pres.Windows.Item(1).WindowState = win_state
                except Exception:
                    pass

            total = int(pres.Slides.Count)
            if index > total:
                log(f"    슬라이드가 {total}장뿐이라 1번으로 바꿉니다")
                use_index = 1
            else:
                use_index = index

            native_w = int(round(float(pres.PageSetup.SlideWidth) * 4 / 3))
            native_h = int(round(float(pres.PageSetup.SlideHeight) * 4 / 3))

            if not fonts_reported:
                fonts_reported = True
                log(f"\n[2] {use_index}번 슬라이드에 쓰인 글꼴")
                for name in slide_fonts(pres, use_index):
                    base = name.split(" / ")[0].strip()
                    mark = "설치됨" if font_installed(base) else "설치 안 됨?"
                    log(f"    - {name}   [{mark}]")
                log(f"\n[3] 슬라이드 원본 크기: {native_w} x {native_h} 픽셀")
                log(f"\n[4] 조건별로 {use_index}번 슬라이드를 내보냅니다 "
                      f"→ {OUT_DIR}")

            ext = "png" if fmt == "PNG" else "jpg"
            out = os.path.join(OUT_DIR, f"{label}.{ext}")
            slide = pres.Slides.Item(use_index)
            started = time.time()
            if scale is None:
                slide.Export(out, fmt)
            else:
                slide.Export(out, fmt, native_w * scale, native_h * scale)
            took = time.time() - started

            size = os.path.getsize(out) if os.path.exists(out) else 0
            try:
                from PIL import Image
                with Image.open(out) as im:
                    dim = f"{im.size[0]}x{im.size[1]}"
            except Exception:
                dim = "?"
            log(f"    OK   {label}   {dim}, {size // 1024}KB, {took:.1f}초")
            results.append((label, True))
        except Exception as e:
            log(f"    실패 {label}   {e}")
            results.append((label, False))
        finally:
            if pres is not None:
                try:
                    pres.Close()
                except Exception:
                    pass
    return results


def main():
    path = pick_file(sys.argv)
    if not path:
        return 1
    if not os.path.exists(path):
        log(f"파일이 없습니다: {path}")
        return 1
    index = pick_index(sys.argv)

    log("=" * 62)
    log("  슬라이드 글꼴 내보내기 진단")
    log("=" * 62)
    log(f"파일: {path}")
    log(f"슬라이드: {index}번")

    inspect_file(path)

    try:
        import win32com.client
        import pythoncom
    except ImportError:
        log("\npywin32 가 없습니다:  pip install pywin32")
        return 1

    pythoncom.CoInitialize()
    app = None
    try:
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")
            log("\n실행 중인 파워포인트에 연결했습니다")
        except Exception:
            app = win32com.client.Dispatch("PowerPoint.Application")
            log("\n파워포인트를 새로 실행했습니다")
        try:
            app.Visible = True
        except Exception:
            pass
        export_variants(app, path, index)
    except Exception as e:
        log(f"\n오류: {e}")
        return 1
    finally:
        pythoncom.CoUninitialize()

    log("\n" + "=" * 62)
    log(f"  결과 폴더: {OUT_DIR}")
    log("=" * 62)
    log("이 폴더의 그림들을 열어서, 원래 글꼴대로 나온 것이 있는지 봐 주세요.")
    return 0


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    except Exception as e:
        log(f"\n예기치 못한 오류: {e}")
    finally:
        save_report()     # 실패하든 성공하든 진단 내용은 파일로 남긴다
    sys.exit(code)
