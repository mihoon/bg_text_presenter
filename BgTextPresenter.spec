# -*- mode: python ; coding: utf-8 -*-
# 폴더(onedir) 방식으로 빌드한다.
#   한 파일(onefile) exe 는 실행할 때마다 안에 든 파일 전부(140MB 가까이 - Qt, 동영상
#   코덱, OpenCV 등)를 임시 폴더에 풀어 놓고 시작하기 때문에(백신 검사까지 겹치면)
#   켜는 데 10초 넘게 걸린다. 폴더 방식은 풀 것이 없어 바로 뜬다.
#   결과: dist\BgTextPresenter\BgTextPresenter.exe  (폴더째로 옮겨서 써야 한다)
from PyInstaller.utils.hooks import collect_all

datas = [('app_icon.png', '.'), ('app_icon.ico', '.')]
binaries = []
hiddenimports = [
    'PySide6.QtMultimedia', 'PySide6.QtNetwork',
    # 파워포인트 슬라이드 불러오기 (COM)
    'win32com', 'win32com.client', 'pythoncom', 'pywintypes',
    # 슬라이드를 PDF 경유로 그림으로 바꾸기 (파일에 포함 저장된 글꼴 유지)
    'pypdfium2',
]
tmp_ret = collect_all('PIL')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('cv2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
try:
    # pdfium 실행 파일(DLL)까지 함께 넣어야 exe 에서도 동작한다
    tmp_ret = collect_all('pypdfium2')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
    tmp_ret = collect_all('pypdfium2_raw')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except Exception as e:
    print(f'[spec] pypdfium2 수집 실패 (설치되어 있지 않으면 정상): {e}')

excludes = [
    'tkinter', 'unittest', 'test', 'pydoc',
    'scipy', 'matplotlib', 'pandas',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BgTextPresenter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app_icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='BgTextPresenter',
)