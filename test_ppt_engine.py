# -*- coding: utf-8 -*-
"""
파워포인트 슬라이드 엔진 테스트 (GUI 없이 실행)

사용법:
    python test_ppt_engine.py                  :: 폴더의 sample_test.pptx 로 테스트
    python test_ppt_engine.py "D:\\설교\\주보.pptx"

확인 항목
1. 첫 슬라이드가 준비되기까지 걸린 시간 (체감 대기 시간)
2. 전체 내보내기 시간
3. 두 번째 로드(캐시 히트) 시간 - 파워포인트를 띄우지 않아야 하므로 매우 빨라야 한다
"""
import os
import sys
import time

import ppt_engine


def _fmt(seconds: float) -> str:
    return f"{seconds:.2f}초"


def run(path: str):
    print(f"대상 파일: {path}")
    available, message = ppt_engine.powerpoint_support()
    print(f"파워포인트 사용 가능: {available}")
    if not available:
        print(f"  → {message}")
        return 1

    cache_dir = ppt_engine.cache_dir_for(path)
    print(f"캐시 폴더: {cache_dir}")
    print(f"기존 캐시 있음: {ppt_engine.read_cache(path) is not None}")

    # --- 1회차 ---
    print("\n[1회차] 내보내기 시작")
    started = time.perf_counter()
    timings = {"first": None}

    notes_found = {"n": 0}

    def on_slide(index, slide_path, note=""):
        elapsed = time.perf_counter() - started
        if timings["first"] is None:
            timings["first"] = elapsed
        if note.strip():
            notes_found["n"] += 1
        size_kb = os.path.getsize(slide_path) // 1024 if os.path.exists(slide_path) else 0
        note_mark = f"  노트 {len(note)}자" if note.strip() else ""
        print(f"  슬라이드 {index + 1:>3}  {_fmt(elapsed):>8}  {size_kb:>5}KB{note_mark}")

    result = ppt_engine.export_blocking(path, on_slide=on_slide, extract_notes=True)
    total = time.perf_counter() - started

    if result["error"]:
        print(f"\n실패: {result['error']}")
        return 1

    print(f"\n  장수:              {result['count']}")
    print(f"  노트 있는 슬라이드: {notes_found['n']}장")
    print(f"  첫 장 준비까지:    {_fmt(timings['first'] or 0)}   ← 사용자 체감 대기")
    print(f"  전체 완료:         {_fmt(total)}")
    if result["count"]:
        print(f"  장당 평균:         {_fmt(total / result['count'])}")

    # --- 2회차 (캐시 히트) ---
    print("\n[2회차] 캐시에서 읽기")
    started = time.perf_counter()
    cached = ppt_engine.read_cache(path)
    elapsed = time.perf_counter() - started
    if cached:
        print(f"  {cached['count']}장 읽음 - {_fmt(elapsed)}  (파워포인트 미실행)")
        missing = [p for p in cached["slides"] if not os.path.exists(p)]
        print(f"  누락 파일: {len(missing)}개")
    else:
        print("  캐시를 읽지 못했습니다 (내보내기가 완료되지 않았을 수 있음)")
        return 1

    print("\n정리 중...")
    ppt_engine.shutdown()
    print("완료")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1:
        target = sys.argv[1]
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        target = os.path.join(here, "sample_test.pptx")

    if not os.path.exists(target):
        print(f"파일이 없습니다: {target}")
        print("사용법: python test_ppt_engine.py \"경로\\파일.pptx\"")
        sys.exit(1)

    sys.exit(run(target))
