# -*- coding: utf-8 -*-
"""
사진 속 숨은 글 (이미지 노트)

사진 파일 안에 글을 숨겨 저장하고 읽는다. 화면에 보이는 그림은 한 점도 바뀌지 않는다.

왜 픽셀(최하위 비트)에 숨기지 않는가
    JPG 는 저장할 때마다 다시 압축되므로 픽셀에 숨긴 글은 깨져 버린다. 그래서 그림
    데이터는 그대로 두고, 파일 안의 '부가 정보 칸'에 글을 넣는다. 사진 보기 프로그램은
    이 칸을 읽지 않으므로 겉보기에는 아무 차이가 없고, 파일을 복사하거나 USB 로 옮겨도
    글이 함께 따라간다. (단, 카카오톡처럼 사진을 다시 압축해 보내는 곳을 거치면 지워진다.)

    - JPG/JPEG : APP15 칸 (b"BGPT-NOTE\\0" 표식 + 순번 + 전체 개수 + UTF-8 글)
                 64KB 가 넘는 글은 여러 칸에 나눠 담는다.
    - PNG      : iTXt 칸 (키워드 "BGPT Note", UTF-8 글)

    그 밖의 형식(bmp/gif/webp/tiff/ico)은 숨은 글을 넣을 수 없다.

ppt2jpg(PPT 를 JPG 로 내보내며 슬라이드 노트를 넣는 다른 프로그램) 방식도 읽는다
    그 프로그램은 그림 데이터가 끝난 뒤 파일 맨 끝에
    b"PPT_NOTE_V1" + 글 길이(4바이트, little-endian) + UTF-8 글 + b"PPT_NOTE_END"
    를 덧붙인다. 이런 사진의 숨은 글을 이 프로그램에서 고치면 같은 방식으로 고쳐 써서,
    그 프로그램의 [View Slide Note] 로 열어도 고친 글이 보이게 한다.

    새 판 ppt2jpg 는 같은 글을 사진 정보(EXIF)에도 넣는다 - 윈도우 탐색기의
    [속성 > 자세히 > 메모](XPComment), 설명(ImageDescription), 사용자 메모(UserComment),
    그리고 제목(XPTitle)에 "Slide Note". 파일 끝의 글이 지워진 사진(다른 프로그램이 다시
    저장한 경우 등)도 이 사진 정보에서 읽는다. 이런 사진을 여기서 고치면 사진 정보도
    함께 고쳐서 탐색기·다른 사진 보기 프로그램에서도 같은 글이 보이게 한다.

읽는 차례: 이 프로그램 방식 → 파일 끝(ppt2jpg) → 사진 정보(EXIF)

쓰기는 같은 폴더에 임시 파일을 만든 뒤 바꿔치기하므로, 도중에 실패해도 원본이
반쯤 쓰인 채로 남지 않는다. 바꿔치기 전에 다시 읽어서 글과 그림 데이터가 맞는지
확인한다.
"""
import os
import struct
import tempfile
import zlib

SUPPORTED_EXTS = (".jpg", ".jpeg", ".png")

_JPEG_MAGIC = b"BGPT-NOTE\x00"
_JPEG_APP15 = 0xEF
_JPEG_MAX_PAYLOAD = 65533 - len(_JPEG_MAGIC) - 2     # 길이 칸(2) 빼고, 순번·개수(2) 빼고
_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_PNG_KEYWORD = b"BGPT Note"
MAX_NOTE_BYTES = 200 * _JPEG_MAX_PAYLOAD             # 약 13MB - 사실상 제한 없음
_PPT2JPG_HEAD = b"PPT_NOTE_V1"
_PPT2JPG_FOOT = b"PPT_NOTE_END"
_TAIL_SCAN = 1024 * 1024                              # 끝 표식이 없을 때 뒤에서 찾아볼 범위


class ImageNoteError(Exception):
    pass


def can_store(path) -> bool:
    return bool(path) and os.path.splitext(str(path))[1].lower() in SUPPORTED_EXTS


def _kind(path):
    ext = os.path.splitext(str(path))[1].lower()
    if ext in (".jpg", ".jpeg"):
        return "jpeg"
    if ext == ".png":
        return "png"
    return None


# ----------------------------------------------------------------------
# JPEG
# ----------------------------------------------------------------------
def _jpeg_segments(data: bytes):
    """SOI 다음부터 SOS 앞까지의 칸들을 (marker, 시작, 끝) 으로 돌려주고,
    SOS 가 시작되는 위치(그 뒤는 그림 데이터 - 그대로 복사한다)를 함께 돌려준다."""
    if len(data) < 4 or data[0:2] != b"\xff\xd8":
        raise ImageNoteError("JPG 파일 형식이 아닙니다")
    segments = []
    pos = 2
    n = len(data)
    while pos < n:
        if data[pos] != 0xFF:
            raise ImageNoteError("JPG 파일 구조를 읽을 수 없습니다")
        # 0xFF 채움 바이트 건너뛰기
        start = pos
        while pos < n and data[pos] == 0xFF:
            pos += 1
        if pos >= n:
            break
        marker = data[pos]
        pos += 1
        if marker == 0xDA or marker == 0xD9:       # SOS(그림 데이터 시작) / EOI
            return segments, start
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            segments.append((marker, start, pos))   # 길이 없는 표식
            continue
        if pos + 2 > n:
            raise ImageNoteError("JPG 파일이 잘려 있습니다")
        length = struct.unpack(">H", data[pos:pos + 2])[0]
        if length < 2 or pos + length > n:
            raise ImageNoteError("JPG 파일이 잘려 있습니다")
        end = pos + length
        segments.append((marker, start, end))
        pos = end
    raise ImageNoteError("JPG 그림 데이터를 찾을 수 없습니다")


def _is_our_jpeg_segment(data, marker, start, end) -> bool:
    if marker != _JPEG_APP15:
        return False
    body = data[start + 4:end]
    return body.startswith(_JPEG_MAGIC)


def _jpeg_read(data: bytes) -> str:
    segments, _ = _jpeg_segments(data)
    parts = []
    for marker, start, end in segments:
        if _is_our_jpeg_segment(data, marker, start, end):
            body = data[start + 4:end][len(_JPEG_MAGIC):]
            if len(body) >= 2:
                parts.append((body[0], body[1], body[2:]))
    if not parts:
        return ""
    parts.sort(key=lambda p: p[0])
    return b"".join(p[2] for p in parts).decode("utf-8", errors="replace")


def _jpeg_write(data: bytes, text: str) -> bytes:
    segments, sos = _jpeg_segments(data)
    kept = [(m, s, e) for (m, s, e) in segments if not _is_our_jpeg_segment(data, m, s, e)]
    # JFIF(APP0)/EXIF(APP1) 등 앞쪽 APPn 칸들 바로 뒤에 넣는다
    insert_at = 0
    for i, (marker, _s, _e) in enumerate(kept):
        if 0xE0 <= marker <= 0xEF:
            insert_at = i + 1
        else:
            break
    ours = b""
    raw = text.encode("utf-8")
    if raw:
        chunks = [raw[i:i + _JPEG_MAX_PAYLOAD] for i in range(0, len(raw), _JPEG_MAX_PAYLOAD)]
        if len(chunks) > 255:
            raise ImageNoteError("글이 너무 깁니다")
        for i, chunk in enumerate(chunks):
            body = _JPEG_MAGIC + bytes([i, len(chunks)]) + chunk
            ours += b"\xff" + bytes([_JPEG_APP15]) + struct.pack(">H", len(body) + 2) + body
    out = [data[0:2]]
    for i, (_m, s, e) in enumerate(kept):
        if i == insert_at:
            out.append(ours)
        out.append(data[s:e])
    if insert_at >= len(kept):
        out.append(ours)
    out.append(data[sos:])
    return b"".join(out)


def _jpeg_image_data(data: bytes) -> bytes:
    """비교용: 우리 칸을 뺀 나머지 (그림 데이터가 그대로인지 확인)"""
    segments, sos = _jpeg_segments(data)
    return b"".join(data[s:e] for (m, s, e) in segments
                    if not _is_our_jpeg_segment(data, m, s, e)) + data[sos:]


# ----------------------------------------------------------------------
# PNG
# ----------------------------------------------------------------------
def _png_chunks(data: bytes):
    if not data.startswith(_PNG_SIG):
        raise ImageNoteError("PNG 파일 형식이 아닙니다")
    chunks = []
    pos = len(_PNG_SIG)
    n = len(data)
    while pos + 12 <= n:
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        ctype = data[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > n:
            raise ImageNoteError("PNG 파일이 잘려 있습니다")
        chunks.append((ctype, pos, end))
        pos = end
        if ctype == b"IEND":
            break
    if not chunks or chunks[0][0] != b"IHDR":
        raise ImageNoteError("PNG 파일 구조를 읽을 수 없습니다")
    return chunks


def _png_itxt_text(payload: bytes):
    """iTXt 내용에서 (키워드, 글) - 형식이 다르면 None"""
    try:
        keyword, rest = payload.split(b"\x00", 1)
        comp_flag, comp_method = rest[0], rest[1]
        rest = rest[2:]
        _lang, rest = rest.split(b"\x00", 1)
        _translated, text = rest.split(b"\x00", 1)
        if comp_flag == 1:
            if comp_method != 0:
                return None
            text = zlib.decompress(text)
        return keyword, text.decode("utf-8", errors="replace")
    except Exception:
        return None


def _is_our_png_chunk(data, ctype, start, end) -> bool:
    if ctype != b"iTXt":
        return False
    return data[start + 8:end - 4].startswith(_PNG_KEYWORD + b"\x00")


def _png_read(data: bytes) -> str:
    for ctype, start, end in _png_chunks(data):
        if _is_our_png_chunk(data, ctype, start, end):
            parsed = _png_itxt_text(data[start + 8:end - 4])
            if parsed:
                return parsed[1]
    return ""


def _png_chunk(ctype: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(ctype + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + ctype + payload + struct.pack(">I", crc)


def _png_write(data: bytes, text: str) -> bytes:
    chunks = _png_chunks(data)
    out = [_PNG_SIG]
    for ctype, start, end in chunks:
        if _is_our_png_chunk(data, ctype, start, end):
            continue
        out.append(data[start:end])
        if ctype == b"IHDR" and text:
            payload = _PNG_KEYWORD + b"\x00" + b"\x00\x00" + b"\x00" + b"\x00" + text.encode("utf-8")
            out.append(_png_chunk(b"iTXt", payload))
    last_end = chunks[-1][2]
    out.append(data[last_end:])           # IEND 뒤에 붙어 있던 것까지 그대로
    return b"".join(out)


def _png_image_data(data: bytes) -> bytes:
    return b"".join(data[s:e] for (c, s, e) in _png_chunks(data)
                    if not _is_our_png_chunk(data, c, s, e))


# ----------------------------------------------------------------------
# 바깥에서 쓰는 함수
# ----------------------------------------------------------------------
def _jpeg_read_stream(f) -> str:
    """파일 앞부분(그림 데이터 앞)만 읽는다 - 큰 사진도 빠르다"""
    if f.read(2) != b"\xff\xd8":
        return ""
    parts = []
    while True:
        b = f.read(1)
        if not b:
            break
        if b != b"\xff":
            break
        marker = f.read(1)
        while marker == b"\xff":
            marker = f.read(1)
        if not marker:
            break
        m = marker[0]
        if m in (0xDA, 0xD9):
            break
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            continue
        raw_len = f.read(2)
        if len(raw_len) < 2:
            break
        length = struct.unpack(">H", raw_len)[0]
        if length < 2:
            break
        if m == _JPEG_APP15:
            body = f.read(length - 2)
            if body.startswith(_JPEG_MAGIC):
                body = body[len(_JPEG_MAGIC):]
                if len(body) >= 2:
                    parts.append((body[0], body[2:]))
        else:
            f.seek(length - 2, os.SEEK_CUR)
    parts.sort(key=lambda p: p[0])
    return b"".join(p[1] for p in parts).decode("utf-8", errors="replace")


def _png_read_stream(f) -> str:
    """칸 머리만 읽고 그림 데이터(IDAT)는 건너뛴다"""
    if f.read(8) != _PNG_SIG:
        return ""
    while True:
        head = f.read(8)
        if len(head) < 8:
            break
        length = struct.unpack(">I", head[:4])[0]
        ctype = head[4:]
        if ctype == b"iTXt" and length < 64 * 1024 * 1024:
            payload = f.read(length)
            f.seek(4, os.SEEK_CUR)
            if payload.startswith(_PNG_KEYWORD + b"\x00"):
                parsed = _png_itxt_text(payload)
                if parsed:
                    return parsed[1]
            continue
        if ctype == b"IEND":
            break
        f.seek(length + 4, os.SEEK_CUR)
    return ""


# ----------------------------------------------------------------------
# ppt2jpg 방식 (파일 끝에 덧붙인 노트)
# ----------------------------------------------------------------------
def _ppt2jpg_split(data: bytes):
    """(그림 부분, 노트 글) - 덧붙인 노트가 없으면 (data, None)"""
    if data.endswith(_PPT2JPG_FOOT):
        end = len(data) - len(_PPT2JPG_FOOT)
        start = data.rfind(_PPT2JPG_HEAD, 0, end)
        while start >= 0:
            pos = start + len(_PPT2JPG_HEAD)
            if pos + 4 <= end:
                length = struct.unpack("<i", data[pos:pos + 4])[0]
                if length >= 0 and pos + 4 + length == end:
                    return data[:start], data[pos + 4:end].decode("utf-8", errors="replace")
            start = data.rfind(_PPT2JPG_HEAD, 0, start)
        return data, None
    # 끝 표식이 없는 형태 (그 프로그램의 보기 도구는 이것도 읽는다)
    lo = max(0, len(data) - _TAIL_SCAN)
    start = data.rfind(_PPT2JPG_HEAD, lo)
    if start >= 0:
        pos = start + len(_PPT2JPG_HEAD)
        if pos + 4 <= len(data):
            length = struct.unpack("<i", data[pos:pos + 4])[0]
            if length > 0 and pos + 4 + length == len(data):
                return data[:start], data[pos + 4:].decode("utf-8", errors="replace")
    return data, None


# ----------------------------------------------------------------------
# 사진 정보(EXIF) 의 메모 칸
# ----------------------------------------------------------------------
_EXIF_XPCOMMENT = 0x9C9C
_EXIF_XPTITLE = 0x9C9B
_EXIF_DESCRIPTION = 0x010E
_EXIF_IFD_POINTER = 0x8769
_EXIF_USERCOMMENT = 0x9286
_SLIDE_NOTE_TITLE = "Slide Note"
_TIFF_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 7: 1, 9: 4, 10: 8}


def _tiff_entries(tiff: bytes, offset: int, endian: str):
    """IFD 하나의 {태그: 값 바이트}"""
    out = {}
    if offset <= 0 or offset + 2 > len(tiff):
        return out
    count = struct.unpack(endian + "H", tiff[offset:offset + 2])[0]
    for i in range(min(count, 1000)):
        pos = offset + 2 + i * 12
        if pos + 12 > len(tiff):
            break
        tag, typ, n = struct.unpack(endian + "HHI", tiff[pos:pos + 8])
        size = _TIFF_TYPE_SIZE.get(typ, 1) * n
        if size <= 4:
            value = tiff[pos + 8:pos + 8 + size]
        else:
            start = struct.unpack(endian + "I", tiff[pos + 8:pos + 12])[0]
            value = tiff[start:start + size]
        out[tag] = value
    return out


def _jpeg_exif_payload(data: bytes):
    """JPEG 의 EXIF(APP1) 내용 (b"Exif\0\0" 로 시작) - 없으면 None"""
    try:
        segments, _ = _jpeg_segments(data)
    except ImageNoteError:
        return None
    for marker, start, end in segments:
        if marker == 0xE1 and data[start + 4:start + 10] == b"Exif\x00\x00":
            return data[start + 4:end]
    return None


def _clean_text(value: str) -> str:
    return (value or "").replace("\x00", "").strip()


def _exif_fields(payload):
    """사진 정보에서 메모 칸들을 읽는다 → dict (없으면 빈 dict)"""
    fields = {}
    if not payload or not payload.startswith(b"Exif\x00\x00"):
        return fields
    tiff = payload[6:]
    if tiff[:2] == b"II":
        endian = "<"
    elif tiff[:2] == b"MM":
        endian = ">"
    else:
        return fields
    try:
        ifd0 = _tiff_entries(tiff, struct.unpack(endian + "I", tiff[4:8])[0], endian)
        if _EXIF_XPCOMMENT in ifd0:
            fields["xpcomment"] = _clean_text(ifd0[_EXIF_XPCOMMENT].decode("utf-16-le", errors="replace"))
        if _EXIF_XPTITLE in ifd0:
            fields["xptitle"] = _clean_text(ifd0[_EXIF_XPTITLE].decode("utf-16-le", errors="replace"))
        if _EXIF_DESCRIPTION in ifd0:
            fields["description"] = _clean_text(ifd0[_EXIF_DESCRIPTION].decode("utf-8", errors="replace"))
        if _EXIF_IFD_POINTER in ifd0 and len(ifd0[_EXIF_IFD_POINTER]) == 4:
            sub = _tiff_entries(tiff, struct.unpack(endian + "I", ifd0[_EXIF_IFD_POINTER])[0], endian)
            raw = sub.get(_EXIF_USERCOMMENT)
            if raw and len(raw) > 8:
                head, body = raw[:8], raw[8:]
                if head.startswith(b"UNICODE"):
                    enc = "utf-16-le" if endian == "<" else "utf-16-be"
                    # ppt2jpg 는 바이트 순서와 상관없이 little-endian 으로 쓴다
                    text = body.decode("utf-16-le", errors="replace")
                    if enc != "utf-16-le" and "\ufffd" in text:
                        text = body.decode(enc, errors="replace")
                elif head.startswith(b"ASCII"):
                    text = body.decode("ascii", errors="replace")
                else:
                    text = body.decode("utf-8", errors="replace")
                fields["usercomment"] = _clean_text(text)
    except Exception:
        return fields
    return fields


def _exif_note(fields) -> str:
    """사진 정보 중 '노트'로 볼 글.

    탐색기 메모(XPComment)는 사람이 일부러 쓴 글이라 늘 읽는다. 설명·사용자 메모는
    카메라가 아무 글이나 넣어 두는 경우가 많아서, ppt2jpg 가 넣은 것(제목이
    "Slide Note")일 때만 읽는다."""
    if fields.get("xpcomment"):
        return fields["xpcomment"]
    if fields.get("xptitle") == _SLIDE_NOTE_TITLE:
        return fields.get("usercomment") or fields.get("description") or ""
    return ""


def _exif_has_note_fields(fields) -> bool:
    return bool(fields.get("xpcomment")) or fields.get("xptitle") == _SLIDE_NOTE_TITLE


def _jpeg_read_exif_stream(f) -> str:
    """파일 앞부분(그림 데이터 앞)에서 EXIF 메모를 읽는다"""
    f.seek(0)
    if f.read(2) != b"\xff\xd8":
        return ""
    while True:
        b = f.read(1)
        if b != b"\xff":
            return ""
        marker = f.read(1)
        while marker == b"\xff":
            marker = f.read(1)
        if not marker:
            return ""
        m = marker[0]
        if m in (0xDA, 0xD9):
            return ""
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            continue
        raw_len = f.read(2)
        if len(raw_len) < 2:
            return ""
        length = struct.unpack(">H", raw_len)[0]
        if length < 2:
            return ""
        if m == 0xE1:
            payload = f.read(length - 2)
            if payload.startswith(b"Exif\x00\x00"):
                return _exif_note(_exif_fields(payload))
        else:
            f.seek(length - 2, os.SEEK_CUR)


def _jpeg_set_exif_note(data: bytes, text: str) -> bytes:
    """EXIF 의 메모 칸을 고친다 (빈 글이면 지운다). 그림 데이터는 그대로 두고
    EXIF(APP1) 칸만 바꿔 끼운다. 사진 정보에 다 들어가지 않을 만큼 긴 글이면
    메모 칸을 비워 둔다(옛 글이 남지 않게 - 글은 파일 끝에 들어간다)."""
    payload = _jpeg_exif_payload(data)
    if payload is None:
        return data
    from PIL import Image           # 필요할 때만 (프로그램 시작을 늦추지 않게)

    def build(note):
        exif = Image.Exif()
        exif.load(payload)
        sub = exif.get_ifd(_EXIF_IFD_POINTER)
        if note:
            exif[_EXIF_XPCOMMENT] = note.encode("utf-16-le") + b"\x00\x00"
            exif[_EXIF_XPTITLE] = _SLIDE_NOTE_TITLE.encode("utf-16-le") + b"\x00\x00"
            exif[_EXIF_DESCRIPTION] = note.encode("utf-8")
            sub[_EXIF_USERCOMMENT] = b"UNICODE\x00" + note.encode("utf-16-le")
        else:
            for tag in (_EXIF_XPCOMMENT, _EXIF_XPTITLE, _EXIF_DESCRIPTION):
                if tag in exif:
                    del exif[tag]
            if _EXIF_USERCOMMENT in sub:
                del sub[_EXIF_USERCOMMENT]
        out = exif.tobytes()
        return out if out.startswith(b"Exif\x00\x00") else b"Exif\x00\x00" + out

    new_payload = build(text)
    if len(new_payload) + 2 > 0xFFFF:
        new_payload = build("")
    segments, sos = _jpeg_segments(data)
    out = [data[0:2]]
    for marker, start, end in segments:
        if marker == 0xE1 and data[start + 4:start + 10] == b"Exif\x00\x00":
            out.append(b"\xff\xe1" + struct.pack(">H", len(new_payload) + 2) + new_payload)
        else:
            out.append(data[start:end])
    out.append(data[sos:])
    return b"".join(out)


def _jpeg_picture_data(data: bytes) -> bytes:
    """비교용: 사진 정보(APP 칸)를 뺀 순수 그림 데이터"""
    segments, sos = _jpeg_segments(data)
    return b"".join(data[s:e] for (m, s, e) in segments
                    if not (0xE0 <= m <= 0xEF or m == 0xFE)) + data[sos:]


def _ppt2jpg_block(text: str) -> bytes:
    raw = text.encode("utf-8")
    return _PPT2JPG_HEAD + struct.pack("<i", len(raw)) + raw + _PPT2JPG_FOOT


def _ppt2jpg_read_tail(f) -> str:
    """파일 끝부분만 읽어 ppt2jpg 노트를 찾는다 (큰 사진도 빠르다)"""
    f.seek(0, os.SEEK_END)
    size = f.tell()
    if size < len(_PPT2JPG_HEAD) + 4:
        return ""
    f.seek(max(0, size - len(_PPT2JPG_FOOT)))
    has_foot = f.read() == _PPT2JPG_FOOT
    span = 64 * 1024
    while True:
        span = min(size, span)
        f.seek(size - span)
        tail = f.read()
        _, note = _ppt2jpg_split(tail)
        if note is not None:
            return note
        if not has_foot or span >= size or span >= MAX_NOTE_BYTES + 64:
            return ""
        span *= 8            # 긴 노트 - 더 넓게 읽어 본다


def read_note(path) -> str:
    """사진에 숨은 글을 읽는다 (없거나 읽을 수 없으면 빈 문자열).

    이 프로그램이 넣은 글이 우선이고, 없으면 ppt2jpg 가 덧붙인 노트를 읽는다."""
    kind = _kind(path)
    try:
        with open(path, "rb") as f:
            text = ""
            if kind == "jpeg":
                text = _jpeg_read_stream(f)
            elif kind == "png":
                text = _png_read_stream(f)
            if not text.strip("\x00").strip():
                text = _ppt2jpg_read_tail(f)
            if not (text or "").strip("\x00").strip() and kind == "jpeg":
                text = _jpeg_read_exif_stream(f)
        return (text or "").strip("\x00")
    except Exception:
        return ""


def write_note(path, text: str):
    """사진에 글을 숨겨 저장한다. 빈 글이면 숨은 글을 지운다.

    실패하면 ImageNoteError 를 낸다 (원본 파일은 그대로 남는다)."""
    kind = _kind(path)
    if kind is None:
        raise ImageNoteError("JPG 또는 PNG 사진에만 숨은 글을 넣을 수 있습니다")
    text = (text or "").replace("\r\n", "\n").rstrip()
    raw_len = len(text.encode("utf-8"))
    if raw_len > MAX_NOTE_BYTES:
        raise ImageNoteError("글이 너무 깁니다")
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        raise ImageNoteError(f"사진 파일을 읽지 못했습니다: {e}") from e

    body, ppt2jpg_note = _ppt2jpg_split(data)
    exif_managed = False
    if kind == "jpeg":
        try:
            exif_managed = _exif_has_note_fields(_exif_fields(_jpeg_exif_payload(body)))
        except Exception:
            exif_managed = False
    if ppt2jpg_note is not None or exif_managed:
        # ppt2jpg 가 넣은 노트가 있는 사진 - 같은 방식으로 고쳐 쓴다 (그 프로그램과
        # 탐색기에서도 보이게). 이 프로그램 방식의 칸이 따로 있었다면 겹치지 않게 지운다.
        if kind == "jpeg":
            clean = _jpeg_write(body, "")
            if exif_managed:
                try:
                    clean = _jpeg_set_exif_note(clean, text)
                except Exception as e:
                    raise ImageNoteError(f"사진 정보(EXIF)를 고치지 못했습니다: {e}") from e
            same_picture = _jpeg_picture_data(clean) == _jpeg_picture_data(body)
        else:
            clean = _png_write(body, "")
            same_picture = _png_image_data(clean) == _png_image_data(body)
        new_data = clean + (_ppt2jpg_block(text) if text else b"")
        _, check = _ppt2jpg_split(new_data)
        check = check or ""
        if kind == "jpeg" and exif_managed and not text:
            # 지웠다면 사진 정보에도 남아 있으면 안 된다
            if _exif_note(_exif_fields(_jpeg_exif_payload(new_data))):
                check = "<남음>"
    elif kind == "jpeg":
        new_data = _jpeg_write(data, text)
        same_picture = _jpeg_image_data(new_data) == _jpeg_image_data(data)
        check = _jpeg_read(new_data)
    else:
        new_data = _png_write(data, text)
        same_picture = _png_image_data(new_data) == _png_image_data(data)
        check = _png_read(new_data)
    if not same_picture or check != text:
        raise ImageNoteError("저장 확인에 실패해 사진을 바꾸지 않았습니다")
    if new_data == data:
        return                                  # 바뀐 것 없음

    folder = os.path.dirname(os.path.abspath(path)) or "."
    fd, temp = tempfile.mkstemp(prefix=".bgpt_note_", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(new_data)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.chmod(temp, os.stat(path).st_mode & 0o777)
        except OSError:
            pass
        os.replace(temp, path)
    except OSError as e:
        try:
            os.remove(temp)
        except OSError:
            pass
        raise ImageNoteError(f"사진 파일에 저장하지 못했습니다 (다른 프로그램이 열고 있거나 "
                             f"읽기 전용일 수 있습니다): {e}") from e
