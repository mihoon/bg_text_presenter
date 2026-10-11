# -*- coding: utf-8 -*-
"""
텍스트 파일 문단 처리 유틸리티
- 빈 줄(공백만 있는 줄 포함)을 기준으로 문단을 분리한다.
"""


def split_paragraphs(text: str) -> list:
    """텍스트를 빈 줄 기준으로 문단 리스트로 분리한다.

    - 빈 줄: 공백/탭만 있는 줄 포함
    - 각 문단은 좌우 공백을 제거하고, 문단 내부 줄은 유지한다.
    """
    paragraphs = []
    current = []
    for raw_line in text.splitlines():
        if raw_line.strip() == "":
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
        else:
            current.append(raw_line.rstrip())
    if current:
        paragraphs.append("\n".join(current).strip())
    return paragraphs


def join_paragraphs(paragraphs: list) -> str:
    """문단 리스트를 빈 줄로 구분된 원본 텍스트로 다시 조립한다."""
    return "\n\n".join(paragraphs)


def load_text_file(file_path: str) -> list:
    """텍스트 파일을 읽어 문단 리스트를 반환한다. (인코딩 자동 감지)"""
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return split_paragraphs(f.read())
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"파일을 읽을 수 없습니다: {file_path}")


def preview_of(paragraph: str, max_chars: int = 24) -> str:
    """문단 목록에 표시할 한 줄 미리보기 문자열."""
    one_line = paragraph.replace("\n", " ").strip()
    if len(one_line) > max_chars:
        return one_line[: max_chars - 1] + "…"
    return one_line