"""파워포인트로 PDF를 내보내 본다 (글꼴이 살아 있는지 확인하기 위한 것)

이 파일의 슬라이드에는 파일 안에 포함 저장된 글꼴(Raleway, Playlist Script 등)이
쓰였는데, 파워포인트의 '그림으로 내보내기'는 그 글꼴을 쓰지 않는다.
PDF로 내보내면 글꼴이 그대로 박히는지 확인하는 것이 이 스크립트의 목적이다.

새로 설치할 것은 없다. 파워포인트만 있으면 된다.

사용법:
    python test_ppt_pdf.py                       (폴더의 pptx 자동 선택)
    python test_ppt_pdf.py "C:\\경로\\파일.pptx"
"""

import os
import sys
import glob
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "font_test")
OUT_PDF = os.path.join(OUT_DIR, "pdf_test.pdf")

PP_FIXED_FORMAT_PDF = 2
PP_INTENT_PRINT = 2          # 화면용보다 품질이 높다
PP_PRINT_ALL = 1
MSO_TRUE = -1
MSO_FALSE = 0


def pick_file(argv):
    for a in argv[1:]:
        if a.lower().endswith((".pptx", ".ppt", ".pptm")):
            return os.path.abspath(a)
    found = [f for f in sorted(glob.glob(os.path.join(HERE, "*.pptx")))
             if not os.path.basename(f).startswith(("sample_", "dummy_", "distinct_",
                                                    "real_test", "test_"))]
    if not found:
        found = sorted(glob.glob(os.path.join(HERE, "*.pptx")))
    return found[0] if found else ""


def main():
    path = pick_file(sys.argv)
    if not path or not os.path.exists(path):
        print("pptx 파일을 찾지 못했습니다. 경로를 인자로 넘겨 주세요.")
        return 1

    print("=" * 60)
    print("  PDF 내보내기 확인")
    print("=" * 60)
    print(f"파일: {os.path.basename(path)}")

    try:
        import win32com.client
        import pythoncom
    except ImportError:
        print("pywin32 가 없습니다:  pip install pywin32")
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    if os.path.exists(OUT_PDF):
        try:
            os.remove(OUT_PDF)
        except Exception:
            pass

    pythoncom.CoInitialize()
    pres = None
    try:
        try:
            app = win32com.client.GetActiveObject("PowerPoint.Application")
            print("실행 중인 파워포인트에 연결했습니다")
        except Exception:
            app = win32com.client.Dispatch("PowerPoint.Application")
            print("파워포인트를 새로 실행했습니다")
        try:
            app.Visible = True
        except Exception:
            pass

        print("파일을 여는 중...")
        pres = app.Presentations.Open(path, MSO_TRUE, MSO_FALSE, MSO_TRUE)
        try:
            pres.Windows.Item(1).WindowState = 2      # 최소화
        except Exception:
            pass

        count = int(pres.Slides.Count)
        print(f"슬라이드 {count}장. PDF로 내보내는 중...")

        started = time.time()
        done = False
        errors = []
        # 인자 개수는 파워포인트 버전마다 다르므로 많은 쪽부터 줄여 가며 시도
        attempts = (
            ("전체 인자", (OUT_PDF, PP_FIXED_FORMAT_PDF, PP_INTENT_PRINT,
                        MSO_FALSE, PP_PRINT_ALL, 1, MSO_FALSE)),
            ("품질 지정", (OUT_PDF, PP_FIXED_FORMAT_PDF, PP_INTENT_PRINT)),
            ("기본",     (OUT_PDF, PP_FIXED_FORMAT_PDF)),
        )
        for label, args in attempts:
            try:
                pres.ExportAsFixedFormat(*args)
                print(f"  → 성공 ({label})")
                done = True
                break
            except Exception as e:
                errors.append(f"{label}: {e}")
        if not done:
            # 마지막 수단: SaveAs 로 PDF 저장 (ppSaveAsPDF = 32)
            try:
                pres.SaveAs(OUT_PDF, 32)
                print("  → 성공 (SaveAs PDF)")
                done = True
            except Exception as e:
                errors.append(f"SaveAs: {e}")

        if not done:
            print("PDF 내보내기에 모두 실패했습니다:")
            for e in errors:
                print(f"    {e}")
            return 1

        took = time.time() - started
        size = os.path.getsize(OUT_PDF) if os.path.exists(OUT_PDF) else 0
        print(f"\n완료: {OUT_PDF}")
        print(f"      {count}장 / {size // 1024}KB / {took:.1f}초")
        print(f"      한 장당 {took / max(1, count):.2f}초")
    except Exception as e:
        print(f"오류: {e}")
        return 1
    finally:
        if pres is not None:
            try:
                pres.Close()
            except Exception:
                pass
        pythoncom.CoUninitialize()

    print("\n이 PDF 파일을 확인하겠습니다. 다 됐다고만 알려 주세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
