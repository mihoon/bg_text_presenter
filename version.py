# -*- coding: utf-8 -*-
"""
프로그램 버전

새 버전을 내보낼 때는 APP_VERSION 숫자를 올리고 RELEASE_NOTES 에 바뀐 점을 적은 뒤
GitHub 에 올린다. 그러면 GitHub Actions(.github/workflows/release.yml)가 exe 를
만들어 Releases 에 올리고, 이미 설치된 프로그램은 켤 때 업데이트 창을 띄운다.
"""

APP_VERSION = "1.1.1"

RELEASE_NOTES = """\
- 📁 이미지 폴더를 지우고 같은 이름으로 다시 만들었을 때(PPT 다시 내보내기, 구글 드라이브 동기화 등)
  사진이 제대로 나오지 않던 문제를 고쳤습니다. 이제 폴더가 바뀌면 목록·썸네일·송출 화면이 저절로 새로 고쳐집니다.
- 아직 다 써지지 않아 읽을 수 없는 사진을 누르면 까만 화면을 내보내지 않고 지금 화면을 그대로 둡니다.
"""
