# -*- coding: utf-8 -*-
"""
사진 속 숨은 글(image_notes) 테스트 - python test_image_notes.py

- JPG/PNG 에 글을 넣고 다시 읽기 (한글, 여러 줄, 64KB 넘는 긴 글)
- 그림은 한 점도 바뀌지 않는지 (픽셀 비교)
- 고쳐 쓰기 / 지우기 / 지원하지 않는 형식
- EXIF 가 있는 JPG, 투명 PNG
- 망가진 파일은 건드리지 않음
"""
import os
import shutil
import sys
import struct
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image
import numpy as np

import image_notes as notes

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"   OK   {label}")
    else:
        print(f"   실패 {label}  {detail}")
        FAILURES.append(label)


def pixels(path):
    with Image.open(path) as im:
        return np.array(im.convert("RGBA"))


def main():
    tmp = tempfile.mkdtemp(prefix="bgpt_imgnote_")
    try:
        rng = np.random.default_rng(1)
        arr = rng.integers(0, 255, (180, 320, 3), dtype=np.uint8)
        jpg = os.path.join(tmp, "광고.jpg")
        Image.fromarray(arr).save(jpg, quality=88)
        exif_jpg = os.path.join(tmp, "카메라.jpeg")
        exif = Image.Exif()
        exif[0x010F] = "TestCam"            # Make
        Image.fromarray(arr).save(exif_jpg, quality=90, exif=exif.tobytes())
        png = os.path.join(tmp, "자막.png")
        rgba = np.dstack([arr, np.full((180, 320), 128, np.uint8)])
        Image.fromarray(rgba, "RGBA").save(png)
        gif = os.path.join(tmp, "움짤.gif")
        Image.fromarray(arr).save(gif)

        text = "오늘 광고\n- 수요예배 7시 30분\n- Salamat sa Ginoo 🙏"

        print("1) JPG")
        before = pixels(jpg)
        check("처음에는 숨은 글 없음", notes.read_note(jpg) == "")
        notes.write_note(jpg, text)
        check("넣은 글을 그대로 읽음", notes.read_note(jpg) == text, repr(notes.read_note(jpg)))
        check("그림은 그대로 (픽셀 동일)", np.array_equal(before, pixels(jpg)))
        notes.write_note(jpg, "고친 글")
        check("고쳐 쓰기", notes.read_note(jpg) == "고친 글")
        with open(jpg, "rb") as f:
            check("숨은 글 칸은 하나만 남음", f.read().count(b"BGPT-NOTE\x00") == 1)
        notes.write_note(jpg, "")
        check("빈 글로 저장하면 지워짐", notes.read_note(jpg) == "")
        with open(jpg, "rb") as f:
            check("지우면 표식도 없음", b"BGPT-NOTE" not in f.read())
        check("지운 뒤에도 그림 그대로", np.array_equal(before, pixels(jpg)))

        print("\n2) EXIF 가 있는 JPG")
        notes.write_note(exif_jpg, text)
        check("글 읽기", notes.read_note(exif_jpg) == text)
        with Image.open(exif_jpg) as im:
            check("EXIF 정보 유지", im.getexif().get(0x010F) == "TestCam", str(dict(im.getexif())))

        print("\n3) 긴 글 (64KB 넘음 → 여러 칸에 나눠 담기)")
        long_text = ("주님의 은혜가 함께하시기를. " * 6000).strip()
        check("글 크기가 64KB 넘음", len(long_text.encode("utf-8")) > 65536)
        notes.write_note(jpg, long_text)
        check("긴 글도 그대로 읽음", notes.read_note(jpg) == long_text)
        check("긴 글 넣어도 그림 그대로", np.array_equal(before, pixels(jpg)))

        print("\n4) PNG (투명)")
        before_png = pixels(png)
        notes.write_note(png, text)
        check("PNG 글 읽기", notes.read_note(png) == text, repr(notes.read_note(png)))
        check("PNG 그림 그대로 (투명도 포함)", np.array_equal(before_png, pixels(png)))
        notes.write_note(png, "두 번째")
        check("PNG 고쳐 쓰기", notes.read_note(png) == "두 번째")
        notes.write_note(png, "")
        check("PNG 지우기", notes.read_note(png) == "")
        with Image.open(png) as im:
            im.load()
            check("PNG 파일이 정상으로 열림", im.size == (320, 180))

        print("\n5) 지원하지 않는 형식 / 망가진 파일")
        check("GIF 는 넣을 수 없음 표시", not notes.can_store(gif) and notes.can_store(jpg) and notes.can_store(png))
        try:
            notes.write_note(gif, "x")
            check("GIF 에 쓰면 오류", False)
        except notes.ImageNoteError:
            check("GIF 에 쓰면 오류", True)
        broken = os.path.join(tmp, "깨짐.jpg")
        with open(broken, "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF")     # 중간에 잘린 파일
        size = os.path.getsize(broken)
        try:
            notes.write_note(broken, "x")
            check("망가진 JPG 는 오류", False)
        except notes.ImageNoteError:
            check("망가진 JPG 는 오류", True)
        check("망가진 파일은 건드리지 않음", os.path.getsize(broken) == size)
        check("망가진 파일 읽기는 빈 글", notes.read_note(broken) == "")
        print("\n6) ppt2jpg 프로그램이 덧붙인 노트 (파일 끝: PPT_NOTE_V1 + 길이 + 글 + PPT_NOTE_END)")
        import struct as _st

        def ppt2jpg_append(path, text):
            raw = text.encode("utf-8")
            with open(path, "ab") as f:
                f.write(b"PPT_NOTE_V1" + _st.pack("<i", len(raw)) + raw + b"PPT_NOTE_END")

        def ppt2jpg_viewer(path):
            """그 프로그램의 [View Slide Note] 와 같은 방법으로 읽기"""
            data = open(path, "rb").read()
            i = data.rfind(b"PPT_NOTE_V1")
            if i < 0:
                return None
            n = _st.unpack("<i", data[i + 11:i + 15])[0]
            return data[i + 15:i + 15 + n].decode("utf-8")

        slide = os.path.join(tmp, "Slide_01.jpg")
        Image.fromarray(arr).save(slide, quality=92)
        slide_pixels = pixels(slide)
        ppt2jpg_append(slide, "이것은 1번 슬라이드의 발표자 노트입니다!")
        check("ppt2jpg 노트 읽기", notes.read_note(slide) == "이것은 1번 슬라이드의 발표자 노트입니다!",
              repr(notes.read_note(slide)))
        notes.write_note(slide, "고친 노트\n둘째 줄")
        check("고치면 이 프로그램에서 보임", notes.read_note(slide) == "고친 노트\n둘째 줄")
        check("고쳐도 ppt2jpg 의 노트 보기에서 보임 (같은 방식으로 저장)",
              ppt2jpg_viewer(slide) == "고친 노트\n둘째 줄", repr(ppt2jpg_viewer(slide)))
        with open(slide, "rb") as f:
            raw = f.read()
        check("노트가 하나만 남음", raw.count(b"PPT_NOTE_V1") == 1 and b"BGPT-NOTE" not in raw)
        check("그림 그대로", np.array_equal(slide_pixels, pixels(slide)))
        notes.write_note(slide, "")
        check("지우면 덧붙인 노트도 없어짐", notes.read_note(slide) == "" and ppt2jpg_viewer(slide) is None)
        check("지운 뒤 그림 그대로", np.array_equal(slide_pixels, pixels(slide)))

        long_slide = os.path.join(tmp, "Slide_02.jpg")
        Image.fromarray(arr).save(long_slide, quality=92)
        long_note = ("Salamat sa Ginoo. " * 9000).strip()
        ppt2jpg_append(long_slide, long_note)
        check("긴 ppt2jpg 노트(64KB 넘음)도 읽음", notes.read_note(long_slide) == long_note)

        nofoot = os.path.join(tmp, "Slide_03.jpg")
        Image.fromarray(arr).save(nofoot, quality=92)
        raw_note = "끝 표식 없는 노트".encode("utf-8")
        with open(nofoot, "ab") as f:
            f.write(b"PPT_NOTE_V1" + _st.pack("<i", len(raw_note)) + raw_note)
        check("끝 표식이 없는 형태도 읽음", notes.read_note(nofoot) == "끝 표식 없는 노트")

        png_slide = os.path.join(tmp, "Slide_04.png")
        Image.fromarray(arr).save(png_slide)
        ppt2jpg_append(png_slide, "PNG 뒤에 붙은 노트")
        check("PNG 뒤에 붙은 노트도 읽음", notes.read_note(png_slide) == "PNG 뒤에 붙은 노트")
        notes.write_note(png_slide, "PNG 고침")
        check("PNG 도 같은 방식으로 고침", ppt2jpg_viewer(png_slide) == "PNG 고침")

        both = os.path.join(tmp, "둘다.jpg")
        Image.fromarray(arr).save(both, quality=92)
        notes.write_note(both, "이 프로그램 노트")
        ppt2jpg_append(both, "ppt2jpg 노트")
        check("둘 다 있으면 이 프로그램 노트가 먼저", notes.read_note(both) == "이 프로그램 노트")

        print("\n7) 새 판 ppt2jpg - 사진 정보(EXIF)에도 넣은 노트")

        def make_exif(entries0, entries_exif):
            """GDI+ 처럼 little-endian TIFF 를 직접 만든다 (Pillow 와 별개로 확인하려고)"""
            def ifd_bytes(entries, base, next_ifd=0):
                entries = sorted(entries, key=lambda e: e[0])
                head = struct.pack("<H", len(entries))
                data_off = base + 2 + 12 * len(entries) + 4
                body, extra = b"", b""
                for tag, typ, value in entries:
                    count = len(value) if typ in (1, 2, 7) else len(value) // 4
                    if len(value) <= 4:
                        body += struct.pack("<HHI", tag, typ, count) + value.ljust(4, b"\x00")
                    else:
                        body += struct.pack("<HHII", tag, typ, count, data_off + len(extra))
                        extra += value + (b"\x00" if len(value) % 2 else b"")
                return head + body + struct.pack("<I", next_ifd) + extra
            ifd0_off = 8
            probe = ifd_bytes(entries0 + [(0x8769, 4, b"\x00\x00\x00\x00")], ifd0_off)
            exif_off = ifd0_off + len(probe)
            ifd0 = ifd_bytes(entries0 + [(0x8769, 4, struct.pack("<I", exif_off))], ifd0_off)
            sub = ifd_bytes(entries_exif, exif_off)
            return b"Exif\x00\x00" + b"II*\x00" + struct.pack("<I", ifd0_off) + ifd0 + sub

        def with_exif(path, exif_payload):
            data = open(path, "rb").read()
            seg = b"\xff\xe1" + struct.pack(">H", len(exif_payload) + 2) + exif_payload
            with open(path, "wb") as f:
                f.write(data[:2] + seg + data[2:])

        def ppt2jpg_new(path, text, keep_tail=True, title="Slide Note"):
            u16 = text.encode("utf-16-le")
            entries0 = [(0x010F, 2, b"TestCam\x00"),
                        (0x9C9C, 1, u16 + b"\x00\x00"),
                        (0x9C9B, 1, title.encode("utf-16-le") + b"\x00\x00"),
                        (0x010E, 2, text.encode("utf-8") + b"\x00")]
            with_exif(path, make_exif(entries0, [(0x9286, 7, b"UNICODE\x00" + u16)]))
            if keep_tail:
                ppt2jpg_append(path, text)

        def exif_of(path):
            with Image.open(path) as im:
                ex = im.getexif()
                return ex, ex.get_ifd(0x8769)

        note_ko = "주일 광고 노트\r\n- 수요예배 7:30"
        a = os.path.join(tmp, "new_01.jpg")
        Image.fromarray(arr).save(a, quality=92)
        a_pixels = pixels(a)
        ppt2jpg_new(a, note_ko)
        check("사진 정보 + 파일 끝 노트 읽기", notes.read_note(a) == note_ko, repr(notes.read_note(a)))

        b = os.path.join(tmp, "new_02.jpg")
        Image.fromarray(arr).save(b, quality=92)
        ppt2jpg_new(b, "파일 끝이 지워진 노트", keep_tail=False)
        check("파일 끝 노트가 없어도 사진 정보(탐색기 메모)에서 읽음",
              notes.read_note(b) == "파일 끝이 지워진 노트", repr(notes.read_note(b)))

        notes.write_note(a, "여기서 고친 노트")
        ex, sub = exif_of(a)
        xp = ex.get(0x9C9C)
        xp = bytes(xp).decode("utf-16-le").rstrip("\x00") if xp is not None else None
        check("고치면 파일 끝 노트가 바뀜", ppt2jpg_viewer(a) == "여기서 고친 노트", repr(ppt2jpg_viewer(a)))
        check("고치면 탐색기 메모(XPComment)도 바뀜", xp == "여기서 고친 노트", repr(xp))
        uc = sub.get(0x9286)
        check("사용자 메모(UserComment)도 바뀜",
              uc is not None and bytes(uc)[8:].decode("utf-16-le") == "여기서 고친 노트", repr(uc))
        desc = ex.get(0x010E)
        # Pillow 는 이 칸을 latin-1 글자로 돌려준다 - 바이트로 되돌려 UTF-8 로 읽는다
        desc = (desc if isinstance(desc, bytes) else (desc or "").encode("latin-1")).decode("utf-8")
        check("설명(ImageDescription)도 바뀜", (desc or "").rstrip("\x00") == "여기서 고친 노트", repr(desc))
        check("다른 사진 정보(카메라 이름)는 그대로", ex.get(0x010F) == "TestCam", repr(ex.get(0x010F)))
        check("그림 그대로", np.array_equal(a_pixels, pixels(a)))
        with open(a, "rb") as f:
            check("이 프로그램 방식 칸은 넣지 않음", b"BGPT-NOTE" not in f.read())

        notes.write_note(a, "")
        ex, sub = exif_of(a)
        check("지우면 어디에도 남지 않음", notes.read_note(a) == "" and ppt2jpg_viewer(a) is None
              and 0x9C9C not in ex and 0x9286 not in sub, f"{notes.read_note(a)!r} {dict(ex)}")
        check("지워도 카메라 이름은 그대로", ex.get(0x010F) == "TestCam")
        check("지운 뒤 그림 그대로", np.array_equal(a_pixels, pixels(a)))

        notes.write_note(b, "탐색기 메모만 있던 사진 고침")
        check("파일 끝 노트가 없던 사진도 고치면 둘 다 맞춤",
              notes.read_note(b) == "탐색기 메모만 있던 사진 고침"
              and ppt2jpg_viewer(b) == "탐색기 메모만 있던 사진 고침")

        c = os.path.join(tmp, "camera.jpg")
        Image.fromarray(arr).save(c, quality=92)
        with_exif(c, make_exif([(0x010F, 2, b"OLYMPUS\x00"),
                                (0x010E, 2, b"OLYMPUS DIGITAL CAMERA\x00")],
                               [(0x9286, 7, b"ASCII\x00\x00\x00" + b" " * 20)]))
        check("카메라가 넣은 설명은 노트로 보지 않음", notes.read_note(c) == "", repr(notes.read_note(c)))

        d = os.path.join(tmp, "explorer.jpg")
        Image.fromarray(arr).save(d, quality=92)
        with_exif(d, make_exif([(0x9C9C, 1, "탐색기에서 쓴 메모".encode("utf-16-le") + b"\x00\x00")], []))
        check("탐색기 [속성 > 자세히 > 메모] 글도 읽음", notes.read_note(d) == "탐색기에서 쓴 메모")

        e = os.path.join(tmp, "long.jpg")
        Image.fromarray(arr).save(e, quality=92)
        ppt2jpg_new(e, "짧은 노트")
        very_long = "주님의 은혜와 평강이 함께하시기를 바랍니다. " * 1200
        very_long = very_long.strip()
        notes.write_note(e, very_long)
        ex, _ = exif_of(e)
        check("사진 정보에 다 안 들어가는 긴 글 → 파일 끝에 저장하고 읽힘",
              notes.read_note(e) == very_long and ppt2jpg_viewer(e) == very_long)
        check("긴 글일 때 사진 정보에 옛 노트가 남지 않음", 0x9C9C not in ex, repr(ex.get(0x9C9C))[:60])

        leftovers = [n for n in os.listdir(tmp) if n.startswith(".bgpt_note_")]
        check("임시 파일이 남지 않음", not leftovers, str(leftovers))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
