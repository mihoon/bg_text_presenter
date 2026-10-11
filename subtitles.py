# -*- coding: utf-8 -*-
"""
동영상 자막 파일(.srt / .smi) 읽기

- 동영상과 같은 폴더에 이름이 같은 자막 파일이 있으면 찾아 준다
  (예: 설교영상.mp4 → 설교영상.srt / 설교영상.smi, 설교영상.ko.srt 도 인정)
- 한국에서 흔한 SAMI(.smi) 파일은 대부분 CP949(EUC-KR)로 저장되어 있으므로
  인코딩을 차례로 시도해 읽는다 (UTF-8 BOM/UTF-16 BOM → UTF-8 → CP949)
- 재생 위치(밀리초)를 주면 그때 보여야 할 자막 문자열을 돌려준다

이 모듈은 Qt에 의존하지 않는다 (단위 테스트가 쉽도록).
"""
import bisect
import html
import os
import re

SUBTITLE_EXTS = (".srt", ".smi", ".sami")

# 자막 파일 이름 뒤에 붙는 흔한 한국어 표시 (설교영상.ko.srt, 설교영상.kor.smi 등)
_KOREAN_TAGS = ("ko", "kor", "kr", "korean", "한국어", "한글")

# SAMI 에서 다음 자막이 없을 때 마지막 자막을 보여 줄 시간
_LAST_CUE_MS = 5000


class Cue:
    __slots__ = ("start", "end", "text")

    def __init__(self, start: int, end: int, text: str):
        self.start = int(start)
        self.end = int(end)
        self.text = text

    def __repr__(self):
        return f"Cue({self.start}, {self.end}, {self.text!r})"


class SubtitleTrack:
    """재생 위치로 자막을 찾는 자막 트랙"""

    def __init__(self, cues, source_path: str = ""):
        self.cues = sorted((c for c in cues if c.text and c.end > c.start),
                           key=lambda c: (c.start, c.end))
        self._starts = [c.start for c in self.cues]
        self.source_path = source_path

    def __len__(self):
        return len(self.cues)

    def text_at(self, position_ms: int) -> str:
        """그 시각에 보여야 할 자막 (없으면 빈 문자열)"""
        if not self.cues:
            return ""
        i = bisect.bisect_right(self._starts, int(position_ms)) - 1
        if i < 0:
            return ""
        # 겹치는 자막(드물다)도 함께 보이도록 바로 앞 몇 개까지 확인한다
        active = []
        for j in range(i, max(-1, i - 4), -1):
            cue = self.cues[j]
            if cue.start <= position_ms < cue.end:
                active.append(cue.text)
        active.reverse()
        return "\n".join(active)


# ----------------------------------------------------------------------
# 파일 찾기 / 읽기
# ----------------------------------------------------------------------
def find_subtitle_for(video_path: str) -> str:
    """동영상과 같은 폴더에서 이름이 같은 자막 파일을 찾는다 (없으면 "")"""
    if not video_path:
        return ""
    folder = os.path.dirname(os.path.abspath(video_path))
    stem = os.path.splitext(os.path.basename(video_path))[0]
    try:
        names = os.listdir(folder)
    except OSError:
        return ""

    stem_lower = stem.lower()
    exact = {}
    tagged = []
    for name in names:
        base, ext = os.path.splitext(name)
        ext = ext.lower()
        if ext not in SUBTITLE_EXTS:
            continue
        base_lower = base.lower()
        if base_lower == stem_lower:
            exact.setdefault(ext, name)
        elif base_lower.startswith(stem_lower + "."):
            tag = base_lower[len(stem_lower) + 1:]
            tagged.append((0 if tag in _KOREAN_TAGS else 1, SUBTITLE_EXTS.index(ext), name))

    for ext in SUBTITLE_EXTS:
        if ext in exact:
            return os.path.join(folder, exact[ext])
    if tagged:
        tagged.sort()
        return os.path.join(folder, tagged[0][2])
    return ""


def read_text_file(path: str) -> str:
    """자막 파일을 인코딩을 추측해 읽는다"""
    with open(path, "rb") as f:
        raw = f.read()
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    for encoding in ("utf-8", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def load_subtitle(path: str):
    """자막 파일을 읽어 SubtitleTrack 으로 (읽을 수 없거나 비어 있으면 None)"""
    if not path or not os.path.isfile(path):
        return None
    try:
        text = read_text_file(path)
    except OSError as e:
        print(f"[자막] 파일을 읽지 못했습니다: {path} ({e})")
        return None
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".smi", ".sami"):
            cues = parse_smi(text)
        else:
            cues = parse_srt(text)
            if not cues and "<sync" in text.lower():
                cues = parse_smi(text)      # 확장자만 .srt 인 SAMI 파일
    except Exception as e:
        print(f"[자막] 형식을 해석하지 못했습니다: {path} ({e})")
        return None
    track = SubtitleTrack(cues, source_path=path)
    return track if len(track) else None


# ----------------------------------------------------------------------
# SRT
# ----------------------------------------------------------------------
_SRT_TIME = r"(\d{1,2}):(\d{1,2}):(\d{1,2})(?:[,.](\d{1,3}))?"
_SRT_TIMING = re.compile(_SRT_TIME + r"\s*-->\s*" + _SRT_TIME)
_TAG = re.compile(r"<[^>]+>")
_ASS_TAG = re.compile(r"\{\\[^}]*\}")


def _ms(h, m, s, frac) -> int:
    frac = (frac or "0").ljust(3, "0")[:3]
    return ((int(h) * 60 + int(m)) * 60 + int(s)) * 1000 + int(frac)


def _clean(text: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = _TAG.sub("", text)
    text = _ASS_TAG.sub("", text)
    text = html.unescape(text).replace("\xa0", " ")
    lines = [line.strip() for line in text.replace("\r", "").split("\n")]
    return "\n".join(line for line in lines if line)


def parse_srt(text: str) -> list:
    cues = []
    blocks = re.split(r"\n\s*\n", text.replace("\r\n", "\n").replace("\r", "\n"))
    for block in blocks:
        lines = [line for line in block.split("\n")]
        for i, line in enumerate(lines):
            match = _SRT_TIMING.search(line)
            if not match:
                continue
            g = match.groups()
            start = _ms(*g[0:4])
            end = _ms(*g[4:8])
            body = _clean("\n".join(lines[i + 1:]))
            if body and end > start:
                cues.append(Cue(start, end, body))
            break
    return cues


# ----------------------------------------------------------------------
# SAMI (.smi)
# ----------------------------------------------------------------------
_SYNC = re.compile(r"<sync\b[^>]*?\bstart\s*=\s*[\"']?(-?\d+)[^>]*>", re.IGNORECASE)
_P_CLASS = re.compile(r"<p\b[^>]*?\bclass\s*=\s*[\"']?([\w-]+)[^>]*>", re.IGNORECASE)
_BODY_END = re.compile(r"</body\s*>", re.IGNORECASE)


def _pick_class(classes: list) -> str:
    """여러 언어가 한 파일에 들어 있으면 한국어 자막을 고른다"""
    for name in classes:
        upper = name.upper()
        if "KR" in upper or "KO" in upper:
            return name
    return classes[0] if classes else ""


def parse_smi(text: str) -> list:
    end_match = _BODY_END.search(text)
    body = text[:end_match.start()] if end_match else text
    syncs = list(_SYNC.finditer(body))
    if not syncs:
        return []

    # 1) SYNC 마다 (시각, {언어: 내용}) 로 나눈다
    entries = []
    classes = []
    for n, match in enumerate(syncs):
        start = int(match.group(1))
        chunk_end = syncs[n + 1].start() if n + 1 < len(syncs) else len(body)
        chunk = body[match.end():chunk_end]
        parts = {}
        p_tags = list(_P_CLASS.finditer(chunk))
        if p_tags:
            for k, p in enumerate(p_tags):
                name = p.group(1)
                if name not in classes:
                    classes.append(name)
                p_end = p_tags[k + 1].start() if k + 1 < len(p_tags) else len(chunk)
                parts[name] = chunk[p.end():p_end]
        else:
            parts[""] = chunk
        entries.append((start, parts))

    chosen = _pick_class(classes)

    # 2) 고른 언어의 내용을 다음 SYNC 까지 보여 준다 (&nbsp; 뿐이면 지우기 표시)
    cues = []
    for n, (start, parts) in enumerate(entries):
        # 다른 언어만 있는 SYNC 는 건너뛴다 (그 시각에 앞 자막은 끝난다)
        raw = parts.get(chosen, parts.get("", ""))
        content = _clean(raw)
        if not content:
            continue
        end = None
        for later_start, _ in entries[n + 1:]:
            if later_start > start:
                end = later_start
                break
        if end is None:
            end = start + _LAST_CUE_MS
        cues.append(Cue(start, end, content))
    return cues
