# -*- coding: utf-8 -*-
"""문단 분리 로직 단위 테스트"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from text_engine import split_paragraphs, join_paragraphs, preview_of

failed = []


def check(name, actual, expected):
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    if not ok:
        print(f"    expected: {expected!r}")
        print(f"    actual:   {actual!r}")
        failed.append(name)


sample = (
    "안녕하세요. 첫 번째 문단입니다.\n"
    "두 번째 줄이 이어집니다.\n"
    "\n"
    "\n"
    "   \n"
    "두 번째 문단입니다.\n"
    "세 번째 줄입니다.\n"
    "\n"
    "세 번째 문단 - 한 줄입니다."
)

paras = split_paragraphs(sample)
check("3개 문단 분리", len(paras), 3)
check("문단1 내용", paras[0], "안녕하세요. 첫 번째 문단입니다.\n두 번째 줄이 이어집니다.")
check("문단2 내용", paras[1], "두 번째 문단입니다.\n세 번째 줄입니다.")
check("문단3 내용", paras[2], "세 번째 문단 - 한 줄입니다.")

check("빈 문자열 -> []", split_paragraphs(""), [])
check("공백만 -> []", split_paragraphs("\n  \n\t\n"), [])
check("줄바꿈 없는 문단", split_paragraphs("한 줄"), ["한 줄"])
check("문단 앞뒤 공백 제거", split_paragraphs("  앞뒤 공백  \n"), ["앞뒤 공백"])

check("재조립(join)", join_paragraphs(paras), (
    "안녕하세요. 첫 번째 문단입니다.\n두 번째 줄이 이어집니다.\n\n"
    "두 번째 문단입니다.\n세 번째 줄입니다.\n\n"
    "세 번째 문단 - 한 줄입니다."
))
check("미리보기 길이 제한", preview_of("아주 긴 문단입니다" * 5, max_chars=10), "아주 긴 문단입니…")
check("미리보기 한 줄", preview_of("짧은 문단"), "짧은 문단")

print()
if failed:
    print(f"FAILED: {len(failed)} tests failed: {failed}")
    sys.exit(1)
print("All paragraph tests passed!")
sys.exit(0)