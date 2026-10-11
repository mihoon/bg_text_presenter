# -*- coding: utf-8 -*-
"""묶음(mix_bundle) 로직 테스트 - python test_mix_bundle.py"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import mix_bundle as mb

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"   OK   {label}")
    else:
        print(f"   실패 {label}  {detail}")
        FAILURES.append(label)


def main():
    tmp = tempfile.mkdtemp(prefix="bgpt_mix_")
    try:
        text = os.path.join(tmp, "찬양.txt")
        with open(text, "w", encoding="utf-8") as f:
            f.write("1절\n\n2절\n\n후렴")
        folder = os.path.join(tmp, "광고")
        os.makedirs(folder)
        for n in ("01.jpg", "02.jpg"):
            open(os.path.join(folder, n), "wb").close()
        ppt = os.path.join(tmp, "설교.pptx")
        open(ppt, "wb").close()
        video = os.path.join(tmp, "영상.mp4")
        open(video, "wb").close()

        ppt_cache = {"ready": False}

        def read_cache(p):
            if not ppt_cache["ready"]:
                return None
            return {"slides": [p + f".s{i}.png" for i in range(3)], "notes": ["", "노트2", ""], "count": 3}

        readers = dict(
            load_text=lambda p: [x for x in open(p, encoding="utf-8").read().split("\n\n") if x.strip()],
            read_ppt_cache=read_cache,
            scan_images=lambda d: sorted(os.path.join(d, n) for n in os.listdir(d)),
            is_ppt=lambda p: p.endswith(".pptx"),
            is_video=lambda p: p.endswith(".mp4"),
        )

        print("1) 묶음 만들기 / 읽기")
        path = mb.create_mix(tmp, [text, folder, text, ppt])
        data = mb.load_mix(path)
        check("확장자 .bgmix, mixes 폴더", mb.is_mix_file(path) and os.path.basename(os.path.dirname(path)) == "mixes")
        check("원본 중복 제거", data["sources"] == [text, folder, ppt], str(data["sources"]))
        check("이름은 원본 이름을 이어서", mb.display_name(data) == "찬양 + 광고 + 설교", mb.display_name(data))

        print("\n2) 카드 늘어놓기")
        entries = mb.build_entries(data, **readers)
        kinds = [e.kind for e in entries]
        check("텍스트 3 + 사진 2 + PPT 준비 중 1", kinds == ["text"] * 3 + ["image"] * 2 + ["wait"], str(kinds))
        check("문단 글", entries[2].title == "후렴")

        print("\n3) 종류가 달라도 순서 섞기 → 저장 → 다시 읽기")
        mixed = [entries[3], entries[0], entries[5], entries[1], entries[4], entries[2]]
        mb.save_order(path, mixed)
        again = mb.build_entries(mb.load_mix(path), **readers)
        check("섞은 순서 그대로", [e.key for e in again] == [e.key for e in mixed],
              str([e for e in again]))

        print("\n4) PPT 준비가 끝나면 '준비 중' 자리에 슬라이드가 들어감")
        ppt_cache["ready"] = True
        ready = mb.build_entries(mb.load_mix(path), **readers)
        kinds = [e.kind for e in ready]
        check("준비 중 자리(3번째)에 슬라이드 3장", kinds == ["image", "text", "slide", "slide", "slide", "text", "image", "text"],
              str(kinds))
        check("슬라이드 노트도 따라옴", ready[3].note == "노트2")
        mb.save_order(path, ready)
        moved = [ready[4]] + ready[:4] + ready[5:]
        mb.save_order(path, moved)
        check("슬라이드도 따로 옮길 수 있음",
              [e.key for e in mb.build_entries(mb.load_mix(path), **readers)] == [e.key for e in moved])

        print("\n5) 원본이 바뀐 경우")
        with open(text, "w", encoding="utf-8") as f:
            f.write("1절\n\n2절\n\n후렴\n\n4절")
        os.remove(os.path.join(folder, "02.jpg"))
        changed = mb.build_entries(mb.load_mix(path), **readers)
        texts = [e for e in changed if e.kind == "text"]
        check("새 문단은 같은 파일의 마지막 카드 뒤", changed.index(texts[-1]) == changed.index(texts[-2]) + 1
              and texts[-1].title == "4절", str(changed))
        check("없어진 사진은 빠짐", not any(e.kind == "image" and e.path.endswith("02.jpg") for e in changed))

        print("\n6) 묶음에 더하기 / 묶음끼리 합치기")
        mb.add_sources(path, [video])
        data = mb.load_mix(path)
        check("동영상 추가", data["sources"][-1] == video)
        other = mb.create_mix(tmp, [text, video])
        path2 = mb.create_mix(tmp, [folder])
        mb.add_sources(path2, [other])
        check("묶음을 넣으면 그 안의 원본이 들어감", mb.load_mix(path2)["sources"] == [folder, text, video],
              str(mb.load_mix(path2)["sources"]))
        check("같은 이름이 겹치지 않는 새 파일", path != path2 != other)

        print("\n6-1) PPT 를 다시 그림으로 만드는 중에 순서를 바꿔도 슬라이드 자리는 그대로")
        ppt_cache["ready"] = True
        p3 = mb.create_mix(tmp, [ppt, text])
        ready = mb.build_entries(mb.load_mix(p3), **readers)
        s0, s1, s2 = [e for e in ready if e.kind == "slide"]
        t0, t1, t2, t3 = [e for e in ready if e.kind == "text"]
        mb.save_order(p3, [s0, t0, s1, t1, s2, t2, t3])          # 슬라이드와 글을 섞어 둠
        ppt_cache["ready"] = False                              # PPT 를 고쳐서 다시 만드는 중
        waiting = mb.build_entries(mb.load_mix(p3), **readers)
        check("준비 중에는 ⏳ 카드 하나", [e.kind for e in waiting].count("wait") == 1, str(waiting))
        wait_card = next(e for e in waiting if e.kind == "wait")
        texts = [e for e in waiting if e.kind == "text"]
        mb.save_order(p3, [texts[3], wait_card, texts[0], texts[1], texts[2]])   # 마지막 글을 맨 앞으로
        ppt_cache["ready"] = True
        back = mb.build_entries(mb.load_mix(p3), **readers)
        check("다시 준비되면 슬라이드가 섞어 둔 자리로 돌아감",
              [e.key for e in back] == [s0.key, t3.key, t0.key, s1.key, t1.key, s2.key, t2.key],
              str(back))

        print("\n7) 망가진 묶음 파일")
        bad = os.path.join(tmp, "bad.bgmix")
        with open(bad, "w") as f:
            f.write("{not json")
        check("빈 묶음으로 읽음", mb.load_mix(bad)["sources"] == [])
        check("없는 원본은 건너뜀", mb.build_entries({"sources": [os.path.join(tmp, "없음.txt")], "order": []},
                                               **readers) == [])
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
