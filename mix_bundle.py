# -*- coding: utf-8 -*-
"""
묶음 (여러 종류의 파일을 한데 모아 보기)

왼쪽 목록에서 파일 하나를 다른 파일 위에 끌어다 겹치면 '묶음'이 된다. 묶음은
텍스트 문단·PPT 슬라이드·이미지 폴더 사진·동영상을 카드 한 줄로 늘어놓고,
종류가 달라도 끌어서 순서를 마음대로 섞을 수 있다. 원본 파일은 바꾸지 않는다 -
순서는 묶음 파일(.bgmix, JSON)에만 저장된다.

카드(항목) 하나는 key 로 구분한다.
    text  \\t <텍스트 파일> \\t <문단 번호>
    slide \\t <PPT 파일>    \\t <슬라이드 번호>      (0부터)
    image \\t <이미지 폴더> \\t <파일 이름>
    video \\t <동영상 파일>
    wait  \\t <PPT 파일>                            (아직 슬라이드를 그림으로 만드는 중)

원본이 바뀌면(문단이 늘거나 사진을 추가) 저장된 순서에 없는 새 카드는 같은 파일의
마지막 카드 바로 뒤에 붙고, 없어진 카드는 빠진다.
"""
import json
import os
import time

MIX_EXT = ".bgmix"
VERSION = 1


def is_mix_file(path) -> bool:
    return bool(path) and str(path).lower().endswith(MIX_EXT)


def mixes_dir(settings_dir: str) -> str:
    path = os.path.join(settings_dir, "mixes")
    os.makedirs(path, exist_ok=True)
    return path


# ----------------------------------------------------------------------
# 파일
# ----------------------------------------------------------------------
def new_mix_path(settings_dir: str) -> str:
    folder = mixes_dir(settings_dir)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = os.path.join(folder, f"묶음_{stamp}")
    path = base + MIX_EXT
    n = 2
    while os.path.exists(path):
        path = f"{base}_{n}{MIX_EXT}"
        n += 1
    return path


def load_mix(path) -> dict:
    """{'sources': [...], 'order': [...], 'name': str} - 읽을 수 없으면 빈 묶음"""
    data = {"sources": [], "order": [], "name": ""}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        if isinstance(raw, dict):
            data["sources"] = [str(s) for s in raw.get("sources", []) if s]
            data["order"] = [str(k) for k in raw.get("order", []) if k]
            data["name"] = str(raw.get("name", "") or "")
    except Exception:
        pass
    return data


def save_mix(path, data: dict):
    payload = {
        "version": VERSION,
        "name": data.get("name", ""),
        "sources": list(data.get("sources", [])),
        "order": list(data.get("order", [])),
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def create_mix(settings_dir: str, sources) -> str:
    path = new_mix_path(settings_dir)
    save_mix(path, {"sources": unique_sources(sources), "order": []})
    return path


def unique_sources(sources):
    """중복을 빼고, 묶음이 들어 있으면 그 안의 원본들로 풀어서 넣는다"""
    out = []
    for s in sources:
        if is_mix_file(s):
            inner = load_mix(s)["sources"]
        else:
            inner = [s]
        for p in inner:
            if p and p not in out:
                out.append(p)
    return out


def add_sources(path, sources, order_first=None):
    """묶음에 파일을 더한다. order_first 는 들어온 묶음의 카드 순서(있으면 이어 붙인다)"""
    data = load_mix(path)
    before = list(data["sources"])
    for p in unique_sources(sources):
        if p not in data["sources"]:
            data["sources"].append(p)
    if order_first:
        data["order"] = list(data["order"]) + [k for k in order_first if k not in data["order"]]
    if data["sources"] != before or order_first:
        save_mix(path, data)
    return data


def display_name(data: dict) -> str:
    if data.get("name"):
        return data["name"]
    names = [os.path.splitext(os.path.basename(p.rstrip("\\/")))[0] or p for p in data.get("sources", [])]
    return " + ".join(names) if names else "(빈 묶음)"


# ----------------------------------------------------------------------
# 카드
# ----------------------------------------------------------------------
class MixEntry:
    __slots__ = ("kind", "source", "index", "path", "title", "note")

    def __init__(self, kind, source, index=0, path="", title="", note=""):
        self.kind = kind          # text / slide / image / video / wait
        self.source = source      # 원본 파일(폴더)
        self.index = index        # 문단·슬라이드 번호
        self.path = path          # 화면에 띄울 그림·동영상 경로 (text 는 "")
        self.title = title        # 카드에 쓸 글
        self.note = note          # 슬라이드 노트 (slide 만)

    @property
    def key(self) -> str:
        if self.kind == "text":
            return f"text\t{self.source}\t{self.index}"
        if self.kind == "slide":
            return f"slide\t{self.source}\t{self.index}"
        if self.kind == "image":
            return f"image\t{self.source}\t{os.path.basename(self.path)}"
        if self.kind == "video":
            return f"video\t{self.source}"
        return f"wait\t{self.source}"

    def __repr__(self):
        return f"MixEntry({self.kind}, {os.path.basename(self.source)}, {self.index})"


def source_entries(source, *, load_text, read_ppt_cache, scan_images, is_ppt, is_video):
    """원본 하나 → 카드 목록 (원래 순서). 읽기 함수들은 바깥에서 넣어 준다(시험하기 쉽게)."""
    if not source or not os.path.exists(source):
        return []
    if os.path.isdir(source):
        return [MixEntry("image", source, i, p, os.path.basename(p))
                for i, p in enumerate(scan_images(source))]
    if is_ppt(source):
        cached = read_ppt_cache(source)
        if not cached:
            return [MixEntry("wait", source, 0, "", os.path.basename(source))]
        notes = cached.get("notes") or []
        return [MixEntry("slide", source, i, p, f"{os.path.splitext(os.path.basename(source))[0]} {i + 1}",
                         notes[i] if i < len(notes) else "")
                for i, p in enumerate(cached.get("slides") or [])]
    if is_video(source):
        return [MixEntry("video", source, 0, source, os.path.basename(source))]
    try:
        paragraphs = load_text(source)
    except Exception:
        return []
    return [MixEntry("text", source, i, "", para) for i, para in enumerate(paragraphs)]


def arrange(entries_by_source, sources, order):
    """원본별 카드들을 저장된 순서대로 늘어놓는다.

    - 저장된 순서에 있는 카드는 그 순서대로
    - 순서에 없는 새 카드는 같은 원본의 (앞에 놓인) 마지막 카드 바로 뒤에, 그런 것이
      없으면 맨 끝에
    - 'wait'(PPT 준비 중) 카드와 그 PPT 의 슬라이드는 서로 같은 자리로 본다
    """
    available = []
    for src in sources:
        available.extend(entries_by_source.get(src, []))
    by_key = {e.key: e for e in available}
    result = []
    used = set()
    for key in order or []:
        e = by_key.get(key)
        if e is not None and key not in used:
            result.append(e)
            used.add(key)
            continue
        # 순서에 'wait' 가 있었는데 이제 슬라이드가 준비됐다 / 반대 - 그 자리에 통째로 넣는다
        if key.startswith("wait\t") or key.startswith("slide\t"):
            src = key.split("\t")[1]
            if key.startswith("wait\t"):
                group = [x for x in entries_by_source.get(src, []) if x.key not in used]
            else:
                group = [x for x in entries_by_source.get(src, [])
                         if x.kind == "wait" and x.key not in used]
            for x in group:
                result.append(x)
                used.add(x.key)
    for e in available:
        if e.key in used:
            continue
        # 같은 원본의 마지막 카드 뒤
        pos = None
        for i in range(len(result) - 1, -1, -1):
            if result[i].source == e.source:
                pos = i + 1
                break
        if pos is None:
            result.append(e)
        else:
            result.insert(pos, e)
        used.add(e.key)
    return result


def build_entries(data: dict, **readers):
    by_source = {src: source_entries(src, **readers) for src in data.get("sources", [])}
    return arrange(by_source, data.get("sources", []), data.get("order", []))


def _key_source(key: str) -> str:
    parts = key.split("\t")
    return parts[1] if len(parts) > 1 else ""


def save_order(path, entries):
    """지금 카드 순서를 저장한다.

    PPT 를 다시 그림으로 만드는 중이면 그 PPT 의 슬라이드들은 ⏳ 카드 하나로 묶여 있다.
    이때 ⏳ 하나만 저장하면 슬라이드 사이사이에 섞어 둔 순서가 없어지므로, 예전에
    저장한 슬라이드 순서를 '바로 앞 카드' 기준으로 기억해 두었다가 그 뒤에 다시 넣는다.
    """
    data = load_mix(path)
    old = data.get("order", [])
    waiting = {e.source for e in entries if e.kind == "wait"}
    present = {e.key for e in entries}

    def held(key):          # 준비 중인 PPT 의 (지금은 화면에 없는) 슬라이드 열쇠
        return key.startswith("slide\t") and _key_source(key) in waiting

    anchored, orphans = {}, {}
    last = None
    for k in old:
        if held(k):
            if last is None or last in present:
                anchored.setdefault(last, []).append(k)
            else:
                orphans.setdefault(_key_source(k), []).append(k)
        elif not (k.startswith("wait\t") and _key_source(k) in waiting):
            last = k
    held_sources = {_key_source(k) for ks in anchored.values() for k in ks}

    out = list(anchored.get(None, []))
    for e in entries:
        if e.kind == "wait":
            extra = orphans.get(e.source, [])
            if extra:
                out.extend(extra)
            elif e.source not in held_sources:
                out.append(e.key)
        else:
            out.append(e.key)
            out.extend(anchored.get(e.key, []))
    data["order"] = out
    save_mix(path, data)
