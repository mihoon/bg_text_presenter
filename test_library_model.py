# -*- coding: utf-8 -*-
"""송출할 목록의 폴더 (목록 폴더) 테스트 - python test_library_model.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from library_model import Library, LOOSE

FAILURES = []


def check(label, condition, detail=""):
    print(f"   {'OK  ' if condition else '실패'} {label}  {'' if condition else detail}")
    if not condition:
        FAILURES.append(label)


def main():
    print("1) 폴더 만들기 · 넣기")
    lib = Library(["찬양.txt", "설교.pptx", "광고"], [])
    t = lib.new_folder("교사 예배")
    a = lib.new_folder("어른 예배")
    check("폴더 2개", [f["name"] for f in lib.folders] == ["교사 예배", "어른 예배"])
    check("같은 이름이면 번호를 붙임", lib.folders[lib.new_folder("교사 예배")]["name"] == "교사 예배 (2)")
    lib.delete_folder(2)

    lib.place([(LOOSE, 0)], t)                                   # 찬양 → 교사 예배 (옮기기)
    check("옮기기: 폴더 밖에서 빠지고 폴더에 들어감", lib.loose == ["설교.pptx", "광고"] and lib.folders[t]["items"] == ["찬양.txt"])
    lib.place([(t, 0)], a, copy=True)                            # 찬양 → 어른 예배에도 (함께 넣기)
    check("함께 넣기: 두 폴더 모두에 있음", lib.folders[t]["items"] == ["찬양.txt"] and lib.folders[a]["items"] == ["찬양.txt"])
    check("찾기: 두 자리", lib.locate("찬양.txt") == [(t, 0), (a, 0)])
    lib.place([(a, 0)], a, copy=True)
    check("같은 폴더에는 두 번 들어가지 않음", lib.folders[a]["items"] == ["찬양.txt"])

    print("\n2) 자리 지정 · 순서")
    lib.place([(LOOSE, 0), (LOOSE, 1)], t, position=0)          # 설교·광고를 교사 예배 맨 앞에
    check("여러 개를 한 번에 원하는 자리로", lib.folders[t]["items"] == ["설교.pptx", "광고", "찬양.txt"] and lib.loose == [])
    lib.place([(t, 2)], t, position=0)                           # 같은 폴더 안에서 순서 바꾸기
    check("폴더 안 순서 바꾸기", lib.folders[t]["items"] == ["찬양.txt", "설교.pptx", "광고"])
    lib.place([(t, 0)], t, position=3)
    check("맨 뒤로", lib.folders[t]["items"] == ["설교.pptx", "광고", "찬양.txt"])
    lib.place([(t, 1)], LOOSE)                                   # 폴더에서 꺼내기
    check("폴더에서 꺼내기", lib.loose == ["광고"] and "광고" not in lib.folders[t]["items"])
    lib.place([(a, 0)], t)                                       # 이미 있는 파일을 옮겨 넣기 → 원래 자리만 정리
    check("이미 있는 폴더로 옮기면 중복 없이 원래 자리만 빠짐",
          lib.folders[t]["items"] == ["설교.pptx", "찬양.txt"] and lib.folders[a]["items"] == [])

    print("\n3) 묶음으로 바꾸기 / 풀기")
    lib.replace((t, 0), "묶음.bgmix")
    check("한 자리를 묶음으로", lib.folders[t]["items"] == ["묶음.bgmix", "찬양.txt"])
    lib.expand((t, 0), ["설교.pptx", "찬양.txt", "영상.mp4"])
    check("묶음 풀기 (이미 있는 찬양은 건너뜀)", lib.folders[t]["items"] == ["설교.pptx", "영상.mp4", "찬양.txt"])

    print("\n4) 폴더 순서 · 이름 · 지우기")
    c = lib.new_folder("수요 예배")
    lib.move_folders([c], 0)
    check("폴더를 맨 위로", [f["name"] for f in lib.folders] == ["수요 예배", "교사 예배", "어른 예배"])
    lib.move_folders([0], 2, after=True)
    check("폴더를 맨 아래로", [f["name"] for f in lib.folders] == ["교사 예배", "어른 예배", "수요 예배"])
    lib.rename_folder(2, "  금요 예배 ")
    check("이름 바꾸기", lib.folders[2]["name"] == "금요 예배")
    lib.toggle_folder(0)
    check("접기", lib.folders[0]["open"] is False)
    lib.delete_folder(2)
    check("폴더 지우기 (파일은 다른 곳에 그대로)", len(lib.folders) == 2 and lib.loose == ["광고"])

    print("\n5) 저장 · 읽기")
    raw = lib.folders_to_json()
    again = Library(["광고"], Library.folders_from_json(raw))
    check("그대로 되살아남", again.folders == lib.folders)
    check("망가진 저장값은 빈 폴더 목록", Library.folders_from_json("{oops") == [])
    check("모든 파일 (중복 없이)", again.all_paths() == ["광고", "설교.pptx", "영상.mp4", "찬양.txt"])

    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
