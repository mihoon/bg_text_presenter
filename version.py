# -*- coding: utf-8 -*-
"""
프로그램 버전

새 버전을 내보낼 때는 APP_VERSION 숫자를 올리고 RELEASE_NOTES 에 바뀐 점을 적은 뒤
GitHub 에 올린다. 그러면 GitHub Actions(.github/workflows/release.yml)가 exe 를
만들어 Releases 에 올리고, 이미 설치된 프로그램은 켤 때 업데이트 창을 띄운다.
"""

APP_VERSION = "1.1.0"

RELEASE_NOTES = """\
- 🔗 묶음 카드 여러 장을 한꺼번에 옮기기: **Ctrl+누르기**(한 장씩 더하기·빼기), **Shift+누르기**(범위)로 고른 뒤
  고른 카드 하나를 끌면 모두 함께 옮겨집니다. 고른 카드는 금색 테두리와 ✓ 로 표시되고, 고르는 동안에는 송출하지 않습니다.
"""
