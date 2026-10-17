# -*- coding: utf-8 -*-
"""
왼쪽 아래 '송출할 목록'의 폴더 (예: 교사 예배 / 어른 예배)

- 폴더는 이 프로그램 안에서만 쓰는 '목록 폴더'다. 실제 파일을 옮기거나 복사하지 않고,
  파일 경로만 담는다. 그래서 같은 파일을 여러 폴더에 함께 넣을 수 있다.
- 한 폴더 안에서는 같은 파일이 두 번 들어가지 않는다.
- 폴더 밖의 항목(예전부터 있던 목록)은 그대로 'loose' 목록으로 둔다 (설정 text_files/paths).

항목 위치는 (group, index) 로 나타낸다. group 은 폴더 번호, 폴더 밖이면 -1.
"""
import json

LOOSE = -1


class Library:
    def __init__(self, loose=None, folders=None):
        self.loose = [p for p in (loose or []) if p]
        self.folders = []
        for f in folders or []:
            if not isinstance(f, dict):
                continue
            items = []
            for p in f.get("items") or []:
                if p and p not in items:
                    items.append(str(p))
            self.folders.append({"name": str(f.get("name") or "폴더"), "items": items,
                                 "open": bool(f.get("open", True))})

    # ------------------------------------------------------------------
    # 저장
    # ------------------------------------------------------------------
    @staticmethod
    def folders_from_json(raw) -> list:
        if not raw:
            return []
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            return []
        return data if isinstance(data, list) else []

    def folders_to_json(self) -> str:
        return json.dumps(self.folders, ensure_ascii=False)

    # ------------------------------------------------------------------
    # 찾기
    # ------------------------------------------------------------------
    def container(self, group: int) -> list:
        return self.loose if group == LOOSE else self.folders[group]["items"]

    def path_at(self, ref):
        group, index = ref
        try:
            return self.container(group)[index]
        except (IndexError, TypeError):
            return None

    def locate(self, path) -> list:
        """그 파일이 있는 모든 자리 [(group, index), ...] (폴더 밖이 먼저)"""
        refs = [(LOOSE, i) for i, p in enumerate(self.loose) if p == path]
        for g, f in enumerate(self.folders):
            refs += [(g, i) for i, p in enumerate(f["items"]) if p == path]
        return refs

    def contains(self, path) -> bool:
        return bool(self.locate(path))

    def all_paths(self) -> list:
        out = []
        for p in self.loose + [p for f in self.folders for p in f["items"]]:
            if p not in out:
                out.append(p)
        return out

    # ------------------------------------------------------------------
    # 넣기 · 빼기
    # ------------------------------------------------------------------
    def add(self, paths, group: int = LOOSE) -> list:
        """끝에 더한다 (그 자리에 이미 있으면 건너뜀). 새로 들어간 것만 돌려준다"""
        target = self.container(group)
        added = []
        for p in paths:
            if p and p not in target:
                target.append(p)
                added.append(p)
        return added

    def remove(self, refs):
        """여러 자리를 한꺼번에 뺀다 (번호가 밀리지 않게 뒤에서부터)"""
        for group, index in sorted(set(refs), key=lambda r: (r[0], r[1]), reverse=True):
            items = self.container(group)
            if 0 <= index < len(items):
                del items[index]

    def place(self, refs, target_group: int, position=None, copy: bool = False) -> list:
        """refs 의 파일들을 target_group 의 position 자리(없으면 끝)에 놓는다.

        copy=False 면 원래 자리에서 빼고(옮기기), True 면 원래 자리에 그대로 둔다(함께 넣기).
        이미 그 폴더에 있는 파일은 다시 넣지 않는다 (옮기기라면 원래 자리만 정리된다).
        놓인 파일 경로들을 돌려준다.
        """
        paths = []
        for ref in refs:
            p = self.path_at(ref)
            if p is not None and p not in paths:
                paths.append(p)
        target = self.container(target_group)
        marker = object()                       # 빼는 동안 번호가 밀려도 놓을 자리를 잃지 않게
        position = len(target) if position is None else max(0, min(position, len(target)))
        valid = [r for r in refs if self.path_at(r) is not None]
        target.insert(position, marker)
        if not copy:
            # 표시를 끼워 넣어 같은 폴더 안의 뒤쪽 번호가 하나씩 밀렸다
            shifted = [(g, i + 1 if g == target_group and i >= position else i) for g, i in valid]
            self.remove(shifted)
        at = next(i for i, x in enumerate(target) if x is marker)
        target.pop(at)
        new = [p for p in paths if p not in target]
        target[at:at] = new
        return paths

    def replace(self, ref, new_path):
        """한 자리의 파일을 다른 것(예: 묶음)으로 바꾼다 (그 폴더에 이미 있으면 그 자리만 지운다)"""
        group, index = ref
        items = self.container(group)
        if not (0 <= index < len(items)):
            return
        if new_path in items and items.index(new_path) != index:
            del items[index]
        else:
            items[index] = new_path

    def expand(self, ref, new_paths):
        """한 자리를 여러 파일로 풀어 놓는다 (묶음 풀기) - 그 폴더에 이미 있는 것은 건너뜀"""
        group, index = ref
        items = self.container(group)
        if not (0 <= index < len(items)):
            return []
        del items[index]
        new = []
        for p in new_paths:
            if p not in items and p not in new:
                new.append(p)
        items[index:index] = new
        return new

    # ------------------------------------------------------------------
    # 폴더
    # ------------------------------------------------------------------
    def new_folder(self, name: str) -> int:
        name = (name or "").strip() or "새 폴더"
        base, n = name, 2
        names = {f["name"] for f in self.folders}
        while name in names:
            name = f"{base} ({n})"
            n += 1
        self.folders.append({"name": name, "items": [], "open": True})
        return len(self.folders) - 1

    def rename_folder(self, group: int, name: str):
        name = (name or "").strip()
        if name and 0 <= group < len(self.folders):
            self.folders[group]["name"] = name

    def delete_folder(self, group: int):
        if 0 <= group < len(self.folders):
            del self.folders[group]

    def toggle_folder(self, group: int):
        if 0 <= group < len(self.folders):
            self.folders[group]["open"] = not self.folders[group]["open"]

    def move_folders(self, groups, target_group: int, after: bool = False):
        """폴더 순서 바꾸기"""
        groups = sorted({g for g in groups if 0 <= g < len(self.folders)})
        if not groups:
            return
        marker = object()
        pos = len(self.folders) if target_group is None or target_group < 0 else target_group + (1 if after else 0)
        self.folders.insert(pos, marker)
        moving = [self.folders[g + (1 if g >= pos else 0)] for g in groups]
        ids = {id(f) for f in moving}
        self.folders = [f for f in self.folders if id(f) not in ids]
        at = next(i for i, f in enumerate(self.folders) if f is marker)
        self.folders[at:at + 1] = moving
