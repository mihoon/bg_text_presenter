# -*- coding: utf-8 -*-
"""
프로그램 버전

새 버전을 내보낼 때는 APP_VERSION 숫자를 올리고 RELEASE_NOTES 에 바뀐 점을 적은 뒤
GitHub 에 올린다. 그러면 GitHub Actions(.github/workflows/release.yml)가 exe 를
만들어 Releases 에 올리고, 이미 설치된 프로그램은 켤 때 업데이트 창을 띄운다.
"""

APP_VERSION = "1.0.0"

RELEASE_NOTES = """\
- 🔄 새 버전 알림: GitHub 에 새 버전이 올라오면 프로그램을 켤 때 업데이트 창이 뜹니다.
  [지금 업데이트] 를 누르면 내려받아 바꿔 끼우고 다시 켜집니다.
- 🔗 묶음: 왼쪽 목록에서 한 항목을 다른 항목 위에 끌어다 겹치면 텍스트·PPT·사진·동영상
  카드를 한 화면에서 보고, 종류가 달라도 끌어서 순서를 섞을 수 있습니다.
"""
