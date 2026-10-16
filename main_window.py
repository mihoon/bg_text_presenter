# -*- coding: utf-8 -*-
"""
배경 텍스트 프리젠터 - 메인 컨트롤 창
- 상단 메뉴(툴바): 배경 선택 버튼 (색상 견본 / 색상 추가 / 이미지 추가 / 동영상 추가)
- 좌측: 배경 라이브러리 (색상 / 이미지 / 동영상 탭)
- 중앙: 실시간 미리보기
- 우측: 텍스트 파일·문단 선택, 편집 모드, 글꼴/크기/색상/테두리 설정
"""
import json
import os
import sys
import time
import urllib.parse
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QThreadPool, QSettings, Slot, QRect, QRectF, QEvent, Signal, QPointF, QTimer
from PySide6.QtCore import QFileSystemWatcher
from PySide6.QtGui import (
    QIcon, QPixmap, QImage, QColor, QPainter, QFont, QFontMetrics, QGuiApplication, QFontDatabase,
    QPen, QBrush, QPainterPath, QCursor,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QToolBar,
    QComboBox, QSpinBox, QCheckBox, QTextEdit, QFileDialog, QFrame,
    QGroupBox, QTabWidget, QColorDialog, QFontComboBox, QSlider,
    QSizePolicy, QScrollArea, QRadioButton, QDialog, QStackedWidget,
    QStyledItemDelegate, QStyle, QAbstractItemView, QMenu, QToolButton,
    QMessageBox, QPlainTextEdit,
)

from presenter_window import (
    PresenterWindow, TextStyle, draw_text_overlay, render_thumbnail, draw_subtitle, fit_rect,
)
from thumbnail_utils import (
    ThumbnailTask, make_color_swatch_pixmap, make_checker_pixmap, IMAGE_EXTS, VIDEO_EXTS,
    scan_folder_images, image_has_transparency, is_video_file, image_is_readable,
    load_display_pixmap, forget_thumbnails, runtime_info,
)
from text_engine import load_text_file, join_paragraphs, split_paragraphs
from music_player import MusicController, MUSIC_EXTS
import image_notes
import mix_bundle
import subtitles
import ppt_engine
from version import APP_VERSION
from update_dialog import UpdateController

# 기본 색상 팔레트 (이름, HEX)
PRESET_COLORS = [
    ("검정", "#000000"),
    ("흰색", "#FFFFFF"),
    ("빨강", "#E53935"),
    ("주황", "#FB8C00"),
    ("노랑", "#FDD835"),
    ("초록", "#43A047"),
    ("파랑", "#1E88E5"),
    ("남색", "#3949AB"),
    ("보라", "#8E24AA"),
    ("핑크", "#D81B60"),
    ("갈색", "#6D4C41"),
    ("회색", "#757575"),
]

PRESET_COLOR_KEYS = {
    "#000000": "color_black",
    "#ffffff": "color_white",
    "#e53935": "color_red",
    "#fb8c00": "color_orange",
    "#fdd835": "color_yellow",
    "#43a047": "color_green",
    "#1e88e5": "color_blue",
    "#3949ab": "color_navy",
    "#8e24aa": "color_purple",
    "#d81b60": "color_pink",
    "#6d4c41": "color_brown",
    "#757575": "color_gray",
}

TRANSLATIONS = {
    "ko": {
        "app_title": "배경 텍스트 프리젠터 (Dual Monitor Presenter)",
        "display": " 🖥️ 디스플레이: ",
        "monitor": "모니터",
        "primary_screen": "[기본]",
        "fullscreen": "⛶ 전체화면",
        "windowed": "⛶ 창모드",
        "open_dual": "🖥️ 듀얼 창 열기",
        "close_dual": "🖥️ 듀얼 창 닫기",
        "bg_label": " 배경: ",
        "transparent": "투명 배경",
        "custom_color": "🎨 색상…",
        "add_images": "🖼️ 이미지 추가…",
        "add_videos": "🎬 동영상 추가…",
        "language": " 🌐 언어: ",
        "tab_color": "색상",
        "tab_image": "이미지",
        "tab_video": "동영상",
        "add_color_btn": "🎨 색상 추가…",
        "delete_btn": "🗑 삭제",
        "clear_all_btn": "🧹 전체 비우기",
        "clear_all_images_tip": "이미지 목록을 모두 비웁니다.",
        "clear_all_videos_tip": "동영상 목록을 모두 비웁니다.",
        "loop_play": "▶ 반복 재생",
        "stop_btn": "⏹ 정지",
        "volume": "🔊 볼륨",
        "playlist_none": "재생 목록: 선택된 동영상 없음",
        "playlist_stopped": "재생 목록: 정지됨",
        "playlist_playing_count": "재생 목록: {0}개 선택",
        "playlist_status_desc": "동영상 {0}/{1}: {2}",
        "text_lib_title": "📑 텍스트·PPT·동영상·이미지 폴더 등록",
        "btn_add_pptx": "📊 PPT…",
        "btn_add_pptx_tip": "파워포인트 파일(.pptx)을 슬라이드로 등록",
        "dialog_add_pptx": "파워포인트 파일 선택",
        "filter_pptx": "파워포인트 (*.pptx *.ppt *.pptm *.ppsx);;모든 파일 (*.*)",
        "slide_prefix": "슬라이드",
        "notes_group": "📝 슬라이드 노트",
        "notes_font_size": "🔍 글자 크기:",
        "notes_empty": "이 슬라이드에는 노트가 없습니다.",
        "image_prefix": "사진",
        "btn_notes_popup": "🗗 노트 따로 보기",
        "btn_notes_popup_tip": "노트를 따로 창으로 띄웁니다. 그 창은 언제나 이 프로그램 앞에 있고,\n다른 프로그램을 띄우면 그 프로그램 뒤로 갑니다.\n켜 두면 노트가 없는 슬라이드·사진에서는 저절로 숨고, 노트가 있으면 다시 뜹니다.\n(그 창에서 →, ←, 스페이스, PageUp/PageDown 을 눌러도 슬라이드가 넘어갑니다)",
        "notes_popup_title": "📝 노트",
        "msg_notes_popup_waiting": "노트 따로 보기를 켰습니다 - 노트가 있는 슬라이드나 사진을 송출하면 노트 창이 뜹니다",
        "notes_popup_nothing": "지금 노트를 보여 줄 슬라이드나 사진이 없습니다.\nPPT 슬라이드나 이미지 폴더의 사진을 송출하면 여기에 노트가 나타납니다.",
        "image_notes_group": "📝 사진 노트 (숨은 글)",
        "image_notes_empty": "이 사진에는 숨은 글이 없습니다.\n'✏ 숨은 글 편집'을 누르거나 사진을 우클릭해서 넣을 수 있습니다.",
        "btn_image_note_edit": "✏ 숨은 글 편집",
        "btn_image_note_edit_tip": "선택한 사진에 글을 숨겨 넣습니다. 송출 화면에는 보이지 않고,\n그 사진을 송출할 때 이 노트 칸에만 나타납니다.",
        "image_note_menu": "✏ 숨은 글(노트) 편집…",
        "image_note_dialog_title": "숨은 글 편집 - {0}",
        "image_note_dialog_info": "💡 이 글은 사진 파일 안에 숨겨 저장됩니다. 사진 모습은 그대로이고,\n이 사진을 송출할 때 오른쪽 노트 칸에만 보입니다. (화면에 새로 내보내지는 않습니다)\n※ 카카오톡 등으로 보내 사진이 다시 압축되면 숨은 글은 지워집니다.",
        "image_note_save": "💾 사진에 저장",
        "image_note_unsupported": "이 형식({0})의 사진에는 숨은 글을 넣을 수 없습니다.\nJPG 또는 PNG 사진에서 사용해 주세요.",
        "image_note_failed": "숨은 글을 저장하지 못했습니다.\n\n{0}",
        "image_note_pick_first": "숨은 글을 넣을 사진을 먼저 선택하세요.",
        "msg_image_note_saved": "숨은 글을 사진에 저장했습니다: {0}",
        "msg_image_note_removed": "숨은 글을 지웠습니다: {0}",
        "msg_ppt_exporting": "슬라이드 준비 중… {0}/{1}",
        "msg_ppt_ready": "슬라이드 {0}장 준비 완료",
        "msg_ppt_cached": "저장된 슬라이드 {0}장을 바로 불러왔습니다",
        "msg_ppt_click_to_load": "PPT는 목록에서 클릭하면 슬라이드를 준비합니다",
        "msg_slide_not_ready": "이 슬라이드는 아직 준비 중입니다",
        "msg_image_unreadable": "이 사진을 아직 읽을 수 없습니다 (저장·동기화 중일 수 있음) - 화면은 그대로 두었습니다. 잠시 뒤 다시 눌러 주세요",
        "msg_folder_reloaded": "📁 폴더 안의 사진이 바뀌어 다시 읽었습니다 ({0}장)",
        "msg_folder_missing": "📁 폴더를 찾을 수 없습니다 - 다시 생기면 저절로 읽습니다",
        "reload_folder_menu": "🔄 사진 다시 읽기 (썸네일 새로 만들기)  F5",
        "msg_ppt_opening_for_edit": "{0}번 슬라이드를 편집할 수 있도록 파워포인트를 새 창으로 엽니다…",
        "msg_ppt_edit_open_failed": "편집용 파워포인트를 여는 데 실패했습니다: {0}",
        "msg_ppt_edit_opened_as_copy": "임시 복사본으로 열었습니다 — 저장(Ctrl+S)하면 원본에 자동 반영됩니다",
        "msg_ppt_edit_synced": "편집한 내용이 반영되어 슬라이드를 새로 불러왔습니다",
        "msg_ppt_edit_synced_pending": "편집한 내용이 원본에 반영됐습니다 (슬라이드쇼 종료 후 목록에 반영됩니다)",
        "msg_text_cleared_stage": "텍스트를 내렸습니다 — ESC를 한 번 더 누르면 배경까지 지웁니다",
        "msg_all_cleared": "송출을 모두 내리고 투명 배경으로 돌아갔습니다 (ESC)",
        "btn_show_mode": "🎬 애니메이션 모드",
        "btn_show_mode_tip": (
            "파워포인트 슬라이드쇼를 직접 띄워 애니메이션·화면 전환을 그대로 재생합니다.\n"
            "이 모드에서는 파워포인트가 송출 화면을 차지하며, 이 창은 리모컨이 됩니다.\n"
            "(끄면 다시 이미지 슬라이드로 송출합니다)"
        ),
        "msg_show_started": "애니메이션 모드: 파워포인트 슬라이드쇼 실행 중 — 방향키로 진행, ESC로 종료",
        "msg_show_stopped": "애니메이션 모드를 껐습니다",
        "msg_show_slide": "슬라이드 {0}/{1} (클릭 {2}/{3})",
        "err_show_title": "애니메이션 모드",
        "err_ppt_title": "파워포인트 슬라이드",
        "err_ppt_failed": (
            "슬라이드를 불러오지 못했습니다.\n\n{0}\n\n"
            "다음을 확인해 주세요.\n"
            "• 파워포인트에서 이 파일이 정상적으로 열리는지\n"
            "• 파워포인트가 아예 문서를 못 여는 상태라면 Office를 복구해 주세요\n"
            "  (설정 - 앱 - Microsoft 365 - 수정 - 빠른 복구 / 온라인 복구)\n"
            "• 추가 기능 문제인지 확인: Windows+R 에서  powerpnt /safe\n"
            "• 인터넷·메신저로 받은 파일이면 파워포인트로 한 번 열어 [편집 사용]을 눌러 주세요\n"
            "• 자세한 진단: 프로젝트 폴더에서  python test_ppt_diag.py \"파일경로\""
        ),
        "add_txt_file": "📂 파일 추가…",
        "txt_lib_hint": "💡 텍스트·PPT·동영상 파일이나 폴더를 끌어다 놓거나(드래그&드롭) 클릭하여 불러옵니다. 목록의 한 항목을 다른 항목 위에 끌어다 겹치면 🔗 묶음이 됩니다.",
        "mix_files_suffix": "개 파일",
        "status_mix_presenting": "| 🔗 묶음 {0}/{1} 송출 중",
        "mix_ppt_preparing": "⏳ PPT 슬라이드를 준비하는 중…",
        "msg_mix_waiting": "이 PPT 는 아직 슬라이드를 그림으로 만드는 중입니다 - 잠시 뒤에 눌러 주세요",
        "msg_mix_picked": "카드 {0}장을 골랐습니다 - 끌면 함께 옮겨집니다 (그냥 누르면 고르기 풀림)",
        "msg_mix_moved": "카드 {0}장을 옮겼습니다",
        "msg_mix_created": "🔗 묶었습니다: {0}  (카드를 끌어 순서를 섞을 수 있습니다)",
        "msg_mix_added": "🔗 묶음에 넣었습니다: {0}",
        "msg_mix_ungrouped": "묶음을 풀었습니다",
        "msg_mix_ppt_failed": "묶음 안의 PPT 를 불러오지 못했습니다: {0}",
        "mix_menu_ungroup": "🔗 묶음 풀기 (원래 파일들로 되돌리기)",
        "mix_menu_hint": "다른 항목 위에 끌어다 겹치면 묶음이 됩니다",
        "btn_add_text_file": "📄 텍스트…",
        "btn_add_text_file_tip": "문단으로 사용할 텍스트 파일(.txt) 등록",
        "btn_add_image_folder": "📁 이미지 폴더…",
        "btn_add_image_folder_tip": "폴더 내의 이미지를 모아 슬라이드로 등록",
        "btn_remove_text_file": "🗑 선택 삭제",
        "btn_remove_text_file_tip": "선택한 항목들을 라이브러리에서 제거 (Ctrl/Shift 다중 선택 가능)",
        "btn_clear_text_files": "🧹 전체 비우기",
        "btn_clear_text_files_tip": "등록된 모든 텍스트 파일 및 폴더를 목록에서 비웁니다.",
        "btn_add_item": "➕ 추가",
        "btn_add_item_tip": "텍스트·PPT·동영상 파일 또는 이미지 폴더를 라이브러리에 추가",
        "add_item_menu_file": "📄 텍스트 / PPT / 동영상 파일…",
        "add_item_menu_folder": "📁 이미지 폴더…",
        "dialog_add_files": "텍스트, PPT 또는 동영상 파일 선택",
        "filter_text_and_pptx": "텍스트/PPT/동영상 (*.txt *.md *.pptx *.ppt *.pptm *.ppsx *.mp4 *.mov *.avi *.mkv *.wmv *.webm *.m4v *.mpg *.mpeg *.flv *.ts *.m2ts);;모든 파일 (*.*)",
        "item_delete_tip": "이 항목 삭제",
        "item_folder_badge": "[폴더]",
        "items_count_suffix": "장",
        "text_file_group": "📄 텍스트 파일",
        "open_txt_btn": "파일 열기…",
        "selected_file": "선택된 파일:",
        "none": "(없음)",
        "para_select_group": "📑 문단 선택 (클릭 시 송출)",
        "tab_para_list": "📋 문단 목록",
        "tab_direct_text": "✍️ 직접 입력 송출",
        "btn_direct_input": "✍️ 직접 입력",
        "tab_thumb_grid": "🖼️ 썸네일 그리드",
        "font_size_label": "🔍 글자 크기:",
        "columns_label": "📊 열(단) 수:",
        "thumb_width_label": "🔍 썸네일 너비:",
        "slide_thumb_title": "🔍 슬라이드 크기:",
        "preview_title": "📡 송출 화면 미리보기",
        "edit_group": "✏️ 텍스트 편집",
        "open_editor_dialog": "✏️ 텍스트 편집기 열기",
        "btn_direct_write": "✍️ 새 텍스트 직접 작성/송출",
        "edit_mode_toggle": "✏️ 편집 모드 켜기",
        "edit_mode_off": "✏️ 편집 모드 끄기",
        "rad_edit_current_short": "현재 문단",
        "rad_edit_all_short": "전체 텍스트",
        "text_style_group": "🎨 글자 스타일",
        "font_family": "글꼴",
        "font_size": "크기",
        "text_color": "글자 색",
        "text_border": "글자 테두리",
        "text_valign": "세로 위치",
        "valign_top": "위",
        "valign_center": "가운데",
        "valign_bottom": "아래",
        "valign_tip": "송출 화면에서 글자를 놓을 세로 위치 (위 / 가운데 / 아래)",
        "margin_top": "위 여백",
        "margin_bottom": "아래 여백",
        "margin_tip": "화면 가장자리와 글자 사이의 여백 (화면 높이의 %)",
        "border_width": "두께",
        "border_color": "테두리 색",
        "clear_text_btn": "✖ 텍스트 숨기기",
        "black": "검정",
        "transparent_swatch": "투명",
        "transparent_swatch_tip": "투명 배경 (데스크톱 표시)",
        "color_black": "검정",
        "color_white": "흰색",
        "color_red": "빨강",
        "color_orange": "주황",
        "color_yellow": "노랑",
        "color_green": "초록",
        "color_blue": "파랑",
        "color_navy": "남색",
        "color_purple": "보라",
        "color_pink": "핑크",
        "color_brown": "갈색",
        "color_gray": "회색",
        "color_custom_prefix": "색상",
        "dialog_title": "✏️ 문단 및 전체 텍스트 편집기",
        "rad_current_para": "현재 문단 편집 (문단 {0})",
        "rad_all_text": "전체 텍스트 편집 (빈 줄로 문단 구분)",
        "editor_font_size": "글자 크기:",
        "dialog_info": "💡 [적용]을 누르면 슬라이드 내용이 바뀝니다 (화면에 새로 내보내지는 않습니다).",
        "dialog_apply": "✅ 적용",
        "dialog_cancel": "↩ 닫기 / 취소",
        "para_prefix": "문단",
        "status_bg": "배경: {0}",
        "status_presenting": "| 문단 {0}/{1} 송출 중",
        "status_blank": "| (텍스트 미선택)",
        "status_direct_presenting": "✍️ 직접 입력 텍스트 송출 중",
        "file_open_err": "파일 열기 실패",
        "direct_realtime": "⚡ 실시간 송출",
        "direct_realtime_tip": "체크하면 텍스트를 입력하거나 수정하는 즉시 송출 화면과 미리보기에 실시간 반영됩니다.",
        "direct_clear": "🧹 지우기",
        "direct_clear_tip": "입력창 내용을 모두 지웁니다.",
        "btn_direct_broadcast": "🚀 즉시 송출 (Ctrl+Enter)",
        "btn_direct_broadcast_tip": "입력한 텍스트를 즉시 화면에 띄웁니다.",
        "btn_direct_stop": "⏹ 텍스트 끄기",
        "btn_direct_stop_tip": "송출 화면에서 텍스트를 내립니다.",
        "btn_para_stop": "⏹ 텍스트 끄기",
        "btn_para_stop_tip": "송출 화면에서 현재 문단 텍스트를 내립니다.",
        "msg_text_stopped": "텍스트 송출이 중단되었습니다.",
        "btn_direct_to_paras": "📋 문단 목록으로 변환",
        "btn_direct_to_paras_tip": "빈 줄로 구분된 여러 문단으로 나누어 [문단 목록] 탭에 로드하고 첫 문단을 송출합니다.",
        "btn_direct_save": "💾 파일로 저장…",
        "btn_direct_save_tip": "작성한 텍스트를 파일로 저장하고 왼쪽 라이브러리에 등록합니다.",
        "direct_placeholder": (
            "여기에 띄울 새 텍스트를 직접 작성하세요...\n\n"
            "• [🚀 즉시 송출] 버튼을 누르면 입력한 텍스트가 화면에 바로 뜹니다. (단축키: Ctrl+Enter)\n"
            "• [⚡ 실시간 송출]을 켜면 타이핑하는 대로 실시간 화면에 송출됩니다.\n"
            "• 여러 문단(빈 줄로 구분)을 작성한 후 [📋 문단 목록으로 변환]을 누르면 문단 카드로 분할되어 하나씩 송출할 수 있습니다.\n"
            "• [💾 파일로 저장]을 누르면 .txt 파일로 저장되어 왼쪽 목록에 영구 보관됩니다."
        ),
        "msg_no_text": "송출할 텍스트가 없습니다. (화면 텍스트 지움)",
        "msg_direct_broadcast": "✍️ 직접 입력한 텍스트를 송출했습니다.",
        "msg_direct_stopped": "직접 입력 텍스트 송출이 중단되었습니다.",
        "msg_media_ended": "미디어 송출이 종료되었습니다.",
        "msg_enter_text_first": "변환할 텍스트를 먼저 입력해 주세요.",
        "msg_empty_text": "저장할 텍스트가 비어 있습니다.",
        "msg_saved_file": "저장 및 등록 완료: {0}",
        "msg_converted_paras": "총 {0}개 문단으로 변환하여 문단 목록에 로드했습니다.",
        "add_paragraph_card": "➕\n새 텍스트 슬라이드",
        "add_paragraph_card_tip": "클릭하면 새 텍스트 슬라이드(문단)를 추가합니다.",
        "btn_save_paragraphs": "💾 저장",
        "btn_save_paragraphs_tip": "지금 문단 목록을 텍스트 파일로 저장합니다.",
        "btn_save_paragraphs_unsaved_tip": "저장하지 않은 변경 사항이 있습니다. 눌러서 파일에 저장하세요.",
        "delete_paragraph_card": "🗑 이 문단 삭제",
        "edit_paragraph_card": "✏ 이 문단 편집",
        "card_edit_tip": "편집 (화면에는 내보내지 않음)",
        "card_delete_tip": "삭제",
        "confirm_delete_paragraph_title": "슬라이드 삭제",
        "confirm_delete_paragraph_msg": "{0}번 슬라이드를 지울까요?\n\n\"{1}\"\n\n(파일에는 '저장'을 눌러야 반영됩니다)",
        "btn_delete_confirm": "삭제",
        "btn_cancel_plain": "취소",
        "empty_paragraph": "(빈 슬라이드)",
        "msg_paragraph_edited_not_shown": "편집했습니다 - 화면에 내보내려면 그 슬라이드를 누르세요 (파일 반영은 '저장')",
        "msg_paragraphs_unsaved": "변경되었습니다 (아직 파일에 저장되지 않음 - 저장 버튼을 눌러주세요)",

        # --- 본문 동영상 (라이브러리) ---
        "video_play": "▶ 재생",
        "video_pause": "⏸ 일시정지",
        "video_resume": "▶ 계속 재생",
        "video_replay": "↻ 처음부터",
        "video_play_tip": "듀얼 화면에서 이 동영상을 재생합니다 (Space)",
        "video_stop": "⏹ 내리기",
        "video_stop_tip": "동영상을 멈추고 듀얼 화면에서 내립니다",
        "video_seek_tip": "재생 위치 (← → 키로 5초씩 이동)",
        "video_volume_tip": "동영상 소리 크기",
        "subtitle_btn": "💬 자막",
        "subtitle_btn_tip": "자막 파일을 고르거나 끕니다",
        "subtitle_menu_choose": "📂 자막 파일 선택…",
        "subtitle_menu_auto": "🔎 같은 이름 자막 자동으로 쓰기",
        "subtitle_menu_off": "🚫 자막 끄기",
        "subtitle_size": "자막 크기:",
        "subtitle_size_tip": "자막 글자 크기 (1080줄 화면 기준 픽셀)",
        "subtitle_status_auto": "💬 자막: {0} (자동)",
        "subtitle_status_manual": "💬 자막: {0}",
        "subtitle_status_none": "💬 같은 이름의 자막 파일 없음",
        "subtitle_status_off": "💬 자막 끔",
        "subtitle_status_bad": "💬 자막을 읽지 못함: {0}",
        "dialog_select_subtitle": "자막 파일 선택",
        "filter_subtitle": "자막 파일 (*.srt *.smi *.sami);;모든 파일 (*.*)",
        "msg_subtitle_load_failed": "자막 파일을 읽지 못했습니다 (형식이나 내용을 확인해 주세요):\n{0}",
        "video_card_hint": "▶ 누르면 듀얼 화면에서 재생",
        "video_card_playing": "⏸ 누르면 일시정지",
        "msg_video_ended": "동영상 재생이 끝났습니다 (ESC 또는 다른 항목을 송출하면 내려갑니다)",
        "msg_video_error_title": "동영상 재생",
        "msg_video_error": "동영상을 재생하지 못했습니다:\n{0}",
        "msg_video_started": "🎬 동영상 재생: {0}",
        "msg_music_paused_for_video": "동영상 소리가 잘 들리도록 음악을 일시정지했습니다",
        "status_video": "🎬 {0} ({1})",
        "video_state_playing": "재생 중",
        "video_state_paused": "일시정지",
        "video_state_ended": "재생 끝",
        # --- 음악 (상단 툴바) ---
        "music_label": " 🎵 음악: ",
        "music_toolbar": "음악",
        "music_open_tip": "음악 파일 선택 (여러 개 선택 가능)",
        "music_menu_new": "📂 음악 파일 선택 (새 목록)…",
        "music_menu_add": "➕ 지금 목록에 추가…",
        "music_menu_clear": "🗑 목록 비우기",
        "music_prev_tip": "이전 곡 (3초 넘게 들었으면 처음부터)",
        "music_play_tip": "재생 / 일시정지",
        "music_next_tip": "다음 곡",
        "music_stop_tip": "정지",
        "music_volume_tip": "음악 소리 크기",
        "music_repeat_tip": "반복: 목록을 다 재생하면 처음부터 다시",
        "music_repeat_one_tip": "반복: 지금 곡을 계속 되풀이",
        "music_mode_continuous": "⏩ 연속 재생",
        "music_mode_single": "1️⃣ 한 곡씩",
        "music_mode_continuous_tip": "연속 재생: 한 곡이 끝나면 다음 곡을 이어서 재생합니다\n(누르면 '한 곡씩'으로 바뀝니다)",
        "music_mode_single_tip": "한 곡씩: 한 곡이 끝나면 멈추고 다음 곡을 준비해 둡니다 - ▶ 를 눌러야 재생\n(누르면 '연속 재생'으로 바뀝니다)",
        "music_list_tip": "재생 목록 - 눌러서 곡을 고릅니다",
        "music_time_tip": "재생한 시간 / 곡 전체 길이   -남은 시간",
        "music_none": "(음악 없음)",
        "dialog_select_music": "음악 파일 선택 (여러 개 선택 가능)",
        "filter_music": "음악 파일 (*.mp3 *.aac *.m4a *.wav *.flac *.ogg *.oga *.opus *.wma);;모든 파일 (*.*)",
        "msg_music_error": "재생할 수 없는 음악 파일을 건너뜁니다: {0}",
        "notice": "알림",
        "err_save_title": "저장 오류",
        "err_save_msg": "파일을 저장하는 중 오류가 발생했습니다:\n{0}",
        "direct_text_title": "✍️ 직접 작성한 텍스트",
        "dialog_select_bg_color": "배경 색상 선택",
        "dialog_select_text_color": "글자 색상 선택",
        "dialog_select_border_color": "테두리 색상 선택",
        "dialog_select_images": "배경 이미지 선택 (여러 개 가능)",
        "dialog_select_videos": "배경 동영상 선택 (여러 개 가능)",
        "dialog_select_txt_file": "텍스트 파일 선택",
        "dialog_add_txt_files": "텍스트 파일 추가",
        "dialog_select_img_folder": "이미지 폴더 선택",
        "dialog_save_direct": "직접 작성한 텍스트 파일 저장",
        "no_images_title": "이미지 없음",
        "no_images_msg": "선택한 폴더에 이미지 파일이 없습니다:\n{0}",
        "item_not_found_title": "항목을 찾을 수 없음",
        "item_not_found_msg": "등록된 항목을 찾을 수 없습니다:\n{0}\n목록에서 제거해 주세요.",
        "top_toolbar": "상단 메뉴",
        "presenter_window_title": "배경 텍스트 프리젠터 - 송출 화면",
        "filter_image": "이미지 파일 (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tiff *.ico)",
        "filter_video": "동영상 파일 (*.mp4 *.avi *.mkv *.mov *.wmv *.webm *.flv *.m4v)",
        "filter_text": "텍스트 파일 (*.txt);;모든 파일 (*.*)",
        "filter_text_lib": "텍스트 파일 (*.txt *.md);;모든 파일 (*.*)",
    },
    "en": {
        "app_title": "Background Text Presenter (Dual Monitor Presenter)",
        "display": " 🖥️ Display: ",
        "monitor": "Monitor",
        "primary_screen": "[Primary]",
        "fullscreen": "⛶ Fullscreen",
        "windowed": "⛶ Windowed",
        "open_dual": "🖥️ Open Presenter",
        "close_dual": "🖥️ Close Presenter",
        "bg_label": " BG: ",
        "transparent": "Transparent BG",
        "custom_color": "🎨 Color…",
        "add_images": "🖼️ Add Images…",
        "add_videos": "🎬 Add Videos…",
        "language": " 🌐 Language: ",
        "tab_color": "Colors",
        "tab_image": "Images",
        "tab_video": "Videos",
        "add_color_btn": "🎨 Add Color…",
        "delete_btn": "🗑 Delete",
        "clear_all_btn": "🧹 Clear All",
        "clear_all_images_tip": "Clear all images from the list.",
        "clear_all_videos_tip": "Clear all videos from the list.",
        "loop_play": "▶ Loop Play",
        "stop_btn": "⏹ Stop",
        "volume": "🔊 Volume",
        "playlist_none": "Playlist: No video selected",
        "playlist_stopped": "Playlist: Stopped",
        "playlist_playing_count": "Playlist: {0} selected",
        "playlist_status_desc": "Video {0}/{1}: {2}",
        "text_lib_title": "📑 Text, PPT, Video & Image Folders",
        "btn_add_pptx": "📊 PPT…",
        "btn_add_pptx_tip": "Register a PowerPoint file (.pptx) as slides",
        "dialog_add_pptx": "Select PowerPoint File",
        "filter_pptx": "PowerPoint (*.pptx *.ppt *.pptm *.ppsx);;All Files (*.*)",
        "slide_prefix": "Slide",
        "notes_group": "📝 Slide Notes",
        "notes_font_size": "🔍 Font size:",
        "notes_empty": "This slide has no notes.",
        "image_prefix": "Image",
        "btn_notes_popup": "🗗 Notes in Window",
        "btn_notes_popup_tip": "Show the notes in a separate window. It always stays in front of this program,\nand goes behind other programs when you switch to them.\nWhile it is on, it hides by itself for slides/images without notes and comes back when there are notes.\n(→, ←, Space, PageUp/PageDown in that window also move the slides)",
        "notes_popup_title": "📝 Notes",
        "msg_notes_popup_waiting": "Notes window is on - it appears when a slide or image with notes is presented",
        "notes_popup_nothing": "There is no slide or image with notes on screen right now.\nPresent a PowerPoint slide or an image from an image folder to see its notes here.",
        "image_notes_group": "📝 Image Notes (hidden text)",
        "image_notes_empty": "This image has no hidden note.\nClick '✏ Edit Hidden Note' or right-click the image to add one.",
        "btn_image_note_edit": "✏ Edit Hidden Note",
        "btn_image_note_edit_tip": "Hide a note inside the selected image. It is not shown on screen;\nit appears only in this notes panel when that image is presented.",
        "image_note_menu": "✏ Edit Hidden Note…",
        "image_note_dialog_title": "Edit Hidden Note - {0}",
        "image_note_dialog_info": "💡 This note is hidden inside the image file. The picture itself does not change,\nand the note appears only in the notes panel when the image is presented (it is not shown on screen).\n※ If the image is re-compressed (e.g. sent through a messenger app), the note is lost.",
        "image_note_save": "💾 Save to Image",
        "image_note_unsupported": "Hidden notes cannot be stored in this format ({0}).\nPlease use a JPG or PNG image.",
        "image_note_failed": "Could not save the hidden note.\n\n{0}",
        "image_note_pick_first": "Select an image first.",
        "msg_image_note_saved": "Hidden note saved into the image: {0}",
        "msg_image_note_removed": "Hidden note removed: {0}",
        "msg_ppt_exporting": "Preparing slides… {0}/{1}",
        "msg_ppt_ready": "{0} slides ready",
        "msg_ppt_cached": "Loaded {0} cached slides instantly",
        "msg_ppt_click_to_load": "Click the PPT in the list to prepare its slides",
        "msg_slide_not_ready": "This slide is still being prepared",
        "msg_image_unreadable": "This image cannot be read yet (it may still be saving or syncing) - the screen was left as it is. Please try again shortly",
        "msg_folder_reloaded": "📁 The images in the folder changed and were reloaded ({0})",
        "msg_folder_missing": "📁 The folder is missing - it will be reloaded automatically when it comes back",
        "reload_folder_menu": "🔄 Reload images (rebuild thumbnails)  F5",
        "msg_ppt_opening_for_edit": "Opening PowerPoint in a new window at slide {0} for editing…",
        "msg_ppt_edit_open_failed": "Failed to open PowerPoint for editing: {0}",
        "msg_ppt_edit_opened_as_copy": "Opened a temporary copy — saving (Ctrl+S) will sync back to the original automatically",
        "msg_ppt_edit_synced": "Changes were synced back — slides reloaded",
        "msg_ppt_edit_synced_pending": "Changes were synced to the original (list will update once the slideshow ends)",
        "msg_text_cleared_stage": "Text cleared — press ESC again to clear the background too",
        "msg_all_cleared": "Everything cleared — back to transparent (ESC)",
        "btn_show_mode": "🎬 Animation Mode",
        "btn_show_mode_tip": (
            "Runs the real PowerPoint slide show so animations and transitions play.\n"
            "PowerPoint takes over the presentation screen and this window becomes a remote.\n"
            "(Turn off to go back to image slides)"
        ),
        "msg_show_started": "Animation mode: slide show running — arrow keys to advance, ESC to stop",
        "msg_show_stopped": "Animation mode turned off",
        "msg_show_slide": "Slide {0}/{1} (click {2}/{3})",
        "err_show_title": "Animation Mode",
        "err_ppt_title": "PowerPoint Slides",
        "err_ppt_failed": (
            "Could not load the slides.\n\n{0}\n\n"
            "Please check:\n"
            "• Does this file open normally in PowerPoint?\n"
            "• If PowerPoint cannot open any document, repair Office\n"
            "  (Settings - Apps - Microsoft 365 - Modify - Quick/Online Repair)\n"
            "• To rule out add-ins, run  powerpnt /safe  from Windows+R\n"
            "• If it came from the internet, open it in PowerPoint once and click [Enable Editing]\n"
            "• For details, run:  python test_ppt_diag.py \"path\\to\\file.pptx\""
        ),
        "add_txt_file": "📂 Add Files…",
        "txt_lib_hint": "💡 Drag and drop text, PPT or video files or folders here, or click to load. Drop one item onto another to make a 🔗 bundle.",
        "mix_files_suffix": " files",
        "status_mix_presenting": "| 🔗 Bundle {0}/{1} presenting",
        "mix_ppt_preparing": "⏳ Preparing PPT slides…",
        "msg_mix_waiting": "This PPT's slides are still being prepared - please try again shortly",
        "msg_mix_picked": "{0} cards selected - drag to move them together (a plain click clears the selection)",
        "msg_mix_moved": "Moved {0} cards",
        "msg_mix_created": "🔗 Bundled: {0}  (drag cards to mix their order)",
        "msg_mix_added": "🔗 Added to the bundle: {0}",
        "msg_mix_ungrouped": "Bundle split back into its files",
        "msg_mix_ppt_failed": "Could not load a PPT in the bundle: {0}",
        "mix_menu_ungroup": "🔗 Split Bundle (back to the original files)",
        "mix_menu_hint": "Drop onto another item to make a bundle",
        "btn_add_text_file": "📄 Text…",
        "btn_add_text_file_tip": "Register text files (.txt) for paragraphs",
        "btn_add_image_folder": "📁 Folder…",
        "btn_add_image_folder_tip": "Register folder of images as slides",
        "btn_remove_text_file": "🗑 Delete",
        "btn_remove_text_file_tip": "Remove selected items from library (Ctrl/Shift multi-select)",
        "btn_clear_text_files": "🧹 Clear All",
        "btn_clear_text_files_tip": "Clear all registered text files and folders from list.",
        "btn_add_item": "➕ Add",
        "btn_add_item_tip": "Add a text, PPT or video file, or an image folder to the library",
        "add_item_menu_file": "📄 Text / PPT / Video File…",
        "add_item_menu_folder": "📁 Image Folder…",
        "dialog_add_files": "Select Text, PPT or Video File",
        "filter_text_and_pptx": "Text/PPT/Video (*.txt *.md *.pptx *.ppt *.pptm *.ppsx *.mp4 *.mov *.avi *.mkv *.wmv *.webm *.m4v *.mpg *.mpeg *.flv *.ts *.m2ts);;All Files (*.*)",
        "item_delete_tip": "Delete this item",
        "item_folder_badge": "[Folder]",
        "items_count_suffix": " imgs",
        "text_file_group": "📄 Text File",
        "open_txt_btn": "Open File…",
        "selected_file": "Selected File:",
        "none": "(None)",
        "para_select_group": "📑 Paragraph Selection (Click to Present)",
        "tab_para_list": "📋 Paragraph List",
        "tab_direct_text": "✍️ Direct Text Input",
        "btn_direct_input": "✍️ Direct Input",
        "tab_thumb_grid": "🖼️ Thumbnail Grid",
        "font_size_label": "🔍 Font Size:",
        "columns_label": "📊 Columns:",
        "thumb_width_label": "🔍 Thumb Width:",
        "slide_thumb_title": "🔍 Slide Size:",
        "preview_title": "📡 Broadcast Preview",
        "edit_group": "✏️ Text Edit",
        "open_editor_dialog": "✏️ Open Text Editor",
        "btn_direct_write": "✍️ Direct Text Input",
        "edit_mode_toggle": "✏️ Edit Mode",
        "edit_mode_off": "✏️ Exit Edit Mode",
        "rad_edit_current_short": "Current Para",
        "rad_edit_all_short": "All Text",
        "text_style_group": "🎨 Text Style",
        "font_family": "Font",
        "font_size": "Size",
        "text_color": "Text Color",
        "text_border": "Outline",
        "text_valign": "Position",
        "valign_top": "Top",
        "valign_center": "Middle",
        "valign_bottom": "Bottom",
        "valign_tip": "Vertical position of the text on the output screen (top / middle / bottom)",
        "margin_top": "Top gap",
        "margin_bottom": "Bottom gap",
        "margin_tip": "Space between the screen edge and the text (% of screen height)",
        "border_width": "Width",
        "border_color": "Outline Color",
        "clear_text_btn": "✖ Hide Text",
        "black": "Black",
        "transparent_swatch": "Transparent",
        "transparent_swatch_tip": "Transparent BG (Show desktop)",
        "color_black": "Black",
        "color_white": "White",
        "color_red": "Red",
        "color_orange": "Orange",
        "color_yellow": "Yellow",
        "color_green": "Green",
        "color_blue": "Blue",
        "color_navy": "Navy",
        "color_purple": "Purple",
        "color_pink": "Pink",
        "color_brown": "Brown",
        "color_gray": "Gray",
        "color_custom_prefix": "Color",
        "dialog_title": "✏️ Paragraph & Full Text Editor",
        "rad_current_para": "Edit Current Paragraph (Para {0})",
        "rad_all_text": "Edit All Text (Blank lines separate paragraphs)",
        "editor_font_size": "Font Size:",
        "dialog_info": "💡 Click [Apply] to update the slide (it is not newly shown on screen).",
        "dialog_apply": "✅ Apply",
        "dialog_cancel": "↩ Close / Cancel",
        "para_prefix": "Para",
        "status_bg": "BG: {0}",
        "status_presenting": "| Presenting Para {0}/{1}",
        "status_blank": "| (No text selected)",
        "status_direct_presenting": "✍️ Presenting direct text",
        "file_open_err": "Failed to Open File",
        "direct_realtime": "⚡ Live Broadcast",
        "direct_realtime_tip": "When checked, typing or editing immediately reflects on presenter and preview.",
        "direct_clear": "🧹 Clear",
        "direct_clear_tip": "Clear all text in editor.",
        "btn_direct_broadcast": "🚀 Broadcast (Ctrl+Enter)",
        "btn_direct_broadcast_tip": "Immediately present entered text on screen.",
        "btn_direct_stop": "⏹ Hide Text",
        "btn_direct_stop_tip": "Hide text from the presenter screen.",
        "btn_para_stop": "⏹ Hide Text",
        "btn_para_stop_tip": "Hide the current paragraph text from the presenter screen.",
        "msg_text_stopped": "Text presentation stopped.",
        "btn_direct_to_paras": "📋 Convert to Paragraphs",
        "btn_direct_to_paras_tip": "Split into paragraphs by blank lines and load into [Paragraph List].",
        "btn_direct_save": "💾 Save to File…",
        "btn_direct_save_tip": "Save text to a .txt file and register it in the left library.",
        "direct_placeholder": (
            "Type or paste text here to present directly...\n\n"
            "• Click [🚀 Broadcast] to present text on screen immediately (Shortcut: Ctrl+Enter).\n"
            "• Turn on [⚡ Live Broadcast] to show changes in real-time as you type.\n"
            "• Write multiple paragraphs (separated by blank lines) and click [📋 Convert to Paragraphs] to create paragraph cards.\n"
            "• Click [💾 Save to File] to save as a .txt file and add it to your library."
        ),
        "msg_no_text": "No text to present. (Cleared screen)",
        "msg_direct_broadcast": "✍️ Presented direct text.",
        "msg_direct_stopped": "Direct text presentation stopped.",
        "msg_media_ended": "Media presentation ended.",
        "msg_enter_text_first": "Please enter text first.",
        "msg_empty_text": "Text is empty. Nothing to save.",
        "msg_saved_file": "Saved and registered: {0}",
        "msg_converted_paras": "Converted to {0} paragraphs and loaded into list.",
        "add_paragraph_card": "➕\nNew Text Slide",
        "add_paragraph_card_tip": "Click to add a new text slide (paragraph).",
        "btn_save_paragraphs": "💾 Save",
        "btn_save_paragraphs_tip": "Save the current paragraph list to a text file.",
        "btn_save_paragraphs_unsaved_tip": "You have unsaved changes. Click to save them to the file.",
        "delete_paragraph_card": "🗑 Delete This Paragraph",
        "edit_paragraph_card": "✏ Edit This Paragraph",
        "card_edit_tip": "Edit (not shown on screen)",
        "card_delete_tip": "Delete",
        "confirm_delete_paragraph_title": "Delete Slide",
        "confirm_delete_paragraph_msg": "Delete slide {0}?\n\n\"{1}\"\n\n(Click Save to apply to the file)",
        "btn_delete_confirm": "Delete",
        "btn_cancel_plain": "Cancel",
        "empty_paragraph": "(empty slide)",
        "msg_paragraph_edited_not_shown": "Edited - click the slide to show it on screen (Save to update the file)",
        "msg_paragraphs_unsaved": "Changed (not yet saved to file - click Save)",

        # --- content video (library) ---
        "video_play": "▶ Play",
        "video_pause": "⏸ Pause",
        "video_resume": "▶ Resume",
        "video_replay": "↻ Replay",
        "video_play_tip": "Play this video on the dual screen (Space)",
        "video_stop": "⏹ Take Down",
        "video_stop_tip": "Stop the video and remove it from the dual screen",
        "video_seek_tip": "Playback position (← → keys jump 5 s)",
        "video_volume_tip": "Video volume",
        "subtitle_btn": "💬 Subtitles",
        "subtitle_btn_tip": "Choose a subtitle file or turn subtitles off",
        "subtitle_menu_choose": "📂 Choose Subtitle File…",
        "subtitle_menu_auto": "🔎 Use Same-Name Subtitle Automatically",
        "subtitle_menu_off": "🚫 Subtitles Off",
        "subtitle_size": "Subtitle size:",
        "subtitle_size_tip": "Subtitle text size (pixels on a 1080-line screen)",
        "subtitle_status_auto": "💬 Subtitles: {0} (auto)",
        "subtitle_status_manual": "💬 Subtitles: {0}",
        "subtitle_status_none": "💬 No same-name subtitle file",
        "subtitle_status_off": "💬 Subtitles off",
        "subtitle_status_bad": "💬 Could not read subtitles: {0}",
        "dialog_select_subtitle": "Select Subtitle File",
        "filter_subtitle": "Subtitle Files (*.srt *.smi *.sami);;All Files (*.*)",
        "msg_subtitle_load_failed": "Could not read the subtitle file (check its format or contents):\n{0}",
        "video_card_hint": "▶ Click to play on the dual screen",
        "video_card_playing": "⏸ Click to pause",
        "msg_video_ended": "Video finished (press ESC or present another item to take it down)",
        "msg_video_error_title": "Video Playback",
        "msg_video_error": "Could not play the video:\n{0}",
        "msg_video_started": "🎬 Playing video: {0}",
        "msg_music_paused_for_video": "Music paused so the video sound can be heard",
        "status_video": "🎬 {0} ({1})",
        "video_state_playing": "playing",
        "video_state_paused": "paused",
        "video_state_ended": "finished",
        # --- music (top toolbar) ---
        "music_label": " 🎵 Music: ",
        "music_toolbar": "Music",
        "music_open_tip": "Choose music files (multiple allowed)",
        "music_menu_new": "📂 Choose Music Files (New List)…",
        "music_menu_add": "➕ Add to Current List…",
        "music_menu_clear": "🗑 Clear List",
        "music_prev_tip": "Previous track (restarts the track after 3 s)",
        "music_play_tip": "Play / Pause",
        "music_next_tip": "Next track",
        "music_stop_tip": "Stop",
        "music_volume_tip": "Music volume",
        "music_repeat_tip": "Repeat: start over after the last track",
        "music_repeat_one_tip": "Repeat: keep repeating the current track",
        "music_mode_continuous": "⏩ Continuous",
        "music_mode_single": "1️⃣ One Track",
        "music_mode_continuous_tip": "Continuous: the next track starts when one ends\n(click to switch to 'One Track')",
        "music_mode_single_tip": "One Track: stops when a track ends and cues the next one - press ▶ to play\n(click to switch to 'Continuous')",
        "music_list_tip": "Playlist - click to choose a track",
        "music_time_tip": "Elapsed / total length   -remaining",
        "music_none": "(no music)",
        "dialog_select_music": "Select Music Files (multiple allowed)",
        "filter_music": "Music Files (*.mp3 *.aac *.m4a *.wav *.flac *.ogg *.oga *.opus *.wma);;All Files (*.*)",
        "msg_music_error": "Skipping a music file that cannot be played: {0}",
        "notice": "Notice",
        "err_save_title": "Save Error",
        "err_save_msg": "Error saving file:\n{0}",
        "direct_text_title": "✍️ Direct Text",
        "dialog_select_bg_color": "Select Background Color",
        "dialog_select_text_color": "Select Text Color",
        "dialog_select_border_color": "Select Outline Color",
        "dialog_select_images": "Select Background Images (Multiple allowed)",
        "dialog_select_videos": "Select Background Videos (Multiple allowed)",
        "dialog_select_txt_file": "Select Text File",
        "dialog_add_txt_files": "Add Text Files",
        "dialog_select_img_folder": "Select Image Folder",
        "dialog_save_direct": "Save Direct Text File",
        "no_images_title": "No Images Found",
        "no_images_msg": "No images found in selected folder:\n{0}",
        "item_not_found_title": "Item Not Found",
        "item_not_found_msg": "Registered item could not be found:\n{0}\nPlease remove from list.",
        "top_toolbar": "Top Toolbar",
        "presenter_window_title": "Background Text Presenter - Display Window",
        "filter_image": "Image Files (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tiff *.ico)",
        "filter_video": "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv *.webm *.flv *.m4v)",
        "filter_text": "Text Files (*.txt);;All Files (*.*)",
        "filter_text_lib": "Text Files (*.txt *.md);;All Files (*.*)",
    }
}

USER_ROLE_PATH = Qt.ItemDataRole.UserRole
USER_ROLE_KIND = Qt.ItemDataRole.UserRole + 1
USER_ROLE_INDEX = Qt.ItemDataRole.UserRole + 2
USER_ROLE_THUMB = Qt.ItemDataRole.UserRole + 3
USER_ROLE_CAPTION = Qt.ItemDataRole.UserRole + 10   # 묶음 카드 아래 이름 줄
USER_ROLE_PICKED = Qt.ItemDataRole.UserRole + 11    # 묶음 카드: Ctrl/Shift 로 함께 고른 카드

# 가운데 썸네일 그리드(이미지 폴더/PPT 슬라이드)의 원본 캐시 해상도.
# Ctrl+휠로 카드를 키워도 확대된 썸네일이 흐려지지 않도록 실제 표시 크기보다
# 넉넉히 크게 만들어 둔다 (QIcon은 원본보다 큰 크기로는 자동으로 키워 그리지
# 않으므로, 화면에 보이는 크기에 맞춰 매번 QPixmap.scaled()로 다시 그린다).
SLIDE_THUMB_BASE_SIZE = (480, 270)


class LibraryRowWidget(QWidget):
    """텍스트/PPT/이미지 폴더 라이브러리 한 줄: 번호 + 이름(종류별 색) + 삭제(휴지통) 버튼

    라벨 영역 클릭은 clicked 로, 휴지통 버튼 클릭은 deleteClicked 로 알린다.
    """
    clicked = Signal()
    deleteClicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 2, 0)
        layout.setSpacing(2)

        self.label = QLabel(self)
        # 라벨 위로는 클릭이 그냥 통과해서 이 위젯(행 전체)의 mousePressEvent 로 간다
        self.label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.label.setStyleSheet("background: transparent;")
        layout.addWidget(self.label, 1)

        self.btn_delete = QToolButton(self)
        self.btn_delete.setText("🗑")
        self.btn_delete.setAutoRaise(True)
        self.btn_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_delete.setStyleSheet(
            "QToolButton { border: none; background: transparent; color: #888; }"
            "QToolButton:hover { color: #e74c3c; }"
        )
        self.btn_delete.clicked.connect(lambda checked=False: self.deleteClicked.emit())
        layout.addWidget(self.btn_delete, 0)

    def set_content(self, number: int, text: str, color: str, tooltip: str = ""):
        self.label.setText(f"{number}. {text}")
        self.label.setStyleSheet(f"background: transparent; color: {color};")
        self.setToolTip(tooltip)

    def set_font_size(self, size: int):
        f = self.label.font()
        f.setPointSize(size)
        self.label.setFont(f)

    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)


class DropListWidget(QListWidget):
    """파일/폴더 외부 드래그 앤 드롭을 지원하는 QListWidget

    reorderable=True 로 만들면 목록 안에서 항목을 드래그로 끌어 순서를 바꿀 수
    있다 (외부 파일 드롭과는 별개로 동작한다 - URL이 있으면 파일 드롭으로,
    없으면 내부 순서 이동으로 처리).
    """
    filesDropped = Signal(list)
    itemsReordered = Signal()   # 드래그로 내부 순서가 바뀐 뒤 발생
    itemsMerged = Signal(list, str)   # (끌어 온 항목 경로들, 겹친 대상 경로) - 묶음 만들기

    def __init__(self, parent=None, reorderable=False):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._reorderable = reorderable
        self._merge_row = -1        # 끌어 겹치려는 대상 줄 (테두리로 표시)
        self.merge_enabled = False
        if reorderable:
            self.setDragEnabled(True)
            self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
            self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def merge_target_row(self, pos) -> int:
        """줄 가운데 부분에 놓으면 '겹치기'(묶음), 위·아래 가장자리에 놓으면 순서 바꾸기"""
        if not self.merge_enabled:
            return -1
        item = self.itemAt(pos)
        if item is None or item.isSelected():
            return -1
        rect = self.visualItemRect(item)
        edge = max(4, rect.height() // 4)
        if rect.top() + edge <= pos.y() <= rect.bottom() - edge:
            return self.row(item)
        return -1

    def _set_merge_row(self, row: int):
        if row != self._merge_row:
            self._merge_row = row
            self.viewport().update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._merge_row >= 0 and self.item(self._merge_row) is not None:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QPen(QColor("#ffd866"), 2))
            painter.setBrush(QColor(255, 216, 102, 40))
            painter.drawRoundedRect(QRectF(self.visualItemRect(self.item(self._merge_row))).adjusted(1, 1, -1, -1), 4, 4)
            painter.end()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        row = self.merge_target_row(event.position().toPoint()) if event.source() is self else -1
        self._set_merge_row(row)
        if row >= 0:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._set_merge_row(-1)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._set_merge_row(-1)
        if event.mimeData().hasUrls():
            paths = []
            for url in event.mimeData().urls():
                p = url.toLocalFile()
                if p:
                    paths.append(p)
            if paths:
                event.acceptProposedAction()
                self.filesDropped.emit(paths)
                return
        row = self.merge_target_row(event.position().toPoint()) if event.source() is self else -1
        if row >= 0:
            sources = [it.data(USER_ROLE_PATH) for it in self.selectedItems() if it.data(USER_ROLE_PATH)]
            target = self.item(row).data(USER_ROLE_PATH)
            # 항목을 옮기지 않는다 (IgnoreAction 이면 원래 자리의 항목도 지워지지 않는다)
            event.setDropAction(Qt.DropAction.IgnoreAction)
            event.accept()
            if sources and target:
                self.itemsMerged.emit(sources, target)
            return
        super().dropEvent(event)
        if self._reorderable:
            self.itemsReordered.emit()


class NotesPopup(QWidget):
    """슬라이드 노트 / 사진 속 숨은 글을 따로 띄워 보는 창

    - 이 프로그램(본 창)에 딸린 창: 본 창 뒤로 넘어가지 않는다. 다른 프로그램을 띄우면
      그 프로그램이 앞에 오고, 이 창도 본 창과 함께 그 뒤로 간다 (다른 프로그램을 가리지 않는다).
    - 작업 표시줄에는 나타나지 않는다 (도구 창). 본 창을 최소화하면 함께 숨는다.
    - 지금 송출 중인 슬라이드/사진의 노트를 따라 바뀐다.
    - 이 창을 눌러 둔 채로 →, ←, 스페이스, PageUp/PageDown, ESC 를 눌러도
      프로그램 본 창에서 누른 것처럼 슬라이드가 넘어간다.
    """
    closed = Signal()
    NAV_KEYS = (Qt.Key.Key_Space, Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown,
                Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Left, Qt.Key.Key_Up,
                Qt.Key.Key_PageUp, Qt.Key.Key_Backspace, Qt.Key.Key_Escape)

    def __init__(self, owner):
        # 본 창을 주인으로 둔 도구 창 - 윈도우는 이런 창을 언제나 주인 창 바로 앞에 둔다.
        # ('항상 위'는 쓰지 않는다 - 다른 프로그램 앞까지 가려 버리므로)
        super().__init__(owner, Qt.WindowType.Window | Qt.WindowType.Tool)
        self._owner = owner
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMinimumSize(220, 140)
        self.setStyleSheet(
            "QWidget { background-color: #1e1e1e; color: #f0f0f0; }"
            "QPushButton { background-color: #3e3e42; border: 1px solid #555; border-radius: 4px;"
            " padding: 2px 8px; color: #fff; }"
            "QPushButton:hover { border-color: #007acc; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 8)
        lay.setSpacing(6)
        head = QHBoxLayout()
        self.lbl_where = QLabel("")
        self.lbl_where.setStyleSheet("color: #9fd3ff; font-weight: bold;")
        head.addWidget(self.lbl_where, 1)
        self.btn_smaller = QPushButton("A−")
        self.btn_bigger = QPushButton("A+")
        for btn, step in ((self.btn_smaller, -2), (self.btn_bigger, 2)):
            btn.setFixedWidth(40)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.clicked.connect(lambda _=False, d=step: self.set_font_size(self._font_size + d))
            head.addWidget(btn)
        lay.addLayout(head)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setStyleSheet("QTextEdit { background-color: #111; border: 1px solid #3e3e42;"
                                " border-radius: 4px; padding: 10px; }")
        self.text.installEventFilter(self)
        self.text.viewport().installEventFilter(self)
        lay.addWidget(self.text, 1)
        self._font_size = 20
        self.set_font_size(20, save=False)

    # --- 내용 ---
    def set_note(self, where: str, text: str, placeholder: str):
        self.lbl_where.setText(where)
        self.text.setPlaceholderText(placeholder)
        if self.text.toPlainText() != (text or ""):
            self.text.setPlainText(text or "")
            self.text.verticalScrollBar().setValue(0)

    def set_font_size(self, size: int, save: bool = True):
        self._font_size = max(10, min(72, int(size)))
        font = QFont("Malgun Gothic", self._font_size)
        self.text.setFont(font)
        if save and self._owner is not None:
            self._owner.settings.setValue("notes/popup_font_size", self._font_size)

    def hideEvent(self, event):
        # 저절로 숨을 때도 위치·크기를 기억한다 (다시 뜰 때 같은 자리)
        if self._owner is not None:
            self._owner.settings.setValue("notes/popup_geometry", self.saveGeometry())
        super().hideEvent(event)

    def closeEvent(self, event):
        super().closeEvent(event)
        self.closed.emit()          # 사용자가 X 로 닫음 = 노트 따로 보기 끄기

    # --- 키: 슬라이드 넘기기는 본 창으로 ---
    def _forward_key(self, event) -> bool:
        if event.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier):
            return False            # Ctrl+C(복사) 등은 이 창에서 처리
        if event.key() in self.NAV_KEYS and self._owner is not None:
            self._owner._handle_navigation_key(event.key())
            return True
        return False

    def keyPressEvent(self, event):
        if not self._forward_key(event):
            super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and self._forward_key(event):
            return True
        return super().eventFilter(obj, event)


class AspectFitBox(QWidget):
    """미리보기를 담는 칸 - 주어진 자리 안에서 송출 화면 비율대로 가장 크게 맞춘다.

    예전에는 미리보기가 '폭에 맞춘 높이'로 고정되어 있어서, 오른쪽 칸을 넓히면
    미리보기가 위아래로도 커지고 줄일 수가 없었다(그래서 위의 슬라이드 노트를
    위아래로 넓힐 수 없었다). 이제는 칸 크기를 스플리터가 정하고, 미리보기는
    그 안에 비율을 지켜 들어간다 (남는 곳은 빈 자리).
    """

    def __init__(self, child, parent=None, footer=None):
        super().__init__(parent)
        self._child = child
        self._footer = footer       # 미리보기 바로 밑에 붙여 둘 글자(상태 표시)
        child.setParent(self)
        if footer is not None:
            footer.setParent(self)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(80, 45)

    def sizeHint(self):
        return QSize(320, 180)

    def minimumSizeHint(self):
        return QSize(80, 45)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_child()

    def _footer_height(self, width: int) -> int:
        f = self._footer
        if f is None or not f.isVisibleTo(self):
            return 0
        if f.hasHeightForWidth():
            return max(0, f.heightForWidth(width))
        return max(0, f.sizeHint().height())

    def fit_child(self):
        aspect = getattr(self._child, "_aspect", 16.0 / 9.0) or 16.0 / 9.0
        avail_w = max(1, self.width())
        footer_h = self._footer_height(avail_w)
        gap = 4 if footer_h else 0
        avail_h = max(1, self.height() - footer_h - gap)
        w = avail_w
        h = int(round(w / aspect))
        if h > avail_h:
            h = avail_h
            w = int(round(h * aspect))
        # 가로는 가운데, 세로는 위쪽에 붙인다 (아래 상태 글자와 떨어지지 않게)
        self._child.setGeometry((avail_w - w) // 2, 0, max(1, w), max(1, h))
        if footer_h:
            self._footer.setGeometry(0, h + gap, avail_w, footer_h)


class PreviewWidget(QWidget):
    """중앙의 송출 미리보기 (송출 창과 동일한 방식으로 렌더링)

    - 송출 화면과 같은 비율(aspect ratio)을 유지해 똑같이 보이게 한다.
    - 색상/이미지/동영상 프레임/텍스트 모두 송출 창과 같은 코드로 그린다.
    - 투명 배경은 체커보드로 표시하며, 투명 PNG는 체커보드 위에 렌더링된다.
    """
    preview_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(16, 9)
        self.setMouseTracking(True)
        self._aspect = 16.0 / 9.0          # 송출 화면 비율
        self._target_res = (1920, 1080)    # 송출 화면 가상 해상도 (비례 렌더링용)
        self._bg_color = QColor("#000000")
        self._bg_pixmap = None
        self._video_frame = None           # QImage (동영상 현재 프레임)
        self._transparent = False
        self._fit_mode = "cover"
        self._overlay_pixmap = None        # 배경 위에 겹쳐 그리는 오버레이 이미지(투명 PNG 등)
        self._text = ""
        self._style = TextStyle()
        self._img_rect = QRect()
        # 본문 동영상 (송출 창과 같은 모습: 배경을 덮고 화면 안에 맞춰 + 자막)
        self._content_active = False
        self._content_frame = None
        self._subtitle = ""
        self._subtitle_size = 44

    def set_content_video(self, active: bool):
        self._content_active = bool(active)
        if not active:
            self._content_frame = None
            self._subtitle = ""
        self.update()

    def set_content_frame(self, image):
        if self._content_active:
            self._content_frame = image
            self.update()

    def set_subtitle(self, text: str):
        self._subtitle = text or ""
        self.update()

    def set_subtitle_size(self, size_px: int):
        self._subtitle_size = max(8, int(size_px))
        self.update()

    def set_video_note(self, text=""):
        """호환성을 위한 더미 메서드"""
        pass

    # --- 송출 화면과 같은 비율 및 가상 해상도 동기화 ---
    def set_target_resolution(self, width: int, height: int):
        if width > 0 and height > 0:
            self._target_res = (width, height)
            self._aspect = width / height
            self._apply_aspect()
            self.update()

    def set_screen_aspect(self, width: int, height: int):
        self.set_target_resolution(width, height)

    def _apply_aspect(self):
        """크기는 담고 있는 칸(AspectFitBox)이 정한다 - 비율이 바뀌었으니 다시 맞춰 달라고 한다"""
        box = self.parentWidget()
        if isinstance(box, AspectFitBox):
            box.fit_child()

    def set_bg_color(self, color: QColor):
        self._bg_color = QColor(color)
        self._bg_pixmap = None
        self._video_frame = None
        self._transparent = False
        self.update()

    def set_bg_image(self, path: str, fit_mode="cover", transparent=None):
        self._bg_pixmap = load_display_pixmap(path, 1920, 1080)
        self._fit_mode = fit_mode
        self._video_frame = None
        if transparent is not None:
            self._transparent = transparent
        self.update()

    def set_bg_pixmap(self, pixmap: QPixmap, fit_mode="fit", transparent=False):
        self._bg_pixmap = pixmap
        self._fit_mode = fit_mode
        self._video_frame = None
        self._transparent = transparent
        self.update()

    def set_video_frame(self, image):
        """동영상 현재 프레임을 송출 창과 동일하게 표시"""
        self._video_frame = image
        self.update()

    def set_transparent(self, enabled: bool):
        self._transparent = enabled
        self._video_frame = None
        if enabled:
            self._bg_pixmap = None
        self.update()

    def set_overlay_image(self, file_path: str):
        """배경(동영상/이미지/색상)은 그대로 둔 채 이미지를 그 위에 겹쳐 그린다."""
        self._overlay_pixmap = load_display_pixmap(file_path, 1920, 1080)
        self.update()

    def clear_overlay_image(self):
        self._overlay_pixmap = None
        self.update()

    def set_text(self, text: str):
        self._text = text or ""
        self.update()

    def set_style(self, style: TextStyle):
        self._style = style
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.preview_clicked.emit()
        super().mousePressEvent(event)

    def _draw_cover(self, painter: QPainter, image):
        """송출 창과 동일한 확대-크롭(cover) 또는 화면 맞춤(fit) 렌더링"""
        mode = (
            Qt.AspectRatioMode.KeepAspectRatio
            if getattr(self, "_fit_mode", "cover") == "fit"
            else Qt.AspectRatioMode.KeepAspectRatioByExpanding
        )
        if isinstance(image, QPixmap):
            scaled = image.scaled(
                self.size(),
                mode,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            self._img_rect = QRect(x, y, scaled.width(), scaled.height())
            painter.drawPixmap(x, y, scaled)
        else:
            scaled = image.scaled(
                self.size(),
                mode,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            self._img_rect = QRect(x, y, scaled.width(), scaled.height())
            painter.drawImage(x, y, scaled)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # 1. 배경 렌더링
        if self._transparent:
            tile = 10
            c1 = QColor("#d8d8d8")
            c2 = QColor("#8a8a8a")
            for y in range(0, self.height(), tile):
                for x in range(0, self.width(), tile):
                    fill = c1 if ((x // tile) + (y // tile)) % 2 == 0 else c2
                    painter.fillRect(x, y, tile, tile, fill)
            # 투명 배경일 때도 투명 PNG 이미지 표시
            if self._bg_pixmap and not self._bg_pixmap.isNull():
                self._draw_cover(painter, self._bg_pixmap)
        else:
            painter.fillRect(self.rect(), self._bg_color)
            if self._video_frame is not None and not self._video_frame.isNull():
                self._draw_cover(painter, self._video_frame)
            elif self._bg_pixmap and not self._bg_pixmap.isNull():
                self._draw_cover(painter, self._bg_pixmap)

        # 2. 오버레이 이미지 (배경 위에 알파 채널을 살려 겹쳐 그림, 잘리지 않게 fit)
        if self._overlay_pixmap and not self._overlay_pixmap.isNull():
            scaled = self._overlay_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            ox = (self.width() - scaled.width()) // 2
            oy = (self.height() - scaled.height()) // 2
            painter.drawPixmap(ox, oy, scaled)

        # 2-1. 본문 동영상 (배경을 덮고 화면 안에 맞춰 그린 뒤 자막)
        if self._content_active:
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            frame = self._content_frame
            if frame is not None and not frame.isNull():
                painter.drawImage(fit_rect(frame.width(), frame.height(),
                                           self.width(), self.height()), frame)
            base_w, base_h = self._target_res
            if self._subtitle and base_w > 0 and base_h > 0:
                painter.save()
                painter.scale(self.width() / float(base_w), self.height() / float(base_h))
                draw_subtitle(painter, QRect(0, 0, base_w, base_h), self._subtitle,
                              self._subtitle_size)
                painter.restore()

        # 3. 텍스트 오버레이 (송출 창 기준 비례 렌더링)
        if self._text:
            base_w, base_h = self._target_res
            if base_w > 0 and base_h > 0 and self.width() > 0 and self.height() > 0:
                painter.save()
                scale_x = self.width() / float(base_w)
                scale_y = self.height() / float(base_h)
                painter.scale(scale_x, scale_y)
                draw_text_overlay(painter, QRect(0, 0, base_w, base_h), self._text, self._style)
                painter.restore()

        painter.end()


class TextEditDialog(QDialog):
    """별도 창으로 크게 열리는 텍스트 / 문단 편집 대화상자"""

    def __init__(self, parent=None, current_para="", all_text="", active_index=0, lang="ko"):
        super().__init__(parent)
        t = TRANSLATIONS.get(lang, TRANSLATIONS["ko"])
        self.setWindowTitle(t["dialog_title"])
        self.resize(880, 620)
        self.setMinimumSize(600, 400)
        self.current_para = current_para
        self.all_text = all_text
        self.active_index = active_index

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # 상단 제어 바
        top_bar = QHBoxLayout()
        self.rad_current = QRadioButton(t["rad_current_para"].format(active_index + 1))
        self.rad_all = QRadioButton(t["rad_all_text"])
        self.rad_current.setChecked(True)
        self.rad_current.toggled.connect(self._on_mode_toggled)
        top_bar.addWidget(self.rad_current)
        top_bar.addWidget(self.rad_all)
        top_bar.addSpacing(20)

        top_bar.addWidget(QLabel(t["editor_font_size"]))
        self.spin_editor_font = QSpinBox()
        self.spin_editor_font.setRange(11, 36)
        self.spin_editor_font.setValue(16)
        self.spin_editor_font.valueChanged.connect(self._on_font_size_changed)
        top_bar.addWidget(self.spin_editor_font)
        top_bar.addStretch(1)
        layout.addLayout(top_bar)

        # 에디터 영역
        self.editor = QTextEdit()
        self.editor.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #f5f5f5; border: 1px solid #3e3e42; border-radius: 6px; padding: 12px; line-height: 1.5; }"
        )
        f = QFont("Consolas" if "Consolas" in QFontDatabase.families() else "Malgun Gothic", 16)
        self.editor.setFont(f)
        self.editor.setPlainText(self.current_para)
        layout.addWidget(self.editor, 1)

        # 하단 안내 및 버튼 바
        btn_bar = QHBoxLayout()
        lbl_info = QLabel(t["dialog_info"])
        lbl_info.setStyleSheet("color: #888888; font-size: 12px;")
        btn_bar.addWidget(lbl_info)
        btn_bar.addStretch(1)

        self.btn_apply = QPushButton(t["dialog_apply"])
        self.btn_apply.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; font-weight: bold; padding: 8px 24px; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #2ecc71; }"
        )
        self.btn_apply.clicked.connect(self.accept)
        btn_bar.addWidget(self.btn_apply)

        self.btn_cancel = QPushButton(t["dialog_cancel"])
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #3e3e42; color: white; padding: 8px 18px; border-radius: 4px; font-size: 13px; }"
            "QPushButton:hover { background-color: #4e4e52; }"
        )
        self.btn_cancel.clicked.connect(self.reject)
        btn_bar.addWidget(self.btn_cancel)

        layout.addLayout(btn_bar)

    def _on_mode_toggled(self):
        if self.rad_current.isChecked():
            self.editor.setPlainText(self.current_para)
        else:
            self.editor.setPlainText(self.all_text)

    def _on_font_size_changed(self, size):
        f = self.editor.font()
        f.setPointSize(size)
        self.editor.setFont(f)

    def get_result(self):
        return {
            "mode": "current" if self.rad_current.isChecked() else "all",
            "text": self.editor.toPlainText()
        }


class DirectTextEdit(QTextEdit):
    """직접 입력 에디터: 백스페이스 등 모든 텍스트 편집 키가 상위 네비게이션으로 새어나가지 않도록 자체 처리"""
    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            # Ctrl+Enter: 송출 창 찾아서 즉시 송출 호출
            parent_win = self.window()
            if hasattr(parent_win, "_broadcast_direct_text"):
                parent_win._broadcast_direct_text()
                event.accept()
                return
        # 백스페이스 및 모든 키는 QTextEdit 내부 편집으로 완결
        super().keyPressEvent(event)
        event.accept()


class LazyFontComboBox(QComboBox):
    """시작 로딩 속도를 위해 폰트 목록을 필요할 때(클릭 시) 지연 로딩하는 콤보박스"""
    currentFontChanged = Signal(QFont)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loaded = False
        self.addItem("Malgun Gothic")
        self.currentTextChanged.connect(self._on_text_changed)

    def _on_text_changed(self, text: str):
        if text:
            self.currentFontChanged.emit(QFont(text))

    def currentFont(self) -> QFont:
        return QFont(self.currentText())

    def setCurrentFont(self, font: QFont):
        fam = font.family() if hasattr(font, "family") else str(font)
        self.set_family(fam)

    def set_family(self, fam: str):
        if not self._loaded:
            self.clear()
            self.addItem(fam)
            self.setCurrentIndex(0)
        else:
            idx = self.findText(fam, Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                self.setCurrentIndex(idx)

    def showPopup(self):
        if not self._loaded:
            cur = self.currentText()
            self._loaded = True
            self.blockSignals(True)
            self.clear()
            fams = sorted(QFontDatabase.families())
            self.addItems(fams)
            idx = self.findText(cur, Qt.MatchFlag.MatchFixedString)
            if idx >= 0:
                self.setCurrentIndex(idx)
            self.blockSignals(False)
        super().showPopup()


def make_media_icon(kind: str, size: int = 22, color: str = "#ffffff") -> QIcon:
    """재생 조작 단추 그림 (▶ ⏸ ⏹ ⏮ ⏭) - 글자(이모지)보다 크고 또렷하게 직접 그린다"""
    scale = 2                                   # 고해상도 화면에서도 선명하게
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(scale, scale)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    s = float(size)

    def tri(x0, x1, y0, y1, right=True):
        path = QPainterPath()
        if right:
            path.moveTo(x0, y0)
            path.lineTo(x1, (y0 + y1) / 2)
            path.lineTo(x0, y1)
        else:
            path.moveTo(x1, y0)
            path.lineTo(x0, (y0 + y1) / 2)
            path.lineTo(x1, y1)
        path.closeSubpath()
        p.drawPath(path)

    if kind == "play":
        tri(s * 0.28, s * 0.82, s * 0.16, s * 0.84)
    elif kind == "pause":
        p.drawRoundedRect(QRectF(s * 0.24, s * 0.18, s * 0.18, s * 0.64), 1.5, 1.5)
        p.drawRoundedRect(QRectF(s * 0.58, s * 0.18, s * 0.18, s * 0.64), 1.5, 1.5)
    elif kind == "stop":
        p.drawRoundedRect(QRectF(s * 0.22, s * 0.22, s * 0.56, s * 0.56), 2, 2)
    elif kind == "prev":
        p.drawRect(QRectF(s * 0.18, s * 0.2, s * 0.12, s * 0.6))
        tri(s * 0.3, s * 0.82, s * 0.2, s * 0.8, right=False)
    elif kind == "next":
        tri(s * 0.18, s * 0.7, s * 0.2, s * 0.8)
        p.drawRect(QRectF(s * 0.7, s * 0.2, s * 0.12, s * 0.6))
    p.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


def format_play_time(ms: int) -> str:
    """밀리초 → 3:05 / 1:02:05"""
    total = max(0, int(ms or 0)) // 1000
    h, rest = divmod(total, 3600)
    m, sec = divmod(rest, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


class ParagraphCardDelegate(QStyledItemDelegate):
    """텍스트 슬라이드 카드: 기본 모양(스타일시트) 위 오른쪽 위 구석에 ✏(편집)·🗑(삭제) 단추를 그린다.

    단추는 그림일 뿐이고, 눌림은 MainWindow 의 마우스 처리에서 같은 위치 계산
    (card_button_rects)으로 판정한다.
    """
    BUTTON = 24
    MARGIN = 5
    GAP = 4

    def __init__(self, owner, parent=None):
        super().__init__(parent)
        self._owner = owner

    @classmethod
    def card_button_rects(cls, rect: QRect):
        """(편집 단추 영역, 삭제 단추 영역)"""
        s = cls.BUTTON
        delete = QRect(rect.right() - cls.MARGIN - s + 1, rect.top() + cls.MARGIN, s, s)
        edit = delete.translated(-(s + cls.GAP), 0)
        return edit, delete

    # 사진/슬라이드 카드: 위에는 그림, 아래 한 줄에는 이름 (서로 겹치지 않게)
    MEDIA_PAD = 6
    MEDIA_TITLE_GAP = 4

    @classmethod
    def media_title_height(cls, font) -> int:
        return QFontMetrics(font).height() + 6

    @classmethod
    def media_card_size(cls, card_w: int, font):
        """카드 폭으로 (카드 높이, 그림 칸 폭, 그림 칸 높이)를 정한다 - 그림 칸은 16:9"""
        inner_w = max(20, card_w - 2 * cls.MEDIA_PAD - 2)
        thumb_h = max(30, int(inner_w * 9 / 16))
        card_h = thumb_h + cls.media_title_height(font) + cls.MEDIA_TITLE_GAP + 2 * cls.MEDIA_PAD + 2
        return card_h, inner_w, thumb_h

    _MIX_BADGES = {"text": ("📄", "#7fd1ff"), "slide": ("📊", "#ffb454"), "wait": ("⏳", "#ffb454"),
                   "image": ("🖼", "#8ce99a"), "video": ("🎬", "#ff9ecf")}

    def _paint_mix_card(self, painter: QPainter, option, index):
        """묶음 카드: 종류마다 모양은 다르지만 크기는 같게 (끌어 섞기 쉽게)"""
        kind = index.data(USER_ROLE_KIND) or ""
        caption = index.data(USER_ROLE_CAPTION) or ""
        if kind in ("text", "wait"):
            self._paint_media_card(painter, option, index, title=caption,
                                   body_text=str(index.data(Qt.ItemDataRole.DisplayRole) or ""))
        else:
            self._paint_media_card(painter, option, index, title=caption)
        glyph, color = self._MIX_BADGES.get(kind, ("•", "#cccccc"))
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        badge = QRect(option.rect.left() + self.MEDIA_PAD + 2, option.rect.top() + self.MEDIA_PAD + 2, 26, 22)
        painter.setPen(QPen(QColor(color), 1.5))
        painter.setBrush(QColor(0, 0, 0, 170))
        painter.drawRoundedRect(QRectF(badge), 5, 5)
        font = QFont(option.font)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, glyph)
        if index.data(USER_ROLE_PICKED):
            # Ctrl/Shift 로 함께 고른 카드: 금색 테두리 + ✓ (송출 중인 파란 카드와 구별)
            painter.setPen(QPen(QColor("#ffd866"), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(option.rect).adjusted(2, 2, -2, -2), 6, 6)
            mark = QRect(option.rect.right() - self.MEDIA_PAD - 26, option.rect.top() + self.MEDIA_PAD + 2, 24, 22)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#ffd866"))
            painter.drawRoundedRect(QRectF(mark), 5, 5)
            painter.setPen(QColor("#222222"))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(mark, Qt.AlignmentFlag.AlignCenter, "✓")
        painter.restore()

    def _paint_media_card(self, painter: QPainter, option, index, title=None, body_text=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(option.rect).adjusted(1, 1, -1, -1)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            painter.setPen(QPen(QColor("#007acc"), 2))
            painter.setBrush(QColor("#0c3b5e"))
        elif hover:
            painter.setPen(QPen(QColor("#00bcd4"), 1))
            painter.setBrush(QColor("#333333"))
        else:
            painter.setPen(QPen(QColor("#3e3e42"), 1))
            painter.setBrush(QColor("#262626"))
        painter.drawRoundedRect(rect, 6, 6)

        pad = self.MEDIA_PAD
        inner = option.rect.adjusted(pad + 1, pad + 1, -pad - 1, -pad - 1)
        title_h = self.media_title_height(option.font)
        img_rect = QRect(inner.left(), inner.top(), inner.width(),
                         max(1, inner.height() - title_h - self.MEDIA_TITLE_GAP))
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if body_text is not None:
            # 글 카드: 그림 칸 자리에 글을 줄바꿈해 넣는다 (넘치면 잘린다)
            inner_text = img_rect.adjusted(6, 26, -6, -4)     # 위쪽은 종류 표시(📄) 자리
            painter.setFont(option.font)
            painter.setPen(QColor("#f0f0f0"))
            flags = int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap)
            need = QFontMetrics(option.font).boundingRect(inner_text, flags, body_text).height()
            if need > inner_text.height():
                # 다 들어가지 않으면 첫 줄부터 보이게 (가운데 맞춤이면 위아래가 함께 잘린다)
                flags = int(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap)
            painter.save()
            painter.setClipRect(inner_text)
            painter.drawText(inner_text, flags, body_text)
            painter.restore()
            icon = None
        if isinstance(icon, QIcon) and not icon.isNull():
            pix = icon.pixmap(img_rect.size())
            if not pix.isNull():
                size = pix.size()
                ratio = pix.devicePixelRatio() or 1.0
                w = min(img_rect.width(), int(size.width() / ratio))
                h = min(img_rect.height(), int(size.height() / ratio))
                target = QRect(img_rect.left() + (img_rect.width() - w) // 2,
                               img_rect.top() + (img_rect.height() - h) // 2, w, h)
                painter.drawPixmap(target, pix)
        text_rect = QRect(inner.left(), img_rect.bottom() + 1 + self.MEDIA_TITLE_GAP,
                          inner.width(), title_h)
        fm = QFontMetrics(option.font)
        label = title if title is not None else str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        text = fm.elidedText(label, Qt.TextElideMode.ElideMiddle, text_rect.width())
        painter.setFont(option.font)
        painter.setPen(QColor("#ffffff") if selected else QColor("#e0e0e0"))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)
        painter.restore()

    def paint(self, painter: QPainter, option, index):
        owner = self._owner
        if getattr(owner, "current_source_type", "text") == "folder":
            self._paint_media_card(painter, option, index)
            return
        if getattr(owner, "current_source_type", "text") == "mix":
            self._paint_mix_card(painter, option, index)
            return
        super().paint(painter, option, index)
        idx = index.data(USER_ROLE_INDEX)
        if not owner._card_buttons_enabled() or idx is None or idx < 0:
            return
        hover = getattr(owner, "_card_hover", None)
        edit_rect, delete_rect = self.card_button_rects(option.rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        for which, rect, glyph, hot in (("edit", edit_rect, "✏", QColor("#1e88e5")),
                                        ("delete", delete_rect, "🗑", QColor("#c0392b"))):
            is_hover = hover == (idx, which)
            painter.setPen(QPen(QColor(255, 255, 255, 90), 1))
            painter.setBrush(hot if is_hover else QColor(0, 0, 0, 150))
            painter.drawRoundedRect(QRectF(rect), 5, 5)
            font = QFont(option.font)
            font.setPixelSize(13)
            painter.setFont(font)
            painter.setPen(QColor("#ffffff"))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, glyph)
        painter.restore()


class VideoThumbnailDelegate(QStyledItemDelegate):
    """동영상 썸네일 카드 및 다중 선택 체크박스 오버레이 델리게이트"""
    CHECK_SIZE = 22
    CHECK_MARGIN = 6

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = option.rect
        card_rect = rect.adjusted(3, 3, -3, -3)

        check_val = index.data(Qt.ItemDataRole.CheckStateRole)
        is_checked = (check_val == 2 or check_val == Qt.CheckState.Checked)
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)

        # 1. 배경 카드
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#222222"))
        painter.drawRoundedRect(card_rect, 6, 6)

        # 2. 썸네일 아이콘 (둥근 모서리 클리핑)
        icon = index.data(Qt.ItemDataRole.DecorationRole)
        if icon and not icon.isNull():
            pix = icon.pixmap(card_rect.size())
            path = QPainterPath()
            path.addRoundedRect(card_rect, 6, 6)
            painter.setClipPath(path)
            px = card_rect.x() + (card_rect.width() - pix.width()) // 2
            py = card_rect.y() + (card_rect.height() - pix.height()) // 2
            painter.drawPixmap(px, py, pix)
            painter.setClipping(False)

        # 3. 테두리 (체크된 항목은 선명한 청록색 테두리로 강조)
        if is_checked:
            pen = QPen(QColor("#00bcd4"), 3.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(card_rect, 6, 6)
        elif is_selected:
            pen = QPen(QColor("#007acc"), 2.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(card_rect, 6, 6)
        elif is_hover:
            pen = QPen(QColor("#666666"), 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(card_rect, 6, 6)

        # 4. 좌측 상단 체크박스 오버레이
        chk_rect = QRect(card_rect.left() + self.CHECK_MARGIN,
                         card_rect.top() + self.CHECK_MARGIN,
                         self.CHECK_SIZE, self.CHECK_SIZE)

        if is_checked:
            # 체크됨: 파란색 배경 + 흰색 체크 표시
            painter.setPen(QPen(QColor("#ffffff"), 1.5))
            painter.setBrush(QColor("#007acc"))
            painter.drawRoundedRect(chk_rect, 4, 4)

            pen_check = QPen(QColor("#ffffff"), 2.4)
            pen_check.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen_check.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen_check)
            cx, cy = chk_rect.x(), chk_rect.y()
            p1 = QPointF(cx + 5, cy + 11)
            p2 = QPointF(cx + 9, cy + 16)
            p3 = QPointF(cx + 17, cy + 6)
            path_chk = QPainterPath()
            path_chk.moveTo(p1)
            path_chk.lineTo(p2)
            path_chk.lineTo(p3)
            painter.drawPath(path_chk)
        else:
            # 체크 안 됨: 반투명 어두운 배경 + 또렷한 흰색 테두리
            painter.setPen(QPen(QColor("#ffffff"), 2.0))
            painter.setBrush(QColor(0, 0, 0, 160))
            painter.drawRoundedRect(chk_rect, 4, 4)

        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick):
            rect = option.rect.adjusted(3, 3, -3, -3)
            chk_hit_rect = QRect(rect.left(), rect.top(),
                                 self.CHECK_SIZE + self.CHECK_MARGIN * 2 + 8,
                                 self.CHECK_SIZE + self.CHECK_MARGIN * 2 + 8)
            if chk_hit_rect.contains(event.position().toPoint()):
                check_val = index.data(Qt.ItemDataRole.CheckStateRole)
                is_checked = (check_val == 2 or check_val == Qt.CheckState.Checked)
                new_state = Qt.CheckState.Unchecked if is_checked else Qt.CheckState.Checked
                model.setData(index, new_state, Qt.ItemDataRole.CheckStateRole)
                return True
        return super().editorEvent(event, model, option, index)


class MainWindow(QMainWindow):
    # 파워포인트 내보내기 작업 스레드 → GUI 스레드 전달용 시그널
    # 첫 인자는 로드 세대(token): 다른 파일로 바꾼 뒤 도착한 지난 콜백을 걸러낸다.
    ppt_count_ready = Signal(int, int, object)   # (token, 장수, 슬라이드 경로 목록)
    ppt_slide_ready = Signal(int, int, str, str) # (token, 인덱스, 이미지 경로, 노트)
    ppt_export_done = Signal(int, int)           # (token, 장수)
    ppt_export_failed = Signal(int, str)         # (token, 오류 메시지)
    ppt_show_state = Signal(object)              # 슬라이드쇼 상태 dict
    ppt_show_failed = Signal(str)                # 슬라이드쇼 오류
    ppt_edit_open_failed = Signal(str)           # 편집용 파워포인트 열기 실패
    ppt_edit_opened_as_copy = Signal(str)        # 편집용으로 원본 대신 임시 복사본이 열림
    ppt_edit_synced = Signal(str)                # 임시 복사본 저장 내용이 원본에 자동 반영됨
    mix_ppt_ready = Signal(str)                  # 묶음 안의 PPT 슬라이드가 그림으로 다 만들어짐
    mix_ppt_failed = Signal(str, str)            # 묶음 안의 PPT 를 그림으로 만들지 못함 (경로, 이유)
    mix_ppt_cancelled = Signal(str)              # 애니메이션 모드 때문에 중단됨 (모드를 끄면 다시)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("배경 텍스트 프리젠터 (Dual Monitor Presenter)")
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.setMinimumSize(800, 500)
        self.resize(1360, 800)

        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)
        # 가운데 카드(사진·슬라이드) 썸네일은 따로 된 일꾼들로 만든다.
        # 왼쪽 라이브러리 썸네일이나 읽기가 오래 걸리는 파일(동기화 중 등) 때문에
        # 가운데 카드가 줄 서서 기다리지 않게 하고, 다른 폴더를 열면 기다리던 일은 버린다.
        self.card_pool = QThreadPool()
        self.card_pool.setMaxThreadCount(4)
        self._old_card_pools = []
        self._card_thumb_serial = 0

        # 설정 저장소 (%APPDATA%/BgTextPresenter/settings.ini)
        # 테스트에서는 BGPT_SETTINGS_DIR 환경변수로 별도 저장소를 쓸 수 있다.
        settings_dir = os.environ.get("BGPT_SETTINGS_DIR") or os.path.join(
            os.environ.get("APPDATA", str(Path.home())), "BgTextPresenter")
        os.makedirs(settings_dir, exist_ok=True)
        self._settings_dir = settings_dir           # 묶음(.bgmix) 파일도 이 아래 mixes 폴더에 둔다
        self.settings = QSettings(os.path.join(settings_dir, "settings.ini"), QSettings.Format.IniFormat)

        # 언어 설정 (기본 ko)
        self.current_lang = str(self.settings.value("app/language", "ko") or "ko")
        if self.current_lang not in ("ko", "en"):
            self.current_lang = "ko"

        self.setWindowTitle(self._window_title())

        # 상태
        self.paragraphs = []            # 현재 텍스트 파일의 문단 리스트
        self.paragraph_index = -1       # 현재 송출 중인 문단 인덱스
        self.text_file_path = ""
        self.custom_colors = []         # 사용자 추가 색상 (hex 문자열)
        self.current_bg_desc = self.t("transparent")
        self._text_color_hex = "#FFFFFF"   # 글자 색상 (hex)
        self._border_color_hex = "#000000" # 테두리 색상 (hex)
        self._thumb_grid_dirty = True      # 썸네일 그리드 지연 생성 플래그
        self._paragraphs_dirty = False     # + 추가/드래그 순서변경/삭제 후 아직 파일 저장 전인지
        self._bg_needs_restore = False     # 시작 직후: 화면은 투명이지만 저장된 배경은 아직 미적용

        # 멀티 소스 상태 ("text", "folder") - 지금 목록/미리보기에 "보고 있는" 파일
        self.current_source_type = "text"
        self.current_source_path = ""
        # 실제 송출 화면에 나가고 있는 파일 (목록에서 다른 파일을 눌러 구경만 할 때는
        # 안 바뀐다 - 문단/슬라이드를 실제로 클릭해야 비로소 여기로 넘어간다)
        self._live_source_type = "text"
        self._live_source_path = ""
        self.media_slides = []              # 이미지 폴더 슬라이드 이미지 경로 목록
        self.media_slide_index = -1         # 현재 송출 중인 슬라이드 인덱스
        self._folder_replaced_bg = False    # 폴더의 불투명 이미지가 배경을 덮어쓴 상태인지
        self.media_source_kind = "folder"   # "folder"(이미지 폴더) 또는 "pptx"
        self.media_source_name = ""         # 원본 이름 (상태 표시용)
        self.media_notes = []               # PPT 슬라이드별 발표자 노트

        # 파워포인트 슬라이드 로딩 상태
        self._ppt_load_token = 0            # 로드 세대 (지난 작업의 콜백 무시용)
        self._ppt_total = 0                 # 전체 장수
        self._ppt_ready = set()             # 준비된 슬라이드 인덱스
        self._ppt_autopresent = False       # 첫 장 준비 시 자동 송출할지
        self._ppt_select_index = 0          # 처음 송출할 슬라이드 인덱스

        # 애니메이션 모드(실제 파워포인트 슬라이드쇼) 상태
        self._show_mode_active = False
        self._show_active_path = ""       # 지금 열려 있는 슬라이드쇼가 어느 파일 것인지
        self._show_timer = None
        self._show_poll_pending = False
        self._show_poll_sent_at = 0.0
        self._show_pending_hide = False   # 슬라이드쇼가 뜬 뒤에 송출 창을 숨기기 위한 표시
        self._show_range_start = 1        # 현재 쇼가 다루는 첫 슬라이드 (이 앞은 다시 열어야 함)

        # 모니터 연결/해제 감지 (HDMI 뽑았다 다시 꽂았을 때 자동 복귀용)
        self._show_screen_name = ""              # 지금 듀얼 송출에 쓰고 있는 모니터 이름
        self._show_screen_pending_restore = False  # 방금 연결이 끊긴 모니터가 그 모니터였는지

        # 파워포인트 내보내기 콜백 → GUI 스레드 (Qt가 자동으로 큐잉한다)
        self.ppt_count_ready.connect(self._on_ppt_count_ready)
        self.ppt_slide_ready.connect(self._on_ppt_slide_ready)
        self.ppt_export_done.connect(self._on_ppt_export_done)
        self.ppt_export_failed.connect(self._on_ppt_export_failed)
        self.ppt_show_state.connect(self._on_show_state)
        self.ppt_show_failed.connect(self._on_show_failed)
        self.ppt_edit_open_failed.connect(self._on_ppt_edit_open_failed)
        self.ppt_edit_opened_as_copy.connect(self._on_ppt_edit_opened_as_copy)
        self.ppt_edit_synced.connect(self._on_ppt_edit_synced)
        self.mix_ppt_ready.connect(self._on_mix_ppt_ready)
        self.mix_ppt_failed.connect(self._on_mix_ppt_failed)
        self.mix_ppt_cancelled.connect(lambda p: self._mix_exporting.discard(p))
        self.mix_entries = []
        self.mix_index = -1
        self._mix_exporting = set()
        self._mix_video_path = ""
        self._mix_drag_from = None
        self._mix_dragging = False
        self._mix_drag_start = None
        # 이미지 폴더 지켜보기: 폴더를 지웠다 다시 만들거나, 사진을 새로 내보내거나,
        # 구글 드라이브가 나중에 파일을 다시 써 넣어도 목록·썸네일·송출 화면을 새로 고친다
        self._folder_watcher = QFileSystemWatcher(self)
        self._folder_watcher.directoryChanged.connect(self._on_watched_folder_changed)
        self._folder_watch_timer = QTimer(self)
        self._folder_watch_timer.setSingleShot(True)
        self._folder_watch_timer.setInterval(1200)      # 여러 파일이 연달아 바뀌면 다 끝난 뒤 한 번만
        self._folder_watch_timer.timeout.connect(self._refresh_image_folder)
        self._folder_snapshot = {}
        self._thumb_retries = {}
        self._mix_picked = set()        # Ctrl/Shift 로 함께 고른 카드들 (카드 key)
        self._mix_anchor = -1           # Shift 범위 고르기의 시작 카드
        self._mix_press_mods = Qt.KeyboardModifier.NoModifier
        self._mix_drag_key = None       # 끌고 있는 (누른) 카드
        self._mix_drag_group = set()    # 함께 옮기는 카드들
        self._mix_scroll_step = 0
        self._mix_scroll_timer = QTimer(self)
        self._mix_scroll_timer.setInterval(40)
        self._mix_scroll_timer.timeout.connect(self._mix_autoscroll_tick)

        # 송출 창
        self.presenter = PresenterWindow()
        self.presenter.media_state_changed.connect(self._on_presenter_media_state)
        self.presenter.playlist_item_changed.connect(self._on_playlist_item_changed)
        # 본문 동영상(라이브러리의 동영상) 상태 → 조작 막대/카드/미리보기
        self.presenter.content_state_changed.connect(self._on_content_video_state)
        self.presenter.content_position_changed.connect(self._on_content_video_position)
        self.presenter.content_error.connect(self._on_content_video_error)
        self._subtitle_cache = {}          # 자막 파일 경로 → (수정 시각, SubtitleTrack)
        self._video_seek_dragging = False

        # 음악 재생 (상단 툴바) - 플레이어는 처음 재생할 때 만들어진다
        self.music = MusicController(self)

        # 새 버전 확인 (GitHub Releases) - 송출 중이면 창 대신 단추만 금색으로
        self.updates = UpdateController(
            self, self.settings, lambda: self.current_lang,
            is_busy=self._is_presenting_now,
            status=lambda msg, ms=8000: self.statusBar().showMessage(msg, ms))

        self._init_ui()
        self.presenter.content_frame_updated.connect(self.preview.set_content_frame)
        self.presenter.content_subtitle_changed.connect(self.preview.set_subtitle)
        self.music.state_changed.connect(self._on_music_state)
        self.music.track_changed.connect(self._on_music_track)
        self.music.playlist_changed.connect(self._rebuild_music_menu)
        self.music.error.connect(self._on_music_error)
        self._restore_window_layout()
        self.preview.preview_clicked.connect(self._on_preview_clicked)
        self._apply_dark_theme()
        self._load_screens()
        # 동영상 프레임을 미리보기에도 동일하게 표시
        self.presenter.video_frame_updated.connect(self.preview.set_video_frame)
        # 미리보기를 송출 화면과 같은 비율로 유지
        self._update_preview_aspect()
        # 복원 중 창이 처음 표시될 때부터 올바른 모니터를 사용하도록 대상 화면을 미리 지정
        screens = QGuiApplication.screens()
        idx = self.combo_screens.currentIndex()
        if 0 <= idx < len(screens):
            self.presenter.set_target_screen(screens[idx])
        self._load_library_and_settings()
        self._show_presenter_default()
        if self.current_lang != "ko":
            self._retranslate_ui()
        QApplication.instance().installEventFilter(self)
        # HDMI 등 모니터가 빠졌다 다시 꽂히는 것을 감지해 듀얼 송출을 자동 복귀시킨다
        QGuiApplication.instance().screenAdded.connect(self._on_screen_added)
        QGuiApplication.instance().screenRemoved.connect(self._on_screen_removed)
        from PySide6.QtGui import QShortcut, QKeySequence
        self._shortcut_reload = QShortcut(QKeySequence(Qt.Key.Key_F5), self)
        self._shortcut_reload.activated.connect(self._reload_image_folder_fresh)
        print(f"[시작] v{APP_VERSION} · {runtime_info()}")
        # 업데이트 뒤 다시 켜졌는지 알리고, 켤 때 새 버전을 조용히 확인한다 (exe 일 때만)
        self.updates.handle_startup_args(sys.argv)
        self.updates.start_auto_check()

    def t(self, key: str, *args) -> str:
        text = TRANSLATIONS.get(self.current_lang, TRANSLATIONS["ko"]).get(key, key)
        if args:
            text = text.format(*args)
        return text

    def _on_lang_changed(self, index: int):
        code = self.combo_lang.currentData()
        if code in ("ko", "en") and code != self.current_lang:
            self.current_lang = code
            self.settings.setValue("app/language", code)
            self._retranslate_ui()

    def _window_title(self) -> str:
        return f"{self.t('app_title')}  v{APP_VERSION}"

    def _is_presenting_now(self) -> bool:
        """지금 무언가를 송출하고 있는지 (업데이트 창을 띄워도 되는지 판단)"""
        try:
            if getattr(self, "_show_mode_active", False):
                return True
            if getattr(self, "paragraph_index", -1) >= 0 or getattr(self, "media_slide_index", -1) >= 0:
                return True
            if getattr(self, "mix_index", -1) >= 0:
                return True
            if self.music.is_playing():
                return True
            if self.presenter.has_text() or getattr(self.presenter, "overlay_image_path", ""):
                return True
            player = getattr(self.presenter, "content_player", None)
            if player is not None and player.playbackState() == player.PlaybackState.PlayingState:
                return True
            return False
        except Exception:
            return False

    def _retranslate_ui(self):
        self.setWindowTitle(self._window_title())
        if hasattr(self, "updates"):
            self.updates.retranslate()
        if hasattr(self, "presenter") and self.presenter:
            self.presenter.setWindowTitle(self.t("presenter_window_title"))
        if hasattr(self, "lbl_display"):
            self.lbl_display.setText(self.t("display"))
        if hasattr(self, "combo_screens"):
            self._load_screens()
        if hasattr(self, "btn_fullscreen"):
            self.btn_fullscreen.setText(self.t("windowed") if (hasattr(self, "presenter") and self.presenter.fill_screen) else self.t("fullscreen"))
        if hasattr(self, "btn_toggle_window"):
            self.btn_toggle_window.setText(self.t("close_dual") if self.btn_toggle_window.isChecked() else self.t("open_dual"))
        if getattr(self, "lbl_bg", None):
            self.lbl_bg.setText(self.t("bg_label"))
        if getattr(self, "btn_transparent", None):
            self.btn_transparent.setToolTip(self.t("transparent"))
        if getattr(self, "btn_custom_color", None):
            self.btn_custom_color.setText(self.t("custom_color"))
        if getattr(self, "btn_add_images", None):
            self.btn_add_images.setText(self.t("add_images"))
        if getattr(self, "btn_add_videos", None):
            self.btn_add_videos.setText(self.t("add_videos"))
        if hasattr(self, "lbl_lang"):
            self.lbl_lang.setText(self.t("language"))

        # 좌측 배경 라이브러리 탭
        if hasattr(self, "library_tabs"):
            self.library_tabs.setTabText(0, self.t("tab_color"))
            self.library_tabs.setTabText(1, self.t("tab_image"))
            self.library_tabs.setTabText(2, self.t("tab_video"))
        if hasattr(self, "btn_color_add"):
            self.btn_color_add.setText(self.t("add_color_btn"))
        if hasattr(self, "btn_color_del"):
            self.btn_color_del.setText(self.t("delete_btn"))

        # 색상 견본 텍스트 및 툴팁 갱신
        if hasattr(self, "list_colors"):
            for i in range(self.list_colors.count()):
                it = self.list_colors.item(i)
                kind = it.data(USER_ROLE_KIND)
                if kind == "transparent":
                    it.setText(self.t("transparent_swatch"))
                    it.setToolTip(self.t("transparent_swatch_tip"))
                elif kind == "preset":
                    path_hex = str(it.data(USER_ROLE_PATH) or "")
                    key = PRESET_COLOR_KEYS.get(path_hex.lower())
                    if key:
                        it.setText(f"{self.t(key)} ({path_hex.upper()})")
                        it.setToolTip(f"{self.t(key)} ({path_hex.upper()})")
                elif kind == "custom":
                    path_hex = str(it.data(USER_ROLE_PATH) or "")
                    it.setText(f"{self.t('color_custom_prefix')} {path_hex}")
                    it.setToolTip(f"{self.t('color_custom_prefix')} {path_hex}")

        if hasattr(self, "btn_img_add"):
            self.btn_img_add.setText(self.t("add_images"))
        if hasattr(self, "btn_img_del"):
            self.btn_img_del.setText(self.t("delete_btn"))
        if hasattr(self, "btn_img_clear"):
            self.btn_img_clear.setText(self.t("clear_all_btn"))
            self.btn_img_clear.setToolTip(self.t("clear_all_images_tip"))

        if hasattr(self, "btn_vid_add"):
            self.btn_vid_add.setText(self.t("add_videos"))
        if hasattr(self, "btn_vid_del"):
            self.btn_vid_del.setText(self.t("delete_btn"))
        if hasattr(self, "btn_vid_clear"):
            self.btn_vid_clear.setText(self.t("clear_all_btn"))
            self.btn_vid_clear.setToolTip(self.t("clear_all_videos_tip"))
        if hasattr(self, "lbl_vol"):
            self.lbl_vol.setText(self.t("volume"))
        if hasattr(self, "lbl_playlist_state"):
            self._update_playlist_state()

        # 좌측 텍스트 파일 & 이미지 폴더 등록
        if hasattr(self, "grp_text_files"):
            self.grp_text_files.setTitle(self.t("text_lib_title"))
        if hasattr(self, "btn_add_item"):
            self.btn_add_item.setText(self.t("btn_add_item"))
            self.btn_add_item.setToolTip(self.t("btn_add_item_tip"))
        if hasattr(self, "btn_clear_text_files"):
            self.btn_clear_text_files.setText(self.t("btn_clear_text_files"))
            self.btn_clear_text_files.setToolTip(self.t("btn_clear_text_files_tip"))
        if hasattr(self, "lbl_text_files_hint"):
            self.lbl_text_files_hint.setText(self.t("txt_lib_hint"))
        self._refresh_text_files_list(select_path=self.text_file_path)

        # 중앙 문단 선택 패널
        if hasattr(self, "grp_file"):
            self.grp_file.setTitle(self.t("text_file_group"))
        if hasattr(self, "btn_open_txt"):
            self.btn_open_txt.setText(self.t("open_txt_btn"))
        if hasattr(self, "lbl_file_prefix"):
            self.lbl_file_prefix.setText(self.t("selected_file"))
        if hasattr(self, "lbl_txt_file"):
            if not self.text_file_path:
                self.lbl_txt_file.setText(self.t("none"))
            elif getattr(self, "current_source_type", "text") == "direct_text":
                self.lbl_txt_file.setText(self.t("direct_text_title"))
            elif getattr(self, "current_source_type", "text") == "folder":
                self.lbl_txt_file.setText(f"📁 {os.path.basename(self.text_file_path)} ({len(self.media_slides)}{self.t('items_count_suffix')})")
        if hasattr(self, "lbl_txt_file") and getattr(self, "current_source_type", "text") == "mix":
            self._set_mix_title_label()

        if hasattr(self, "grp_para"):
            self.grp_para.setTitle(self.t("para_select_group"))
        if hasattr(self, "para_tab"):
            self.para_tab.setTabText(0, self.t("tab_para_list"))
            if self.para_tab.count() > 1:
                self.para_tab.setTabText(1, self.t("tab_direct_text"))
        if hasattr(self, "lbl_list_font_size"):
            self.lbl_list_font_size.setText(self.t("font_size_label"))
        if hasattr(self, "lbl_list_columns"):
            self.lbl_list_columns.setText(self.t("columns_label"))
        if hasattr(self, "lbl_thumb_size"):
            self.lbl_thumb_size.setText(self.t("slide_thumb_title"))

        # 직접 입력 탭 위젯들
        if hasattr(self, "lbl_dir_font"):
            self.lbl_dir_font.setText(self.t("font_size_label"))
        if hasattr(self, "chk_direct_realtime"):
            self.chk_direct_realtime.setText(self.t("direct_realtime"))
            self.chk_direct_realtime.setToolTip(self.t("direct_realtime_tip"))
        if hasattr(self, "btn_direct_clear"):
            self.btn_direct_clear.setText(self.t("direct_clear"))
            self.btn_direct_clear.setToolTip(self.t("direct_clear_tip"))
        if hasattr(self, "txt_direct_input"):
            self.txt_direct_input.setPlaceholderText(self.t("direct_placeholder"))
        if hasattr(self, "btn_direct_broadcast"):
            self.btn_direct_broadcast.setText(self.t("btn_direct_broadcast"))
            self.btn_direct_broadcast.setToolTip(self.t("btn_direct_broadcast_tip"))
        if hasattr(self, "btn_direct_stop"):
            self.btn_direct_stop.setText(self.t("btn_direct_stop"))
            self.btn_direct_stop.setToolTip(self.t("btn_direct_stop_tip"))
        if hasattr(self, "btn_stop_paragraph_text"):
            self.btn_stop_paragraph_text.setText(self.t("btn_para_stop"))
            self.btn_stop_paragraph_text.setToolTip(self.t("btn_para_stop_tip"))
        if hasattr(self, "btn_save_paragraphs"):
            if getattr(self, "_paragraphs_dirty", False):
                self.btn_save_paragraphs.setText("● " + self.t("btn_save_paragraphs"))
                self.btn_save_paragraphs.setToolTip(self.t("btn_save_paragraphs_unsaved_tip"))
            else:
                self.btn_save_paragraphs.setText(self.t("btn_save_paragraphs"))
                self.btn_save_paragraphs.setToolTip(self.t("btn_save_paragraphs_tip"))
        if hasattr(self, "btn_direct_to_paras"):
            self.btn_direct_to_paras.setText(self.t("btn_direct_to_paras"))
            self.btn_direct_to_paras.setToolTip(self.t("btn_direct_to_paras_tip"))
        if hasattr(self, "btn_direct_save"):
            self.btn_direct_save.setText(self.t("btn_direct_save"))
            self.btn_direct_save.setToolTip(self.t("btn_direct_save_tip"))

        # 우측 편집 및 스타일 패널
        if hasattr(self, "grp_edit"):
            self.grp_edit.setTitle(self.t("edit_group"))
        if hasattr(self, "btn_edit_dialog"):
            self.btn_edit_dialog.setText(self.t("open_editor_dialog"))
        if hasattr(self, "btn_direct_write"):
            self.btn_direct_write.setText(self.t("btn_direct_write"))
        if hasattr(self, "btn_edit_toggle"):
            self.btn_edit_toggle.setText(self.t("edit_mode_off") if self.btn_edit_toggle.isChecked() else self.t("edit_mode_toggle"))
        if hasattr(self, "rad_edit_current"):
            self.rad_edit_current.setText(self.t("rad_edit_current_short"))
        if hasattr(self, "rad_edit_all"):
            self.rad_edit_all.setText(self.t("rad_edit_all_short"))
        if hasattr(self, "btn_apply_edit"):
            self.btn_apply_edit.setText(self.t("dialog_apply"))
        if hasattr(self, "btn_cancel_edit"):
            self.btn_cancel_edit.setText(self.t("dialog_cancel"))

        if hasattr(self, "grp_style"):
            self.grp_style.setTitle(self.t("text_style_group"))
        if hasattr(self, "grp_notes"):
            images = self._is_image_folder_mode()
            self.grp_notes.setTitle(self.t("image_notes_group" if images else "notes_group"))
            self.lbl_notes_font.setText(self.t("notes_font_size"))
            self.txt_slide_notes.setPlaceholderText(self.t("image_notes_empty" if images else "notes_empty"))
            self.btn_image_note_edit.setText(self.t("btn_image_note_edit"))
            self.btn_image_note_edit.setToolTip(self.t("btn_image_note_edit_tip"))
            self.btn_notes_popup.setText(self.t("btn_notes_popup"))
            self.btn_notes_popup.setToolTip(self.t("btn_notes_popup_tip"))
            if getattr(self, "notes_popup", None) is not None:
                self.notes_popup.setWindowTitle(self.t("notes_popup_title"))
                self._sync_notes_popup()
            if self._is_pptx_mode() or (images and getattr(self, "_notes_shown_index", -1) >= 0):
                self._show_slide_notes(getattr(self, "media_slide_index", -1))
        if hasattr(self, "lbl_style_font"):
            self.lbl_style_font.setText(self.t("font_family"))
        if hasattr(self, "lbl_style_size"):
            self.lbl_style_size.setText(self.t("font_size"))
        if hasattr(self, "lbl_style_color"):
            self.lbl_style_color.setText(self.t("text_color"))
        if hasattr(self, "chk_border"):
            self.chk_border.setText(self.t("text_border"))
        if hasattr(self, "valign_buttons"):
            self.lbl_valign.setText(self.t("text_valign"))
            for key, btn in self.valign_buttons.items():
                btn.setText(self.t(f"valign_{key}"))
                btn.setToolTip(self.t("valign_tip"))
            self.lbl_margin_top.setText(self.t("margin_top"))
            self.lbl_margin_bottom.setText(self.t("margin_bottom"))
            self.spin_margin_top.setToolTip(self.t("margin_tip"))
            self.spin_margin_bottom.setToolTip(self.t("margin_tip"))
        if hasattr(self, "lbl_border_width"):
            self.lbl_border_width.setText(self.t("border_width"))
        if hasattr(self, "lbl_border_color"):
            self.lbl_border_color.setText(self.t("border_color"))
        if hasattr(self, "btn_clear_text"):
            self.btn_clear_text.setText(self.t("clear_text_btn"))

        if hasattr(self, "lbl_preview_title"):
            self.lbl_preview_title.setText(self.t("preview_title"))

        # 본문 동영상 조작 막대
        if hasattr(self, "btn_video_play"):
            self.btn_video_play.setToolTip(self.t("video_play_tip"))
            self.btn_video_stop.setText(self.t("video_stop"))
            self.btn_video_stop.setToolTip(self.t("video_stop_tip"))
            self.sld_video_pos.setToolTip(self.t("video_seek_tip"))
            self.sld_video_volume.setToolTip(self.t("video_volume_tip"))
            self.btn_subtitle.setText(self.t("subtitle_btn"))
            self.btn_subtitle.setToolTip(self.t("subtitle_btn_tip"))
            self.act_subtitle_choose.setText(self.t("subtitle_menu_choose"))
            self.act_subtitle_auto.setText(self.t("subtitle_menu_auto"))
            self.act_subtitle_off.setText(self.t("subtitle_menu_off"))
            self.lbl_subtitle_size.setText(self.t("subtitle_size"))
            self.spin_subtitle_size.setToolTip(self.t("subtitle_size_tip"))
            self._update_video_bar()
        # 음악
        if hasattr(self, "lbl_music"):
            self.lbl_music.setText(self.t("music_label"))
            self.lbl_music_time.setToolTip(self.t("music_time_tip"))
            self.btn_music_open.setToolTip(self.t("music_open_tip"))
            self.btn_music_prev.setToolTip(self.t("music_prev_tip"))
            self.btn_music_play.setToolTip(self.t("music_play_tip"))
            self.btn_music_next.setToolTip(self.t("music_next_tip"))
            self.btn_music_stop.setToolTip(self.t("music_stop_tip"))
            self.sld_music_volume.setToolTip(self.t("music_volume_tip"))
            self._update_music_mode_button()
            name = (os.path.basename(self.music.playlist[self.music.index])
                    if 0 <= self.music.index < len(self.music.playlist) else "")
            self._on_music_track(self.music.index, len(self.music.playlist), name)

        bg_type = str(self.settings.value("bg/type", "transparent") or "transparent")
        if bg_type == "transparent" or getattr(self, "_bg_needs_restore", False):
            self.current_bg_desc = self.t("transparent")
        elif bg_type == "color":
            bg_val = str(self.settings.value("bg/value", "") or "")
            if bg_val.lower() in PRESET_COLOR_KEYS:
                self.current_bg_desc = f"{self.t(PRESET_COLOR_KEYS[bg_val.lower()])} ({bg_val.upper()})"
            elif bg_val:
                self.current_bg_desc = f"{self.t('color_custom_prefix')} {bg_val}"
        elif getattr(self, "current_source_type", "text") == "folder" and 0 <= getattr(self, "media_slide_index", -1) < len(getattr(self, "media_slides", [])):
            self.current_bg_desc = self._media_slide_desc(self.media_slide_index)

        self._rebuild_paragraph_list()
        self._update_status()

    def resizeEvent(self, event):
        """창 크기가 바뀌면 문단 목록 레이아웃 재배치"""
        super().resizeEvent(event)
        self._relayout_paragraph_list()

    # ------------------------------------------------------------------
    # UI 구성
    # ------------------------------------------------------------------
    def _init_ui(self):
        # ---------- 상단 메뉴(툴바): 배경 선택 버튼 ----------
        toolbar = QToolBar(self.t("top_toolbar"), self)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)

        self.lbl_display = QLabel(" 🖥️ 디스플레이: ")
        toolbar.addWidget(self.lbl_display)
        self.combo_screens = QComboBox(self)
        self.combo_screens.setMinimumWidth(110)
        self.combo_screens.currentIndexChanged.connect(self._on_screen_selected)
        toolbar.addWidget(self.combo_screens)

        self.btn_fullscreen = QPushButton("⛶ 전체화면", self)
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        toolbar.addWidget(self.btn_fullscreen)

        self.btn_toggle_window = QPushButton("🖥️ 듀얼 창 열기", self)
        self.btn_toggle_window.setCheckable(True)
        self.btn_toggle_window.setChecked(True)
        self.btn_toggle_window.clicked.connect(self._toggle_presenter_window)
        toolbar.addWidget(self.btn_toggle_window)

        toolbar.addSeparator()
        self.lbl_lang = QLabel(" 🌐 언어: ")
        toolbar.addWidget(self.lbl_lang)
        self.combo_lang = QComboBox(self)
        self.combo_lang.addItem("한국어", "ko")
        self.combo_lang.addItem("English", "en")
        idx_lang = self.combo_lang.findData(self.current_lang)
        if idx_lang >= 0:
            self.combo_lang.setCurrentIndex(idx_lang)
        self.combo_lang.currentIndexChanged.connect(self._on_lang_changed)
        toolbar.addWidget(self.combo_lang)

        toolbar.addSeparator()
        self.btn_update = QPushButton(self)
        toolbar.addWidget(self.btn_update)
        self.updates.set_button(self.btn_update)

        # ---------- 음악 (여러 곡을 골라 차례로 재생) ----------
        # 단추가 커지고 시간 표시가 생겨 자리를 많이 차지하므로 따로 된 도구 막대에 둔다.
        # 화면이 넓으면 위 막대 옆에 이어서, 좁으면(노트북 등) 한 줄 아래에 놓는다.
        music_bar = QToolBar(self.t("music_toolbar"), self)
        music_bar.setIconSize(QSize(22, 22))
        music_bar.setMovable(False)
        music_bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None or screen.availableGeometry().width() < 1700:
            self.addToolBarBreak()
        self.addToolBar(music_bar)
        self.music_bar = music_bar
        self._build_music_controls(music_bar)

        # ---------- 메인 스플리터 (3단 구조) ----------
        # 구조:
        #   [좌측: 배경 라이브러리 + 텍스트 파일 등록]
        #   [가운데: 문단 선택 패널 (문단 목록 / 썸네일 그리드) - 가장 넓게]
        #   [우측 (세로): 상단 텍스트 편집·글자 스타일 / 하단 송출 화면 미리보기]
        main_splitter = QSplitter(Qt.Orientation.Horizontal, self)
        main_splitter.setChildrenCollapsible(False)
        self.setCentralWidget(main_splitter)

        # ----- 1. 좌측: 배경 라이브러리 + 텍스트 파일 등록 -----
        left_container = QWidget()
        left_container.setMinimumWidth(180)
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        left_splitter = QSplitter(Qt.Orientation.Vertical, left_container)
        left_layout.addWidget(left_splitter)

        left_splitter.addWidget(self._build_background_library())
        left_splitter.addWidget(self._build_text_files_panel())
        left_splitter.setSizes([520, 240])
        left_splitter.setStretchFactor(0, 1)
        left_splitter.setStretchFactor(1, 0)
        self.left_splitter = left_splitter
        main_splitter.addWidget(left_container)

        # ----- 2. 가운데: 문단 선택 패널 (가장 넓게) -----
        center_widget = self._build_paragraph_panel()
        center_widget.setMinimumWidth(350)
        main_splitter.addWidget(center_widget)

        # ----- 3. 우측: 상단 텍스트 편집·스타일 / 하단 송출 미리보기 -----
        right_container = QWidget()
        right_container.setMinimumWidth(180)
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        right_splitter = QSplitter(Qt.Orientation.Vertical, right_container)
        right_layout.addWidget(right_splitter)

        # 우측 상단: 텍스트 편집 + 글자 스타일 (컴팩트)
        right_splitter.addWidget(self._build_edit_and_style_panel())

        # 우측 하단: 송출 화면 미리보기
        right_splitter.addWidget(self._build_preview_panel())

        right_splitter.setSizes([300, 360])
        right_splitter.setStretchFactor(0, 0)
        right_splitter.setStretchFactor(1, 1)
        self.right_splitter = right_splitter
        main_splitter.addWidget(right_container)

        # 3단 크기 분배: 좌측(240px), 가운데(860px, stretch=1), 우측(220px)
        main_splitter.setSizes([240, 860, 220])
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setStretchFactor(2, 0)
        self.main_splitter = main_splitter

        # 스플리터 드래그 시 문단 목록 및 미리보기 자동 재배치
        self.main_splitter.splitterMoved.connect(lambda *_: self._relayout_paragraph_list())
        self.right_splitter.splitterMoved.connect(lambda *_: self._update_preview_aspect())

    # ------------------------------------------------------------------
    # 음악 (상단 툴바)
    # ------------------------------------------------------------------
    def _build_music_controls(self, toolbar):
        # 단추를 크게, 그림은 직접 그려서 또렷하게 (작은 이모지는 알아보기 어려웠다)
        button_css = ("QPushButton { padding: 2px; }"
                      "QPushButton[emoji=\"true\"] { font-size: 17px; }")

        def small(icon_kind, text, tip, slot, width=40):
            btn = QPushButton(text, self)
            btn.setToolTip(tip)
            btn.setFixedSize(width, 32)
            btn.setStyleSheet(button_css)
            if icon_kind:
                btn.setIcon(make_media_icon(icon_kind, 22))
                btn.setIconSize(QSize(22, 22))
            else:
                btn.setProperty("emoji", True)
            btn.clicked.connect(slot)
            toolbar.addWidget(btn)
            return btn

        self.lbl_music = QLabel(self.t("music_label"))
        toolbar.addWidget(self.lbl_music)
        self.btn_music_open = small(None, "📂", self.t("music_open_tip"), lambda: self._choose_music_files(False))
        self.btn_music_prev = small("prev", "", self.t("music_prev_tip"), self.music.previous)
        self.btn_music_play = small("play", "", self.t("music_play_tip"), self._on_music_play_clicked, width=48)
        self.btn_music_next = small("next", "", self.t("music_next_tip"), self.music.next)
        self.btn_music_stop = small("stop", "", self.t("music_stop_tip"), self.music.stop)

        # 재생한 시간 / 곡 길이 와 남은 시간
        self.lbl_music_time = QLabel("")
        self.lbl_music_time.setToolTip(self.t("music_time_tip"))
        self.lbl_music_time.setStyleSheet("QLabel { color: #9fd3ff; font-size: 13px; padding: 0 6px; }")
        self.lbl_music_time.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_music_time.setMinimumWidth(QFontMetrics(self.lbl_music_time.font()).horizontalAdvance(
            "00:00 / 00:00  -00:00") + 24)
        toolbar.addWidget(self.lbl_music_time)
        self.music.position_changed.connect(self._on_music_position)
        self._on_music_position(0, 0)

        self.sld_music_volume = QSlider(Qt.Orientation.Horizontal, self)
        self.sld_music_volume.setRange(0, 100)
        self.sld_music_volume.setFixedWidth(80)
        self.sld_music_volume.setToolTip(self.t("music_volume_tip"))
        self.sld_music_volume.valueChanged.connect(self._on_music_volume_changed)
        toolbar.addWidget(self.sld_music_volume)

        self.btn_music_repeat = QPushButton("🔁", self)
        self.btn_music_repeat.setCheckable(True)
        self.btn_music_repeat.setFixedSize(40, 32)
        self.btn_music_repeat.setStyleSheet("QPushButton { font-size: 17px; padding: 2px; }")
        self.btn_music_repeat.setToolTip(self.t("music_repeat_tip"))
        self.btn_music_repeat.toggled.connect(self._on_music_repeat_toggled)
        toolbar.addWidget(self.btn_music_repeat)

        # 재생 방식: 연속 재생 ↔ 한 곡씩 (누를 때마다 바뀜)
        self.btn_music_mode = QPushButton(self)
        self.btn_music_mode.clicked.connect(self._toggle_music_mode)
        toolbar.addWidget(self.btn_music_mode)
        self._update_music_mode_button()

        # 지금 곡 표시 + 누르면 목록(곡 고르기 / 추가 / 비우기)
        self.btn_music_list = QPushButton(self.t("music_none"), self)
        self.btn_music_list.setToolTip(self.t("music_list_tip"))
        self.btn_music_list.setMinimumWidth(120)
        self.btn_music_list.setMaximumWidth(260)
        self.music_menu = QMenu(self)
        self.btn_music_list.setMenu(self.music_menu)
        toolbar.addWidget(self.btn_music_list)
        self._rebuild_music_menu()

    def _music_settings_save(self):
        self.settings.setValue("music/files", "\n".join(self.music.playlist))
        self.settings.setValue("music/index", max(0, self.music.index))

    def _restore_music_settings(self):
        s = self.settings
        volume = int(s.value("music/volume", 70) or 70)
        self.sld_music_volume.blockSignals(True)
        self.sld_music_volume.setValue(volume)
        self.sld_music_volume.blockSignals(False)
        self.music.set_volume(volume)
        repeat = str(s.value("music/repeat", "true")).lower() in ("true", "1")
        self.btn_music_repeat.blockSignals(True)
        self.btn_music_repeat.setChecked(repeat)
        self.btn_music_repeat.blockSignals(False)
        self.music.set_repeat(repeat)
        mode = str(s.value("music/mode", "continuous") or "continuous")
        self.music.set_mode(mode)
        self._update_music_mode_button()
        raw = str(s.value("music/files", "") or "")
        files = [p for p in raw.split("\n") if p and os.path.isfile(p)]
        if files:
            index = int(s.value("music/index", 0) or 0)
            # 시작할 때는 목록만 되살리고 재생은 하지 않는다
            self.music.set_playlist(files, start_index=min(index, len(files) - 1), autoplay=False)

    def _choose_music_files(self, append: bool = False):
        last_dir = self.settings.value("music/last_dir", "") or self.settings.value("last_dir", str(Path.home()))
        files, _ = QFileDialog.getOpenFileNames(
            self, self.t("dialog_select_music"), str(last_dir), self.t("filter_music"))
        files = [f for f in files if f]
        if not files:
            return
        self.settings.setValue("music/last_dir", os.path.dirname(files[0]))
        if append and self.music.playlist:
            self.music.add(files)
        else:
            self.music.set_playlist(files, 0, autoplay=True)
        self._music_settings_save()

    def _clear_music(self):
        self.music.clear()
        self._music_settings_save()

    def _on_music_play_clicked(self):
        if not self.music.playlist:
            self._choose_music_files(False)
            return
        self.music.toggle()

    def _on_music_volume_changed(self, value: int):
        self.music.set_volume(value)
        self.settings.setValue("music/volume", int(value))

    def _on_music_repeat_toggled(self, checked: bool):
        self.music.set_repeat(checked)
        self.settings.setValue("music/repeat", bool(checked))

    def _toggle_music_mode(self):
        self._set_music_mode("single" if self.music.mode == "continuous" else "continuous")

    def _set_music_mode(self, mode: str):
        self.music.set_mode(mode)
        self.settings.setValue("music/mode", self.music.mode)
        self._update_music_mode_button()

    def _update_music_mode_button(self):
        if not hasattr(self, "btn_music_mode"):
            return
        single = self.music.mode == "single"
        self.btn_music_mode.setText(self.t("music_mode_single" if single else "music_mode_continuous"))
        self.btn_music_mode.setToolTip(self.t("music_mode_single_tip" if single else "music_mode_continuous_tip"))
        if hasattr(self, "btn_music_repeat"):
            # 한 곡씩일 때 반복은 '한 곡 반복'
            self.btn_music_repeat.setText("🔂" if single else "🔁")
            self.btn_music_repeat.setToolTip(self.t("music_repeat_one_tip" if single else "music_repeat_tip"))

    def _on_music_position(self, position: int, duration: int):
        """재생한 시간 / 곡 길이  -남은 시간"""
        if not hasattr(self, "lbl_music_time"):
            return
        if not self.music.playlist:
            self.lbl_music_time.setText("--:-- / --:--")
            return
        if duration <= 0:
            self.lbl_music_time.setText(f"{format_play_time(position)} / --:--")
            return
        remain = max(0, duration - position)
        self.lbl_music_time.setText(
            f"{format_play_time(position)} / {format_play_time(duration)}  -{format_play_time(remain)}")

    def _on_music_state(self, state: str):
        if hasattr(self, "btn_music_play"):
            self.btn_music_play.setIcon(make_media_icon("pause" if state == "playing" else "play", 22))

    def _on_music_track(self, index: int, total: int, name: str):
        if not hasattr(self, "btn_music_list"):
            return
        if total <= 0 or index < 0:
            label = self.t("music_none")
        else:
            label = f"{index + 1}/{total}  {name}"
        fm = QFontMetrics(self.btn_music_list.font())
        self.btn_music_list.setText(fm.elidedText(label, Qt.TextElideMode.ElideMiddle, 230))
        self._on_music_position(self.music.position(), self.music.duration())
        self.btn_music_list.setToolTip(f"{self.t('music_list_tip')}\n{label}")
        self._rebuild_music_menu()
        self.settings.setValue("music/index", max(0, index))

    def _rebuild_music_menu(self):
        if not hasattr(self, "music_menu"):
            return
        menu = self.music_menu
        menu.clear()
        for i, path in enumerate(self.music.playlist):
            mark = "▶ " if i == self.music.index else "    "
            act = menu.addAction(f"{mark}{i + 1}. {os.path.basename(path)}")
            act.triggered.connect(lambda _=False, n=i: self.music.play(n))
        if self.music.playlist:
            menu.addSeparator()
        act_add = menu.addAction(self.t("music_menu_add"))
        act_add.triggered.connect(lambda: self._choose_music_files(True))
        act_clear = menu.addAction(self.t("music_menu_clear"))
        act_clear.triggered.connect(self._clear_music)
        act_clear.setEnabled(bool(self.music.playlist))
        if not self.music.playlist and hasattr(self, "btn_music_list"):
            self.btn_music_list.setText(self.t("music_none"))

    def _on_music_error(self, name: str):
        self.statusBar().showMessage(self.t("msg_music_error", name), 5000)

    def _build_background_library(self) -> QWidget:
        """좌측: 배경 라이브러리 (색상/이미지/동영상 탭)"""
        self.library_tabs = QTabWidget()
        self.library_tabs.setMinimumWidth(160)

        # --- 색상 탭 ---
        color_widget = QWidget()
        color_layout = QVBoxLayout(color_widget)
        color_layout.setContentsMargins(6, 6, 6, 6)

        # 색상 탭은 작은 견본 그리드로 컴팩트하게 표시
        self.list_colors = QListWidget()
        self.list_colors.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_colors.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_colors.setIconSize(QSize(44, 28))
        self.list_colors.setGridSize(QSize(60, 50))
        self.list_colors.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_colors.setMovement(QListWidget.Movement.Static)
        self.list_colors.setSpacing(4)
        self.list_colors.setWordWrap(False)
        self.list_colors.itemClicked.connect(self._on_color_selected)
        self.list_colors.installEventFilter(self)
        self.list_colors.viewport().installEventFilter(self)
        color_layout.addWidget(self.list_colors, 1)

        color_btns = QHBoxLayout()
        self.btn_color_add = QPushButton("🎨 색상 추가…")
        self.btn_color_add.clicked.connect(self._add_custom_color)
        self.btn_color_del = QPushButton("🗑 삭제")
        self.btn_color_del.clicked.connect(self._delete_selected_color)
        color_btns.addWidget(self.btn_color_add)
        color_btns.addWidget(self.btn_color_del)
        color_layout.addLayout(color_btns)

        self.library_tabs.addTab(color_widget, "색상")

        # --- 이미지 탭 ---
        image_widget = QWidget()
        image_layout = QVBoxLayout(image_widget)
        image_layout.setContentsMargins(6, 6, 6, 6)

        self.list_images = DropListWidget()
        self.list_images.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_images.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_images.setIconSize(QSize(100, 75))
        self.list_images.setGridSize(QSize(112, 85))
        self.list_images.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_images.setMovement(QListWidget.Movement.Static)
        self.list_images.setSpacing(6)
        self.list_images.setWrapping(True)
        self.list_images.itemClicked.connect(self._on_image_selected)
        self.list_images.installEventFilter(self)
        self.list_images.viewport().installEventFilter(self)
        self.list_images.filesDropped.connect(self._handle_images_dropped)
        image_layout.addWidget(self.list_images, 1)

        image_btns = QHBoxLayout()
        image_btns.setSpacing(4)
        self.btn_img_add = QPushButton("🖼️ 추가")
        self.btn_img_add.clicked.connect(self._add_images)
        self.btn_img_del = QPushButton("🗑 삭제")
        self.btn_img_del.clicked.connect(self._delete_selected_image)
        self.btn_img_clear = QPushButton("🧹 전체 비우기")
        self.btn_img_clear.setToolTip("이미지 목록을 모두 비웁니다.")
        self.btn_img_clear.clicked.connect(self._clear_all_images)
        image_btns.addWidget(self.btn_img_add)
        image_btns.addWidget(self.btn_img_del)
        image_btns.addWidget(self.btn_img_clear)
        image_layout.addLayout(image_btns)

        self.library_tabs.addTab(image_widget, "이미지")

        # --- 동영상 탭 ---
        video_widget = QWidget()
        video_layout = QVBoxLayout(video_widget)
        video_layout.setContentsMargins(6, 6, 6, 6)

        self.list_videos = DropListWidget()
        self.list_videos.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_videos.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_videos.setItemDelegate(VideoThumbnailDelegate(self.list_videos))
        self.list_videos.setIconSize(QSize(110, 80))
        self.list_videos.setGridSize(QSize(124, 94))
        self.list_videos.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_videos.setMovement(QListWidget.Movement.Static)
        self.list_videos.setSpacing(6)
        self.list_videos.setWrapping(True)
        self.list_videos.itemClicked.connect(self._on_video_clicked)
        self.list_videos.itemChanged.connect(self._on_video_check_changed)
        self.list_videos.installEventFilter(self)
        self.list_videos.viewport().installEventFilter(self)
        self.list_videos.filesDropped.connect(self._handle_videos_dropped)
        video_layout.addWidget(self.list_videos, 1)

        video_btns2 = QHBoxLayout()
        video_btns2.setSpacing(4)
        self.btn_vid_add = QPushButton("🎬 추가")
        self.btn_vid_add.clicked.connect(self._add_videos)
        self.btn_vid_del = QPushButton("🗑 삭제")
        self.btn_vid_del.clicked.connect(self._delete_selected_video)
        self.btn_vid_clear = QPushButton("🧹 전체 비우기")
        self.btn_vid_clear.setToolTip("동영상 목록을 모두 비웁니다.")
        self.btn_vid_clear.clicked.connect(self._clear_all_videos)
        video_btns2.addWidget(self.btn_vid_add)
        video_btns2.addWidget(self.btn_vid_del)
        video_btns2.addWidget(self.btn_vid_clear)
        video_layout.addLayout(video_btns2)

        vol_row = QHBoxLayout()
        self.lbl_vol = QLabel("🔊 볼륨")
        vol_row.addWidget(self.lbl_vol)
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(70)
        self.vol_slider.valueChanged.connect(self.presenter.set_volume)
        vol_row.addWidget(self.vol_slider, 1)
        video_layout.addLayout(vol_row)

        self.lbl_playlist_state = QLabel("재생 목록: 선택된 동영상 없음")
        self.lbl_playlist_state.setWordWrap(True)
        video_layout.addWidget(self.lbl_playlist_state)

        self.library_tabs.addTab(video_widget, "동영상")

        return self.library_tabs

    def _build_preview_panel(self) -> QWidget:
        """중앙: 실시간 미리보기"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)

        self.lbl_preview_title = QLabel("📡 송출 화면 미리보기")
        self.lbl_preview_title.setStyleSheet("font-weight: bold; color: #e74c3c;")
        layout.addWidget(self.lbl_preview_title)

        self.preview = PreviewWidget()
        self.preview.setStyleSheet("border: 1px solid #3e3e42; border-radius: 6px; background-color: #000;")
        # 칸 크기는 스플리터로 자유롭게, 미리보기는 그 안에 비율대로 (노트를 위아래로 넓힐 수 있게)
        self.lbl_status = QLabel("배경: 투명 배경")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #9ad0ff; font-weight: bold;")
        # 상태 글자는 미리보기 바로 밑에 붙어 다닌다
        self.preview_box = AspectFitBox(self.preview, footer=self.lbl_status)
        layout.addWidget(self.preview_box, 1)
        return widget

    def _build_paragraph_panel(self) -> QWidget:
        """가운데 위쪽: 텍스트 파일 선택 + 문단 목록 / 썸네일 그리드"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- 텍스트 파일 (좌측 아래에 라이브러리가 있으므로 화면 표시 제거, 객체는 호환용 유지) ---
        self.grp_file = QGroupBox("📄 텍스트 파일")
        file_layout = QVBoxLayout(self.grp_file)
        file_row = QHBoxLayout()
        self.btn_open_txt = QPushButton("파일 열기…")
        self.btn_open_txt.clicked.connect(self._open_text_file)
        file_row.addWidget(self.btn_open_txt)
        self.lbl_file_prefix = QLabel("선택된 파일:")
        file_row.addWidget(self.lbl_file_prefix)
        self.lbl_txt_file = QLabel("(없음)")
        self.lbl_txt_file.setWordWrap(True)
        file_row.addWidget(self.lbl_txt_file, 1)
        file_layout.addLayout(file_row)
        self.grp_file.hide()

        # --- 문단 선택 패널 (탭: 📋 문단 목록 / 🖼️ 썸네일 그리드) ---
        self.grp_para = QGroupBox("📑 문단 선택 (클릭 시 송출)")
        para_layout = QVBoxLayout(self.grp_para)
        para_layout.setContentsMargins(6, 6, 6, 6)

        self.para_tab = QTabWidget()

        # 1. 텍스트 목록 탭
        list_tab_widget = QWidget()
        list_tab_layout = QVBoxLayout(list_tab_widget)
        list_tab_layout.setContentsMargins(4, 4, 4, 4)

        list_ctrl_row = QHBoxLayout()
        self.lbl_list_font_size = QLabel("🔍 글자 크기:")
        list_ctrl_row.addWidget(self.lbl_list_font_size)
        self.spin_list_font_size = QSpinBox()
        self.spin_list_font_size.setRange(9, 36)
        self.spin_list_font_size.setValue(13)
        self.spin_list_font_size.valueChanged.connect(self._on_list_font_size_changed)
        list_ctrl_row.addWidget(self.spin_list_font_size)

        list_ctrl_row.addSpacing(16)
        self.lbl_list_columns = QLabel("📊 열(단) 수:")
        list_ctrl_row.addWidget(self.lbl_list_columns)
        self.spin_list_columns = QSpinBox()
        self.spin_list_columns.setRange(1, 6)
        self.spin_list_columns.setValue(2)
        self.spin_list_columns.valueChanged.connect(self._on_list_columns_changed)
        list_ctrl_row.addWidget(self.spin_list_columns)

        list_ctrl_row.addStretch(1)

        self.btn_save_paragraphs = QPushButton(self.t("btn_save_paragraphs"))
        self.btn_save_paragraphs.setToolTip(self.t("btn_save_paragraphs_tip"))
        self.btn_save_paragraphs.setStyleSheet(
            "QPushButton { background-color: #3e3e42; color: white; font-size: 12px; padding: 4px 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #4e4e52; }"
        )
        self.btn_save_paragraphs.clicked.connect(self._on_save_paragraphs_clicked)
        list_ctrl_row.addWidget(self.btn_save_paragraphs)

        self.btn_stop_paragraph_text = QPushButton(self.t("btn_para_stop"))
        self.btn_stop_paragraph_text.setToolTip(self.t("btn_para_stop_tip"))
        self.btn_stop_paragraph_text.setStyleSheet(
            "QPushButton { background-color: #555555; color: white; font-size: 12px; padding: 4px 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #666666; }"
        )
        self.btn_stop_paragraph_text.clicked.connect(self._clear_text)
        list_ctrl_row.addWidget(self.btn_stop_paragraph_text)

        # PPT 모드에서만 보이는 애니메이션(슬라이드쇼) 토글
        self.btn_show_mode = QPushButton(self.t("btn_show_mode"))
        self.btn_show_mode.setCheckable(True)
        self.btn_show_mode.setVisible(False)
        self.btn_show_mode.setToolTip(self.t("btn_show_mode_tip"))
        self.btn_show_mode.setStyleSheet(
            "QPushButton { background-color: #3e3e42; color: white; font-size: 12px; padding: 4px 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #4e4e52; }"
            "QPushButton:checked { background-color: #c0392b; font-weight: bold; }"
        )
        self.btn_show_mode.toggled.connect(self._on_show_mode_toggled)
        list_ctrl_row.addWidget(self.btn_show_mode)

        list_tab_layout.addLayout(list_ctrl_row)
        # 동영상을 골랐을 때만 보이는 재생 조작 막대
        self.video_bar = self._build_video_bar()
        self.video_bar.setVisible(False)
        list_tab_layout.addWidget(self.video_bar)

        self.list_paragraphs = DropListWidget()
        self.list_paragraphs.setViewMode(QListWidget.ViewMode.IconMode)
        self.list_paragraphs.setFlow(QListWidget.Flow.LeftToRight)
        self.list_paragraphs.setWrapping(True)
        self.list_paragraphs.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.list_paragraphs.setMovement(QListWidget.Movement.Static)
        self.list_paragraphs.setWordWrap(True)
        self.list_paragraphs.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.list_paragraphs.setSpacing(0)
        self.list_paragraphs.setUniformItemSizes(True)
        self.list_paragraphs.setDropIndicatorShown(True)
        self.list_paragraphs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._apply_paragraph_card_style(False)
        # 텍스트 슬라이드 카드 오른쪽 위 구석의 ✏ 편집 / 🗑 삭제 단추
        self._card_hover = None            # (문단 번호, "edit"/"delete") - 마우스가 올라간 단추
        self._card_button_press = None     # 눌린 단추 (같은 단추 위에서 떼야 실행)
        self._paragraph_card_style_mode = None
        self.list_paragraphs.setItemDelegate(ParagraphCardDelegate(self, self.list_paragraphs))
        self.list_paragraphs.viewport().setMouseTracking(True)
        self.list_paragraphs.itemClicked.connect(self._on_paragraph_list_clicked)
        self.list_paragraphs.itemDoubleClicked.connect(self._on_paragraph_list_double_clicked)
        # 순서 변경은 Qt 내장 드래그(InternalMove) 대신 마우스 이벤트를 직접 받아 처리한다
        # (_handle_paragraph_drag_event / eventFilter 참고) - 아래에서 관련 상태를 초기화한다
        self._para_drag_from_idx = None
        self._para_dragging = False
        self._para_drag_start_pos = None
        self.list_paragraphs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_paragraphs.customContextMenuRequested.connect(self._on_paragraph_list_context_menu)
        self._apply_list_font_size(13)
        list_tab_layout.addWidget(self.list_paragraphs, 1)
        self.para_tab.addTab(list_tab_widget, "📋 문단 목록")

        self.list_paragraphs.installEventFilter(self)
        self.list_paragraphs.viewport().installEventFilter(self)

        # 2. 직접 입력 송출 탭
        direct_tab_widget = QWidget()
        direct_tab_layout = QVBoxLayout(direct_tab_widget)
        direct_tab_layout.setContentsMargins(6, 6, 6, 6)
        direct_tab_layout.setSpacing(6)

        direct_ctrl_row = QHBoxLayout()
        direct_ctrl_row.setSpacing(8)

        self.lbl_dir_font = QLabel("🔍 글자 크기:")
        direct_ctrl_row.addWidget(self.lbl_dir_font)

        self.spin_direct_font_size = QSpinBox()
        self.spin_direct_font_size.setRange(10, 60)
        self.spin_direct_font_size.setValue(18)
        self.spin_direct_font_size.valueChanged.connect(self._on_direct_font_size_changed)
        direct_ctrl_row.addWidget(self.spin_direct_font_size)

        direct_ctrl_row.addSpacing(12)
        self.chk_direct_realtime = QCheckBox("⚡ 실시간 송출")
        self.chk_direct_realtime.setToolTip("체크하면 텍스트를 입력하거나 수정하는 즉시 송출 화면과 미리보기에 실시간 반영됩니다.")
        self.chk_direct_realtime.toggled.connect(self._on_direct_realtime_toggled)
        direct_ctrl_row.addWidget(self.chk_direct_realtime)

        direct_ctrl_row.addStretch(1)

        self.btn_direct_clear = QPushButton("🧹 지우기")
        self.btn_direct_clear.setToolTip("입력창 내용을 모두 지웁니다.")
        self.btn_direct_clear.clicked.connect(self._clear_direct_input)
        direct_ctrl_row.addWidget(self.btn_direct_clear)

        direct_tab_layout.addLayout(direct_ctrl_row)

        self.txt_direct_input = DirectTextEdit()
        self.txt_direct_input.setPlaceholderText(
            "여기에 띄울 새 텍스트를 직접 작성하세요...\n\n"
            "• [🚀 즉시 송출] 버튼을 누르면 입력한 텍스트가 화면에 바로 뜹니다. (단축키: Ctrl+Enter)\n"
            "• [⚡ 실시간 송출]을 켜면 타이핑하는 대로 실시간 화면에 송출됩니다.\n"
            "• 여러 문단(빈 줄로 구분)을 작성한 후 [📋 문단 목록으로 변환]을 누르면 문단 카드로 분할되어 하나씩 송출할 수 있습니다.\n"
            "• [💾 파일로 저장]을 누르면 .txt 파일로 저장되어 왼쪽 목록에 영구 보관됩니다."
        )
        self.txt_direct_input.setStyleSheet(
            "QTextEdit { background-color: #1a1a1a; color: #f5f5f5; border: 1px solid #3e3e42; border-radius: 4px; padding: 10px; line-height: 1.5; }"
            "QTextEdit:focus { border: 1px solid #00bcd4; }"
        )
        self.txt_direct_input.setFont(QFont("Malgun Gothic", 18))
        self.txt_direct_input.textChanged.connect(self._on_direct_text_changed)
        direct_tab_layout.addWidget(self.txt_direct_input, 1)

        direct_btn_grid = QGridLayout()
        direct_btn_grid.setSpacing(6)

        self.btn_direct_broadcast = QPushButton("🚀 즉시 송출 (Ctrl+Enter)")
        self.btn_direct_broadcast.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: white; font-weight: bold; font-size: 13px; padding: 7px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #2ecc71; }"
        )
        self.btn_direct_broadcast.setToolTip("입력한 텍스트를 즉시 화면에 띄웁니다.")
        self.btn_direct_broadcast.clicked.connect(lambda: self._broadcast_direct_text())

        self.btn_direct_stop = QPushButton("⏹ 텍스트 끄기")
        self.btn_direct_stop.setStyleSheet(
            "QPushButton { background-color: #555555; color: white; font-size: 12px; padding: 7px 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #666666; }"
        )
        self.btn_direct_stop.setToolTip("송출 화면에서 텍스트를 내립니다.")
        self.btn_direct_stop.clicked.connect(self._clear_text)

        self.btn_direct_to_paras = QPushButton("📋 문단 목록으로 변환")
        self.btn_direct_to_paras.setStyleSheet(
            "QPushButton { background-color: #2980b9; color: white; font-weight: bold; font-size: 12px; padding: 7px 14px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #3498db; }"
        )
        self.btn_direct_to_paras.setToolTip("빈 줄로 구분된 여러 문단으로 나누어 [문단 목록] 탭에 로드하고 첫 문단을 송출합니다.")
        self.btn_direct_to_paras.clicked.connect(self._convert_direct_text_to_paragraphs)

        self.btn_direct_save = QPushButton("💾 파일로 저장…")
        self.btn_direct_save.setStyleSheet(
            "QPushButton { background-color: #3e3e42; color: white; font-size: 12px; padding: 7px 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #4e4e52; }"
        )
        self.btn_direct_save.setToolTip("작성한 텍스트를 파일로 저장하고 왼쪽 라이브러리에 등록합니다.")
        self.btn_direct_save.clicked.connect(self._save_direct_text_to_file)

        direct_btn_grid.addWidget(self.btn_direct_broadcast, 0, 0)
        direct_btn_grid.addWidget(self.btn_direct_stop, 0, 1)
        direct_btn_grid.addWidget(self.btn_direct_to_paras, 1, 0)
        direct_btn_grid.addWidget(self.btn_direct_save, 1, 1)

        direct_tab_layout.addLayout(direct_btn_grid)

        self.para_tab.addTab(direct_tab_widget, "✍️ 직접 입력 송출")
        self.para_tab.currentChanged.connect(self._on_para_tab_changed)

        para_layout.addWidget(self.para_tab, 1)
        layout.addWidget(self.grp_para, 1)

        return widget

    def _build_video_bar(self) -> QWidget:
        """본문 동영상 조작 막대: 재생/일시정지, 내리기, 위치, 소리, 자막 선택, 자막 크기"""
        bar = QWidget()
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(0, 2, 0, 2)
        outer.setSpacing(4)
        button_style = (
            "QPushButton { background-color: #3e3e42; color: white; font-size: 12px; padding: 4px 12px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #4e4e52; }"
            "QPushButton:disabled { color: #777777; }"
        )

        row1 = QHBoxLayout()
        self.btn_video_play = QPushButton(self.t("video_play"))
        self.btn_video_play.setToolTip(self.t("video_play_tip"))
        self.btn_video_play.setStyleSheet(
            "QPushButton { background-color: #1e7e34; color: white; font-size: 13px; font-weight: bold; padding: 5px 16px; border-radius: 4px; }"
            "QPushButton:hover { background-color: #28a745; }")
        self.btn_video_play.clicked.connect(self._video_play_toggle)
        row1.addWidget(self.btn_video_play)

        self.btn_video_stop = QPushButton(self.t("video_stop"))
        self.btn_video_stop.setToolTip(self.t("video_stop_tip"))
        self.btn_video_stop.setStyleSheet(button_style)
        self.btn_video_stop.clicked.connect(self._stop_content_video)
        row1.addWidget(self.btn_video_stop)

        self.sld_video_pos = QSlider(Qt.Orientation.Horizontal)
        self.sld_video_pos.setRange(0, 0)
        self.sld_video_pos.setToolTip(self.t("video_seek_tip"))
        self.sld_video_pos.sliderPressed.connect(lambda: setattr(self, "_video_seek_dragging", True))
        self.sld_video_pos.sliderReleased.connect(self._on_video_seek_released)
        self.sld_video_pos.sliderMoved.connect(self._on_video_seek_moved)
        row1.addWidget(self.sld_video_pos, 1)

        self.lbl_video_time = QLabel("--:-- / --:--")
        self.lbl_video_time.setStyleSheet("color: #cfcfcf; font-family: Consolas, monospace;")
        row1.addWidget(self.lbl_video_time)
        outer.addLayout(row1)

        row2 = QHBoxLayout()
        self.lbl_video_volume = QLabel("🔊")
        row2.addWidget(self.lbl_video_volume)
        self.sld_video_volume = QSlider(Qt.Orientation.Horizontal)
        self.sld_video_volume.setRange(0, 100)
        self.sld_video_volume.setFixedWidth(110)
        self.sld_video_volume.setToolTip(self.t("video_volume_tip"))
        self.sld_video_volume.valueChanged.connect(self._on_video_volume_changed)
        row2.addWidget(self.sld_video_volume)
        self.lbl_video_volume_value = QLabel("80")
        self.lbl_video_volume_value.setFixedWidth(28)
        row2.addWidget(self.lbl_video_volume_value)
        row2.addSpacing(12)

        self.btn_subtitle = QPushButton(self.t("subtitle_btn"))
        self.btn_subtitle.setToolTip(self.t("subtitle_btn_tip"))
        self.btn_subtitle.setStyleSheet(button_style)
        self.subtitle_menu = QMenu(self)
        self.act_subtitle_choose = self.subtitle_menu.addAction(self.t("subtitle_menu_choose"))
        self.act_subtitle_choose.triggered.connect(self._choose_subtitle_file)
        self.act_subtitle_auto = self.subtitle_menu.addAction(self.t("subtitle_menu_auto"))
        self.act_subtitle_auto.triggered.connect(lambda: self._set_subtitle_choice(None))
        self.act_subtitle_off = self.subtitle_menu.addAction(self.t("subtitle_menu_off"))
        self.act_subtitle_off.triggered.connect(lambda: self._set_subtitle_choice("off"))
        self.btn_subtitle.setMenu(self.subtitle_menu)
        row2.addWidget(self.btn_subtitle)

        self.lbl_subtitle_state = QLabel("")
        self.lbl_subtitle_state.setStyleSheet("color: #9ad0ff;")
        self.lbl_subtitle_state.setMinimumWidth(60)
        self.lbl_subtitle_state.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row2.addWidget(self.lbl_subtitle_state, 1)

        self.lbl_subtitle_size = QLabel(self.t("subtitle_size"))
        row2.addWidget(self.lbl_subtitle_size)
        self.spin_subtitle_size = QSpinBox()
        self.spin_subtitle_size.setRange(16, 160)
        self.spin_subtitle_size.setValue(44)
        self.spin_subtitle_size.setToolTip(self.t("subtitle_size_tip"))
        self.spin_subtitle_size.valueChanged.connect(self._on_subtitle_size_changed)
        row2.addWidget(self.spin_subtitle_size)
        outer.addLayout(row2)
        return bar

    def _build_text_files_panel(self) -> QWidget:
        """좌측 아래: 텍스트 파일 등록 목록 (라이브러리처럼 추가/삭제 가능)

        - 📂 파일 추가… 버튼으로 여러 텍스트 파일(.txt/.md 등)을 등록
        - 등록된 파일은 QSettings에 저장되어 재실행 시에도 유지됨
        - 목록에서 클릭하면 해당 파일을 열어 문단 선택 창에 표시
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)

        self.grp_text_files = QGroupBox("📑 텍스트 파일, 이미지 폴더 등록")
        group = self.grp_text_files
        group_layout = QVBoxLayout(group)

        # 버튼 한 줄 (추가 - 텍스트/PPT/이미지 폴더 중 고르는 메뉴, 전체 비우기)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self.btn_add_item = QPushButton(self.t("btn_add_item"))
        self.btn_add_item.setToolTip(self.t("btn_add_item_tip"))
        self.btn_add_item.clicked.connect(self._show_add_item_menu)

        self.btn_clear_text_files = QPushButton(self.t("btn_clear_text_files"))
        self.btn_clear_text_files.setToolTip(self.t("btn_clear_text_files_tip"))
        self.btn_clear_text_files.clicked.connect(self._clear_all_text_files)

        btn_row.addWidget(self.btn_add_item)
        btn_row.addWidget(self.btn_clear_text_files)
        group_layout.addLayout(btn_row)

        # 등록된 파일 목록 (한 줄에 번호 + 종류별 색 이름 + 삭제(휴지통) 버튼)
        self.list_text_files = DropListWidget(reorderable=True)
        self.list_text_files.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_text_files.setWordWrap(False)
        self.list_text_files.setStyleSheet("""
            QListWidget {
                background-color: #1a1a1a;
                border: 1px solid #333337;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 0px;
                margin: 1px 2px;
                border-radius: 3px;
            }
            QListWidget::item:hover {
                background-color: #333338;
            }
            QListWidget::item:selected {
                background-color: #005a9e;
            }
        """)
        self.list_text_files.itemClicked.connect(self._on_text_file_library_clicked)
        self.list_text_files.installEventFilter(self)
        self.list_text_files.viewport().installEventFilter(self)
        self.list_text_files.filesDropped.connect(self._handle_text_files_dropped)
        self.list_text_files.itemsReordered.connect(self._on_text_files_reordered)
        # 한 항목을 다른 항목 위에 끌어다 겹치면 묶음이 된다
        self.list_text_files.merge_enabled = True
        self.list_text_files.itemsMerged.connect(self._on_library_items_merged)
        self.list_text_files.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_text_files.customContextMenuRequested.connect(self._on_library_context_menu)
        group_layout.addWidget(self.list_text_files, 1)

        self.lbl_text_files_hint = QLabel("💡 텍스트 파일이나 폴더를 직접 끌어다 놓거나(드래그&드롭) 클릭하여 로드합니다.")
        self.lbl_text_files_hint.setWordWrap(True)
        self.lbl_text_files_hint.setStyleSheet("color: #777; font-size: 10px; margin-top: 2px;")
        group_layout.addWidget(self.lbl_text_files_hint)

        layout.addWidget(group)
        return widget

    def _build_edit_and_style_panel(self) -> QWidget:
        """우측 상단: 편집 모드 + 글자 스타일 (컴팩트)"""
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # --- 편집 모드 ---
        self.grp_edit = QGroupBox("✏️ 텍스트 편집")
        edit_layout = QVBoxLayout(self.grp_edit)
        self.btn_edit_dialog = QPushButton("✏️ 텍스트 편집기 열기")
        self.btn_edit_dialog.setStyleSheet(
            "QPushButton { background-color: #2c3e50; color: #ffffff; font-weight: bold; padding: 8px 4px; border-radius: 6px; font-size: 12px; }"
            "QPushButton:hover { background-color: #34495e; }"
        )
        self.btn_edit_dialog.clicked.connect(self._open_edit_dialog)
        edit_layout.addWidget(self.btn_edit_dialog)

        self.btn_direct_write = QPushButton("✍️ 새 텍스트 직접 작성/송출")
        self.btn_direct_write.setStyleSheet(
            "QPushButton { background-color: #1e3a5f; color: #ffffff; font-weight: bold; padding: 7px 4px; border-radius: 6px; font-size: 12px; }"
            "QPushButton:hover { background-color: #2a4d7a; }"
        )
        self.btn_direct_write.clicked.connect(self._open_direct_text_tab)
        edit_layout.addWidget(self.btn_direct_write)

        # test_gui_init.py 호환을 위한 위젯들 (필요 시 프로그래밍 방식으로 조작 가능)
        self.btn_edit_toggle = QPushButton("✏️ 편집 모드 켜기")
        self.btn_edit_toggle.setCheckable(True)
        self.btn_edit_toggle.setVisible(False)
        self.btn_edit_toggle.clicked.connect(self._toggle_edit_mode)
        edit_layout.addWidget(self.btn_edit_toggle)

        self.edit_area = QWidget()
        self.edit_area.setVisible(False)
        self.edit_area_layout = QVBoxLayout(self.edit_area)
        self.rad_edit_current = QRadioButton("현재 문단")
        self.rad_edit_all = QRadioButton("전체 텍스트")
        self.rad_edit_current.setChecked(True)
        self.txt_editor = QTextEdit()
        self.btn_apply_edit = QPushButton("✅ 적용")
        self.btn_apply_edit.clicked.connect(self._apply_edit)
        self.btn_cancel_edit = QPushButton("↩ 취소")
        self.btn_cancel_edit.clicked.connect(self._cancel_edit)
        edit_layout.addWidget(self.edit_area)

        layout.addWidget(self.grp_edit)

        # --- 텍스트 스타일 ---
        self.grp_style = QGroupBox("🎨 글자 스타일")
        style_layout = QVBoxLayout(self.grp_style)

        row_font = QHBoxLayout()
        self.lbl_style_font = QLabel("글꼴")
        row_font.addWidget(self.lbl_style_font)
        self.font_combo = LazyFontComboBox()
        self.font_combo.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.font_combo.setMinimumContentsLength(3)
        self.font_combo.currentFontChanged.connect(self._on_style_changed)
        row_font.addWidget(self.font_combo, 1)
        style_layout.addLayout(row_font)

        row_size = QHBoxLayout()
        self.lbl_style_size = QLabel("크기")
        row_size.addWidget(self.lbl_style_size)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(8, 400)
        self.size_spin.setValue(48)
        self.size_spin.valueChanged.connect(self._on_style_changed)
        row_size.addWidget(self.size_spin, 1)
        style_layout.addLayout(row_size)

        row_color = QHBoxLayout()
        self.lbl_style_color = QLabel("글자 색")
        row_color.addWidget(self.lbl_style_color)
        self.btn_text_color = QPushButton("")
        self.btn_text_color.setFixedHeight(26)
        self.btn_text_color.setMaximumWidth(80)
        self.btn_text_color.clicked.connect(self._pick_text_color)
        self._set_chip_color(self.btn_text_color, QColor("#FFFFFF"))
        row_color.addWidget(self.btn_text_color, 1)
        style_layout.addLayout(row_color)

        row_border = QHBoxLayout()
        self.chk_border = QCheckBox("글자 테두리")
        self.chk_border.setChecked(True)
        self.chk_border.toggled.connect(self._on_style_changed)
        row_border.addWidget(self.chk_border)
        self.border_width_spin = QSpinBox()
        self.border_width_spin.setRange(1, 20)
        self.border_width_spin.setValue(3)
        self.border_width_spin.valueChanged.connect(self._on_style_changed)
        self.lbl_border_width = QLabel("두께")
        row_border.addWidget(self.lbl_border_width)
        row_border.addWidget(self.border_width_spin, 1)
        style_layout.addLayout(row_border)

        row_border_color = QHBoxLayout()
        self.lbl_border_color = QLabel("테두리 색")
        row_border_color.addWidget(self.lbl_border_color)
        self.btn_border_color = QPushButton("")
        self.btn_border_color.setFixedHeight(26)
        self.btn_border_color.setMaximumWidth(80)
        self.btn_border_color.clicked.connect(self._pick_border_color)
        self._set_chip_color(self.btn_border_color, QColor("#000000"))
        row_border_color.addWidget(self.btn_border_color, 1)
        style_layout.addLayout(row_border_color)

        # 세로 위치 (위 / 가운데 / 아래) - 예배 중에도 한 번에 누를 수 있게 단추로
        self._text_valign = "center"
        self.lbl_valign = QLabel(self.t("text_valign"))
        style_layout.addWidget(self.lbl_valign)
        row_valign = QHBoxLayout()
        row_valign.setSpacing(3)
        self.valign_buttons = {}
        valign_style = (
            "QPushButton { background-color: #3e3e42; color: #dddddd; padding: 3px 6px; border-radius: 3px; }"
            "QPushButton:checked { background-color: #007acc; color: white; font-weight: bold; }"
        )
        for key in TextStyle.VALIGNS:
            btn = QPushButton(self.t(f"valign_{key}"))
            btn.setCheckable(True)
            btn.setStyleSheet(valign_style)
            btn.setToolTip(self.t("valign_tip"))
            btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _=False, k=key: self._set_text_valign(k))
            self.valign_buttons[key] = btn
            row_valign.addWidget(btn, 1)
        self.valign_buttons["center"].setChecked(True)
        style_layout.addLayout(row_valign)

        # 위/아래 여백 (화면 높이의 %) - 오른쪽 칸이 좁으므로 한 줄에 하나씩
        row_margin = QHBoxLayout()
        self.lbl_margin_top = QLabel(self.t("margin_top"))
        row_margin.addWidget(self.lbl_margin_top)
        self.spin_margin_top = QSpinBox()
        self.spin_margin_top.setRange(0, TextStyle.MAX_MARGIN)
        self.spin_margin_top.setValue(5)
        self.spin_margin_top.setSuffix("%")
        self.spin_margin_top.setToolTip(self.t("margin_tip"))
        self.spin_margin_top.valueChanged.connect(self._on_style_changed)
        row_margin.addWidget(self.spin_margin_top, 1)
        style_layout.addLayout(row_margin)
        row_margin = QHBoxLayout()
        self.lbl_margin_bottom = QLabel(self.t("margin_bottom"))
        row_margin.addWidget(self.lbl_margin_bottom)
        self.spin_margin_bottom = QSpinBox()
        self.spin_margin_bottom.setRange(0, TextStyle.MAX_MARGIN)
        self.spin_margin_bottom.setValue(5)
        self.spin_margin_bottom.setSuffix("%")
        self.spin_margin_bottom.setToolTip(self.t("margin_tip"))
        self.spin_margin_bottom.valueChanged.connect(self._on_style_changed)
        row_margin.addWidget(self.spin_margin_bottom, 1)
        style_layout.addLayout(row_margin)

        self.btn_clear_text = QPushButton("✖ 텍스트 숨기기")
        self.btn_clear_text.clicked.connect(self._clear_text)
        style_layout.addWidget(self.btn_clear_text)

        layout.addWidget(self.grp_style)

        # --- 슬라이드 노트 (PPT 모드에서 편집/스타일 대신 표시) ---
        self.grp_notes = QGroupBox(self.t("notes_group"))
        self.grp_notes.setVisible(False)
        notes_layout = QVBoxLayout(self.grp_notes)
        notes_layout.setContentsMargins(6, 6, 6, 6)
        notes_layout.setSpacing(6)

        notes_head = QHBoxLayout()
        self.lbl_notes_slide = QLabel("")
        self.lbl_notes_slide.setStyleSheet("color: #9fd3ff; font-weight: bold;")
        notes_head.addWidget(self.lbl_notes_slide)
        notes_head.addStretch(1)
        self.lbl_notes_font = QLabel(self.t("notes_font_size"))
        notes_head.addWidget(self.lbl_notes_font)
        self.spin_notes_font_size = QSpinBox()
        self.spin_notes_font_size.setRange(9, 32)
        self.spin_notes_font_size.setValue(13)
        self.spin_notes_font_size.valueChanged.connect(self._on_notes_font_size_changed)
        notes_head.addWidget(self.spin_notes_font_size)
        notes_layout.addLayout(notes_head)

        # 노트 따로 보기 (언제나 맨 위에 뜨는 창) + 이미지 폴더 모드에서만: 숨은 글 넣기
        # (칸이 좁아도 잘리지 않게 줄을 따로 둔다)
        self.btn_notes_popup = QPushButton(self.t("btn_notes_popup"))
        self.btn_notes_popup.setCheckable(True)
        self.btn_notes_popup.setToolTip(self.t("btn_notes_popup_tip"))
        self.btn_notes_popup.toggled.connect(self._set_notes_popup_visible)
        notes_layout.addWidget(self.btn_notes_popup)
        self.btn_image_note_edit = QPushButton(self.t("btn_image_note_edit"))
        self.btn_image_note_edit.setToolTip(self.t("btn_image_note_edit_tip"))
        self.btn_image_note_edit.clicked.connect(lambda: self._edit_image_note())
        self.btn_image_note_edit.setVisible(False)
        notes_layout.addWidget(self.btn_image_note_edit)

        self.txt_slide_notes = QTextEdit()
        self.txt_slide_notes.setReadOnly(True)
        self.txt_slide_notes.setPlaceholderText(self.t("notes_empty"))
        self.txt_slide_notes.setMinimumHeight(200)
        self.txt_slide_notes.setStyleSheet(
            "QTextEdit { background-color: #1a1a1a; color: #f0f0f0; border: 1px solid #3e3e42;"
            " border-radius: 4px; padding: 8px; line-height: 1.5; }"
        )
        self.txt_slide_notes.setFont(QFont("Malgun Gothic", 13))
        notes_layout.addWidget(self.txt_slide_notes, 1)

        layout.addWidget(self.grp_notes, 1)

        self.side_panel_container = widget
        return widget

    # ------------------------------------------------------------------
    # 우측 패널 전환 (텍스트 편집·스타일 ↔ 슬라이드 노트)
    # ------------------------------------------------------------------
    def _update_side_panel_mode(self):
        """PPT 슬라이드 모드에서는 텍스트 편집/스타일 대신 슬라이드 노트를 보여준다."""
        if not hasattr(self, "grp_notes"):
            return
        pptx = self._is_pptx_mode()
        images = self._is_image_folder_mode()
        mix_kind = self._mix_focus_kind()
        if mix_kind:
            # 묶음: 지금 고른(송출한) 카드의 종류에 따라 노트 칸 / 글자 스타일 칸
            images = mix_kind == "image"
        notes_mode = pptx or images or mix_kind == "slide"   # 오른쪽 칸에 노트를 보여 주는 모드
        video = getattr(self, "current_source_type", "text") in ("video", "mix")
        self.grp_edit.setVisible(not notes_mode and not video)
        self.grp_style.setVisible(not notes_mode)
        self.grp_notes.setVisible(notes_mode)
        self.btn_image_note_edit.setVisible(images)
        self.grp_notes.setTitle(self.t("image_notes_group" if images else "notes_group"))
        self.txt_slide_notes.setPlaceholderText(self.t("image_notes_empty" if images else "notes_empty"))
        if hasattr(self, "btn_show_mode"):
            self.btn_show_mode.setVisible(pptx)
        container = getattr(self, "side_panel_container", None)
        if container is not None:
            # 노트는 스플리터로 크기를 조절할 수 있게 세로로 늘어나도록 한다
            policy = (QSizePolicy.Policy.Preferred if notes_mode
                      else QSizePolicy.Policy.Maximum)
            container.setSizePolicy(QSizePolicy.Policy.Preferred, policy)
        mode_key = ("mix" if mix_kind and notes_mode else
                    "pptx" if pptx else ("images" if images else ""))
        if not notes_mode or mode_key != getattr(self, "_notes_panel_mode", ""):
            # 모드가 바뀌면 앞 모드의 노트를 남겨 두지 않는다
            self.txt_slide_notes.clear()
            self.lbl_notes_slide.setText("")
        self._notes_panel_mode = mode_key
        self._sync_notes_popup()

    # ------------------------------------------------------------------
    # 애니메이션 모드 (실제 파워포인트 슬라이드쇼)
    # ------------------------------------------------------------------
    def _target_screen_rect(self):
        """송출 모니터 영역을 실제 픽셀 좌표로 반환 (x, y, w, h)

        Qt 논리 좌표에 배율(devicePixelRatio)을 곱하는 계산은 모니터마다 배율이
        다르면 어긋난다(창이 옆으로 밀리고 폭이 넘친다). 그래서 이미 송출
        모니터에 떠 있는 송출 창을 기준으로 윈도우에 직접 모니터 영역을 묻는다.
        """
        rect = self._presenter_monitor_rect()
        if rect:
            return rect

        # 윈도우에 물어볼 수 없는 경우에만 Qt 정보로 추정한다
        screens = QGuiApplication.screens()
        if not screens:
            return None
        idx = self.combo_screens.currentIndex() if hasattr(self, "combo_screens") else 0
        if not (0 <= idx < len(screens)):
            idx = 0
        screen = screens[idx]
        geo = screen.geometry()
        ratio = screen.devicePixelRatio() or 1.0
        return (int(geo.x() * ratio), int(geo.y() * ratio),
                int(geo.width() * ratio), int(geo.height() * ratio))

    def _presenter_monitor_rect(self):
        """송출 창이 올라가 있는 모니터의 실제 픽셀 영역 (윈도우 API 사용)"""
        if os.name != "nt":
            return None
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.presenter.winId())
            if not hwnd:
                return None

            class MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD),
                            ("rcMonitor", wintypes.RECT),
                            ("rcWork", wintypes.RECT),
                            ("dwFlags", wintypes.DWORD)]

            MONITOR_DEFAULTTONEAREST = 2
            user32 = ctypes.windll.user32
            monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if monitor and user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
                r = info.rcMonitor
                width, height = r.right - r.left, r.bottom - r.top
                if width > 0 and height > 0:
                    return (r.left, r.top, width, height)

            # 모니터 정보를 못 얻으면 송출 창 자체의 영역을 쓴다
            rect = wintypes.RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                width, height = rect.right - rect.left, rect.bottom - rect.top
                if width > 0 and height > 0:
                    return (rect.left, rect.top, width, height)
        except Exception as e:
            print(f"송출 모니터 영역을 읽지 못했습니다: {e}")
        return None

    def _on_show_mode_toggled(self, checked: bool):
        if checked:
            self._start_slideshow()
        else:
            self._stop_slideshow()

    def _start_slideshow(self, start_index=None):
        """현재 PPT 파일로 실제 슬라이드쇼를 띄운다

        start_index: 생략하면 지금 보고 있는 슬라이드부터. 다른 파일의 슬라이드를
        눌러서 쇼를 그 파일로 전환할 때는 그 슬라이드 번호를 직접 넘긴다.
        """
        path = getattr(self, "current_source_path", "")
        if not self._is_pptx_mode() or not path or not os.path.exists(path):
            self.btn_show_mode.setChecked(False)
            return
        available, message = ppt_engine.powerpoint_support()
        if not available:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, self.t("err_show_title"), message)
            self.btn_show_mode.setChecked(False)
            return

        self._stop_content_video_if_active()
        # 애니메이션 모드를 쓰는 사람이라는 표시 - 다음에 프로그램을 켜면 마지막 PPT를
        # 파워포인트에 미리 열어 두어 첫 애니메이션 모드도 빨리 뜨게 한다
        self.settings.setValue("ppt/show_mode_used", True)
        # 송출 창은 지금 숨기지 않는다. 슬라이드쇼가 실제로 뜬 뒤에 숨겨야
        # 그 사이에 빈 화면(바탕화면)이 보이지 않는다.
        self._show_mode_active = True
        self._show_pending_hide = True
        self._show_active_path = path

        if start_index is None:
            start_index = max(0, getattr(self, "media_slide_index", 0)) + 1
        ppt_engine.show_start(
            path, index=start_index,
            screen_rect=self._target_screen_rect(),
            on_state=self.ppt_show_state.emit,
            on_error=self.ppt_show_failed.emit,
        )
        self.statusBar().showMessage(self.t("msg_show_started"), 6000)

        # 사용자가 슬라이드쇼를 직접 끝냈는지 주기적으로 확인
        self._show_poll_pending = False
        self._show_poll_sent_at = 0.0
        if self._show_timer is None:
            self._show_timer = QTimer(self)
            # 슬라이드쇼 중에는 파워포인트가 키보드를 가져가므로, 사용자가 ESC로
            # 쇼를 끝낸 것을 우리가 알아채는 유일한 방법이 이 확인이다.
            # 너무 느리면 "ESC가 한 번에 안 먹는다"고 느껴지므로 짧게 잡는다.
            self._show_timer.setInterval(400)
            self._show_timer.timeout.connect(self._poll_show_state)
        self._show_timer.start()

    def _stop_slideshow(self, silent=False, resume_export=True):
        """슬라이드쇼를 끝내고 원래 송출 창으로 돌아온다

        resume_export: 다른 파일로 넘어가거나 프로그램을 닫는 경우에는 False
        """
        was_active = self._show_mode_active
        self._show_mode_active = False
        self._show_pending_hide = False
        self._show_active_path = ""
        if self._show_timer is not None:
            self._show_timer.stop()
        if was_active:
            ppt_engine.show_stop(on_error=self.ppt_show_failed.emit)
        if hasattr(self, "btn_show_mode") and self.btn_show_mode.isChecked():
            self.btn_show_mode.blockSignals(True)
            self.btn_show_mode.setChecked(False)
            self.btn_show_mode.blockSignals(False)
        if was_active:
            # 송출 창 복귀 (ESC로 온 경우 이어서 투명 배경 처리가 된다)
            self._show_presenter_fullscreen(self.combo_screens.currentIndex())
            if not silent:
                self.statusBar().showMessage(self.t("msg_show_stopped"), 3000)
            # 애니메이션 모드 때문에 멈춰 둔 이미지 내보내기를 이어서 진행
            if resume_export:
                self._resume_ppt_export()
        if was_active and getattr(self, "current_source_type", "") == "mix":
            # 슬라이드쇼 때문에 미뤄 둔 묶음 안 PPT 그림 만들기를 이어서
            QTimer.singleShot(0, self._mix_start_ppt_exports)

    def _resume_ppt_export(self):
        """애니메이션 모드로 중단됐던 슬라이드 이미지 내보내기를 이어서 진행한다"""
        if not self._is_pptx_mode():
            return
        path = getattr(self, "current_source_path", "")
        if not path or not os.path.exists(path):
            return
        total = getattr(self, "_ppt_total", 0)
        if not total or len(self._ppt_ready) >= total:
            # 장수를 모르거나(아직 한 번도 못 읽음) 이미 전부 준비된 경우
            return

        self._ppt_load_token += 1
        token = self._ppt_load_token
        self._ppt_autopresent = False
        ppt_engine.export_async(
            path,
            on_count=lambda c, paths, t=token: self.ppt_count_ready.emit(t, c, paths),
            on_slide=lambda i, p, n, t=token: self.ppt_slide_ready.emit(t, i, p, n),
            on_done=lambda c, t=token: self.ppt_export_done.emit(t, c),
            on_error=lambda m, t=token: self.ppt_export_failed.emit(t, m),
            cancel=lambda t=token: t != self._ppt_load_token or self._show_mode_active,
            extract_notes=True,
            # 이어서 할 때는 지금 보고 있는 슬라이드부터 챙긴다
            first_index=max(0, getattr(self, "media_slide_index", 0)) + 1,
        )

    def _cover_show_gap(self, idx: int):
        """슬라이드쇼를 다시 여는 사이를 송출 창으로 덮는다.

        애니메이션을 살리려면 슬라이드마다 쇼를 다시 열어야 하는데, 그 사이
        (쇼 종료 ~ 재실행)에 바탕화면이 잠깐 보인다. 같은 슬라이드 이미지를
        송출 창에 띄워 두면 회중에게는 화면이 바뀌지 않은 것처럼 보인다.
        """
        if not self._show_mode_active:
            return
        try:
            path = self.media_slides[idx] if 0 <= idx < len(self.media_slides) else ""
            if path and os.path.exists(path):
                self.presenter.set_image_background(path, fit_mode="fit")
            else:
                # 아직 이미지를 준비하지 못했으면 최소한 검은 화면으로 덮는다
                self.presenter.set_color_background(QColor("#000000"))
            self.presenter.clear_overlay_image()
            self.presenter.clear_text()
            if not self.presenter.isVisible():
                self._show_presenter_fullscreen(self.combo_screens.currentIndex())
            # 쇼가 다시 뜨면 이 창을 도로 내린다
            self._show_pending_hide = True
        except Exception as e:
            print(f"슬라이드쇼 전환 화면 준비 실패: {e}")

    def _poll_show_state(self):
        """슬라이드쇼 상태 확인 (응답이 안 온 조회가 있으면 새로 보내지 않는다)"""
        if not self._show_mode_active:
            return
        now = time.monotonic()
        # 방금 슬라이드를 옮겼다면 잠시 조회를 쉰다. 조회도 같은 COM 스레드를
        # 쓰기 때문에, 이동 중에 조회를 밀어 넣으면 이동이 그만큼 늦어진다.
        if now - getattr(self, "_show_command_at", 0.0) < 1.0:
            return
        if self._show_poll_pending and (now - self._show_poll_sent_at) < 3.0:
            return   # 아직 답을 기다리는 중 - 큐를 더 채우지 않는다
        self._show_poll_pending = True
        self._show_poll_sent_at = now
        ppt_engine.show_state(on_state=self.ppt_show_state.emit,
                              on_error=lambda m: self.ppt_show_state.emit({}))

    @Slot(object)
    def _on_show_state(self, state):
        self._show_poll_pending = False
        if not isinstance(state, dict) or not state:
            return
        if not self._show_mode_active:
            return
        if not state.get("running"):
            # 슬라이드쇼가 끝났다. 슬라이드쇼 중에는 키보드를 파워포인트가 가져가므로
            # 사용자가 누른 ESC도 여기로 들어온다. ESC 규칙대로 투명 화면으로 정리한다.
            self._reset_to_transparent()
            self.statusBar().showMessage(self.t("msg_all_cleared"), 3000)
            return

        # 슬라이드쇼가 실제로 화면에 뜬 뒤에야 우리 송출 창을 내린다
        if getattr(self, "_show_pending_hide", False):
            self._show_pending_hide = False
            self.presenter.hide()

        self._show_range_start = int(state.get("range_start", 1) or 1)
        slide = int(state.get("slide", 0))
        total = int(state.get("total", 0))
        # 지금 목록에서 구경하고 있는 파일이 애니메이션 중인 파일과 같을 때만 목록
        # 강조/노트를 갱신한다 - 다른 파일을 구경 중이라면 그 목록을 애니메이션
        # 파일의 슬라이드 번호로 건드리지 않는다.
        browsing_same_file = (getattr(self, "current_source_path", "")
                              == getattr(self, "_show_active_path", ""))
        if slide > 0 and browsing_same_file:
            self.media_slide_index = slide - 1
            if hasattr(self, "list_paragraphs") and 0 <= slide - 1 < self.list_paragraphs.count():
                self.list_paragraphs.blockSignals(True)
                self.list_paragraphs.setCurrentRow(slide - 1)
                self.list_paragraphs.blockSignals(False)
            self._show_slide_notes(slide - 1)
        self.statusBar().showMessage(
            self.t("msg_show_slide", slide, total,
                   state.get("click", 0), state.get("clicks", 0)))

    @Slot(str)
    def _on_show_failed(self, message: str):
        from PySide6.QtWidgets import QMessageBox
        self._stop_slideshow(silent=True)
        QMessageBox.warning(self, self.t("err_show_title"),
                            self.t("err_ppt_failed", message))

    def _on_notes_font_size_changed(self, size: int):
        font = self.txt_slide_notes.font()
        font.setPointSize(size)
        self.txt_slide_notes.setFont(font)
        self.settings.setValue("text/notes_font_size", size)

    def _show_slide_notes(self, idx: int):
        """현재 슬라이드의 노트를 우측 패널에 표시"""
        if not hasattr(self, "txt_slide_notes"):
            return
        total = len(self.media_slides)
        images = self._is_image_folder_mode()
        if images:
            # 다른 프로그램(ppt2jpg 의 노트 편집 등)에서 바꿨을 수 있으니 보여 줄 때마다
            # 파일에서 새로 읽는다 (머리·끝 부분만 읽어서 빠르다)
            before = self._image_note(idx)
            note = self._image_note(idx, fresh=True)
            if note != before:
                self._refresh_image_card_title(idx)
        else:
            notes = getattr(self, "media_notes", [])
            note = notes[idx] if 0 <= idx < len(notes) else ""
        self.txt_slide_notes.setPlainText(note or "")
        if 0 <= idx < total:
            prefix = self.t("image_prefix" if images else "slide_prefix")
            self.lbl_notes_slide.setText(f"{prefix} {idx + 1}/{total}")
            self.lbl_notes_slide.setToolTip(os.path.basename(self.media_slides[idx]) if images else "")
        else:
            self.lbl_notes_slide.setText("")
        self._notes_shown_index = idx
        self._sync_notes_popup()

    # ------------------------------------------------------------------
    # 노트 따로 보기 (언제나 맨 위에 뜨는 창)
    # ------------------------------------------------------------------
    def _set_notes_popup_visible(self, visible: bool):
        """노트 따로 보기 켜기/끄기. 켜 두면 노트가 있을 때만 창이 보인다."""
        popup = getattr(self, "notes_popup", None)
        if not visible:
            if popup is not None and popup.isVisible():
                popup.hide()
            return
        if popup is None:
            popup = NotesPopup(self)
            popup.closed.connect(self._on_notes_popup_closed)
            size = int(self.settings.value("notes/popup_font_size", 20) or 20)
            popup.set_font_size(size, save=False)
            geometry = self.settings.value("notes/popup_geometry")
            restored = False
            if geometry is not None:
                try:
                    restored = popup.restoreGeometry(geometry)
                except Exception:
                    restored = False
            if not restored:
                popup.resize(440, 380)
            self.notes_popup = popup
        popup.setWindowTitle(self.t("notes_popup_title"))
        self._popup_position_checked = False
        self._sync_notes_popup()
        if not popup.isVisible():
            self.statusBar().showMessage(self.t("msg_notes_popup_waiting"), 5000)

    def _keep_popup_off_presenter_screen(self):
        """노트 창이 송출 모니터 위에 있으면(회중에게 보이면 안 된다) 이 프로그램이
        있는 모니터로 옮긴다. 처음 띄울 때는 본 창 오른쪽 위에 둔다."""
        popup = getattr(self, "notes_popup", None)
        if popup is None:
            return
        main_screen = self.screen()
        presenter_screen = self.presenter.screen() if self.presenter.isVisible() else None
        center = popup.frameGeometry().center()
        on_screen = QGuiApplication.screenAt(center)
        bad = (on_screen is None
               or (presenter_screen is not None and on_screen is presenter_screen
                   and presenter_screen is not main_screen))
        if bad or not self.settings.contains("notes/popup_geometry"):
            area = (main_screen or QGuiApplication.primaryScreen()).availableGeometry()
            frame = self.frameGeometry()
            x = min(frame.right() - popup.width() - 20, area.right() - popup.width() - 10)
            y = max(area.top() + 10, frame.top() + 80)
            popup.move(max(area.left() + 10, x), y)

    def _on_notes_popup_closed(self):
        if hasattr(self, "btn_notes_popup") and self.btn_notes_popup.isChecked():
            self.btn_notes_popup.blockSignals(True)
            self.btn_notes_popup.setChecked(False)
            self.btn_notes_popup.blockSignals(False)

    def _sync_notes_popup(self):
        """노트 칸의 내용을 따로 띄운 창에도 똑같이"""
        """노트 칸의 내용을 따로 띄운 창에도 똑같이.

        노트 따로 보기가 켜져 있으면: 지금 슬라이드/사진에 노트가 있을 때만 창을 보이고,
        없으면 숨긴다(꺼지는 것은 아니다 - 노트가 있는 것으로 가면 다시 뜬다)."""
        popup = getattr(self, "notes_popup", None)
        if popup is None or not hasattr(self, "txt_slide_notes"):
            return
        enabled = hasattr(self, "btn_notes_popup") and self.btn_notes_popup.isChecked()
        notes_mode = (self._is_pptx_mode() or self._is_image_folder_mode()
                      or self._mix_focus_kind() in ("slide", "image"))
        where = self.lbl_notes_slide.text() if notes_mode else ""
        text = self.txt_slide_notes.toPlainText() if notes_mode else ""
        if notes_mode and (self._is_image_folder_mode() or self._mix_focus_kind() in ("slide", "image")):
            name = self.lbl_notes_slide.toolTip()
            if name and where:
                where = f"{where}  {name}"
        has_note = bool(where and text.strip())
        if has_note:
            popup.set_note(where, text, self.txt_slide_notes.placeholderText())
        else:
            popup.set_note(where, "", self.t("notes_popup_nothing"))
        if not enabled:
            return
        if has_note and not popup.isVisible():
            popup.show()                      # 초점은 빼앗지 않는다 (WA_ShowWithoutActivating)
            if not getattr(self, "_popup_position_checked", False):
                self._popup_position_checked = True
                self._keep_popup_off_presenter_screen()
        elif not has_note and popup.isVisible():
            was_active = popup.isActiveWindow()
            popup.hide()
            if was_active:
                # 노트 창에서 키로 넘기다 숨었다면 계속 본 창에서 넘길 수 있게
                self.activateWindow()

    def _handle_navigation_key(self, key) -> bool:
        """노트 창 등 본 창 밖에서 누른 이동 키를 본 창에서 누른 것처럼 처리한다"""
        if key == Qt.Key.Key_Escape:
            self._on_escape_action()
            return True
        if QApplication.activeModalWidget() is not None:
            return False
        next_keys = (Qt.Key.Key_Space, Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown,
                     Qt.Key.Key_Return, Qt.Key.Key_Enter)
        prev_keys = (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backspace)
        if hasattr(self, "para_tab") and self.para_tab.currentIndex() == 1:
            return False        # 직접 입력 탭에서는 문단 넘김을 하지 않는다 (본 창과 같게)
        source = getattr(self, "current_source_type", "text")
        if source == "mix":
            return self._mix_handle_key(key)
        if source == "folder":
            if key in next_keys:
                self._slide_step(True)
                return True
            if key in prev_keys:
                self._slide_step(False)
                return True
        elif source == "video":
            return bool(self._handle_video_key(key))
        elif source == "text":
            if key in next_keys:
                if self.paragraph_index + 1 < len(self.paragraphs):
                    self._broadcast_paragraph(self.paragraph_index + 1)
                return True
            if key in prev_keys:
                if self.paragraph_index - 1 >= 0:
                    self._broadcast_paragraph(self.paragraph_index - 1)
                return True
        return False

    # ------------------------------------------------------------------
    # 사진 속 숨은 글 (이미지 폴더 모드의 노트)
    # ------------------------------------------------------------------
    def _image_note(self, idx: int, fresh: bool = False) -> str:
        """idx 번째 사진의 숨은 글 (한 번 읽으면 기억해 둔다. fresh=True 면 파일에서 다시 읽는다)"""
        if not (0 <= idx < len(self.media_slides)):
            return ""
        notes = getattr(self, "media_notes", None)
        if not isinstance(notes, list) or len(notes) != len(self.media_slides):
            notes = [None] * len(self.media_slides)
            self.media_notes = notes
        if notes[idx] is None or fresh:
            notes[idx] = image_notes.read_note(self.media_slides[idx])
        return notes[idx] or ""

    def _image_card_title(self, idx: int, path: str) -> str:
        notes = getattr(self, "media_notes", None)
        has_note = (isinstance(notes, list) and idx < len(notes) and bool(notes[idx]))
        return f"{'📝 ' if has_note else ''}{idx + 1}. {os.path.basename(path)}"

    def _scan_image_notes(self):
        """폴더의 사진들에 숨은 글이 있는지 조금씩 읽어 카드에 📝 표시를 붙인다
        (사진이 많아도 화면이 멈추지 않도록 나눠서 읽는다)"""
        self._image_note_scan_serial = getattr(self, "_image_note_scan_serial", 0) + 1
        serial = self._image_note_scan_serial
        folder = getattr(self, "current_source_path", "")

        def step(start=0):
            if (serial != self._image_note_scan_serial or not self._is_image_folder_mode()
                    or getattr(self, "current_source_path", "") != folder):
                return
            end = min(len(self.media_slides), start + 40)
            for i in range(start, end):
                self._image_note(i)
                self._refresh_image_card_title(i)
            if end < len(self.media_slides):
                QTimer.singleShot(0, lambda: step(end))

        QTimer.singleShot(0, step)

    def _refresh_image_card_title(self, idx: int):
        if not hasattr(self, "list_paragraphs") or not (0 <= idx < self.list_paragraphs.count()):
            return
        item = self.list_paragraphs.item(idx)
        if item is None or item.data(USER_ROLE_INDEX) != idx:
            return
        path = self.media_slides[idx]
        title = self._image_card_title(idx, path)
        if item.text() != title:
            item.setText(title)

    def _image_note_target(self) -> int:
        """숨은 글을 편집할 사진: 선택한 카드 → 없으면 지금 송출 중인 사진"""
        row = self.list_paragraphs.currentRow() if hasattr(self, "list_paragraphs") else -1
        if 0 <= row < len(self.media_slides):
            return row
        idx = getattr(self, "media_slide_index", -1)
        return idx if 0 <= idx < len(self.media_slides) else -1

    def _edit_image_note(self, idx: int = None):
        """사진에 숨은 글을 넣거나 고친다. 화면(송출)에는 아무것도 내보내지 않는다."""
        if getattr(self, "current_source_type", "text") == "mix":
            self._edit_mix_image_note(idx)
            return
        if not self._is_image_folder_mode():
            return
        if idx is None:
            idx = self._image_note_target()
        if not (0 <= idx < len(self.media_slides)):
            QMessageBox.information(self, self.t("btn_image_note_edit"), self.t("image_note_pick_first"))
            return
        path = self.media_slides[idx]
        name = os.path.basename(path)
        if not image_notes.can_store(path):
            ext = os.path.splitext(path)[1].lower() or "?"
            QMessageBox.information(self, self.t("btn_image_note_edit"),
                                    self.t("image_note_unsupported", ext))
            return
        text = self._image_note_dialog_for(path)
        if text is None:
            return
        # 목록 위치가 그대로인지 확인 (편집하는 동안 다른 폴더로 바뀌었을 수 있다)
        if 0 <= idx < len(self.media_slides) and self.media_slides[idx] == path:
            self._image_note(idx)
            self.media_notes[idx] = image_notes.read_note(path)
            self._refresh_image_card_title(idx)
            if getattr(self, "_notes_shown_index", -1) == idx:
                self._show_slide_notes(idx)

    def _image_note_dialog_for(self, path: str):
        """숨은 글 편집 창을 띄워 저장한다. 저장했으면 새 글, 취소·실패·변화 없음이면 None"""
        name = os.path.basename(path)
        # 다른 곳에서 바뀌었을 수 있으니 편집할 때는 파일에서 새로 읽는다
        current = image_notes.read_note(path)

        dlg = QDialog(self)
        dlg.setWindowTitle(self.t("image_note_dialog_title", name))
        dlg.resize(560, 420)
        lay = QVBoxLayout(dlg)
        info = QLabel(self.t("image_note_dialog_info"))
        info.setWordWrap(True)
        info.setStyleSheet("color: #9fd3ff;")
        lay.addWidget(info)
        editor = QPlainTextEdit()
        editor.setPlainText(current)
        editor.setFont(self.txt_slide_notes.font())
        lay.addWidget(editor, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        btn_save = QPushButton(self.t("image_note_save"))
        btn_cancel = QPushButton(self.t("btn_cancel_plain"))
        btn_save.clicked.connect(dlg.accept)
        btn_cancel.clicked.connect(dlg.reject)
        row.addWidget(btn_save)
        row.addWidget(btn_cancel)
        lay.addLayout(row)
        self._image_note_dialog = dlg          # 테스트에서 찾을 수 있도록
        dlg._editor = editor
        editor.setFocus()
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        self._image_note_dialog = None
        if not accepted:
            return None
        text = editor.toPlainText().replace("\r\n", "\n").rstrip()
        if text == current.rstrip():
            return None
        try:
            image_notes.write_note(path, text)
        except image_notes.ImageNoteError as e:
            QMessageBox.warning(self, self.t("btn_image_note_edit"), self.t("image_note_failed", e))
            return None
        self.statusBar().showMessage(
            self.t("msg_image_note_saved" if text else "msg_image_note_removed", name), 4000)
        return text

    # ------------------------------------------------------------------
    # 다크 테마
    # ------------------------------------------------------------------
    def _apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow { background-color: #202020; color: #f0f0f0; }
            QWidget { background-color: #202020; color: #e0e0e0;
                      font-family: 'Segoe UI', 'Malgun Gothic', sans-serif; }
            QToolBar { background-color: #2d2d30; border-bottom: 1px solid #3e3e42;
                       padding: 4px; spacing: 6px; }
            QPushButton { background-color: #3e3e42; border: 1px solid #555;
                          border-radius: 4px; padding: 5px 10px; color: #ffffff; }
            QPushButton:hover { background-color: #4e4e54; border-color: #007acc; }
            QPushButton:checked { background-color: #007acc; border-color: #0098ff; }
            QComboBox, QFontComboBox {
                background-color: #2d2d30; border: 1px solid #555;
                border-radius: 4px; padding: 3px 6px; color: #fff; }
            QSpinBox {
                background-color: #2d2d30; border: 1px solid #555;
                border-radius: 4px; padding: 3px 22px 3px 6px; color: #fff; }
            QSpinBox::up-button {
                subcontrol-origin: border;
                subcontrol-position: top right;
                width: 20px;
                background-color: #38383c;
                border-left: 1px solid #555;
                border-bottom: 1px solid #444;
                border-top-right-radius: 4px;
            }
            QSpinBox::up-button:hover {
                background-color: #4e4e54;
            }
            QSpinBox::up-button:pressed {
                background-color: #007acc;
            }
            QSpinBox::up-arrow {
                image: none;
                width: 0;
                height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-bottom: 5px solid #ffffff;
            }
            QSpinBox::down-button {
                subcontrol-origin: border;
                subcontrol-position: bottom right;
                width: 20px;
                background-color: #38383c;
                border-left: 1px solid #555;
                border-top-right-radius: 0px;
                border-bottom-right-radius: 4px;
            }
            QSpinBox::down-button:hover {
                background-color: #4e4e54;
            }
            QSpinBox::down-button:pressed {
                background-color: #007acc;
            }
            QSpinBox::down-arrow {
                image: none;
                width: 0;
                height: 0;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QListWidget { background-color: #1e1e1e; border: 1px solid #333337;
                          border-radius: 4px; }
            QListWidget::item { padding: 6px; margin: 3px; color: #e0e0e0;
                                border-radius: 4px; }
            QListWidget::item:hover { background-color: #38383e; }
            QListWidget::item:selected { background-color: #005a9e; color: #ffffff; }
            QGroupBox { border: 1px solid #3e3e42; border-radius: 5px;
                        margin-top: 8px; font-weight: bold; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QTextEdit { background-color: #242424; color: #f0f0f0;
                        border: 1px solid #3c3c3c; border-radius: 4px; padding: 6px; }
            QTabWidget::pane { border: 1px solid #3e3e42; border-radius: 4px; }
            QTabBar::tab { background: #2d2d30; padding: 6px 14px; border: 1px solid #3e3e42;
                           border-bottom: none; border-top-left-radius: 4px;
                           border-top-right-radius: 4px; }
            QTabBar::tab:selected { background: #007acc; color: #fff; }
            QSlider::groove:horizontal { height: 6px; background: #3e3e42; border-radius: 3px; }
            QSlider::sub-page:horizontal { background: #007acc; border-radius: 3px; }
            QSlider::handle:horizontal { background: #fff; border: 1px solid #777; width: 14px;
        """)

    # ------------------------------------------------------------------
    # 창/패널 크기 기억
    # ------------------------------------------------------------------
    def _restore_window_layout(self):
        """이전에 마우스로 조정해 둔 메인 창 크기와 내부 패널(스플리터) 크기를 복원한다"""
        s = self.settings
        geo = s.value("window/geometry")
        if geo is not None:
            try:
                self.restoreGeometry(geo)
            except Exception as e:
                print(f"창 크기 복원 실패: {e}")
        for key, splitter in (
            ("window/splitter_main", getattr(self, "main_splitter", None)),
            ("window/splitter_left", getattr(self, "left_splitter", None)),
            ("window/splitter_right", getattr(self, "right_splitter", None)),
        ):
            state = s.value(key)
            if state is not None and splitter is not None:
                try:
                    splitter.restoreState(state)
                except Exception as e:
                    print(f"패널 크기 복원 실패({key}): {e}")

    def _save_window_layout(self):
        """지금 창/패널 크기를 다음 실행에서도 쓰도록 저장한다"""
        s = self.settings
        try:
            s.setValue("window/geometry", self.saveGeometry())
        except Exception as e:
            print(f"창 크기 저장 실패: {e}")
        for key, splitter in (
            ("window/splitter_main", getattr(self, "main_splitter", None)),
            ("window/splitter_left", getattr(self, "left_splitter", None)),
            ("window/splitter_right", getattr(self, "right_splitter", None)),
        ):
            if splitter is not None:
                try:
                    s.setValue(key, splitter.saveState())
                except Exception as e:
                    print(f"패널 크기 저장 실패({key}): {e}")

    # ------------------------------------------------------------------
    # 디스플레이 관리
    # ------------------------------------------------------------------
    def _load_screens(self):
        prev_idx = self.combo_screens.currentIndex() if hasattr(self, "combo_screens") else -1
        self.combo_screens.blockSignals(True)
        self.combo_screens.clear()
        screens = QGuiApplication.screens()
        mon_str = self.t("monitor")
        pri_str = self.t("primary_screen")
        for idx, scr in enumerate(screens):
            geo = scr.geometry()
            name = f"{mon_str} {idx + 1} ({geo.width()}x{geo.height()})"
            if idx == 0:
                name += f" {pri_str}"
            self.combo_screens.addItem(name, idx)
        if 0 <= prev_idx < len(screens):
            self.combo_screens.setCurrentIndex(prev_idx)
        elif len(screens) > 1:
            self.combo_screens.setCurrentIndex(1)
        self.combo_screens.blockSignals(False)

    def _on_screen_selected(self, index):
        screens = QGuiApplication.screens()
        if 0 <= index < len(screens):
            target = screens[index]
            self._update_preview_aspect()
            if self.presenter.fill_screen:
                # 화면 채움 상태에서는 모니터만 바꿔준다
                self.presenter.set_target_screen(target)
                self._remember_show_screen(target)
            else:
                geo = target.geometry()
                self.presenter.setGeometry(geo.x() + 60, geo.y() + 60, 1280, 720)

    def _update_preview_aspect(self):
        """미리보기를 현재 선택된 송출 모니터와 같은 비율로 맞춘다"""
        screens = QGuiApplication.screens()
        idx = self.combo_screens.currentIndex()
        if 0 <= idx < len(screens):
            geo = screens[idx].geometry()
            self.preview.set_screen_aspect(geo.width(), geo.height())

    def _show_presenter_default(self):
        """시작 시 듀얼 창을 선택된 모니터에 전체 화면으로 표시"""
        self._show_presenter_fullscreen(self.combo_screens.currentIndex())

    def _show_presenter_fullscreen(self, index):
        """선택된 모니터에 송출 창을 화면 전체(프레임 없는 창)로 표시"""
        screens = QGuiApplication.screens()
        if not (0 <= index < len(screens)):
            return
        self.presenter.set_target_screen(screens[index])
        self.presenter.set_fill_screen(True)
        self.btn_fullscreen.setText(self.t("windowed"))
        self._remember_show_screen(screens[index])

    def _remember_show_screen(self, screen):
        """지금 듀얼 송출에 쓰고 있는 모니터를 기억해 둔다 (HDMI가 빠졌다 다시
        꽂혔을 때 같은 모니터가 돌아오면 자동으로 복귀시키기 위함)"""
        try:
            name = screen.name() if screen is not None else ""
        except Exception:
            name = ""
        if name:
            self._show_screen_name = name

    # ------------------------------------------------------------------
    # 모니터 연결/해제 감지 (HDMI 뽑았다 다시 꽂았을 때 자동 복귀)
    # ------------------------------------------------------------------
    def _on_screen_removed(self, screen):
        """모니터 연결이 끊겼다. 쓰던 화면이 사라진 거라면 다시 꽂혔을 때
        자동으로 복귀하도록 표시해 두고, 매달려 있는 참조를 정리한다."""
        try:
            name = screen.name()
        except Exception:
            name = ""
        was_our_screen = bool(name) and name == getattr(self, "_show_screen_name", "")
        # 이 QScreen 객체는 곧 파괴되므로, 나중에 잘못 건드리지 않도록 참조를 비운다
        if getattr(self.presenter, "target_screen", None) is screen:
            self.presenter.target_screen = None
        if was_our_screen and getattr(self, "btn_toggle_window", None) is not None:
            self._show_screen_pending_restore = self.btn_toggle_window.isChecked() and self.presenter.fill_screen
            print(f"[모니터] 송출에 쓰던 모니터({name})의 연결이 끊겼습니다")
        # 화면 개수가 실제로 바뀐 뒤(다음 이벤트 루프)에 콤보박스를 갱신한다
        QTimer.singleShot(0, self._load_screens)

    def _on_screen_added(self, screen):
        """모니터가 새로 연결됐다. 방금 전까지 쓰던 모니터가 다시 꽂힌 거라면
        듀얼 송출을 자동으로 복귀시킨다."""
        QTimer.singleShot(0, lambda: self._handle_screen_added(screen))

    def _handle_screen_added(self, screen):
        self._load_screens()
        try:
            name = screen.name()
        except Exception:
            name = ""
        if not (name and name == getattr(self, "_show_screen_name", "")
                and getattr(self, "_show_screen_pending_restore", False)):
            return
        self._show_screen_pending_restore = False
        screens = QGuiApplication.screens()
        for idx, scr in enumerate(screens):
            try:
                same = scr is screen or scr.name() == name
            except Exception:
                same = False
            if same:
                self.combo_screens.blockSignals(True)
                self.combo_screens.setCurrentIndex(idx)
                self.combo_screens.blockSignals(False)
                print(f"[모니터] 쓰던 모니터({name})가 다시 연결되어 듀얼 송출을 복귀합니다")
                self._show_presenter_fullscreen(idx)
                self._update_preview_aspect()
                break

    def _toggle_presenter_window(self, checked):
        if checked:
            self._on_screen_selected(self.combo_screens.currentIndex())
            self.presenter.show()
            self.btn_toggle_window.setText(self.t("close_dual"))
        else:
            self.presenter.hide()
            self.btn_toggle_window.setText(self.t("open_dual"))

    def _toggle_fullscreen(self):
        if self.presenter.fill_screen:
            self.presenter.set_fill_screen(False)
            self.btn_fullscreen.setText(self.t("fullscreen"))
        else:
            self._show_presenter_fullscreen(self.combo_screens.currentIndex())

    # ------------------------------------------------------------------
    # 배경: 색상
    # ------------------------------------------------------------------
    def _set_color_bg(self, color: QColor, name: str = ""):
        self.presenter.set_color_background(color)
        self.preview.set_bg_color(color)
        self.current_bg_desc = name or color.name()
        self._update_status()
        self._bg_needs_restore = False
        self.settings.setValue("bg/type", "color")
        self.settings.setValue("bg/value", color.name())
        self._refresh_paragraph_thumbs()

    def _set_transparent_bg(self):
        """투명 배경: 듀얼 창이 투명해져 데스크톱이 비치고 텍스트만 표시"""
        self.presenter.set_transparent(True)
        self.preview.set_transparent(True)
        self.current_bg_desc = self.t("transparent")
        self._update_status()
        self._bg_needs_restore = False
        self.settings.setValue("bg/type", "transparent")
        self.settings.setValue("bg/value", "")
        self._refresh_paragraph_thumbs()

    def _restore_configured_background(self):
        """이전 미디어(폴더 이미지) 잔상을 제거하고 사용자가 설정한 원래 배경으로 복원"""
        self._bg_needs_restore = False
        self._folder_replaced_bg = False
        self.presenter.clear_overlay_image()
        self.preview.clear_overlay_image()
        bg_type = str(self.settings.value("bg/type", "transparent") or "transparent")
        bg_val = str(self.settings.value("bg/value", "") or "")
        if bg_type == "color" and bg_val:
            self.presenter.set_color_background(QColor(bg_val))
            self.preview.set_bg_color(QColor(bg_val))
            key = PRESET_COLOR_KEYS.get(bg_val.lower())
            self.current_bg_desc = (f"{self.t(key)} ({bg_val.upper()})" if key
                                    else f"{self.t('color_custom_prefix')} {bg_val}")
        elif bg_type == "image" and bg_val and os.path.isfile(bg_val):
            self.presenter.set_image_background(bg_val)
            self.preview.set_bg_image(bg_val)
            self.current_bg_desc = os.path.basename(bg_val)
        elif bg_type == "video" and bg_val and os.path.isfile(bg_val):
            self.presenter.play_playlist([bg_val], 0)
            self.preview.set_video_note("")
            self.current_bg_desc = os.path.basename(bg_val)
        else:
            self.presenter.set_transparent(True)
            self.preview.set_transparent(True)
            self.current_bg_desc = self.t("transparent")
        self._update_status()

    def _add_custom_color(self):
        color = QColorDialog.getColor(QColor("#3498db"), self, self.t("dialog_select_bg_color"))
        if not color.isValid():
            return
        hex_str = color.name()
        if hex_str not in self.custom_colors:
            self.custom_colors.append(hex_str)
            self._add_color_item(color, f"{self.t('color_custom_prefix')} {hex_str}", kind="custom")
            self.settings.setValue("lib/custom_colors", self.custom_colors)
        self._set_color_bg(color, hex_str)

    def _add_color_item(self, color: QColor, text: str, kind="preset"):
        item = QListWidgetItem(make_color_swatch_pixmap(color), text)
        item.setData(USER_ROLE_PATH, color.name())
        item.setData(USER_ROLE_KIND, kind)
        item.setToolTip(f"{text} ({color.name()})")
        self.list_colors.addItem(item)
        return item

    def _on_color_selected(self, item):
        modifiers = QGuiApplication.keyboardModifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            return
        if item.data(USER_ROLE_PATH) == "transparent":
            self._set_transparent_bg()
            return
        color = QColor(item.data(USER_ROLE_PATH))
        self._set_color_bg(color, item.text())

    def _delete_selected_color(self):
        selected_items = self.list_colors.selectedItems()
        if not selected_items:
            row = self.list_colors.currentRow()
            if row >= 0:
                selected_items = [self.list_colors.item(row)]
        if not selected_items:
            return

        changed = False
        for item in selected_items:
            if item.data(USER_ROLE_KIND) != "custom":
                continue  # 기본 색상은 삭제 불가
            hex_str = item.data(USER_ROLE_PATH)
            if hex_str in self.custom_colors:
                self.custom_colors.remove(hex_str)
                changed = True
            row = self.list_colors.row(item)
            if row >= 0:
                self.list_colors.takeItem(row)

        if changed:
            self.settings.setValue("lib/custom_colors", self.custom_colors)

    # ------------------------------------------------------------------
    # 배경: 이미지
    # ------------------------------------------------------------------
    def _add_images(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, self.t("dialog_select_images"),
            self.settings.value("last_dir", str(Path.home())),
            self.t("filter_image")
        )
        if files:
            self._handle_images_dropped(files)

    def _handle_images_dropped(self, files: list):
        """이미지 파일들을 이미지 라이브러리에 추가 (드래그앤드롭 또는 파일 대화상자)"""
        valid_files = [f for f in files if os.path.isfile(f) and Path(f).suffix.lower() in IMAGE_EXTS]
        if not valid_files:
            return
        self.settings.setValue("last_dir", os.path.dirname(valid_files[0]))
        paths = self._existing_image_paths()
        added = []
        for f in valid_files:
            if f not in paths:
                paths.append(f)
                added.append(f)
        self.settings.setValue("lib/images", paths)
        for f in added:
            self._add_image_item(f)
        if added:
            self._set_image_bg(added[-1])

    def _add_image_item(self, path: str):
        item = QListWidgetItem("")
        item.setData(USER_ROLE_PATH, path)
        item.setToolTip(os.path.basename(path))
        item.setSizeHint(QSize(106, 80))
        self.list_images.addItem(item)
        task = ThumbnailTask(path, 100, 75)
        task.signals.finished.connect(self._on_thumb_ready)
        self.thread_pool.start(task)

    def _existing_image_paths(self) -> list:
        return [self.list_images.item(i).data(USER_ROLE_PATH)
                for i in range(self.list_images.count())]

    def _set_image_bg(self, path: str):
        self.presenter.set_image_background(path)
        self.preview.set_bg_image(path)
        self.current_bg_desc = os.path.basename(path)
        self._update_status()
        self._bg_needs_restore = False
        self.settings.setValue("bg/type", "image")
        self.settings.setValue("bg/value", path)
        self._refresh_paragraph_thumbs()

    def _on_image_selected(self, item):
        modifiers = QGuiApplication.keyboardModifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            return
        self._set_image_bg(item.data(USER_ROLE_PATH))

    def _delete_selected_image(self):
        selected_items = self.list_images.selectedItems()
        if not selected_items:
            row = self.list_images.currentRow()
            if row >= 0:
                selected_items = [self.list_images.item(row)]
        if not selected_items:
            return

        deleted_paths = []
        for item in selected_items:
            path = item.data(USER_ROLE_PATH)
            deleted_paths.append(path)
            row = self.list_images.row(item)
            if row >= 0:
                self.list_images.takeItem(row)

        paths = self._existing_image_paths()
        self.settings.setValue("lib/images", paths)
        if getattr(self.presenter, "bg_image_path", None) in deleted_paths:
            self._set_color_bg(QColor("#000000"), self.t("black"))

    def _clear_all_images(self):
        """이미지 라이브러리 목록을 전체 비움"""
        if self.list_images.count() == 0:
            return
        current_bg = getattr(self.presenter, "bg_image_path", None)
        all_paths = self._existing_image_paths()
        self.list_images.clear()
        self.settings.setValue("lib/images", [])
        if current_bg in all_paths:
            self._set_color_bg(QColor("#000000"), self.t("black"))

    def _delete_selected_video(self):
        selected_items = self.list_videos.selectedItems()
        if not selected_items:
            row = self.list_videos.currentRow()
            if row >= 0:
                selected_items = [self.list_videos.item(row)]
        if not selected_items:
            return

        deleted_paths = []
        for item in selected_items:
            path = item.data(USER_ROLE_PATH)
            deleted_paths.append(path)
            row = self.list_videos.row(item)
            if row >= 0:
                self.list_videos.takeItem(row)

        paths = self._existing_video_paths()
        self.settings.setValue("lib/videos", paths)
        self.settings.setValue("video/checked", self._checked_video_paths())
        self._update_playlist_state()

        playing_paths = set(getattr(self.presenter, "playlist", []))
        if any(p in playing_paths for p in deleted_paths):
            self._stop_videos()
            self._set_color_bg(QColor("#000000"), self.t("black"))
        elif getattr(self.presenter, "bg_image_path", None) in deleted_paths:
            self._set_color_bg(QColor("#000000"), self.t("black"))

    def _clear_all_videos(self):
        """동영상 라이브러리 목록을 전체 비움"""
        if self.list_videos.count() == 0:
            return
        self._stop_videos()
        self.list_videos.clear()
        self.settings.setValue("lib/videos", [])
        self.settings.setValue("video/checked", [])
        self._update_playlist_state()
        if getattr(self.presenter, "bg_video_path", None):
            self._set_color_bg(QColor("#000000"), self.t("black"))

    # ------------------------------------------------------------------
    # 배경: 동영상 (재생목록 반복)
    # ------------------------------------------------------------------
    def _add_videos(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, self.t("dialog_select_videos"),
            self.settings.value("last_dir", str(Path.home())),
            self.t("filter_video")
        )
        if files:
            self._handle_videos_dropped(files)

    def _handle_videos_dropped(self, files: list):
        """동영상 파일들을 동영상 라이브러리에 추가 (드래그앤드롭 또는 파일 대화상자)"""
        valid_files = [f for f in files if os.path.isfile(f) and Path(f).suffix.lower() in VIDEO_EXTS]
        if not valid_files:
            return
        self.settings.setValue("last_dir", os.path.dirname(valid_files[0]))
        paths = self._existing_video_paths()
        added = []
        for f in valid_files:
            if f not in paths:
                paths.append(f)
                added.append(f)
        self.settings.setValue("lib/videos", paths)
        for f in added:
            self._add_video_item(f)
        if added:
            self._update_playlist_state()

    def _add_video_item(self, path: str, checked=False):
        item = QListWidgetItem("")
        item.setData(USER_ROLE_PATH, path)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        item.setToolTip(os.path.basename(path))
        item.setSizeHint(QSize(118, 88))
        self.list_videos.addItem(item)
        task = ThumbnailTask(path, 110, 80)
        task.signals.finished.connect(self._on_thumb_ready)
        self.thread_pool.start(task)

    def _existing_video_paths(self) -> list:
        return [self.list_videos.item(i).data(USER_ROLE_PATH)
                for i in range(self.list_videos.count())]

    def _checked_video_paths(self) -> list:
        return [self.list_videos.item(i).data(USER_ROLE_PATH)
                for i in range(self.list_videos.count())
                if self.list_videos.item(i).checkState() == Qt.CheckState.Checked]

    def _on_video_clicked(self, item):
        """동영상 클릭 시 해당 영상 즉시 재생 (자동 반복)"""
        modifiers = QGuiApplication.keyboardModifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            return
        path = item.data(USER_ROLE_PATH)
        self.presenter.play_playlist([path], 0)
        self.preview.set_video_note("")
        self.current_bg_desc = f"{self.t('tab_video')}: {os.path.basename(path)}"
        self._update_status()
        self._bg_needs_restore = False
        self.settings.setValue("bg/type", "video")
        self.settings.setValue("bg/value", path)
        self._refresh_paragraph_thumbs()

    def _on_video_check_changed(self, item):
        """동영상 체크 상태가 바뀔 때마다 - 버튼 없이 - 바로 반복 재생을 갱신한다.

        체크된 게 있으면 그 목록을 곧바로(반복) 재생하고, 전부 해제하면 정지한다.
        """
        self._update_playlist_state()
        checked = self._checked_video_paths()
        self.settings.setValue("video/checked", checked)
        if checked:
            self._play_selected_videos()
        else:
            self.presenter.stop_playlist()
            self._update_status()

    def _play_selected_videos(self):
        checked = self._checked_video_paths()
        if not checked:
            # 선택된 항목이 없으면 전체 목록 재생
            checked = self._existing_video_paths()
        if not checked:
            return
        self.presenter.play_playlist(checked, 0)
        self.current_bg_desc = f"{self.t('tab_video')} ({len(checked)})"
        self._update_status()
        self._bg_needs_restore = False
        self.settings.setValue("bg/type", "video")
        self.settings.setValue("bg/value", checked[0])
        self._refresh_paragraph_thumbs()

    def _stop_videos(self):
        self.presenter.stop_playlist()
        self.lbl_playlist_state.setText(self.t("playlist_stopped"))
        self._set_color_bg(QColor("#000000"), self.t("black"))
        self._update_status()

    def _update_playlist_state(self):
        checked = self._checked_video_paths()
        total = self.list_videos.count()
        if not checked:
            self.lbl_playlist_state.setText(self.t("playlist_none"))
            return
        names = [os.path.basename(p) for p in checked[:3]]
        suffix = "…" if len(checked) > 3 else ""
        self.lbl_playlist_state.setText(
            f"{self.t('playlist_playing_count', f'{len(checked)}/{total}')} → {' / '.join(names)}{suffix}")

    # ------------------------------------------------------------------
    # 텍스트 파일 / 문단
    # ------------------------------------------------------------------
    def _open_text_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, self.t("dialog_select_txt_file"),
            self.settings.value("last_dir", str(Path.home())),
            self.t("filter_text")
        )
        if not file_path:
            return
        self.settings.setValue("last_dir", os.path.dirname(file_path))
        self._load_text_file(file_path)

    # ------------------------------------------------------------------
    # 텍스트 파일 라이브러리 (좌측 아래)
    # ------------------------------------------------------------------
    def _show_add_item_menu(self):
        """'추가' 버튼: 텍스트/PPT 파일 또는 이미지 폴더 중 고르는 메뉴를 띄운다"""
        menu = QMenu(self)
        act_file = menu.addAction(self.t("add_item_menu_file"))
        act_folder = menu.addAction(self.t("add_item_menu_folder"))
        chosen = menu.exec(self.btn_add_item.mapToGlobal(self.btn_add_item.rect().bottomLeft()))
        if chosen is act_file:
            self._add_files_to_library()
        elif chosen is act_folder:
            self._add_image_folder_to_library()

    def _add_files_to_library(self):
        """텍스트(.txt/.md) 또는 파워포인트(.pptx 등) 파일을 하나 이상 라이브러리에 추가"""
        # 파워포인트가 섞여 있을 수 있으므로, 대화상자를 여는 동안 미리 띄워 둔다
        # (실제로 텍스트만 고르면 그냥 버려진다 - 비용이 적어 손해가 없다)
        ppt_engine.warmup_async()

        last_dir = self.settings.value("last_dir", str(Path.home()))
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, self.t("dialog_add_files"), last_dir, self.t("filter_text_and_pptx")
        )
        if not file_paths:
            return
        self.settings.setValue("last_dir", os.path.dirname(file_paths[0]))
        existing = self._get_registered_text_files()
        added = False
        for p in file_paths:
            if p and p not in existing:
                existing.append(p)
                added = True
        if added:
            self._save_registered_text_files(existing)
        self._refresh_text_files_list(select_path=file_paths[0])
        first = file_paths[0]
        if ppt_engine.is_ppt_file(first):
            self._load_pptx(first)
        elif is_video_file(first):
            self._load_video_item(first)      # 동영상은 재생 단추를 눌러야 시작
        else:
            self._load_text_file(first)

    def _load_pptx(self, file_path: str, select_index=0, broadcast=True, prepare=None):
        """파워포인트 슬라이드를 불러온다.

        - 캐시가 있으면 파워포인트를 띄우지 않고 즉시 표시한다.
        - 없으면 장수를 먼저 받아 빈 카드를 배치하고, 한 장씩 채워 넣는다.
        - broadcast: 준비되는 대로 실제 송출 화면에 낼지. False 면 목록/미리보기만
          갱신하고 지금 화면에 나가고 있는 내용은 그대로 둔다 (라이브러리에서 구경만
          하는 경우).
        - prepare: 지금 바로 슬라이드를 준비(내보내기)할지. 생략하면 broadcast 값을
          따른다. 시작 직후 세션 복원은 prepare 도 생략해 아무 준비도 하지 않는다
          (파워포인트를 조용히 띄우지 않기 위함) - 목록에서 실제로 클릭해야 준비된다.
        """
        if prepare is None:
            prepare = broadcast

        # 캐시가 있으면 파워포인트 자동화 모듈을 불러올 필요도 없다
        # (pywin32 첫 불러오기는 1초 가까이 걸릴 수 있어 시작이 느려진다)
        cached = ppt_engine.read_cache(file_path)
        if not cached:
            available, message = ppt_engine.powerpoint_support()
            if not available:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, self.t("err_ppt_title"), message)
                return

        # 글꼴이 포함 저장된 파일은 PDF 를 거쳐야 원본 글꼴이 유지된다.
        # 변환 라이브러리가 없으면 조용히 글꼴이 바뀌므로 한 번은 알린다.
        if not cached and not getattr(self, "_pdf_warned", False):
            ok_pdf, pdf_message = ppt_engine.pdf_render_support()
            if not ok_pdf:
                self._pdf_warned = True
                self.statusBar().showMessage(pdf_message, 15000)

        # 실제로 이 파일을 송출하는 경우에만 진행 중인 슬라이드쇼를 끝낸다.
        # 구경만 하는 것(broadcast=False)이라면 다른 파일의 슬라이드쇼를 그대로 둔다.
        if broadcast and getattr(self, "_show_mode_active", False):
            self._stop_slideshow(silent=True, resume_export=False)

        # 이전 로드의 콜백을 무시하고, 진행 중인 내보내기는 중단시킨다
        self._ppt_load_token += 1
        token = self._ppt_load_token
        self._ppt_total = 0
        self._ppt_ready = set()
        self._ppt_autopresent = bool(broadcast)
        self._ppt_select_index = max(0, int(select_index))

        # 기존 폴더-슬라이드 파이프라인을 그대로 재사용한다
        self.current_source_type = "folder"
        self.current_source_path = file_path
        self.media_source_kind = "pptx"
        self.media_source_name = os.path.basename(file_path)
        self.media_slides = []
        self.media_notes = []
        self.media_slide_index = -1
        self._update_side_panel_mode()
        self.paragraphs = []
        self.paragraph_index = -1
        self.text_file_path = file_path
        if not self.presenter.isVisible():
            self.presenter.show()
        try:
            self.lbl_txt_file.setText(f"📊 {os.path.basename(file_path)}")
        except RuntimeError:
            pass
        self.settings.setValue("text/file", file_path)
        self.settings.setValue("text/source_type", "pptx")
        self._rebuild_paragraph_list()
        if hasattr(self, "para_tab"):
            self.para_tab.setCurrentIndex(0)

        if cached:
            self.media_slides = list(cached["slides"])
            notes = list(cached.get("notes") or [])
            notes += [""] * max(0, cached["count"] - len(notes))
            self.media_notes = notes
            self._ppt_total = cached["count"]
            self._ppt_ready = set(range(cached["count"]))
            self._rebuild_paragraph_list()
            self.statusBar().showMessage(self.t("msg_ppt_cached", cached["count"]), 3000)
            if broadcast and self.media_slides:
                self._present_media_slide(
                    min(self._ppt_select_index, len(self.media_slides) - 1))
            # else: 목록만 갱신됐다 - 화면은 그대로 둔다 (문단을 클릭해야 나간다)
            return

        if not prepare:
            # 프로그램 시작 직후에는 파워포인트를 띄우지 않는다 (목록에서 클릭할 때 준비)
            self.statusBar().showMessage(self.t("msg_ppt_click_to_load"), 5000)
            return

        self.statusBar().showMessage(self.t("msg_ppt_exporting", 0, 0))
        ppt_engine.export_async(
            file_path,
            on_count=lambda c, paths, t=token: self.ppt_count_ready.emit(t, c, paths),
            on_slide=lambda i, p, n, t=token: self.ppt_slide_ready.emit(t, i, p, n),
            on_done=lambda c, t=token: self.ppt_export_done.emit(t, c),
            on_error=lambda m, t=token: self.ppt_export_failed.emit(t, m),
            # 애니메이션 모드가 켜지면 내보내기를 멈춘다. 같은 COM 스레드를 쓰므로
            # 내보내기가 돌고 있으면 슬라이드 조작이 몇 초씩 밀린다.
            # (이미 내보낸 장은 캐시에 남아 모드를 끄면 이어서 진행한다)
            cancel=lambda t=token: t != self._ppt_load_token or self._show_mode_active,
            extract_notes=True,
            # 지금 보려는 슬라이드를 가장 먼저 만들게 한다 (첫 화면을 앞당긴다)
            first_index=self._ppt_select_index + 1,
        )

    def _media_slide_desc(self, idx: int) -> str:
        """상태 표시줄에 쓸 현재 슬라이드 설명"""
        total = len(self.media_slides)
        if not (0 <= idx < total):
            return ""
        if getattr(self, "media_source_kind", "folder") == "pptx":
            name = getattr(self, "media_source_name", "") or ""
            return f"📊 {name} {idx + 1}/{total}"
        return (f"📁 {self.t('tab_image')} {idx + 1}/{total}: "
                f"{os.path.basename(self.media_slides[idx])}")

    def _is_pptx_mode(self, token: int = None) -> bool:
        """지금도 이 PPT 로드가 유효한지 (다른 파일로 바뀌었으면 False)"""
        if token is not None and token != self._ppt_load_token:
            return False
        return (getattr(self, "current_source_type", "text") == "folder"
                and getattr(self, "media_source_kind", "folder") == "pptx")

    def _is_image_folder_mode(self) -> bool:
        """이미지 폴더를 보고 있는지 (PPT 슬라이드가 아닌 사진들)"""
        return (getattr(self, "current_source_type", "text") == "folder"
                and getattr(self, "media_source_kind", "folder") == "folder")

    @Slot(int, int, object)
    def _on_ppt_count_ready(self, token: int, count: int, paths):
        """장수를 먼저 받아 빈 슬라이드 카드를 즉시 배치한다"""
        if not self._is_pptx_mode(token):
            return
        self._ppt_total = int(count)
        self.media_slides = [str(p) for p in paths]
        if len(self.media_notes) != int(count):
            # 이어서 내보내는 경우에는 이미 받은 노트를 유지한다
            self.media_notes = [""] * int(count)
        self._rebuild_paragraph_list()
        self.statusBar().showMessage(self.t("msg_ppt_exporting", 0, count))

    @Slot(int, int, str, str)
    def _on_ppt_slide_ready(self, token: int, index: int, path: str, note: str):
        """한 장이 준비될 때마다 썸네일·노트를 채우고, 첫 장은 바로 송출한다"""
        if not self._is_pptx_mode(token):
            return
        self._ppt_ready.add(index)
        if 0 <= index < len(self.media_notes):
            self.media_notes[index] = note or ""
        elif index >= len(self.media_notes):
            self.media_notes += [""] * (index + 1 - len(self.media_notes))
            self.media_notes[index] = note or ""
        # 지금 송출 중인 슬라이드의 노트가 방금 도착했다면 즉시 반영
        if index == getattr(self, "media_slide_index", -1):
            self._show_slide_notes(index)
        if 0 <= index < len(self.media_slides):
            self._start_card_thumb(self.media_slides[index])
        total = self._ppt_total or len(self._ppt_ready)
        self.statusBar().showMessage(self.t("msg_ppt_exporting", len(self._ppt_ready), total))

        target = min(self._ppt_select_index, max(0, self._ppt_total - 1))
        if self._ppt_autopresent and index == target:
            self._ppt_autopresent = False
            self._present_media_slide(index)

    @Slot(int, int)
    def _on_ppt_export_done(self, token: int, count: int):
        if not self._is_pptx_mode(token):
            return
        self.statusBar().showMessage(self.t("msg_ppt_ready", count), 4000)
        # 라이브러리 항목에 장수 표시를 갱신
        self._refresh_text_files_list(select_path=self.current_source_path)

    @Slot(int, str)
    def _on_ppt_export_failed(self, token: int, message: str):
        if token != self._ppt_load_token:
            return   # 이미 다른 파일로 넘어간 뒤 도착한 오류는 알리지 않는다
        from PySide6.QtWidgets import QMessageBox
        self.statusBar().clearMessage()
        QMessageBox.warning(self, self.t("err_ppt_title"),
                            self.t("err_ppt_failed", message))

    def _add_image_folder_to_library(self):
        """이미지 폴더를 라이브러리에 추가"""
        last_dir = self.settings.value("last_dir", str(Path.home()))
        folder = QFileDialog.getExistingDirectory(
            self, self.t("dialog_select_img_folder"),
            last_dir
        )
        if not folder:
            return
        self.settings.setValue("last_dir", folder)
        existing = self._get_registered_text_files()
        if folder not in existing:
            existing.append(folder)
            self._save_registered_text_files(existing)
        self._refresh_text_files_list(select_path=folder)
        self._load_image_folder(folder)

    def _remove_text_file_from_library(self):
        """선택한 항목들을 라이브러리에서 제거 (여러 개 선택 가능, 현재 열려있는 파일도 영향 없음)"""
        items = self.list_text_files.selectedItems()
        if not items:
            row = self.list_text_files.currentRow()
            if row >= 0:
                items = [self.list_text_files.item(row)]
        if not items:
            return
        target_paths = {item.data(USER_ROLE_PATH) for item in items if item.data(USER_ROLE_PATH)}
        current = self._get_registered_text_files()
        new_list = [p for p in current if p not in target_paths]
        if len(new_list) != len(current):
            self._save_registered_text_files(new_list)
            self._refresh_text_files_list()

    def _clear_all_text_files(self):
        """텍스트 파일/폴더 라이브러리 목록을 전체 비움"""
        if self.list_text_files.count() == 0:
            return
        self._save_registered_text_files([])
        self._refresh_text_files_list()

    def _handle_text_files_dropped(self, paths: list):
        """드래그 앤 드롭된 텍스트 파일(.txt, .md) 및 이미지 폴더를 라이브러리에 등록"""
        TEXT_EXTS = {".txt", ".md"}
        valid_items = []
        for p in paths:
            if not os.path.exists(p):
                continue
            if os.path.isdir(p):
                imgs = scan_folder_images(p)
                if imgs:
                    valid_items.append(p)
            elif os.path.isfile(p):
                if (Path(p).suffix.lower() in TEXT_EXTS or ppt_engine.is_ppt_file(p)
                        or is_video_file(p)):
                    valid_items.append(p)

        if not valid_items:
            return

        existing = self._get_registered_text_files()
        added = False
        first_added = valid_items[0]
        for p in valid_items:
            if p not in existing:
                existing.append(p)
                added = True

        if added:
            self._save_registered_text_files(existing)
            self._refresh_text_files_list(select_path=first_added)
            if os.path.isdir(first_added):
                self._load_image_folder(first_added)
            elif ppt_engine.is_ppt_file(first_added):
                self._load_pptx(first_added)
            elif is_video_file(first_added):
                self._load_video_item(first_added)
            else:
                self._load_text_file(first_added)

    def _on_text_file_library_clicked(self, item):
        """라이브러리에서 항목 클릭 시 해당 텍스트 또는 폴더 로드"""
        modifiers = QGuiApplication.keyboardModifiers()
        if modifiers & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier):
            return
        path = item.data(USER_ROLE_PATH)
        kind = item.data(USER_ROLE_KIND)
        if not path or not os.path.exists(path):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, self.t("item_not_found_title"),
                self.t("item_not_found_msg", path)
            )
            return
        # 라이브러리에서 클릭한 것만으로는 아직 송출하지 않는다 - 목록/미리보기만
        # 갱신하고, 실제로 문단이나 슬라이드를 클릭해야 비로소 화면에 나간다.
        if kind == "mix" or mix_bundle.is_mix_file(path):
            self._load_mix(path)
        elif kind == "pptx" or ppt_engine.is_ppt_file(path):
            self._load_pptx(path, broadcast=False, prepare=True)
            # 애니메이션 모드를 켤 때 바로 뜨도록 파워포인트에 미리 열어 둔다
            self._show_prepared_path = path
            ppt_engine.prepare_show_async(path)
        elif kind == "folder" or os.path.isdir(path):
            self._load_image_folder(path, broadcast=False)
        elif kind == "video" or is_video_file(path):
            self._load_video_item(path)
        else:
            self._load_text_file(path, broadcast=False)

    def _get_registered_text_files(self) -> list:
        raw = self.settings.value("text_files/paths", "")
        if not raw:
            return []
        if isinstance(raw, str):
            parts = [p for p in raw.split("\n") if p.strip()]
            return parts
        if isinstance(raw, list):
            return [str(p) for p in raw if p]
        return [str(raw)]

    def _save_registered_text_files(self, paths: list):
        self.settings.setValue("text_files/paths", "\n".join(paths))
        self.settings.setValue("text_files/count", len(paths))

    def _on_text_files_reordered(self):
        """라이브러리 목록에서 항목을 드래그해 순서를 바꾼 뒤 - 그 순서를 저장하고
        (번호/행 위젯을 새 순서에 맞게 다시 그리도록) 목록을 새로 그린다"""
        paths = []
        for row in range(self.list_text_files.count()):
            it = self.list_text_files.item(row)
            p = it.data(USER_ROLE_PATH)
            if p:
                paths.append(p)
        self._save_registered_text_files(paths)
        self._refresh_text_files_list()

    def _register_text_file(self, file_path: str):
        """텍스트 파일 하나를 좌측 라이브러리에 등록(중복 제외)하고 목록에서 선택한다."""
        if not file_path:
            return
        existing = self._get_registered_text_files()
        if file_path not in existing:
            existing.append(file_path)
            self._save_registered_text_files(existing)
        self._refresh_text_files_list(select_path=file_path)

    # 종류별 이름 색 (어두운 배경에서도 잘 읽히도록)
    _LIBRARY_ITEM_COLORS = {
        "text": "#7fd1ff",     # 텍스트 - 하늘색
        "pptx": "#ffb454",     # PPT - 주황
        "folder": "#8ce99a",   # 이미지 폴더 - 연두
        "video": "#ff9ecf",    # 동영상 - 분홍
        "mix": "#ffd866",      # 묶음 - 노랑
    }

    def _remove_one_text_file(self, path: str):
        """라이브러리 한 줄의 휴지통 버튼 - 그 항목 하나만 제거"""
        if not path:
            return
        current = self._get_registered_text_files()
        new_list = [p for p in current if p != path]
        if len(new_list) != len(current):
            self._save_registered_text_files(new_list)
            self._refresh_text_files_list()

    def _refresh_text_files_list(self, select_path: str = ""):
        """QSettings에서 등록 항목을 읽어 list_text_files를 다시 그림 (번호/종류별 색/삭제 버튼 포함)"""
        if not hasattr(self, "list_text_files"):
            return
        self.list_text_files.blockSignals(True)
        self.list_text_files.clear()
        folder_badge = self.t("item_folder_badge")
        count_suffix = self.t("items_count_suffix")
        font_size = getattr(self, "_library_font_size", 12)
        row_height = max(22, font_size + 14)
        for number, path in enumerate(self._get_registered_text_files(), start=1):
            if not path:
                continue
            base = os.path.basename(path)
            if mix_bundle.is_mix_file(path):
                data = mix_bundle.load_mix(path)
                text = f"🔗 {mix_bundle.display_name(data)} ({len(data['sources'])}{self.t('mix_files_suffix')})"
                kind = "mix"
            elif os.path.isdir(path):
                imgs = scan_folder_images(path)
                text = f"📁 {folder_badge} {base} ({len(imgs)}{count_suffix})"
                kind = "folder"
            elif ppt_engine.is_ppt_file(path):
                cached = ppt_engine.read_cache(path)
                text = (f"📊 {base} ({cached['count']}{count_suffix})"
                        if cached else f"📊 {base}")
                kind = "pptx"
            elif is_video_file(path):
                text = f"🎬 {base}"
                kind = "video"
            else:
                text = f"📄 {base}"
                kind = "text"
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, row_height))
            item.setData(USER_ROLE_KIND, kind)
            item.setData(USER_ROLE_PATH, path)
            self.list_text_files.addItem(item)

            row_widget = LibraryRowWidget()
            row_widget.set_content(number, text, self._LIBRARY_ITEM_COLORS.get(kind, "#e0e0e0"), path)
            row_widget.set_font_size(font_size)
            row_widget.clicked.connect(lambda it=item: self._on_text_file_library_clicked(it))
            row_widget.deleteClicked.connect(lambda p=path: self._remove_one_text_file(p))
            self.list_text_files.setItemWidget(item, row_widget)
        # 선택 복원
        if select_path:
            for row in range(self.list_text_files.count()):
                it = self.list_text_files.item(row)
                if it.data(USER_ROLE_PATH) == select_path:
                    self.list_text_files.setCurrentRow(row)
                    break
        self.list_text_files.blockSignals(False)

    def _adjust_library_font_size(self, delta: int):
        """왼쪽 파일 목록 글자 크기 조정 (Ctrl+휠)"""
        size = max(9, min(28, getattr(self, "_library_font_size", 12) + delta))
        if size == getattr(self, "_library_font_size", 12):
            return
        self._library_font_size = size
        self.settings.setValue("text_files/list_font_size", size)
        self._refresh_text_files_list(select_path=getattr(self, "current_source_path", ""))


    # ------------------------------------------------------------------
    # 묶음 (텍스트·PPT·사진·동영상을 한데 모아 보고, 끌어서 순서를 섞기)
    # ------------------------------------------------------------------
    def _mix_readers(self):
        return dict(load_text=load_text_file, read_ppt_cache=ppt_engine.read_cache,
                    scan_images=scan_folder_images, is_ppt=ppt_engine.is_ppt_file,
                    is_video=is_video_file)

    def _load_mix(self, path: str, broadcast: bool = False):
        """묶음을 가운데에 펼친다 (누르기 전에는 송출하지 않는다)"""
        same = (getattr(self, "current_source_type", "") == "mix"
                and getattr(self, "current_source_path", "") == path)
        focus_key = (self.mix_entries[self.mix_index].key
                     if same and 0 <= self.mix_index < len(self.mix_entries) else None)
        self.current_source_type = "mix"
        self.current_source_path = path
        self.media_source_kind = "mix"
        data = mix_bundle.load_mix(path)
        self.media_source_name = mix_bundle.display_name(data)
        self.media_slides = []
        self.media_notes = []
        self.media_slide_index = -1
        self.paragraphs = []
        self.paragraph_index = -1
        # 묶음에는 저장할 텍스트 파일이 없다 (편집기의 '적용'이 원본을 덮어쓰지 않게)
        self.text_file_path = ""
        self._clear_paragraphs_unsaved()
        self.mix_data = data
        self.mix_entries = mix_bundle.build_entries(data, **self._mix_readers())
        self.mix_index = -1
        if focus_key is not None:
            for i, e in enumerate(self.mix_entries):
                if e.key == focus_key:
                    self.mix_index = i
                    break
        if not same:
            self._mix_video_path = ""
            self._mix_picked = set()
            self._mix_anchor = -1
        else:
            keys = {e.key for e in self.mix_entries}
            self._mix_picked = {k for k in getattr(self, "_mix_picked", set()) if k in keys}
        self._set_mix_title_label()
        self.settings.setValue("text/file", path)
        self.settings.setValue("text/source_type", "mix")
        self._mix_start_ppt_exports()
        if hasattr(self, "para_tab"):
            self.para_tab.setCurrentIndex(0)
        self._update_side_panel_mode()
        self._rebuild_paragraph_list()
        self._update_status()

    def _set_mix_title_label(self):
        try:
            self.lbl_txt_file.setText(
                f"🔗 {self.media_source_name} ({len(self.mix_entries)}{self.t('items_count_suffix')})")
        except (RuntimeError, AttributeError):
            pass

    def _mix_start_ppt_exports(self):
        """묶음 안의 PPT 중 아직 그림으로 만들지 않은 것은 뒤에서 만든다"""
        if getattr(self, "_show_mode_active", False):
            return      # 슬라이드쇼가 같은 파워포인트를 쓰고 있다 - 모드를 끄면 그때 만든다
        for src in getattr(self, "mix_data", {}).get("sources", []):
            if (src in self._mix_exporting or not os.path.isfile(src)
                    or not ppt_engine.is_ppt_file(src) or ppt_engine.read_cache(src)):
                continue
            self._mix_exporting.add(src)
            ppt_engine.export_async(
                src,
                on_done=lambda c, p=src: self.mix_ppt_ready.emit(p),
                on_error=lambda m, p=src: self.mix_ppt_failed.emit(p, str(m)),
                on_cancelled=lambda n, p=src: self.mix_ppt_cancelled.emit(p),
                cancel=lambda: getattr(self, "_show_mode_active", False),
                extract_notes=True,
            )

    def _on_mix_ppt_ready(self, path: str):
        self._mix_exporting.discard(path)
        if not ppt_engine.read_cache(path):
            return              # 아직 그림이 없다 - 다시 읽어도 같다 (되풀이하지 않는다)
        if (getattr(self, "current_source_type", "") == "mix"
                and path in getattr(self, "mix_data", {}).get("sources", [])):
            self._load_mix(self.current_source_path)

    def _on_mix_ppt_failed(self, path: str, message: str):
        self._mix_exporting.discard(path)
        self.statusBar().showMessage(self.t("msg_mix_ppt_failed", f"{os.path.basename(path)} - {message}"), 8000)

    def _fill_mix_cards(self):
        """묶음 카드들을 가운데 목록에 넣는다 (그림은 뒤에서 읽어 붙인다)"""
        for i, e in enumerate(self.mix_entries):
            if e.kind == "text":
                display = e.title
                caption = f"{os.path.splitext(os.path.basename(e.source))[0]} · {e.index + 1}"
            elif e.kind == "wait":
                display = self.t("mix_ppt_preparing")
                caption = os.path.basename(e.source)
            elif e.kind == "slide":
                display = caption = e.title
            else:
                display = caption = os.path.basename(e.path)
            item = QListWidgetItem(display)
            item.setData(USER_ROLE_INDEX, i)
            item.setData(USER_ROLE_KIND, e.kind)
            item.setData(USER_ROLE_PATH, e.path)
            item.setData(USER_ROLE_CAPTION, caption)
            item.setData(USER_ROLE_PICKED, e.key in getattr(self, "_mix_picked", set()))
            self.list_paragraphs.addItem(item)
            if e.kind in ("slide", "image", "video") and e.path and os.path.exists(e.path):
                self._start_card_thumb(e.path, badge=(e.kind == "video"))
        if 0 <= self.mix_index < self.list_paragraphs.count():
            self.list_paragraphs.setCurrentRow(self.mix_index)
        else:
            self.list_paragraphs.setCurrentRow(-1)

    def _mix_focus_entry(self):
        if getattr(self, "current_source_type", "") != "mix":
            return None
        i = getattr(self, "mix_index", -1)
        entries = getattr(self, "mix_entries", [])
        return entries[i] if 0 <= i < len(entries) else None

    def _mix_focus_kind(self) -> str:
        e = self._mix_focus_entry()
        return e.kind if e is not None else ""

    def _mix_video_selected(self) -> bool:
        return self._mix_focus_kind() == "video"

    def _select_mix_row(self, i: int):
        if hasattr(self, "list_paragraphs"):
            self.list_paragraphs.blockSignals(True)
            self.list_paragraphs.setCurrentRow(i)
            self.list_paragraphs.blockSignals(False)

    def _focus_mix_entry(self, i: int):
        """카드를 고르기만 한다 (송출하지 않는다) - 동영상 카드를 키로 골랐을 때 등"""
        self.mix_index = i
        e = self.mix_entries[i]
        if e.kind == "video":
            self._mix_video_path = e.path
        self._select_mix_row(i)
        self._after_mix_focus(e)

    def _after_mix_focus(self, e):
        if hasattr(self, "video_bar"):
            self.video_bar.setVisible(e.kind == "video")
        self._update_side_panel_mode()
        self._show_mix_notes(e)
        self._sync_notes_popup()
        self._update_video_bar()
        self._update_status()

    def _present_mix_entry(self, i: int, from_click: bool = True):
        """묶음 카드 하나를 송출한다 - 종류에 따라 글자 / 그림 / 동영상"""
        if not (0 <= i < len(self.mix_entries)):
            return
        e = self.mix_entries[i]
        if e.kind == "wait":
            self._select_mix_row(i)
            self.statusBar().showMessage(self.t("msg_mix_waiting"), 4000)
            return
        if e.kind == "video":
            if not os.path.exists(e.path):
                QMessageBox.warning(self, self.t("item_not_found_title"), self.t("item_not_found_msg", e.path))
                return
            self.mix_index = i
            self._mix_video_path = e.path
            self._select_mix_row(i)
            self._video_play_toggle(from_click=from_click)
            self._after_mix_focus(e)
            return
        if e.kind in ("slide", "image") and not os.path.exists(e.path):
            self.statusBar().showMessage(self.t("msg_slide_not_ready"), 2000)
            return
        if getattr(self, "_show_mode_active", False):
            self._stop_slideshow(silent=True, resume_export=False)
        self.mix_index = i
        if e.kind == "text":
            self._mix_show_text(e.title)
        else:
            self._show_image_on_screen(e.path)
            self.current_bg_desc = f"🔗 {os.path.basename(e.path)}"
            self._live_source_type = "folder"     # 다음에 글자를 내보낼 때 배경을 되돌리도록
            self._live_source_path = self.current_source_path
        self._select_mix_row(i)
        self._after_mix_focus(e)

    def _mix_show_text(self, text: str):
        """묶음의 글 카드 송출 - 설정해 둔 배경 위에 글자를 띄운다"""
        live_type = getattr(self, "_live_source_type", "text")
        self._stop_content_video_if_active()
        if not self.presenter.isVisible():
            self.presenter.show()
        if live_type == "folder" or self._bg_needs_restore or self._folder_replaced_bg:
            # 사진·슬라이드가 덮어쓴 배경을 원래 배경으로 되돌린다
            self._restore_configured_background()
        self.presenter.set_text(text)
        self.preview.set_text(text)
        self._live_source_type = "text"
        self._live_source_path = self.current_source_path

    def _show_mix_notes(self, e):
        """슬라이드 노트 / 사진 속 숨은 글을 노트 칸에 (글·동영상 카드는 노트 칸을 쓰지 않는다)"""
        if e.kind == "slide":
            note = e.note or ""
            label = f"📊 {self.t('slide_prefix')} {e.index + 1}"
            name = os.path.basename(e.source)
        elif e.kind == "image":
            note = image_notes.read_note(e.path)
            label = f"🖼 {self.t('image_prefix')}"
            name = os.path.basename(e.path)
        else:
            return
        # 노트 칸 머리는 짧게 (오른쪽 칸이 좁아도 글자 크기 칸이 밀리지 않게) - 파일 이름은 풍선 도움말과 노트 창에
        self.txt_slide_notes.setPlainText(note)
        self.lbl_notes_slide.setText(label)
        self.lbl_notes_slide.setToolTip(name)
        self._notes_shown_index = -1

    def _mix_step(self, forward: bool):
        """다음 / 앞 카드 (아직 준비 중인 PPT 자리는 건너뛴다)"""
        if getattr(self, "_show_mode_active", False):
            self._slide_step(forward)
            return
        i = self.mix_index
        step = 1 if forward else -1
        while True:
            i += step
            if not (0 <= i < len(self.mix_entries)):
                return
            if self.mix_entries[i].kind != "wait":
                break
        if self.mix_entries[i].kind == "video":
            # 동영상은 키로 넘어왔을 때 곧바로 재생하지 않는다 (스페이스/엔터로 재생)
            self._focus_mix_entry(i)
        else:
            self._present_mix_entry(i, from_click=False)

    def _mix_handle_key(self, key) -> bool:
        next_keys = (Qt.Key.Key_Space, Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown,
                     Qt.Key.Key_Return, Qt.Key.Key_Enter)
        prev_keys = (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backspace)
        e = self._mix_focus_entry()
        if e is not None and e.kind == "video" and key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._mix_video_path = e.path
            self._video_play_toggle()
            self._after_mix_focus(e)
            return True
        if key in next_keys:
            self._mix_step(True)
            return True
        if key in prev_keys:
            self._mix_step(False)
            return True
        return False

    # --- 여러 장 고르기 (Ctrl: 하나씩 더하기·빼기, Shift: 범위) ---
    def _mix_set_picked(self, keys):
        self._mix_picked = set(keys)
        lst = self.list_paragraphs
        for r in range(lst.count()):
            it = lst.item(r)
            e = self.mix_entries[r] if r < len(self.mix_entries) else None
            it.setData(USER_ROLE_PICKED, e is not None and e.key in self._mix_picked)
        lst.viewport().update()

    def _mix_pick_click(self, idx: int, mods):
        """Ctrl/Shift 를 누른 채 카드를 눌렀을 때 - 송출하지 않고 고르기만 한다"""
        entries = self.mix_entries
        picked = set(self._mix_picked)
        if not picked and 0 <= self.mix_index < len(entries) and self.mix_index != idx:
            picked.add(entries[self.mix_index].key)     # 지금 송출 중인 카드부터 함께
        if mods & Qt.KeyboardModifier.ShiftModifier:
            anchor = self._mix_anchor if 0 <= self._mix_anchor < len(entries) else self.mix_index
            if not (0 <= anchor < len(entries)):
                anchor = idx
            lo, hi = sorted((anchor, idx))
            rng = {entries[i].key for i in range(lo, hi + 1)}
            picked = (picked | rng) if mods & Qt.KeyboardModifier.ControlModifier else rng
        else:
            key = entries[idx].key
            if key in picked:
                picked.discard(key)
            else:
                picked.add(key)
            self._mix_anchor = idx
        live_key = entries[self.mix_index].key if 0 <= self.mix_index < len(entries) else None
        if picked == {live_key}:
            picked = set()          # 송출 중인 카드 하나만 남으면 고르기를 푼다
        self._mix_set_picked(picked)
        if picked:
            self.statusBar().showMessage(self.t("msg_mix_picked", len(picked)), 5000)

    def _handle_mix_drag_event(self, event) -> bool:
        """묶음 카드: 누르고 끌면 순서 바꾸기(종류가 달라도), 그냥 누르면 송출.
        Ctrl/Shift 로 여러 장을 골라 두면 끌 때 함께 옮겨진다."""
        et = event.type()
        try:
            pos = event.position().toPoint()
        except AttributeError:
            pos = event.pos()
        mod_mask = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier
        if et == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            item = self.list_paragraphs.itemAt(pos)
            if item is None or item.data(USER_ROLE_INDEX) is None:
                return False
            self._mix_drag_from = item.data(USER_ROLE_INDEX)
            self._mix_drag_start = pos
            self._mix_dragging = False
            self._mix_press_mods = event.modifiers() & mod_mask
            return True
        if et == QEvent.Type.MouseMove:
            if self._mix_drag_from is None or not (event.buttons() & Qt.MouseButton.LeftButton):
                return False
            if not self._mix_dragging:
                if (pos - self._mix_drag_start).manhattanLength() < QApplication.startDragDistance():
                    return True
                self._mix_start_group_drag(self._mix_drag_from)
                self._mix_dragging = True
                self.list_paragraphs.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._mix_autoscroll_check(pos)
            self._mix_drag_to(pos)
            return True
        if et == QEvent.Type.MouseButtonRelease:
            if self._mix_drag_from is None:
                return False
            was_dragging, idx = self._mix_dragging, self._mix_drag_from
            mods = self._mix_press_mods
            moved = len(self._mix_drag_group)
            self._mix_drag_from = None
            self._mix_dragging = False
            self._mix_drag_start = None
            self._mix_drag_key = None
            self._mix_drag_group = set()
            self._mix_scroll_step = 0
            try:
                self.list_paragraphs.unsetCursor()
            except RuntimeError:
                pass
            if was_dragging:
                # 순서는 곧바로 묶음 파일에 저장한다 (원본 파일은 바뀌지 않는다)
                try:
                    mix_bundle.save_order(self.current_source_path, self.mix_entries)
                except OSError as e:
                    self.statusBar().showMessage(str(e), 5000)
                self._select_mix_row(self.mix_index)
                if moved > 1:
                    self.statusBar().showMessage(self.t("msg_mix_moved", moved), 4000)
            elif mods and 0 <= idx < len(self.mix_entries):
                self._mix_pick_click(idx, mods)
            else:
                if self._mix_picked:
                    self._mix_set_picked(set())
                self._mix_anchor = idx
                self._present_mix_entry(idx)
            return True
        return False

    def _mix_start_group_drag(self, idx: int):
        """끌기 시작: 고른 카드 위에서 끌면 고른 것 모두, 아니면 그 카드 하나"""
        entries = self.mix_entries
        if not (0 <= idx < len(entries)):
            return
        key = entries[idx].key
        picked = set(self._mix_picked)
        if self._mix_press_mods & Qt.KeyboardModifier.ControlModifier and key not in picked:
            if not picked and 0 <= self.mix_index < len(entries) and self.mix_index != idx:
                picked.add(entries[self.mix_index].key)
            picked.add(key)
        if key in picked and len(picked) > 1:
            group = picked
        else:
            group = {key}
            picked = set()
        self._mix_set_picked(picked)
        self._mix_drag_key = key
        self._mix_drag_group = group

    def _mix_drag_to(self, pos):
        """끌고 있는 카드(들)를 마우스 아래 카드 자리로 옮긴다.
        여러 장이면 떨어져 있던 카드들도 한 덩어리로 모여 그 자리에 들어간다."""
        if self._mix_drag_from is None:
            return
        target = self.list_paragraphs.itemAt(pos)
        if target is None or target.data(USER_ROLE_INDEX) is None:
            return
        entries = self.mix_entries
        to = target.data(USER_ROLE_INDEX)
        if not (0 <= to < len(entries)):
            return
        if not self._mix_drag_group:
            self._mix_start_group_drag(self._mix_drag_from)
        group = self._mix_drag_group
        target_entry = entries[to]
        if target_entry.key in group:
            return
        group_rows = [i for i, e in enumerate(entries) if e.key in group]
        if not group_rows:
            return
        moving = [entries[i] for i in group_rows]
        rest = [e for e in entries if e.key not in group]
        r = rest.index(target_entry)
        # 아래(뒤)로 끌면 대상 카드 뒤에, 위(앞)로 끌면 대상 카드 앞에 놓는다
        insert_at = r + 1 if to > group_rows[0] else r
        new_entries = rest[:insert_at] + moving + rest[insert_at:]
        if [e.key for e in new_entries] == [e.key for e in entries]:
            return
        focus_key = entries[self.mix_index].key if 0 <= self.mix_index < len(entries) else None
        bar = self.list_paragraphs.verticalScrollBar()
        keep_scroll = bar.value()
        # 목록 전체를 다시 만들지 않고 카드만 옮긴다 (그림이 깜빡이지 않게)
        lst = self.list_paragraphs
        lst.blockSignals(True)
        taken = [lst.takeItem(i) for i in reversed(group_rows)]
        taken.reverse()
        for k, item in enumerate(taken):
            lst.insertItem(insert_at + k, item)
        for r2 in range(lst.count()):
            lst.item(r2).setData(USER_ROLE_INDEX, r2)
        lst.blockSignals(False)
        self.mix_entries = new_entries
        # 지금 고른(송출 중인) 카드가 함께 따라가도록
        self.mix_index = next((i for i, e in enumerate(new_entries) if e.key == focus_key), -1)
        self._mix_drag_from = next(i for i, e in enumerate(new_entries) if e.key == self._mix_drag_key)
        self._mix_anchor = self._mix_drag_from
        if len(group) == 1:
            self._select_mix_row(self._mix_drag_from)
        else:
            self._select_mix_row(self.mix_index)
        bar.setValue(keep_scroll)          # 보던 자리 그대로

    def _mix_autoscroll_check(self, pos):
        """끄는 중에 목록 위·아래 가장자리에 가면 저절로 굴린다 (안 보이는 자리로도 옮길 수 있게)"""
        h = self.list_paragraphs.viewport().height()
        edge = 40
        if pos.y() < edge:
            self._mix_scroll_step = -max(8, (edge - pos.y()) // 2)
        elif pos.y() > h - edge:
            self._mix_scroll_step = max(8, (pos.y() - (h - edge)) // 2)
        else:
            self._mix_scroll_step = 0
        if self._mix_scroll_step and not self._mix_scroll_timer.isActive():
            self._mix_scroll_timer.start()

    def _mix_autoscroll_tick(self):
        if not self._mix_dragging or not self._mix_scroll_step:
            self._mix_scroll_timer.stop()
            return
        bar = self.list_paragraphs.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + self._mix_scroll_step)
        if bar.value() == before:
            self._mix_scroll_timer.stop()
            return
        self._mix_drag_to(self.list_paragraphs.viewport().mapFromGlobal(QCursor.pos()))

    def _edit_mix_image_note(self, idx: int = None):
        if idx is None:
            row = self.list_paragraphs.currentRow() if hasattr(self, "list_paragraphs") else -1
            idx = row if 0 <= row < len(self.mix_entries) else self.mix_index
        if not (0 <= idx < len(self.mix_entries)) or self.mix_entries[idx].kind != "image":
            QMessageBox.information(self, self.t("btn_image_note_edit"), self.t("image_note_pick_first"))
            return
        e = self.mix_entries[idx]
        if not image_notes.can_store(e.path):
            QMessageBox.information(self, self.t("btn_image_note_edit"),
                                    self.t("image_note_unsupported", os.path.splitext(e.path)[1].lower() or "?"))
            return
        if self._image_note_dialog_for(e.path) is None:
            return
        if idx == self.mix_index:
            self._show_mix_notes(e)
            self._sync_notes_popup()

    # --- 왼쪽 목록: 겹쳐서 묶기 / 묶음 풀기 ---
    def _on_library_items_merged(self, sources: list, target: str):
        sources = [p for p in sources if p and p != target]
        if not sources or not target:
            return
        library = self._get_registered_text_files()
        # 겹친 대상의 카드들 → 끌어 온 것들의 카드들 순서로 (묶음은 섞어 둔 순서 그대로)
        order = []
        for src in [target] + sources:
            order += [k for k in self._arranged_keys(src) if k not in order]
        try:
            if mix_bundle.is_mix_file(target):
                mix_bundle.add_sources(target, sources)
                mix_path = target
                message = "msg_mix_added"
            else:
                mix_path = mix_bundle.create_mix(self._settings_dir, [target] + sources)
                message = "msg_mix_created"
            data = mix_bundle.load_mix(mix_path)
            data["order"] = order
            mix_bundle.save_mix(mix_path, data)
        except OSError as e:
            QMessageBox.warning(self, self.t("notice"), str(e))
            return
        new_library = []
        for p in library:
            if p == target:
                new_library.append(mix_path)
            elif p in sources:
                continue
            else:
                new_library.append(p)
        if mix_path not in new_library:
            new_library.append(mix_path)
        self._save_registered_text_files(new_library)
        self._refresh_text_files_list(select_path=mix_path)
        self._load_mix(mix_path)
        self.statusBar().showMessage(self.t(message, self.media_source_name), 6000)

    def _arranged_keys(self, path: str) -> list:
        """파일(또는 묶음) 하나의 카드 순서 - 묶음이면 섞어 둔 순서, 파일이면 원래 순서"""
        readers = self._mix_readers()
        if mix_bundle.is_mix_file(path):
            return [e.key for e in mix_bundle.build_entries(mix_bundle.load_mix(path), **readers)]
        return [e.key for e in mix_bundle.source_entries(path, **readers)]

    def _on_library_context_menu(self, pos):
        item = self.list_text_files.itemAt(pos)
        if item is None:
            return
        path = item.data(USER_ROLE_PATH)
        menu = QMenu(self)
        if mix_bundle.is_mix_file(path):
            act = menu.addAction(self.t("mix_menu_ungroup"))
            if menu.exec(self.list_text_files.viewport().mapToGlobal(pos)) is act:
                QTimer.singleShot(0, lambda: self._ungroup_mix(path))
        else:
            hint = menu.addAction(self.t("mix_menu_hint"))
            hint.setEnabled(False)
            menu.exec(self.list_text_files.viewport().mapToGlobal(pos))

    def _ungroup_mix(self, path: str):
        """묶음을 풀어 원래 파일들을 그 자리에 되돌려 놓는다 (묶음 파일은 남겨 둔다)"""
        data = mix_bundle.load_mix(path)
        library = self._get_registered_text_files()
        if path not in library:
            return
        at = library.index(path)
        rest = [p for p in library if p != path]
        back = [p for p in data["sources"] if p not in rest and os.path.exists(p)]
        new_library = rest[:at] + back + rest[at:]
        self._save_registered_text_files(new_library)
        self._refresh_text_files_list(select_path=back[0] if back else "")
        if getattr(self, "current_source_path", "") == path and back:
            first = back[0]
            if os.path.isdir(first):
                self._load_image_folder(first, broadcast=False)
            elif ppt_engine.is_ppt_file(first):
                self._load_pptx(first, broadcast=False, prepare=True)
            elif is_video_file(first):
                self._load_video_item(first)
            else:
                self._load_text_file(first, broadcast=False)
        self.statusBar().showMessage(self.t("msg_mix_ungrouped"), 4000)

    def _load_text_file(self, file_path: str, select_index=0, broadcast=True):
        try:
            self.paragraphs = load_text_file(file_path)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, self.t("file_open_err"), str(e))
            return
        # broadcast=False 면 목록에 구경하러 온 것일 뿐이므로, 다른 파일의 슬라이드쇼나
        # 화면 내용이 실제로 송출 중이어도 건드리지 않는다.
        if broadcast and getattr(self, "_show_mode_active", False):
            self._stop_slideshow(silent=True, resume_export=False)
        self.current_source_type = "text"
        self.current_source_path = file_path
        self.media_slides = []
        self.media_slide_index = -1
        self._update_side_panel_mode()       # 노트 칸 → 텍스트 편집/스타일 칸
        if not self.presenter.isVisible():
            self.presenter.show()
        self.text_file_path = file_path
        try:
            self.lbl_txt_file.setText(os.path.basename(file_path))
        except RuntimeError:
            pass
        self._clear_paragraphs_unsaved()
        self._rebuild_paragraph_list()
        if hasattr(self, "para_tab"):
            self.para_tab.setCurrentIndex(0)
        self.settings.setValue("text/file", file_path)
        self.settings.setValue("text/source_type", "text")

        if not broadcast:
            # 목록만 갱신하고 실제 송출 화면은 그대로 둔다 - 문단을 직접 클릭해야 나간다
            self.paragraph_index = -1
            if hasattr(self, "list_paragraphs"):
                self.list_paragraphs.blockSignals(True)
                self.list_paragraphs.setCurrentRow(-1)
                self.list_paragraphs.blockSignals(False)
            return

        if self.paragraphs:
            idx = max(0, min(select_index, len(self.paragraphs) - 1))
            self._broadcast_paragraph(idx)
        else:
            if getattr(self, "_live_source_type", "text") == "folder":
                # 폴더 슬라이드 잔상 제거 (내보낼 문단이 없는 빈 파일인 경우)
                self._restore_configured_background()
            self.paragraph_index = -1
            self._clear_text()
            self._live_source_type = "text"
            self._live_source_path = file_path

    def _load_image_folder(self, folder_path: str, select_index=0, broadcast=True):
        images = scan_folder_images(folder_path)
        if not images:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, self.t("no_images_title"), self.t("no_images_msg", folder_path))
            return
        # 실제로 이 폴더를 송출하는 경우에만 진행 중인 슬라이드쇼를 끝낸다.
        # 구경만 하는 것(broadcast=False)이라면 다른 파일의 슬라이드쇼를 그대로 둔다.
        if broadcast and getattr(self, "_show_mode_active", False):
            self._stop_slideshow(silent=True, resume_export=False)
        self.current_source_type = "folder"
        self.current_source_path = folder_path
        self.media_source_kind = "folder"
        self.media_source_name = os.path.basename(folder_path)
        self.media_slides = images
        self.media_notes = [None] * len(images)     # 사진 속 숨은 글 (읽으면 채워진다)
        self.media_slide_index = -1
        self._watch_image_folder(folder_path, images)
        self._update_side_panel_mode()
        if not self.presenter.isVisible():
            self.presenter.show()
        self.paragraphs = []
        self.paragraph_index = -1
        self.text_file_path = folder_path
        try:
            self.lbl_txt_file.setText(f"📁 {os.path.basename(folder_path)} ({len(images)}{self.t('items_count_suffix')})")
        except RuntimeError:
            pass
        self.settings.setValue("text/file", folder_path)
        self.settings.setValue("text/source_type", "folder")
        self._rebuild_paragraph_list()
        self._scan_image_notes()
        if hasattr(self, "para_tab"):
            self.para_tab.setCurrentIndex(0)
        if broadcast and images:
            self._present_media_slide(max(0, min(select_index, len(images) - 1)))
        # else: 목록만 갱신됐다 - 화면은 그대로 둔다 (사진을 클릭해야 나간다)


    def _apply_paragraph_card_style(self, text_cards: bool):
        """카드 모양. 텍스트 카드는 위쪽에 ✏/🗑 단추 자리를 비워 글자와 겹치지 않게 한다.
        (스타일시트를 바꾸면 목록 전체를 다시 꾸미므로 모드가 바뀔 때만 적용)"""
        mode = "text" if text_cards else "media"
        if getattr(self, "_paragraph_card_style_mode", None) == mode:
            return
        self._paragraph_card_style_mode = mode
        padding = "30px 6px 6px 6px" if text_cards else "6px"
        self.list_paragraphs.setStyleSheet(
            "QListWidget { background-color: #1a1a1a; border: 1px solid #3e3e42; border-radius: 4px; }"
            f"QListWidget::item {{ background-color: #262626; border: 1px solid #3e3e42; border-radius: 6px; color: #e0e0e0; padding: {padding}; }}"
            "QListWidget::item:hover { background-color: #333333; border: 1px solid #00bcd4; }"
            "QListWidget::item:selected { background-color: #0c3b5e; border: 2px solid #007acc; color: #ffffff; }"
        )

    def _card_buttons_enabled(self) -> bool:
        return getattr(self, "current_source_type", "text") == "text"

    def _card_button_at(self, pos):
        """그 위치에 있는 카드 단추 → (문단 번호, "edit"/"delete"), 없으면 None"""
        if not self._card_buttons_enabled():
            return None
        item = self.list_paragraphs.itemAt(pos)
        if item is None:
            return None
        idx = item.data(USER_ROLE_INDEX)
        if idx is None or idx < 0 or idx >= len(self.paragraphs):
            return None
        edit_rect, delete_rect = ParagraphCardDelegate.card_button_rects(
            self.list_paragraphs.visualItemRect(item))
        if delete_rect.adjusted(-2, -2, 2, 2).contains(pos):
            return idx, "delete"
        if edit_rect.adjusted(-2, -2, 2, 2).contains(pos):
            return idx, "edit"
        return None

    def _set_card_hover(self, hover):
        if hover != self._card_hover:
            self._card_hover = hover
            self.list_paragraphs.viewport().update()

    def _rebuild_paragraph_list(self):
        """텍스트 목록 또는 이미지 폴더 그리드를 갱신"""
        if not hasattr(self, "list_paragraphs"):
            return
        is_text_mode = getattr(self, "current_source_type", "text") == "text"
        self._apply_paragraph_card_style(is_text_mode)

        # Qt 내장 아이콘모드 드래그 재배치(InternalMove)는 카드 크기가 자주 바뀌는 이
        # 그리드에서 놓일 위치가 표시되지 않거나 이동 자체가 먹통이 되는 등 불안정해서,
        # 대신 마우스 이벤트를 직접 받아 카드 순서를 바꾼다 (_handle_paragraph_drag_event 참고).
        self.list_paragraphs.setDragEnabled(False)
        self.list_paragraphs.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.list_paragraphs.setMovement(QListWidget.Movement.Static)
        self.list_paragraphs._reorderable = False
        self._para_drag_enabled = is_text_mode
        if hasattr(self, "btn_save_paragraphs"):
            self.btn_save_paragraphs.setVisible(is_text_mode)
        # 동영상일 때는 글자 크기/열 수 대신 재생 조작 막대를 보여 준다
        is_video_mode = getattr(self, "current_source_type", "text") == "video"
        for name in ("lbl_list_font_size", "spin_list_font_size", "lbl_list_columns", "spin_list_columns"):
            widget = getattr(self, name, None)
            if widget is not None:
                widget.setVisible(not is_video_mode)
        if hasattr(self, "video_bar"):
            self.video_bar.setVisible(is_video_mode or self._mix_video_selected())

        self.list_paragraphs.blockSignals(True)
        self.list_paragraphs.clear()
        self.card_pool.clear()              # 앞 폴더에서 기다리던 썸네일 일은 버린다
        self._card_thumb_serial += 1
        serial = self._card_thumb_serial
        QTimer.singleShot(6000, lambda: self._check_missing_card_thumbs(serial, 1))

        if is_video_mode:
            # 동영상: 카드 하나 (누르면 듀얼 화면에서 재생 / 일시정지)
            path = getattr(self, "current_source_path", "")
            item = QListWidgetItem(self._video_card_title(path))
            item.setData(USER_ROLE_PATH, path)
            item.setData(USER_ROLE_INDEX, 0)
            item.setToolTip(path)
            self.list_paragraphs.addItem(item)
            if path and os.path.exists(path):
                self._start_card_thumb(path, 960, 540, badge=False)   # 카드가 크므로 선명하게
            self.list_paragraphs.setCurrentRow(0 if self._video_is_live(path) else -1)
            self._update_video_bar()
        elif getattr(self, "current_source_type", "text") == "mix":
            self._fill_mix_cards()
        elif not is_text_mode:
            # 이미지 폴더 / PPT 슬라이드 그리드 모드
            is_pptx = getattr(self, "media_source_kind", "folder") == "pptx"
            for i, img_path in enumerate(self.media_slides):
                if is_pptx:
                    title = f"{self.t('slide_prefix')} {i + 1}"
                else:
                    title = self._image_card_title(i, img_path)
                item = QListWidgetItem(title)
                item.setData(USER_ROLE_PATH, img_path)
                item.setData(USER_ROLE_INDEX, i)
                # 그림 위 풍선 도움말은 띄우지 않는다 (송출하며 마우스를 올릴 때 방해된다)
                self.list_paragraphs.addItem(item)
                # 썸네일 비동기 로딩 (PPT는 아직 내보내지 않은 장을 건너뛴다)
                if os.path.exists(img_path):
                    self._start_card_thumb(img_path)

            if 0 <= self.media_slide_index < self.list_paragraphs.count():
                self.list_paragraphs.setCurrentRow(self.media_slide_index)
            else:
                self.list_paragraphs.setCurrentRow(-1)
        else:
            # 텍스트 문단 모드
            for i, para in enumerate(self.paragraphs):
                item = QListWidgetItem(para)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setToolTip(f"{self.t('para_prefix')} {i + 1}")
                item.setData(USER_ROLE_INDEX, i)
                self.list_paragraphs.addItem(item)
            # 맨 끝에 '+' 카드를 두어 클릭 한 번으로 새 텍스트 슬라이드를 만들 수 있게 한다
            add_item = QListWidgetItem(self.t("add_paragraph_card"))
            add_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            add_item.setToolTip(self.t("add_paragraph_card_tip"))
            add_item.setData(USER_ROLE_INDEX, -1)   # -1 = 새로 추가하는 카드 표식
            add_item.setFlags(add_item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
            self.list_paragraphs.addItem(add_item)
            if 0 <= self.paragraph_index < len(self.paragraphs):
                self.list_paragraphs.setCurrentRow(self.paragraph_index)
            else:
                self.list_paragraphs.setCurrentRow(-1)

        self.list_paragraphs.blockSignals(False)
        self._relayout_paragraph_list()
        # 대화상자를 열고 닫는 것처럼 화면 레이아웃이 아직 확정되지 않은 시점에 바로 위
        # 계산이 일어나면 뷰포트 폭을 일시적으로 잘못(작게) 읽어서 카드가 작게 굳어버리는
        # 경우가 있다. 이벤트 루프가 한 바퀴 돈 뒤 한 번 더 계산해서 바로잡는다.
        QTimer.singleShot(0, self._safe_relayout_paragraph_list)

    def _safe_relayout_paragraph_list(self):
        try:
            if hasattr(self, "list_paragraphs"):
                self._relayout_paragraph_list()
        except RuntimeError:
            pass

    @Slot(str, str)
    def _on_slide_thumb_ready(self, file_path: str, thumb_path: str):
        if not thumb_path or not os.path.exists(thumb_path):
            # 아직 저장·동기화 중이라 읽지 못한 사진 - 조금 뒤에 몇 번 더 해 본다
            tries = self._thumb_retries.get(file_path, 0)
            if tries < 5 and file_path in self._listed_card_paths():
                self._thumb_retries[file_path] = tries + 1
                QTimer.singleShot(1500 * (tries + 1), lambda p=file_path: self._retry_thumb(p))
            return
        self._thumb_retries.pop(file_path, None)
        if not hasattr(self, "list_paragraphs"):
            return
        for i in range(self.list_paragraphs.count()):
            item = self.list_paragraphs.item(i)
            if item.data(USER_ROLE_PATH) == file_path:
                item.setData(USER_ROLE_THUMB, thumb_path)
                icon_size = self.list_paragraphs.iconSize()
                self._set_scaled_thumb_icon(item, thumb_path, icon_size.width(), icon_size.height())
                break

    def _set_scaled_thumb_icon(self, item: QListWidgetItem, thumb_path: str, w: int, h: int):
        """캐시된 원본 썸네일을 현재 표시 크기에 맞춰 다시 그려 아이콘으로 설정한다.

        QIcon은 원본 픽셀맵보다 큰 아이콘 크기를 요청해도 저절로 확대해 그리지
        않는다(테두리만 커지고 그림은 그대로인 문제의 원인). 그래서 Ctrl+휠로 카드
        크기가 바뀔 때마다 원본을 직접 QPixmap.scaled()로 다시 그려 넣는다.
        """
        if getattr(self, "current_source_type", "text") == "video":
            self._set_video_card_icon(item, w, h)
            return
        if not thumb_path or w <= 0 or h <= 0:
            return
        pm = QPixmap(thumb_path)
        if pm.isNull():
            return
        scaled = pm.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        item.setIcon(QIcon(scaled))

    def _on_paragraph_list_clicked(self, item: QListWidgetItem):
        if getattr(self, "btn_edit_toggle", None) and self.btn_edit_toggle.isChecked():
            return
        if getattr(self, "current_source_type", "text") == "mix":
            idx = item.data(USER_ROLE_INDEX)
            if idx is not None and 0 <= idx < len(getattr(self, "mix_entries", [])):
                self._present_mix_entry(idx)
            return
        if getattr(self, "current_source_type", "text") == "video":
            # 동영상 카드 = 커다란 재생 단추 (두 번 눌러도 한 번만 처리)
            self._video_play_toggle(from_click=True)
            return
        if getattr(self, "current_source_type", "text") == "folder":
            idx = item.data(USER_ROLE_INDEX)
            if idx is None:
                idx = self.list_paragraphs.row(item)
            if 0 <= idx < len(self.media_slides):
                self._present_media_slide(idx)
            return

        row = item.data(USER_ROLE_INDEX)
        if row is None:
            row = self.list_paragraphs.row(item)
        if row == -1:
            self._add_new_paragraph_card()
            return
        if 0 <= row < len(self.paragraphs):
            self._broadcast_paragraph(row)

    def _on_paragraph_list_double_clicked(self, item: QListWidgetItem):
        """PPT 슬라이드를 더블클릭하면 그 슬라이드가 바로 보이도록 파워포인트를
        새 창으로 열어 직접 수정할 수 있게 한다 (이미지 폴더/텍스트 문단은 해당 없음)."""
        if getattr(self, "current_source_type", "text") != "folder":
            return
        if getattr(self, "media_source_kind", "folder") != "pptx":
            return
        idx = item.data(USER_ROLE_INDEX)
        if idx is None:
            idx = self.list_paragraphs.row(item)
        path = getattr(self, "current_source_path", "")
        if not path or not os.path.exists(path):
            return
        self.statusBar().showMessage(self.t("msg_ppt_opening_for_edit", idx + 1), 4000)
        ppt_engine.open_for_edit(
            path, idx,
            on_error=self.ppt_edit_open_failed.emit,
            on_notice=self.ppt_edit_opened_as_copy.emit,
            on_synced=self.ppt_edit_synced.emit,
        )

    def _on_ppt_edit_open_failed(self, message: str):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(self, self.t("err_ppt_title"), self.t("msg_ppt_edit_open_failed", message))

    def _on_ppt_edit_opened_as_copy(self, original_path: str):
        # 저장하면 원본에 자동으로 반영되므로(별도 확인이 필요한 경고가 아니라
        # 참고 정보일 뿐이므로), 클릭이 더 필요한 팝업 대신 상태 표시줄에만 띄운다.
        self.statusBar().showMessage(self.t("msg_ppt_edit_opened_as_copy"), 6000)

    def _on_ppt_edit_synced(self, original_path: str):
        """편집 중이던 임시 복사본이 저장되어 원본에 자동 반영됐다는 알림 - 지금
        이 파일을 보고 있다면 캐시를 새로 만들어 화면 목록에 곧바로 반영한다."""
        if getattr(self, "current_source_path", "") != original_path:
            return
        if getattr(self, "media_source_kind", "folder") != "pptx":
            return
        if getattr(self, "_show_mode_active", False):
            # 실제 슬라이드쇼가 지금 돌고 있으면 목록을 건드리지 않는다
            # (파일 다시 읽기 자체도 슬라이드쇼가 끝날 때까지 내부에서 미뤄진다)
            self.statusBar().showMessage(self.t("msg_ppt_edit_synced_pending"), 5000)
            return
        keep_index = max(0, getattr(self, "media_slide_index", -1))
        self._load_pptx(original_path, select_index=keep_index, broadcast=False, prepare=True)
        self.statusBar().showMessage(self.t("msg_ppt_edit_synced"), 4000)

    # ------------------------------------------------------------------
    # 이미지 폴더 지켜보기 (지웠다 다시 만들기 / 다시 내보내기 / 동기화)
    # ------------------------------------------------------------------
    @staticmethod
    def _folder_stat_snapshot(images):
        snap = {}
        for p in images:
            try:
                st = os.stat(p)
                snap[p] = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
        return snap

    def _watch_image_folder(self, folder: str, images=None):
        """폴더와 그 위 폴더를 지켜본다 (폴더째 지웠다 다시 만들어도 알 수 있게)"""
        w = self._folder_watcher
        old = w.directories()
        if old:
            w.removePaths(old)
        for p in (folder, os.path.dirname(folder.rstrip("\\/"))):
            if p and os.path.isdir(p):
                w.addPath(p)
        self._watched_folder = folder
        self._folder_snapshot = self._folder_stat_snapshot(images if images is not None else self.media_slides)

    def _on_watched_folder_changed(self, _path=""):
        if self._is_image_folder_mode() and getattr(self, "current_source_path", "") == getattr(self, "_watched_folder", None):
            self._folder_watch_timer.start()

    def _listed_card_paths(self):
        lst = getattr(self, "list_paragraphs", None)
        if lst is None:
            return set()
        return {lst.item(r).data(USER_ROLE_PATH) for r in range(lst.count())}

    def _retry_thumb(self, path: str):
        if path not in self._listed_card_paths() or not os.path.exists(path):
            return
        self._start_card_thumb(path)

    def _start_card_thumb(self, path: str, w: int = None, h: int = None, badge: bool = True):
        if w is None or h is None:
            w, h = SLIDE_THUMB_BASE_SIZE
        task = ThumbnailTask(path, w, h, badge=badge)
        task.signals.finished.connect(self._on_slide_thumb_ready)
        self.card_pool.start(task)

    def _check_missing_card_thumbs(self, serial: int, round_no: int):
        """카드를 채운 뒤 몇 초가 지나도 그림이 안 붙은 카드가 있으면 이유를 남기고 다시 만든다.
        일꾼들이 모두 (읽기가 멈춘 파일 때문에) 붙잡혀 있으면 새 일꾼들로 바꿔서 한다."""
        if serial != self._card_thumb_serial or not hasattr(self, "list_paragraphs"):
            return
        if getattr(self, "current_source_type", "") == "text":
            return
        lst = self.list_paragraphs
        missing = []
        for r in range(lst.count()):
            it = lst.item(r)
            p = it.data(USER_ROLE_PATH)
            kind = it.data(USER_ROLE_KIND)
            if (p and not it.data(USER_ROLE_THUMB) and kind not in ("text", "wait")
                    and os.path.splitext(str(p))[1].lower() in IMAGE_EXTS and os.path.exists(p)):
                missing.append(p)
        if not missing:
            return
        busy = self.card_pool.activeThreadCount()
        print(f"[썸네일] {round_no}번째 확인: {len(missing)}장이 아직 그림 없음 "
              f"(일하는 중 {busy}/{self.card_pool.maxThreadCount()}) 예: {missing[0]}")
        if busy >= self.card_pool.maxThreadCount():
            # 모두 붙잡혀 있다 - 새 일꾼들로 바꾼다 (붙잡힌 일꾼은 끝날 때까지 그대로 둔다)
            self._old_card_pools.append(self.card_pool)
            self.card_pool = QThreadPool()
            self.card_pool.setMaxThreadCount(4)
            print("[썸네일] 일꾼들이 모두 오래 붙잡혀 있어 새 일꾼으로 바꿨습니다")
        else:
            self.card_pool.clear()
        for p in missing:
            self._thumb_retries.pop(p, None)
            self._start_card_thumb(p)
        if round_no < 3:
            QTimer.singleShot(8000, lambda: self._check_missing_card_thumbs(serial, round_no + 1))

    def _reload_image_folder_fresh(self):
        """🔄 사진 다시 읽기: 이 폴더의 썸네일·송출 그림 저장분을 지우고 폴더를 처음부터 다시 읽는다"""
        if not self._is_image_folder_mode():
            return
        folder = getattr(self, "current_source_path", "")
        live = self.media_slide_index
        live_path = self.media_slides[live] if 0 <= live < len(self.media_slides) else None
        removed = forget_thumbnails(self.media_slides, [SLIDE_THUMB_BASE_SIZE])
        images = scan_folder_images(folder)
        print(f"[썸네일] 사진 다시 읽기: {folder} - 저장분 {removed}개 지움, 사진 {len(images)}장")
        if not images:
            self.statusBar().showMessage(self.t("msg_folder_missing"), 8000)
            return
        self.media_slides = images
        self.media_notes = [None] * len(images)
        self.media_slide_index = images.index(live_path) if live_path in images else -1
        self._thumb_retries = {}
        self._watch_image_folder(folder, images)
        try:
            self.lbl_txt_file.setText(f"📁 {os.path.basename(folder)} ({len(images)}{self.t('items_count_suffix')})")
        except RuntimeError:
            pass
        self._rebuild_paragraph_list()
        self._scan_image_notes()
        self.statusBar().showMessage(self.t("msg_folder_reloaded", len(images)), 6000)

    def _refresh_image_folder(self):
        """지켜보던 폴더가 바뀌었을 때: 바뀐 사진만 썸네일·노트를 다시 읽고, 송출 중인 사진이 바뀌었으면 다시 띄운다"""
        folder = getattr(self, "current_source_path", "")
        if not self._is_image_folder_mode() or folder != getattr(self, "_watched_folder", None):
            return
        # 폴더가 지워졌다 다시 생기면 지켜보기 목록에서 빠져 있으므로 다시 넣는다
        for p in (folder, os.path.dirname(folder.rstrip("\\/"))):
            if p and os.path.isdir(p) and p not in self._folder_watcher.directories():
                self._folder_watcher.addPath(p)
        images = scan_folder_images(folder)
        snap = self._folder_stat_snapshot(images)
        if snap == self._folder_snapshot and images == self.media_slides:
            return
        old_snap = self._folder_snapshot
        if not images:
            self._folder_snapshot = snap
            self.statusBar().showMessage(self.t("msg_folder_missing"), 8000)
            return
        live_path = (self.media_slides[self.media_slide_index]
                     if 0 <= self.media_slide_index < len(self.media_slides) else None)
        if images == self.media_slides:
            changed = [i for i, p in enumerate(images) if old_snap.get(p) != snap.get(p)]
            for i in changed:
                self.media_notes[i] = None
                self._thumb_retries.pop(images[i], None)
                self._retry_thumb(images[i])
                self._image_note(i)
                self._refresh_image_card_title(i)
        else:
            changed = list(range(len(images)))
            self.media_slides = images
            self.media_notes = [None] * len(images)
            self.media_slide_index = images.index(live_path) if live_path in images else -1
            try:
                self.lbl_txt_file.setText(f"📁 {os.path.basename(folder)} ({len(images)}{self.t('items_count_suffix')})")
            except RuntimeError:
                pass
            self._rebuild_paragraph_list()
            self._scan_image_notes()
        self._folder_snapshot = snap
        self.statusBar().showMessage(self.t("msg_folder_reloaded", len(images)), 6000)
        # 송출 중인 사진 파일이 새로 바뀌었으면 화면도 새 그림으로 (읽을 수 있을 때만)
        idx = self.media_slide_index
        on_air = (getattr(self, "_live_source_type", "") == "folder"
                  and getattr(self, "_live_source_path", "") == folder
                  and not getattr(self, "_show_mode_active", False))
        if on_air and 0 <= idx < len(images) and idx in changed and image_is_readable(images[idx]):
            self._present_media_slide(idx)

    def _present_media_slide(self, idx: int):
        """이미지 폴더의 사진을 송출 및 미리보기에 표시

        - 배경이 없는(알파 채널이 있는) PNG는 오버레이로 취급하여 현재 재생 중인
          동영상/배경 이미지/색상을 그대로 둔 채 그 위에 겹쳐 그린다.
        - 그 외 일반 사진은 기존과 같이 전체 화면 슬라이드로 배경을 대체한다.
        """
        if not (0 <= idx < len(self.media_slides)):
            return

        if (getattr(self, "_show_mode_active", False)
                and getattr(self, "_show_active_path", "")
                != getattr(self, "current_source_path", "")):
            # 지금 목록에서 클릭한 파일이, 애니메이션이 돌고 있는 파일과 다르다.
            # (다른 파일을 구경만 하다가 그 파일의 슬라이드를 클릭한 경우) 애니메이션
            # 모드를 끄고 - 버튼도 꺼진 상태로 돌아간다 - 이 슬라이드를 정지 화면으로 낸다.
            # 지금 클릭한 파일(this file)의 내보내기가 멈춰 있었다면 이어서 진행한다.
            self._stop_slideshow(silent=True, resume_export=True)

        if getattr(self, "_show_mode_active", False):
            # 애니메이션 모드: 파워포인트 슬라이드쇼가 화면을 담당한다
            previous = getattr(self, "media_slide_index", -1)
            self.media_slide_index = idx
            # 쇼 범위보다 앞으로 가는 경우에만 쇼를 다시 열게 되므로(2초 남짓),
            # 그때만 전환 사이를 덮는다. 그 외의 이동은 빠르기 때문에 덮으면
            # 오히려 화면이 한 번 더 바뀌어 느리게 느껴진다.
            #
            # 덮을 때는 '가려던 슬라이드'가 아니라 '보고 있던 슬라이드'를 띄운다.
            # 목표를 미리 띄우면 애니메이션이 다 끝난 모습이 먼저 보였다가
            # 처음 상태로 되돌아가 버린다.
            if idx + 1 <= getattr(self, "_show_range_start", 1):
                self._cover_show_gap(previous if previous >= 0 else idx)
            self._show_command_at = time.monotonic()
            ppt_engine.show_goto(idx + 1, on_state=self.ppt_show_state.emit,
                                 on_error=self.ppt_show_failed.emit)
            self._show_slide_notes(idx)
            self.list_paragraphs.blockSignals(True)
            self.list_paragraphs.setCurrentRow(idx)
            self.list_paragraphs.blockSignals(False)
            self._live_source_type = "folder"
            self._live_source_path = getattr(self, "current_source_path", "")
            return

        if self._is_pptx_mode():
            # 이 파일로 애니메이션 모드를 켤 수 있으니 파워포인트에 미리 열어 둔다
            # (파일마다 한 번만 요청 - 이미 열려 있으면 엔진이 그냥 넘어간다)
            path = getattr(self, "current_source_path", "")
            if path and path != getattr(self, "_show_prepared_path", ""):
                self._show_prepared_path = path
                ppt_engine.prepare_show_async(path)

        img_path = self.media_slides[idx]
        if not os.path.exists(img_path):
            # PPT 슬라이드가 아직 내보내지는 중 (빈 화면 송출 방지 - 동영상도 그대로 둔다)
            self.statusBar().showMessage(self.t("msg_slide_not_ready"), 2000)
            if self._is_image_folder_mode():
                self._folder_watch_timer.start()     # 폴더가 다시 만들어졌을 수 있다 - 다시 읽어 본다
            return
        if not image_is_readable(img_path):
            # 저장·동기화 중이라 아직 읽을 수 없는 사진 - 까만 화면을 내보내지 않고 지금 화면을 그대로 둔다
            self.statusBar().showMessage(self.t("msg_image_unreadable"), 6000)
            if self._is_image_folder_mode():
                self._folder_watch_timer.start()
            return
        self.media_slide_index = idx
        self._show_image_on_screen(img_path)
        self.current_bg_desc = self._media_slide_desc(idx)
        if self._is_pptx_mode() or self._is_image_folder_mode():
            self._show_slide_notes(idx)

        self.list_paragraphs.blockSignals(True)
        self.list_paragraphs.setCurrentRow(idx)
        self.list_paragraphs.blockSignals(False)

        self._live_source_type = "folder"
        self._live_source_path = getattr(self, "current_source_path", "")
        self._update_status()

    def _show_image_on_screen(self, img_path: str):
        """사진(또는 슬라이드 그림) 한 장을 송출 화면과 미리보기에 띄운다.

        - 배경이 없는(알파 채널이 있는) PNG는 오버레이로 지금 배경 위에 겹쳐 그린다.
        - 그 외 일반 사진은 전체 화면 슬라이드로 배경을 대체한다.
        """
        # 나가고 있던 동영상은 내린다 (이 사진이 새 송출 내용)
        self._stop_content_video_if_active()
        if not self.presenter.isVisible():
            self.presenter.show()

        is_png = img_path.lower().endswith(".png")
        is_overlay = is_png and image_has_transparency(img_path)

        if is_overlay:
            # 오버레이 모드: 이전에 다른 폴더 사진이 배경을 덮어쓴 상태였다면
            # 원래 배경(동영상/이미지/색상)을 먼저 복원한 뒤 그 위에 겹쳐 그린다.
            # 이미 원래 배경이 유지되고 있다면(예: 동영상이 계속 재생 중) 다시
            # 복원하지 않아 동영상이 처음부터 재생되는 일이 없도록 한다.
            if self._folder_replaced_bg:
                self._restore_configured_background()
            self.presenter.set_overlay_image(img_path)
            self.preview.set_overlay_image(img_path)
        else:
            self.presenter.clear_overlay_image()
            self.preview.clear_overlay_image()
            self.presenter.set_image_background(img_path, fit_mode="fit")
            self.preview.set_bg_image(img_path, fit_mode="fit", transparent=False)
            self._folder_replaced_bg = True

        self.presenter.set_text("")
        self.preview.set_text("")

    # ------------------------------------------------------------------
    # 본문 동영상 (라이브러리의 동영상 - 재생 단추를 눌러야 듀얼 화면에 나간다)
    # ------------------------------------------------------------------
    def _load_video_item(self, path: str):
        """라이브러리에서 동영상을 골랐다. 가운데에 카드와 조작 막대만 보여 주고
        재생은 하지 않는다 (카드의 ▶ 단추나 재생 버튼을 눌러야 시작)."""
        self.current_source_type = "video"
        self.current_source_path = path
        self.media_source_kind = "video"
        self.media_source_name = os.path.basename(path)
        self.media_slides = []
        self.media_notes = []
        self.media_slide_index = -1
        self.paragraphs = []
        self.paragraph_index = -1
        # 주의: 동영상 경로를 text_file_path 에 넣으면 편집기의 '적용'이 동영상
        # 파일을 텍스트로 덮어쓴다 - 동영상일 때는 저장할 텍스트 파일이 없다
        self.text_file_path = ""
        self._video_browse_path = path
        self._clear_paragraphs_unsaved()
        try:
            self.lbl_txt_file.setText(f"🎬 {os.path.basename(path)}")
        except RuntimeError:
            pass
        self.settings.setValue("text/file", path)
        self.settings.setValue("text/source_type", "video")
        self._rebuild_paragraph_list()
        if hasattr(self, "para_tab"):
            self.para_tab.setCurrentIndex(0)
        self._update_status()

    def _browsed_video_path(self) -> str:
        if getattr(self, "current_source_type", "text") == "mix":
            return getattr(self, "_mix_video_path", "") if self._mix_video_selected() else ""
        if getattr(self, "current_source_type", "text") == "video":
            return getattr(self, "_video_browse_path", "") or getattr(self, "current_source_path", "") or ""
        return ""

    def _video_is_live(self, path: str) -> bool:
        return (bool(path) and self.presenter.content_active
                and self.presenter.content_path == path)

    def _video_play_toggle(self, from_click: bool = False):
        """재생 단추 / 카드 / Space: 이 동영상이 나가고 있으면 일시정지↔재생, 아니면 재생 시작"""
        if from_click:
            # 더블클릭은 클릭 신호가 두 번 오므로(재생했다가 곧바로 멈춤) 짧은 간격은 무시한다
            now = time.monotonic()
            if now - getattr(self, "_video_click_at", 0.0) < QApplication.doubleClickInterval() / 1000.0:
                return
            self._video_click_at = now
        path = self._browsed_video_path()
        if not path:
            return
        if not os.path.exists(path):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, self.t("item_not_found_title"), self.t("item_not_found_msg", path))
            return
        if self._video_is_live(path):
            self.presenter.toggle_content_video()
        else:
            self._start_content_video(path)
        if from_click:
            # 시작이 오래 걸렸으면(큰 파일 첫 장면 읽기 등) 그 사이 들어온 두 번째
            # 클릭까지 막히도록 끝난 시각으로 다시 잰다
            self._video_click_at = time.monotonic()

    def _start_content_video(self, path: str):
        if getattr(self, "_show_mode_active", False):
            self._stop_slideshow(silent=True, resume_export=False)
        if not self.presenter.isVisible():
            self.presenter.show()
        track, _mode, _sub = self._subtitle_track_for(path)
        # 새 송출 내용이므로 떠 있던 문단 글자와 겹침 사진은 내린다
        self.presenter.clear_overlay_image()
        self.preview.clear_overlay_image()
        self.presenter.set_text("")
        self.preview.set_text("")
        self.paragraph_index = -1
        self.media_slide_index = -1
        if self.music.is_playing():
            self.music.pause()
            self.statusBar().showMessage(self.t("msg_music_paused_for_video"), 4000)
        self.presenter.set_subtitle_size(self.spin_subtitle_size.value())
        self.preview.set_subtitle_size(self.spin_subtitle_size.value())
        self.presenter.set_content_volume(self.sld_video_volume.value())
        self.preview.set_content_video(True)
        if not self.presenter.play_content_video(path, track):
            self.preview.set_content_video(False)
            return
        self._live_source_type = "video"
        self._live_source_path = path
        self.statusBar().showMessage(self.t("msg_video_started", os.path.basename(path)), 3000)
        self._refresh_video_card()
        self._update_video_bar()
        self._update_status()

    def _stop_content_video(self):
        """동영상을 멈추고 듀얼 화면에서 내린다 (배경은 그대로)"""
        if self.presenter.content_active:
            self.presenter.stop_content_video()
        self.preview.set_content_video(False)
        self._refresh_video_card()
        self._update_video_bar()
        self._update_status()

    def _stop_content_video_if_active(self):
        """다른 내용(문단/슬라이드/직접 입력)을 송출하면 나가고 있던 동영상은 내린다"""
        if self.presenter.content_active:
            self._stop_content_video()

    def _on_content_video_state(self, state: str):
        if state == "stopped":
            self.preview.set_content_video(False)
        elif state == "ended":
            self.statusBar().showMessage(self.t("msg_video_ended"), 8000)
        self._refresh_video_card()
        self._update_video_bar()
        self._update_status()

    def _on_content_video_position(self, position: int, duration: int):
        path = self._browsed_video_path()
        if not path or not self._video_is_live(path):
            return
        if duration > 0 and self.sld_video_pos.maximum() != duration:
            self.sld_video_pos.setRange(0, duration)
        if not self._video_seek_dragging:
            self.sld_video_pos.blockSignals(True)
            self.sld_video_pos.setValue(position)
            self.sld_video_pos.blockSignals(False)
            self.lbl_video_time.setText(f"{self._fmt_ms(position)} / {self._fmt_ms(duration)}")

    def _on_content_video_error(self, message: str):
        was_active = self.presenter.content_active
        self._stop_content_video()
        if was_active:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, self.t("msg_video_error_title"), self.t("msg_video_error", message))
        else:
            self.statusBar().showMessage(self.t("msg_video_error", message).replace("\n", " "), 6000)

    def _on_video_seek_moved(self, value: int):
        self.lbl_video_time.setText(
            f"{self._fmt_ms(value)} / {self._fmt_ms(self.presenter.content_duration())}")

    def _on_video_seek_released(self):
        self._video_seek_dragging = False
        path = self._browsed_video_path()
        if self._video_is_live(path):
            self.presenter.seek_content_video(self.sld_video_pos.value())

    def _seek_video_by(self, delta_ms: int):
        path = self._browsed_video_path()
        if not self._video_is_live(path):
            return
        target = self.presenter.content_position() + int(delta_ms)
        duration = self.presenter.content_duration()
        if duration > 0:
            target = min(target, max(0, duration - 200))
        self.presenter.seek_content_video(max(0, target))

    def _handle_video_key(self, key) -> bool:
        """동영상을 보고 있을 때의 단축키: Space/Enter 재생·일시정지, ←/→ 5초 이동"""
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._video_play_toggle()
            return True
        if key == Qt.Key.Key_Right:
            self._seek_video_by(5000)
            return True
        if key == Qt.Key.Key_Left:
            self._seek_video_by(-5000)
            return True
        return False

    def _on_video_volume_changed(self, value: int):
        self.presenter.set_content_volume(value)
        self.lbl_video_volume_value.setText(str(int(value)))
        self.settings.setValue("video/content_volume", int(value))

    def _on_subtitle_size_changed(self, value: int):
        self.presenter.set_subtitle_size(value)
        self.preview.set_subtitle_size(value)
        self.settings.setValue("video/subtitle_size", int(value))

    @staticmethod
    def _fmt_ms(ms: int) -> str:
        if ms is None or ms < 0:
            return "--:--"
        total = int(ms) // 1000
        h, rem = divmod(total, 3600)
        m, sec = divmod(rem, 60)
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"

    def _update_video_bar(self):
        if not hasattr(self, "btn_video_play"):
            return
        path = self._browsed_video_path()
        live = self._video_is_live(path)
        state = self.presenter.content_state if live else "stopped"
        label = {"playing": "video_pause", "paused": "video_resume",
                 "ended": "video_replay"}.get(state, "video_play")
        self.btn_video_play.setText(self.t(label))
        self.btn_video_stop.setEnabled(live)
        self.sld_video_pos.setEnabled(live)
        if live:
            position = self.presenter.content_position()
            duration = self.presenter.content_duration()
            self.sld_video_pos.blockSignals(True)
            self.sld_video_pos.setRange(0, max(0, duration))
            self.sld_video_pos.setValue(position)
            self.sld_video_pos.blockSignals(False)
            self.lbl_video_time.setText(f"{self._fmt_ms(position)} / {self._fmt_ms(duration)}")
        else:
            self.sld_video_pos.blockSignals(True)
            self.sld_video_pos.setRange(0, 0)
            self.sld_video_pos.blockSignals(False)
            self.lbl_video_time.setText("--:-- / --:--")
        status = self._subtitle_status_text(path) if path else ""
        self.lbl_subtitle_state.setText(status)
        self.lbl_subtitle_state.setToolTip(status)

    # --- 동영상 카드 ---
    def _video_card_title(self, path: str) -> str:
        name = os.path.basename(path) if path else ""
        live = self._video_is_live(path)
        hint = self.t("video_card_playing") if (live and self.presenter.content_state == "playing") \
            else self.t("video_card_hint")
        return f"🎬 {name}\n{hint}"

    def _video_card_pixmap(self, thumb: QPixmap, w: int, h: int, state: str) -> QPixmap:
        """장면 위에 큰 재생(▶)/일시정지(⏸) 단추를 그린 카드 그림"""
        canvas = QPixmap(max(1, w), max(1, h))
        canvas.fill(QColor("#111111"))
        p = QPainter(canvas)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if thumb is not None and not thumb.isNull():
            p.drawPixmap(fit_rect(thumb.width(), thumb.height(), w, h), thumb, thumb.rect().toRectF())
        r = max(14.0, min(w, h) * 0.17)
        cx, cy = w / 2.0, h / 2.0
        p.setBrush(QColor(0, 0, 0, 150))
        p.setPen(QPen(QColor(255, 255, 255, 235), max(2.0, r / 9.0)))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 240))
        if state == "playing":
            bar_w, bar_h = r * 0.24, r * 0.9
            p.drawRoundedRect(QRectF(cx - r * 0.38, cy - bar_h / 2, bar_w, bar_h), 2, 2)
            p.drawRoundedRect(QRectF(cx + r * 0.14, cy - bar_h / 2, bar_w, bar_h), 2, 2)
        else:
            tri = QPainterPath()
            tri.moveTo(cx - r * 0.32, cy - r * 0.5)
            tri.lineTo(cx - r * 0.32, cy + r * 0.5)
            tri.lineTo(cx + r * 0.55, cy)
            tri.closeSubpath()
            p.drawPath(tri)
        if state in ("playing", "paused", "ended"):
            # 지금 듀얼 화면에 나가고 있다는 표시
            label = self.t(f"video_state_{state}")
            font = QFont(self.font())
            font.setBold(True)
            font.setPixelSize(max(11, int(h * 0.06)))
            p.setFont(font)
            fm = QFontMetrics(font)
            text = f"● {label}"
            chip = QRectF(8, 8, fm.horizontalAdvance(text) + 16, fm.height() + 6)
            p.setBrush(QColor("#c0392b") if state == "playing" else QColor(60, 60, 60, 220))
            p.drawRoundedRect(chip, 4, 4)
            p.setPen(QColor("#ffffff"))
            p.drawText(chip, Qt.AlignmentFlag.AlignCenter, text)
        p.end()
        return canvas

    def _set_video_card_icon(self, item: QListWidgetItem, w: int, h: int):
        if item is None or w <= 0 or h <= 0:
            return
        thumb_path = item.data(USER_ROLE_THUMB)
        thumb = QPixmap(thumb_path) if thumb_path and os.path.exists(thumb_path) else QPixmap()
        path = item.data(USER_ROLE_PATH) or ""
        state = self.presenter.content_state if self._video_is_live(path) else ""
        pixmap = self._video_card_pixmap(thumb, w, h, state)
        icon = QIcon()
        # 선택된 카드도 파랗게 물들이지 않고 그대로 보이게 한다 (재생 중 표시 색이 흐려지지 않게)
        icon.addPixmap(pixmap, QIcon.Mode.Normal)
        icon.addPixmap(pixmap, QIcon.Mode.Selected)
        item.setIcon(icon)
        item.setText(self._video_card_title(path))

    def _refresh_video_card(self):
        if getattr(self, "current_source_type", "text") != "video" or not hasattr(self, "list_paragraphs"):
            return
        item = self.list_paragraphs.item(0)
        if item is None:
            return
        size = self.list_paragraphs.iconSize()
        self._set_video_card_icon(item, size.width(), size.height())
        path = item.data(USER_ROLE_PATH) or ""
        self.list_paragraphs.blockSignals(True)
        self.list_paragraphs.setCurrentRow(0 if self._video_is_live(path) else -1)
        self.list_paragraphs.blockSignals(False)

    # --- 자막 ---
    def _subtitle_choices(self) -> dict:
        raw = self.settings.value("video/subtitle_choices", "") or ""
        try:
            data = json.loads(raw) if isinstance(raw, str) and raw else {}
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _video_key(path: str) -> str:
        return os.path.normcase(os.path.abspath(path)) if path else ""

    def _subtitle_info(self, video_path: str):
        """(방식, 자막 파일) - 방식: manual(직접 고름) / auto(같은 이름) / off(끔) / none(없음)"""
        choice = self._subtitle_choices().get(self._video_key(video_path))
        if choice == "off":
            return "off", ""
        if choice and os.path.isfile(choice):
            return "manual", choice
        found = subtitles.find_subtitle_for(video_path)
        return ("auto", found) if found else ("none", "")

    def _subtitle_track_for(self, video_path: str):
        mode, sub = self._subtitle_info(video_path)
        if not sub:
            return None, mode, sub
        try:
            mtime = os.path.getmtime(sub)
        except OSError:
            return None, mode, sub
        cached = self._subtitle_cache.get(sub)
        if cached and cached[0] == mtime:
            return cached[1], mode, sub
        track = subtitles.load_subtitle(sub)
        self._subtitle_cache[sub] = (mtime, track)
        return track, mode, sub

    def _subtitle_status_text(self, video_path: str) -> str:
        track, mode, sub = self._subtitle_track_for(video_path)
        name = os.path.basename(sub)
        if mode == "off":
            return self.t("subtitle_status_off")
        if mode == "none":
            return self.t("subtitle_status_none")
        if track is None:
            return self.t("subtitle_status_bad", name)
        return self.t("subtitle_status_manual" if mode == "manual" else "subtitle_status_auto", name)

    def _set_subtitle_choice(self, value):
        """value: None(같은 이름 자막 자동) / "off"(끄기) / 자막 파일 경로"""
        path = self._browsed_video_path()
        if not path:
            return
        choices = self._subtitle_choices()
        key = self._video_key(path)
        if value is None:
            choices.pop(key, None)
        else:
            choices[key] = value
        self.settings.setValue("video/subtitle_choices", json.dumps(choices, ensure_ascii=False))
        if self._video_is_live(path):
            track, _mode, _sub = self._subtitle_track_for(path)
            self.presenter.set_content_subtitles(track)
        self._update_video_bar()

    def _choose_subtitle_file(self):
        path = self._browsed_video_path()
        if not path:
            return
        sub, _ = QFileDialog.getOpenFileName(
            self, self.t("dialog_select_subtitle"), os.path.dirname(path), self.t("filter_subtitle"))
        if not sub:
            return
        track = subtitles.load_subtitle(sub)
        if track is None:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, self.t("msg_video_error_title"),
                                self.t("msg_subtitle_load_failed", sub))
            return
        try:
            self._subtitle_cache[sub] = (os.path.getmtime(sub), track)
        except OSError:
            pass
        self._set_subtitle_choice(sub)

    def _on_list_font_size_changed(self, size: int):
        self._apply_list_font_size(size)
        self.settings.setValue("text/list_font_size", size)
        self._relayout_paragraph_list()

    def _apply_list_font_size(self, size: int):
        if hasattr(self, "list_paragraphs"):
            f = self.list_paragraphs.font()
            f.setPointSize(size)
            self.list_paragraphs.setFont(f)

    def _on_list_columns_changed(self, cols: int):
        self.settings.setValue("text/list_columns", cols)
        self._relayout_paragraph_list()

    def _relayout_paragraph_list(self):
        """문단 목록의 열(단) 수와 폰트 크기에 맞게 각 항목 크기 및 그리드 재계산"""
        if not hasattr(self, "list_paragraphs") or not hasattr(self, "spin_list_columns"):
            return
        cols = max(1, self.spin_list_columns.value())
        viewport_w = self.list_paragraphs.viewport().width()
        if viewport_w <= 0:
            viewport_w = self.list_paragraphs.width()
        if viewport_w <= 50:
            viewport_w = 600

        # 스크롤바(약 20px)와 양쪽 테두리 여백을 확보하여 열 너비 계산
        scroll_w = 20
        gap = 8  # 카드 사이 간격
        avail_w = max(100, viewport_w - scroll_w - 4)
        cell_w = max(60, avail_w // cols)
        card_w = max(50, cell_w - gap)

        if getattr(self, "current_source_type", "text") == "video":
            # 카드 하나를 목록 칸에 맞게 크게 (세로도 넘치지 않도록)
            fm = QFontMetrics(self.list_paragraphs.font())
            title_h = fm.lineSpacing() * 2 + 16
            viewport_h = self.list_paragraphs.viewport().height()
            if viewport_h <= 50:
                viewport_h = 400
            by_height = int((viewport_h - title_h - 2 * gap - 12) * 16 / 9)
            card_w = max(200, min(avail_w - gap, by_height))
            thumb_h = max(60, int((card_w - 8) * 9 / 16))
            card_h = thumb_h + title_h
            icon_w = max(1, card_w - 8)
            self.list_paragraphs.setIconSize(QSize(icon_w, thumb_h))
            self.list_paragraphs.setGridSize(QSize(max(card_w + gap, avail_w), card_h + gap))
            for i in range(self.list_paragraphs.count()):
                it = self.list_paragraphs.item(i)
                it.setSizeHint(QSize(card_w, card_h))
                it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
                self._set_video_card_icon(it, icon_w, thumb_h)
            return

        if getattr(self, "current_source_type", "text") in ("folder", "mix"):
            # 16:9 그림 칸 + 아래 한 줄 이름 칸 (글자 크기에 맞춰 높이를 잡아 겹치지 않게)
            card_h, icon_w, thumb_h = ParagraphCardDelegate.media_card_size(
                card_w, self.list_paragraphs.font())
            cell_h = card_h + gap
            self.list_paragraphs.setIconSize(QSize(icon_w, thumb_h))
            self.list_paragraphs.setGridSize(QSize(cell_w, cell_h))
            for i in range(self.list_paragraphs.count()):
                it = self.list_paragraphs.item(i)
                it.setSizeHint(QSize(card_w, card_h))
                it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
                # 이미 로드된 썸네일은 원본에서 새 크기로 다시 그려 넣는다
                # (QIcon은 원본보다 크게는 자동으로 확대해 그리지 않는다)
                thumb_path = it.data(USER_ROLE_THUMB)
                if thumb_path:
                    self._set_scaled_thumb_icon(it, thumb_path, icon_w, thumb_h)
            return

        font = self.list_paragraphs.font()
        fm = QFontMetrics(font)
        # 최대 6줄까지 텍스트가 잘리지 않고 표시되도록 높이 계산 (+ 위쪽 ✏/🗑 단추 자리)
        card_h = max(115, int(fm.lineSpacing() * 6.5) + 16) + 24
        cell_h = card_h + gap

        self.list_paragraphs.setIconSize(QSize(0, 0))
        self.list_paragraphs.setGridSize(QSize(cell_w, cell_h))

        for i in range(self.list_paragraphs.count()):
            it = self.list_paragraphs.item(i)
            it.setSizeHint(QSize(card_w, card_h))
            it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def _on_para_tab_changed(self, index: int):
        """탭 변경 시 직접 입력 탭이면 자동으로 입력창에 포커스를 맞춤"""
        if index == 1 and hasattr(self, "txt_direct_input"):
            self.txt_direct_input.setFocus()

    def _open_direct_text_tab(self):
        """직접 입력 송출 탭으로 전환하고 포커스 설정"""
        if hasattr(self, "para_tab"):
            self.para_tab.setCurrentIndex(1)
        if hasattr(self, "txt_direct_input"):
            self.txt_direct_input.setFocus()

    def _on_direct_font_size_changed(self, size: int):
        if hasattr(self, "txt_direct_input"):
            f = self.txt_direct_input.font()
            f.setPointSize(size)
            self.txt_direct_input.setFont(f)

    def _on_direct_realtime_toggled(self, checked: bool):
        if checked:
            text = self.txt_direct_input.toPlainText()
            if text.strip():
                self._broadcast_direct_text(text)

    def _on_direct_text_changed(self):
        if hasattr(self, "chk_direct_realtime") and self.chk_direct_realtime.isChecked():
            text = self.txt_direct_input.toPlainText()
            if text.strip():
                self._broadcast_direct_text(text)
            else:
                self._clear_text()

    def _clear_direct_input(self):
        if hasattr(self, "txt_direct_input"):
            self.txt_direct_input.clear()
        if (getattr(self, "current_source_type", "text") == "direct_text"
                or getattr(self, "_live_source_type", "") == "direct_text"):
            self._clear_text()

    def _broadcast_direct_text(self, text: str = None):
        if text is None:
            text = self.txt_direct_input.toPlainText().strip()
        if not text:
            self._clear_text()
            self.statusBar().showMessage(self.t("msg_no_text"), 2000)
            return

        # "지금 화면에 나가고 있던 것"을 기준으로 판단한다 (라이브러리에서 다른 파일을
        # 구경만 하고 있었을 수도 있으므로 current_source_type 만으로는 알 수 없다)
        live_type = getattr(self, "_live_source_type", "text")
        if getattr(self, "_show_mode_active", False):
            # 파워포인트 애니메이션 슬라이드쇼가 화면을 차지하고 있었다면 끝내고 텍스트를 낸다
            self._stop_slideshow(silent=True, resume_export=False)
        self._stop_content_video_if_active()
        # 동영상 화면·묶음을 보던 중이면 그 화면(카드·조작 막대)은 그대로 쓸 수 있게 둔다
        if self.current_source_type == "mix":
            self.mix_index = -1            # 직접 쓴 글은 묶음 카드가 아니다
            self._select_mix_row(-1)
        elif self.current_source_type != "video":
            self.current_source_type = "direct_text"
        self.media_slide_index = -1
        if not self.presenter.isVisible():
            self.presenter.show()
        # 이미지 폴더 모드만 배경을 슬라이드로 덮어쓰므로 그 경우에만 원래 배경을 복원한다.
        # (실시간 송출 중 매 입력마다 복원하면 동영상 배경이 키 입력 때마다 처음부터 재생된다)
        if live_type == "folder" or self._bg_needs_restore:
            self._restore_configured_background()

        try:
            self.presenter.set_text(text)
        except RuntimeError:
            pass
        try:
            self.preview.set_text(text)
        except RuntimeError:
            pass

        if hasattr(self, "list_paragraphs"):
            self.list_paragraphs.blockSignals(True)
            self.list_paragraphs.setCurrentRow(-1)
            self.list_paragraphs.blockSignals(False)

        self.statusBar().showMessage(self.t("msg_direct_broadcast"), 3000)
        self._live_source_type = "direct_text"
        self._live_source_path = ""
        self._update_status()

    def _convert_direct_text_to_paragraphs(self):
        raw_text = self.txt_direct_input.toPlainText().strip()
        if not raw_text:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, self.t("notice"), self.t("msg_enter_text_first"))
            return

        self.paragraphs = split_paragraphs(raw_text)
        if not self.paragraphs:
            self.paragraphs = [raw_text]

        self.current_source_type = "text"
        self.media_slide_index = -1
        self.current_source_path = ""
        self.text_file_path = ""
        try:
            self.lbl_txt_file.setText(self.t("direct_text_title"))
        except RuntimeError:
            pass

        self._rebuild_paragraph_list()
        if hasattr(self, "para_tab"):
            self.para_tab.setCurrentIndex(0)

        self._broadcast_paragraph(0)
        self.statusBar().showMessage(self.t("msg_converted_paras", len(self.paragraphs)), 3000)

    def _save_direct_text_to_file(self):
        raw_text = self.txt_direct_input.toPlainText()
        if not raw_text.strip():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, self.t("notice"), self.t("msg_empty_text"))
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, self.t("dialog_save_direct"),
            self.settings.value("last_dir", str(Path.home())),
            self.t("filter_text")
        )
        if not file_path:
            return

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(raw_text)
            self.settings.setValue("last_dir", os.path.dirname(file_path))
            self._register_text_file(file_path)
            self._load_text_file(file_path, select_index=0, broadcast=True)
            self.statusBar().showMessage(self.t("msg_saved_file", os.path.basename(file_path)), 3000)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, self.t("err_save_title"), self.t("err_save_msg", e))

    def _on_escape_action(self):
        """ESC: 위에 얹힌 것부터 한 단계씩 내린다.

        1단계 - 텍스트가 떠 있으면 텍스트만 내린다 (배경 동영상은 계속 재생)
        2단계 - 한 번 더 누르면 배경까지 모두 내리고 투명 화면으로 돌아간다
        """
        try:
            text_showing = self.presenter.has_text()
        except (RuntimeError, AttributeError):
            text_showing = False

        if text_showing:
            self._clear_text()
            self.statusBar().showMessage(self.t("msg_text_cleared_stage"), 4000)
            return

        self._reset_to_transparent()
        self.statusBar().showMessage(self.t("msg_all_cleared"), 3000)

    def _reset_to_transparent(self):
        """모든 송출을 끄고 시작 직후와 같은 상태(투명 배경 + 빈 텍스트)로 만든다.

        저장된 배경 설정(bg/type, bg/value)은 지우지 않는다. 다음에 문단이나
        직접 입력을 송출하면 그 배경이 다시 적용된다.
        """
        # 1. 파워포인트 슬라이드쇼(애니메이션 모드)가 떠 있으면 종료
        if getattr(self, "_show_mode_active", False):
            self._stop_slideshow(silent=True)

        # 2. 재생 중인 동영상 정지 (본문 동영상 + 배경 동영상)
        self._stop_content_video_if_active()
        try:
            self.presenter.stop_playlist()
        except Exception as e:
            print(f"동영상 정지 실패: {e}")
        if hasattr(self, "lbl_playlist_state"):
            self.lbl_playlist_state.setText(self.t("playlist_stopped"))
            self.lbl_playlist_state.setStyleSheet("")
        # 체크박스로 재생을 제어하므로, 정지 시 체크 상태도 함께 해제해 둔다
        # (그대로 두면 다음에 아무 체크박스나 건드릴 때 조용히 재생이 재개된 것처럼 보일 수 있음)
        if hasattr(self, "list_videos"):
            self.list_videos.blockSignals(True)
            try:
                for i in range(self.list_videos.count()):
                    item = self.list_videos.item(i)
                    if item is not None:
                        item.setCheckState(Qt.CheckState.Unchecked)
            finally:
                self.list_videos.blockSignals(False)
            self.settings.setValue("video/checked", [])
            self._update_playlist_state()

        # 3. 슬라이드/오버레이 해제
        self.presenter.clear_overlay_image()
        self.preview.clear_overlay_image()
        self.media_slide_index = -1
        self._folder_replaced_bg = False

        # 4. 배경을 투명으로 (저장된 설정은 보존 → 다음 송출 때 복원)
        self.presenter.set_transparent(True)
        self.preview.set_transparent(True)
        self.current_bg_desc = self.t("transparent")
        self._bg_needs_restore = True

        # 5. 텍스트 내리기 (목록 선택도 함께 해제된다)
        self._clear_text()

    def _on_preview_clicked(self):
        """송출 미리보기 화면 클릭 시: 슬라이드 모드이면 다음으로 진행"""
        if getattr(self, "current_source_type", "text") == "folder":
            self._slide_step(True)
        elif getattr(self, "current_source_type", "text") == "mix":
            self._mix_step(True)

    def _slide_step(self, forward: bool):
        """슬라이드 넘김. 애니메이션 모드에서는 애니메이션 한 단계씩 진행한다."""
        if getattr(self, "_show_mode_active", False):
            # 조작 직후에는 상태 조회를 쉬게 한다 (같은 COM 스레드를 쓴다)
            self._show_command_at = time.monotonic()
            if forward:
                ppt_engine.show_next(on_state=self.ppt_show_state.emit,
                                     on_error=self.ppt_show_failed.emit)
            else:
                ppt_engine.show_previous(on_state=self.ppt_show_state.emit,
                                         on_error=self.ppt_show_failed.emit)
            return
        idx = getattr(self, "media_slide_index", -1) + (1 if forward else -1)
        if 0 <= idx < len(self.media_slides):
            self._present_media_slide(idx)

    def eventFilter(self, obj, event):
        try:
            if hasattr(self, "list_paragraphs") and (obj is self.list_paragraphs or obj is self.list_paragraphs.viewport()):
                if event.type() == QEvent.Type.Resize:
                    self._relayout_paragraph_list()
        except (RuntimeError, Exception):
            pass

        if (event.type() == QEvent.Type.ToolTip and hasattr(self, "list_paragraphs")
                and obj is self.list_paragraphs.viewport()):
            hit = self._card_button_at(event.pos())
            if hit is not None:
                from PySide6.QtWidgets import QToolTip
                QToolTip.showText(event.globalPos(),
                                  self.t("card_edit_tip" if hit[1] == "edit" else "card_delete_tip"),
                                  self.list_paragraphs.viewport())
                return True
        if (event.type() == QEvent.Type.Leave and hasattr(self, "list_paragraphs")
                and obj is self.list_paragraphs.viewport()):
            self._set_card_hover(None)

        if (hasattr(self, "list_paragraphs") and obj is self.list_paragraphs.viewport()
                and getattr(self, "current_source_type", "text") == "mix"
                and event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease)):
            if QApplication.activeModalWidget() is not None:
                self._mix_drag_from = None
                self._mix_dragging = False
            elif self._handle_mix_drag_event(event):
                return True

        if (hasattr(self, "list_paragraphs") and obj is self.list_paragraphs.viewport()
                and getattr(self, "current_source_type", "text") == "text"
                and getattr(self, "_para_drag_enabled", False)
                and event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseMove, QEvent.Type.MouseButtonRelease)):
            if QApplication.activeModalWidget() is not None:
                # 추가/편집 대화상자 같은 모달 창이 떠 있는 동안에는 뒤에 깔린 카드 목록에
                # 대한 마우스 이벤트를 절대 처리하지 않는다 (QApplication 전역 이벤트 필터는
                # 모달 창이 열려 있어도 뒤 창의 이벤트를 계속 받아오므로, 대화상자가 열리고
                # 닫히는 순간의 잔여/합성 이벤트가 엉뚱한 카드를 클릭/삭제/이동시키는 사고를
                # 막기 위한 안전장치)
                self._para_drag_from_idx = None
                self._para_dragging = False
                self._para_drag_start_pos = None
            elif self._handle_paragraph_drag_event(event):
                return True

        if event.type() == QEvent.Type.Wheel and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            # Ctrl+휠: 왼쪽 파일 목록은 글자 크기, 가운데 썸네일 그리드는 썸네일 크기 조정
            delta = event.angleDelta().y()
            if delta:
                step = 1 if delta > 0 else -1
                if hasattr(self, "list_text_files") and (obj is self.list_text_files or obj is self.list_text_files.viewport()):
                    self._adjust_library_font_size(step)
                    return True
                if (hasattr(self, "list_paragraphs")
                        and (obj is self.list_paragraphs or obj is self.list_paragraphs.viewport())):
                    if getattr(self, "current_source_type", "text") == "video":
                        return True   # 동영상 카드는 목록 칸 크기에 자동으로 맞춘다
                    if (getattr(self, "current_source_type", "text") in ("folder", "mix")
                            and hasattr(self, "spin_list_columns")):
                        # 휠 위로 = 썸네일을 키움(열 수를 줄임), 휠 아래로 = 썸네일을 줄임(열 수를 늘림)
                        new_cols = self.spin_list_columns.value() - step
                        new_cols = max(self.spin_list_columns.minimum(),
                                       min(self.spin_list_columns.maximum(), new_cols))
                        self.spin_list_columns.setValue(new_cols)
                        return True
                    elif hasattr(self, "spin_list_font_size"):
                        # 텍스트 문단 카드는 썸네일이 없으므로 글자 크기를 키우는 것으로 대신한다
                        new_size = self.spin_list_font_size.value() + step
                        new_size = max(self.spin_list_font_size.minimum(),
                                       min(self.spin_list_font_size.maximum(), new_size))
                        self.spin_list_font_size.setValue(new_size)
                        return True

        if event.type() == QEvent.Type.KeyPress:
            # 메인 창/송출 창 밖(대화상자, 메시지 박스, 편집기 창 등)의 키 입력은 가로채지 않음
            # (가로채면 Enter가 OK 버튼 대신 다음 문단을 송출하고 Esc로 창을 닫을 수 없게 된다)
            if QApplication.activeModalWidget() is not None:
                return super().eventFilter(obj, event)
            top = obj.window() if isinstance(obj, QWidget) else None
            if top is not self and top is not getattr(self, "presenter", None):
                return super().eventFilter(obj, event)

            key = event.key()

            # 텍스트 입력/편집 위젯(또는 해당 위젯의 viewport)에서 입력하는 경우 키 이벤트를 가로채지 않음
            from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox
            curr = obj
            is_input_widget = False
            while curr is not None:
                if isinstance(curr, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox)):
                    is_input_widget = True
                    break
                curr = getattr(curr, "parent", lambda: None)()

            if is_input_widget:
                # 직접 입력 에디터에서 Ctrl+Enter를 누르면 즉시 송출
                if hasattr(self, "txt_direct_input") and (obj is self.txt_direct_input or obj is self.txt_direct_input.viewport()):
                    if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                        self._broadcast_direct_text()
                        return True
                # 그 외 모든 키(백스페이스, 엔터, 화살표, 스페이스 등)는 에디터 고유 동작으로 정상 처리되도록 통과
                return False


            key = event.key()
            if key == Qt.Key.Key_Delete:
                if hasattr(self, "list_colors") and (obj is self.list_colors or obj is self.list_colors.viewport()):
                    self._delete_selected_color()
                    return True
                if hasattr(self, "list_images") and (obj is self.list_images or obj is self.list_images.viewport()):
                    self._delete_selected_image()
                    return True
                if hasattr(self, "list_videos") and (obj is self.list_videos or obj is self.list_videos.viewport()):
                    self._delete_selected_video()
                    return True
                if hasattr(self, "list_text_files") and (obj is self.list_text_files or obj is self.list_text_files.viewport()):
                    self._remove_text_file_from_library()
                    return True
                if (hasattr(self, "list_paragraphs")
                        and (obj is self.list_paragraphs or obj is self.list_paragraphs.viewport())
                        and getattr(self, "current_source_type", "text") == "text"):
                    row = self.list_paragraphs.currentRow()
                    if row >= 0:
                        item = self.list_paragraphs.item(row)
                        idx = item.data(USER_ROLE_INDEX) if item else None
                        if idx is not None and idx != -1:
                            QTimer.singleShot(0, lambda i=idx: self._confirm_delete_paragraph_card(i))
                    return True

            if key == Qt.Key.Key_Escape:
                self._on_escape_action()
                return True

            next_keys = (Qt.Key.Key_Space, Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Return, Qt.Key.Key_Enter)
            prev_keys = (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backspace)

            # 직접 입력 송출 탭(인덱스 1)이 활성화되어 있을 때는 문단 탐색 키를 완전히 비활성화
            if hasattr(self, "para_tab") and self.para_tab.currentIndex() == 1:
                return super().eventFilter(obj, event)

            if getattr(self, "current_source_type", "text") == "folder":
                if key in next_keys:
                    self._slide_step(True)
                    return True
                elif key in prev_keys:
                    self._slide_step(False)
                    return True
            elif getattr(self, "current_source_type", "text") == "mix":
                if self._mix_handle_key(key):
                    return True
            elif getattr(self, "current_source_type", "text") == "video":
                if self._handle_video_key(key):
                    return True
            elif getattr(self, "current_source_type", "text") == "text":
                if key in next_keys:
                    if self.paragraph_index + 1 < len(self.paragraphs):
                        self._broadcast_paragraph(self.paragraph_index + 1)
                    return True
                elif key in prev_keys:
                    if self.paragraph_index - 1 >= 0:
                        self._broadcast_paragraph(self.paragraph_index - 1)
                    return True

        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self._on_escape_action()
            return

        # 텍스트 입력 위젯에 포커스가 있거나 직접 입력 탭(1)인 경우 문단 넘김 방지
        from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox
        fw = QApplication.focusWidget()
        curr = fw
        while curr is not None:
            if isinstance(curr, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox)):
                super().keyPressEvent(event)
                return
            curr = getattr(curr, "parent", lambda: None)()

        if hasattr(self, "para_tab") and self.para_tab.currentIndex() == 1:
            super().keyPressEvent(event)
            return

        next_keys = (Qt.Key.Key_Space, Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_PageDown, Qt.Key.Key_Return, Qt.Key.Key_Enter)
        prev_keys = (Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_PageUp, Qt.Key.Key_Backspace)
        if getattr(self, "current_source_type", "text") == "folder":
            if key in next_keys:
                self._slide_step(True)
                return
            elif key in prev_keys:
                self._slide_step(False)
                return
        elif getattr(self, "current_source_type", "text") == "mix":
            if self._mix_handle_key(key):
                return
        elif getattr(self, "current_source_type", "text") == "video":
            if self._handle_video_key(key):
                return
        elif getattr(self, "current_source_type", "text") == "text":
            if key in next_keys:
                if self.paragraph_index + 1 < len(self.paragraphs):
                    self._broadcast_paragraph(self.paragraph_index + 1)
                return
            elif key in prev_keys:
                if self.paragraph_index - 1 >= 0:
                    self._broadcast_paragraph(self.paragraph_index - 1)
                return
        super().keyPressEvent(event)

    def _rebuild_thumb_grid(self, force=False):
        """호환용 메서드"""
        pass

    def _on_thumb_item_clicked(self, item: QListWidgetItem):
        """썸네일 클릭 → 해당 문단 송출 (편집 모드 중이면 무시)"""
        if getattr(self, "btn_edit_toggle", None) and self.btn_edit_toggle.isChecked():
            return
        idx = item.data(Qt.ItemDataRole.UserRole)
        if idx is not None and 0 <= idx < len(self.paragraphs):
            self._broadcast_paragraph(idx)

    def _render_thumb_pixmap(self, text: str, width: int, height: int, idx: int = -1) -> QPixmap:
        """흰색 배경에 검은 글씨로 한 문단을 깔끔하게 렌더링한 카드 Pixmap"""
        pix = QPixmap(width, height)
        pix.fill(QColor("#FFFFFF"))
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # 상단 문단 헤더 바 (회색빛 배경 + 볼드 타이틀)
        header_h = 24
        p.fillRect(QRect(0, 0, width, header_h), QColor("#EFEFEF"))
        p.setPen(QColor("#D5D5D5"))
        p.drawLine(0, header_h - 1, width, header_h - 1)

        if idx >= 0:
            badge_text = f"{self.t('para_prefix')} {idx + 1}"
            p.setFont(QFont("Malgun Gothic", 9, QFont.Weight.Bold))
            p.setPen(QColor("#222222"))
            p.drawText(QRect(8, 0, width - 16, header_h), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), badge_text)

        # 본문 텍스트 (흰색 배경에 선명한 검은 글씨)
        if text:
            p.setFont(QFont("Malgun Gothic", 10))
            p.setPen(QColor("#1A1A1A"))
            text_rect = QRect(8, header_h + 4, width - 16, height - header_h - 8)
            p.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap),
                text
            )

        # 전체 카드 외곽선
        p.setPen(QColor("#CCCCCC"))
        p.drawRect(0, 0, width - 1, height - 1)

        p.end()
        return pix

    def _thumb_size(self) -> int:
        return self.spin_thumb_size.value() if hasattr(self, "spin_thumb_size") else 200

    def _on_thumb_size_changed(self, size: int):
        """슬라이드 썸네일 크기 변경 → 그리드 재배치"""
        self.settings.setValue("text/thumb_size", size)

    def _highlight_thumb(self, active_idx: int):
        if not hasattr(self, "list_thumbs"):
            return
        self.list_thumbs.blockSignals(True)
        if 0 <= active_idx < self.list_thumbs.count():
            self.list_thumbs.setCurrentRow(active_idx)
        else:
            self.list_thumbs.setCurrentRow(-1)
        self.list_thumbs.blockSignals(False)

    def _broadcast_paragraph(self, idx: int):
        if not (0 <= idx < len(self.paragraphs)):
            return
        # "지금 화면에 나가고 있던 것"을 기준으로 정리한다 (목록에서 다른 파일을
        # 구경만 했을 수도 있으므로 current_source_type 만으로는 알 수 없다)
        live_type = getattr(self, "_live_source_type", "text")
        if getattr(self, "_show_mode_active", False):
            # 파워포인트 애니메이션 슬라이드쇼가 화면을 차지하고 있었다면 끝내고 텍스트를 낸다
            self._stop_slideshow(silent=True, resume_export=False)
        self._stop_content_video_if_active()
        if self.media_slide_index >= 0 or self.current_source_type != "text":
            self.current_source_type = "text"
            self.media_slide_index = -1
            if not self.presenter.isVisible():
                self.presenter.show()
        if live_type == "folder" or self._bg_needs_restore:
            # 폴더 슬라이드 잔상 제거, 또는 시작 후 첫 송출 시 저장된 배경 적용
            self._restore_configured_background()

        self.paragraph_index = idx
        text = self.paragraphs[idx]
        try:
            self.presenter.set_text(text)
        except RuntimeError:
            pass
        try:
            self.preview.set_text(text)
        except RuntimeError:
            pass

        # 목록 선택 동기화
        if hasattr(self, "list_paragraphs"):
            self.list_paragraphs.blockSignals(True)
            self.list_paragraphs.setCurrentRow(idx)
            self.list_paragraphs.blockSignals(False)

        # 썸네일 선택 강조 동기화
        self._highlight_thumb(idx)

        # 편집 모드가 켜져있고 '현재 문단' 편집 중이면 에디터 텍스트도 동기화
        if getattr(self, "btn_edit_toggle", None) and self.btn_edit_toggle.isChecked():
            if getattr(self, "rad_edit_current", None) and self.rad_edit_current.isChecked():
                self.txt_editor.setPlainText(text)

        self.settings.setValue("text/paragraph", idx)
        self._live_source_type = "text"
        self._live_source_path = getattr(self, "current_source_path", "")
        self._update_status()

    def _add_new_paragraph_card(self):
        """가운데 문단 미리보기 끝의 '+' 카드 - 새 텍스트 슬라이드(빈 문단)를 만들고
        바로 입력할 수 있도록 편집창을 연다. 취소하면 방금 추가한 빈 문단을 다시 뺀다."""
        if getattr(self, "current_source_type", "text") != "text":
            return
        self.paragraphs.append("")
        new_index = len(self.paragraphs) - 1
        self._rebuild_paragraph_list()

        dialog = TextEditDialog(
            self, current_para="", all_text=self._join_paragraphs_text(),
            active_index=new_index, lang=self.current_lang,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            res = dialog.get_result()
            if res["mode"] == "all":
                self.paragraphs = self._split_paragraphs_text(res["text"])
                if self.paragraph_index >= len(self.paragraphs):
                    self.paragraph_index = -1
            else:
                self.paragraphs[new_index] = res["text"]
            # 만든 슬라이드를 곧바로 송출하지 않는다 - 화면에 내보내려면 카드를 눌러야 한다.
            # 파일에도 바로 반영하지 않고 '저장' 버튼을 눌러야 반영된다.
            self._mark_paragraphs_unsaved()
            self._rebuild_paragraph_list()
            self.statusBar().showMessage(self.t("msg_paragraph_edited_not_shown"), 5000)
        else:
            # 취소 - 방금 추가한 빈 문단을 다시 뺀다
            if 0 <= new_index < len(self.paragraphs) and self.paragraphs[new_index] == "":
                del self.paragraphs[new_index]
            self._rebuild_paragraph_list()

    def _edit_paragraph_card(self, idx: int):
        """카드의 ✏ 단추 - 그 슬라이드를 편집한다.

        편집해도 화면에는 아무것도 내보내지 않는다 (지금 화면에 나가 있는 것도 그대로).
        고친 슬라이드를 화면에 내보내려면 그 카드를 눌러야 한다.
        """
        if not self._card_buttons_enabled() or not (0 <= idx < len(self.paragraphs)):
            return
        dialog = TextEditDialog(
            self, current_para=self.paragraphs[idx], all_text=self._join_paragraphs_text(),
            active_index=idx, lang=self.current_lang,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        res = dialog.get_result()
        if res["mode"] == "all":
            self.paragraphs = self._split_paragraphs_text(res["text"]) or [""]
            if self.paragraph_index >= len(self.paragraphs):
                self.paragraph_index = -1
        else:
            if res["text"] == self.paragraphs[idx]:
                return                       # 바뀐 것이 없다
            self.paragraphs[idx] = res["text"]
        self._mark_paragraphs_unsaved()
        self._rebuild_paragraph_list()
        self.statusBar().showMessage(self.t("msg_paragraph_edited_not_shown"), 5000)

    def _confirm_delete_paragraph_card(self, idx: int) -> bool:
        """카드의 🗑 단추 / 우클릭 삭제 / Delete 키 - 정말 지울지 한 번 묻고 지운다"""
        if not self._card_buttons_enabled() or not (0 <= idx < len(self.paragraphs)):
            return False
        from PySide6.QtWidgets import QMessageBox
        first_line = next((line.strip() for line in self.paragraphs[idx].splitlines() if line.strip()), "")
        if len(first_line) > 40:
            first_line = first_line[:40] + "…"
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(self.t("confirm_delete_paragraph_title"))
        box.setText(self.t("confirm_delete_paragraph_msg", idx + 1, first_line or self.t("empty_paragraph")))
        btn_delete = box.addButton(self.t("btn_delete_confirm"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = box.addButton(self.t("btn_cancel_plain"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_cancel)
        box.exec()
        if box.clickedButton() is not btn_delete:
            return False
        self._delete_paragraph_card(idx)
        return True

    def _delete_paragraph_card(self, idx: int):
        """문단 카드 하나를 목록에서 제거한다 (다른 목록의 Delete 키 삭제와 동일하게
        확인창 없이 바로 제거 - 실수로 추가한 임시 문단을 뺄 때 쓴다. 파일에는
        '저장' 버튼을 눌러야 반영된다)."""
        if getattr(self, "current_source_type", "text") != "text":
            return
        if not (0 <= idx < len(self.paragraphs)):
            return
        del self.paragraphs[idx]
        if not self.paragraphs:
            self.paragraphs = [""]
        if self.paragraph_index == idx:
            # 화면에 나가 있던 슬라이드를 지웠다 - 화면은 그대로 두고, 목록에서는 선택 해제
            self.paragraph_index = -1
        elif self.paragraph_index > idx:
            self.paragraph_index -= 1
        self._mark_paragraphs_unsaved()
        self._rebuild_paragraph_list()

    def _on_paragraph_list_context_menu(self, pos):
        """문단 카드 우클릭 - 편집/삭제 메뉴 ('+' 카드에서는 뜨지 않는다).
        이미지 폴더에서는 사진 카드에 '숨은 글 편집' 메뉴를 띄운다."""
        if getattr(self, "current_source_type", "text") == "mix":
            item = self.list_paragraphs.itemAt(pos)
            idx = item.data(USER_ROLE_INDEX) if item is not None else None
            if idx is None or not (0 <= idx < len(self.mix_entries)) or self.mix_entries[idx].kind != "image":
                return
            menu = QMenu(self)
            act_note = menu.addAction(self.t("image_note_menu"))
            act_note.setEnabled(image_notes.can_store(self.mix_entries[idx].path))
            if menu.exec(self.list_paragraphs.mapToGlobal(pos)) is act_note:
                QTimer.singleShot(0, lambda: self._edit_mix_image_note(idx))
            return
        if self._is_image_folder_mode():
            item = self.list_paragraphs.itemAt(pos)
            idx = item.data(USER_ROLE_INDEX) if item is not None else None
            menu = QMenu(self)
            act_note = None
            if idx is not None and 0 <= idx < len(self.media_slides):
                act_note = menu.addAction(self.t("image_note_menu"))
                act_note.setEnabled(image_notes.can_store(self.media_slides[idx]))
                menu.addSeparator()
            act_reload = menu.addAction(self.t("reload_folder_menu"))
            chosen = menu.exec(self.list_paragraphs.mapToGlobal(pos))
            if act_note is not None and chosen is act_note:
                QTimer.singleShot(0, lambda: self._edit_image_note(idx))
            elif chosen is act_reload:
                QTimer.singleShot(0, self._reload_image_folder_fresh)
            return
        if getattr(self, "current_source_type", "text") != "text":
            return
        item = self.list_paragraphs.itemAt(pos)
        if item is None:
            return
        idx = item.data(USER_ROLE_INDEX)
        if idx is None or idx == -1 or not (0 <= idx < len(self.paragraphs)):
            return
        menu = QMenu(self)
        act_edit = menu.addAction(self.t("edit_paragraph_card"))
        act_delete = menu.addAction(self.t("delete_paragraph_card"))
        chosen = menu.exec(self.list_paragraphs.mapToGlobal(pos))
        if chosen is act_delete:
            self._confirm_delete_paragraph_card(idx)
        elif chosen is act_edit:
            self._edit_paragraph_card(idx)

    def _mark_paragraphs_unsaved(self):
        """+ 추가/드래그 순서변경/삭제로 파일과 화면 내용이 달라졌음을 저장 버튼에 표시한다."""
        self._paragraphs_dirty = True
        if hasattr(self, "btn_save_paragraphs"):
            self.btn_save_paragraphs.setText("● " + self.t("btn_save_paragraphs"))
            self.btn_save_paragraphs.setToolTip(self.t("btn_save_paragraphs_unsaved_tip"))
        self.statusBar().showMessage(self.t("msg_paragraphs_unsaved"), 4000)

    def _clear_paragraphs_unsaved(self):
        self._paragraphs_dirty = False
        if hasattr(self, "btn_save_paragraphs"):
            self.btn_save_paragraphs.setText(self.t("btn_save_paragraphs"))
            self.btn_save_paragraphs.setToolTip(self.t("btn_save_paragraphs_tip"))

    def _handle_paragraph_drag_event(self, event) -> bool:
        """텍스트 문단 카드를 마우스로 눌러 끌면 순서를 실시간으로 바꾼다.

        Qt 내장 아이콘모드 드래그(InternalMove)가 이 카드 그리드에서 불안정했기 때문에
        (놓일 위치가 표시되지 않거나 드래그 자체가 안 먹는 문제) 대신 마우스 press/move/release
        를 직접 받아서 처리한다. 반환값 True 면 이벤트를 여기서 다 처리했다는 뜻이라
        (eventFilter 가 그대로 삼켜서) Qt 기본 처리로 넘어가지 않는다.
        '+' 카드 위로는 옮길 수 없다(항상 맨 끝에 고정).
        """
        et = event.type()
        try:
            pos = event.position().toPoint()
        except AttributeError:
            pos = event.pos()

        # --- 카드 오른쪽 위 ✏(편집) / 🗑(삭제) 단추 ---
        # 단추를 누른 것은 송출(카드 클릭)도, 끌어 옮기기도 아니다
        if et == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            hit = self._card_button_at(pos)
            if hit is not None:
                self._card_button_press = hit
                return True
        elif et == QEvent.Type.MouseButtonRelease and self._card_button_press is not None:
            pressed, self._card_button_press = self._card_button_press, None
            if self._card_button_at(pos) == pressed:
                idx, which = pressed
                # 대화상자는 이 마우스 처리가 끝난 뒤 띄운다 (떼는 신호 처리 중에 창을 열지 않게)
                if which == "delete":
                    QTimer.singleShot(0, lambda i=idx: self._confirm_delete_paragraph_card(i))
                else:
                    QTimer.singleShot(0, lambda i=idx: self._edit_paragraph_card(i))
            return True
        elif et == QEvent.Type.MouseMove and self._card_button_press is not None:
            return True
        if et == QEvent.Type.MouseMove and self._para_drag_from_idx is None:
            self._set_card_hover(self._card_button_at(pos))

        if getattr(self, "btn_edit_toggle", None) and self.btn_edit_toggle.isChecked():
            return False

        if et == QEvent.Type.MouseButtonPress:
            if event.button() != Qt.MouseButton.LeftButton:
                return False
            item = self.list_paragraphs.itemAt(pos)
            if item is None:
                return False
            idx = item.data(USER_ROLE_INDEX)
            if idx is None or idx == -1:
                return False  # '+' 카드는 기존 클릭 처리(_on_paragraph_list_clicked)로 넘긴다
            self._para_drag_from_idx = idx
            self._para_drag_start_pos = pos
            self._para_dragging = False
            return True  # 눌림 순간부터 직접 처리 (release 에서 클릭/드래그를 구분해 마무리)

        if et == QEvent.Type.MouseMove:
            if self._para_drag_from_idx is None:
                return False
            if not (event.buttons() & Qt.MouseButton.LeftButton):
                return False
            if not self._para_dragging:
                moved = (pos - self._para_drag_start_pos).manhattanLength()
                if moved < QApplication.startDragDistance():
                    return True
                self._para_dragging = True
                self.list_paragraphs.setCursor(Qt.CursorShape.ClosedHandCursor)

            target_item = self.list_paragraphs.itemAt(pos)
            if target_item is None:
                return True
            target_idx = target_item.data(USER_ROLE_INDEX)
            if target_idx is None or target_idx == -1:
                return True  # '+' 카드 위로는 옮기지 않는다
            from_idx = self._para_drag_from_idx
            if (target_idx == from_idx or not (0 <= from_idx < len(self.paragraphs))
                    or not (0 <= target_idx < len(self.paragraphs))):
                return True

            moving_text = self.paragraphs.pop(from_idx)
            self.paragraphs.insert(target_idx, moving_text)
            # 지금 화면에 나가고 있는 문단이 있으면 같이 따라가도록 인덱스를 보정한다
            if self.paragraph_index == from_idx:
                self.paragraph_index = target_idx
            elif from_idx < self.paragraph_index <= target_idx:
                self.paragraph_index -= 1
            elif target_idx <= self.paragraph_index < from_idx:
                self.paragraph_index += 1
            self._para_drag_from_idx = target_idx
            self._rebuild_paragraph_list()
            self.list_paragraphs.setCurrentRow(target_idx)
            return True

        if et == QEvent.Type.MouseButtonRelease:
            if self._para_drag_from_idx is None:
                return False
            was_dragging = self._para_dragging
            release_idx = self._para_drag_from_idx
            self._para_drag_from_idx = None
            self._para_dragging = False
            self._para_drag_start_pos = None
            try:
                self.list_paragraphs.unsetCursor()
            except RuntimeError:
                pass
            if was_dragging:
                self._mark_paragraphs_unsaved()
            else:
                # 실제로 끌지 않고 그냥 클릭만 한 것 - 평소처럼 그 문단을 송출한다
                if 0 <= release_idx < len(self.paragraphs):
                    self._broadcast_paragraph(release_idx)
            return True

        return False

    def _can_write_text_file(self) -> bool:
        """문단을 저장해도 되는 텍스트 파일이 열려 있는지.

        PPT·이미지 폴더·동영상을 보고 있을 때는 text_file_path 가 비었거나 그 원본을
        가리킬 수 있는데, 거기에 문단 글자를 쓰면 원본이 망가진다.
        """
        path = self.text_file_path
        if not path or getattr(self, "current_source_type", "text") != "text":
            return False
        if os.path.isdir(path) or ppt_engine.is_ppt_file(path) or is_video_file(path):
            return False
        return True

    def _save_paragraphs_to_current_file(self):
        """현재 self.paragraphs 내용을 지금 열려 있는 텍스트 파일에 그대로 저장한다
        (열린 파일이 없으면 아무 것도 하지 않는다 - 새로 저장하려면 별도 저장 버튼 사용)."""
        if not self._can_write_text_file():
            return False
        try:
            with open(self.text_file_path, "w", encoding="utf-8") as f:
                f.write(join_paragraphs(self.paragraphs))
            return True
        except Exception as e:
            print(f"파일 저장 실패: {e}")
            return False

    def _save_current_paragraphs_as(self):
        """지금 문단 목록을 새 텍스트 파일로 저장하고 라이브러리에 등록한다
        (아직 저장된 파일이 없을 때 - 예: '+' 로 처음부터 만든 경우)."""
        text = self._join_paragraphs_text()
        if not text.strip():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, self.t("notice"), self.t("msg_empty_text"))
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, self.t("dialog_save_direct"),
            self.settings.value("last_dir", str(Path.home())),
            self.t("filter_text")
        )
        if not file_path:
            return
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
            self.settings.setValue("last_dir", os.path.dirname(file_path))
            self._register_text_file(file_path)
            self.text_file_path = file_path
            self.current_source_path = file_path
            try:
                self.lbl_txt_file.setText(os.path.basename(file_path))
            except RuntimeError:
                pass
            self._clear_paragraphs_unsaved()
            self.statusBar().showMessage(self.t("msg_saved_file", os.path.basename(file_path)), 3000)
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, self.t("err_save_title"), self.t("err_save_msg", e))

    def _on_save_paragraphs_clicked(self):
        if getattr(self, "current_source_type", "text") != "text":
            return
        if self.text_file_path:
            if self._save_paragraphs_to_current_file():
                self._clear_paragraphs_unsaved()
                self.statusBar().showMessage(self.t("msg_saved_file", os.path.basename(self.text_file_path)), 3000)
        else:
            self._save_current_paragraphs_as()

    def _refresh_paragraph_thumbs(self):
        """배경/스타일이 바뀌었을 때 썸네일을 다시 그림"""
        self._rebuild_thumb_grid()

    # ------------------------------------------------------------------
    # 편집 모드 (요구사항 2-3: 적용 시 즉시 반영)
    # ------------------------------------------------------------------
    def _join_paragraphs_text(self) -> str:
        """paragraphs 리스트를 빈 줄로 join (마지막 빈 문단도 보존)"""
        return "\n\n".join(self.paragraphs)

    def _split_paragraphs_text(self, text: str) -> list:
        """빈 줄(연속 \\n 포함)로 분리"""
        return split_paragraphs(text) if text.strip() else [""]

    def _on_edit_target_changed(self):
        if not hasattr(self, "txt_editor"):
            return
        if hasattr(self, "rad_edit_current") and self.rad_edit_current.isChecked():
            if 0 <= self.paragraph_index < len(self.paragraphs):
                self.txt_editor.setPlainText(self.paragraphs[self.paragraph_index])
            else:
                self.txt_editor.setPlainText("")
        else:
            self.txt_editor.setPlainText(self._join_paragraphs_text())

    def _toggle_edit_mode(self, checked):
        if checked:
            self.btn_edit_toggle.setText(self.t("edit_mode_off"))
            self.edit_area.show()
            self._on_edit_target_changed()
        else:
            self.btn_edit_toggle.setText(self.t("edit_mode_toggle"))
            self.edit_area.hide()

    def _showing_current_paragraph(self) -> bool:
        """지금 송출 화면에 '선택된 문단'이 그대로 떠 있는지"""
        return (getattr(self, "_live_source_type", "") == "text"
                and 0 <= self.paragraph_index < len(self.paragraphs)
                and self.presenter.has_text())

    def _open_edit_dialog(self):
        """별도 창(TextEditDialog)으로 텍스트 / 문단 편집기를 띄우고 결과 즉시 적용"""
        cur_para = ""
        if 0 <= self.paragraph_index < len(self.paragraphs):
            cur_para = self.paragraphs[self.paragraph_index]
        all_text = self._join_paragraphs_text()

        dialog = TextEditDialog(
            self,
            current_para=cur_para,
            all_text=all_text,
            active_index=max(0, self.paragraph_index),
            lang=self.current_lang,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            res = dialog.get_result()
            mode = res["mode"]
            new_text = res["text"]

            showing = self._showing_current_paragraph()
            if mode == "all":
                self.paragraphs = self._split_paragraphs_text(new_text)
                if not self.paragraphs:
                    self.paragraphs = [""]
                if not (0 <= self.paragraph_index < len(self.paragraphs)):
                    self.paragraph_index = -1
                    showing = False
                cur_text = self.paragraphs[self.paragraph_index] if showing else ""
            else:
                if 0 <= self.paragraph_index < len(self.paragraphs):
                    self.paragraphs[self.paragraph_index] = new_text
                elif new_text.strip():
                    # 고른 문단이 없으면 기존 문단을 지우지 않고 새 문단으로 덧붙인다
                    self.paragraphs.append(new_text)
                cur_text = new_text

            # 편집으로 새 화면을 띄우지 않는다. 지금 화면에 나가 있는 바로 그 문단을
            # 고친 경우에만 화면 글자를 고친 내용으로 바꾼다.
            if showing:
                self.presenter.set_text(cur_text)
                self.preview.set_text(cur_text)
            self._rebuild_paragraph_list()
            self._rebuild_thumb_grid()
            if self._can_write_text_file():
                try:
                    with open(self.text_file_path, "w", encoding="utf-8") as f:
                        f.write(join_paragraphs(self.paragraphs))
                    self._clear_paragraphs_unsaved()
                except Exception as e:
                    print(f"파일 저장 실패: {e}")
            self._update_status()

    def _apply_edit(self):
        new_text = self.txt_editor.toPlainText()
        showing = self._showing_current_paragraph()
        if hasattr(self, "rad_edit_all") and self.rad_edit_all.isChecked():
            self.paragraphs = self._split_paragraphs_text(new_text)
            if not self.paragraphs:
                self.paragraphs = [""]
            if not (0 <= self.paragraph_index < len(self.paragraphs)):
                self.paragraph_index = -1
                showing = False
            cur_text = self.paragraphs[self.paragraph_index] if showing else ""
        else:
            if 0 <= self.paragraph_index < len(self.paragraphs):
                self.paragraphs[self.paragraph_index] = new_text
            elif new_text.strip():
                self.paragraphs.append(new_text)
            cur_text = new_text

        # 편집으로 새 화면을 띄우지 않는다 (지금 나가 있는 그 문단만 고친 내용으로 바꾼다)
        if showing:
            self.presenter.set_text(cur_text)
            self.preview.set_text(cur_text)
        self._rebuild_paragraph_list()
        self._rebuild_thumb_grid()
        if self._can_write_text_file():
            try:
                with open(self.text_file_path, "w", encoding="utf-8") as f:
                    f.write(join_paragraphs(self.paragraphs))
                self._clear_paragraphs_unsaved()
            except Exception as e:
                print(f"파일 저장 실패: {e}")
        self._update_status()

    def _cancel_edit(self):
        self._on_edit_target_changed()

    def _clear_text(self):
        """송출 화면에서 텍스트를 내리고, 선택되어 있던 문단도 해제한다."""
        self.presenter.clear_text()
        self.preview.set_text("")
        self.paragraph_index = -1
        if getattr(self, "current_source_type", "") == "mix":
            self.mix_index = -1            # 화면이 비었으니 '송출 중인 카드'도 없다
        if hasattr(self, "list_paragraphs"):
            self.list_paragraphs.blockSignals(True)
            self.list_paragraphs.setCurrentRow(-1)
            self.list_paragraphs.blockSignals(False)
        self.statusBar().showMessage(self.t("msg_text_stopped"), 2000)
        self._update_status()

    # ------------------------------------------------------------------
    # 텍스트 스타일 (요구사항 2-2: 글꼴/크기/색상/테두리)
    # ------------------------------------------------------------------
    def _current_style(self) -> TextStyle:
        return TextStyle(
            font_family=self.font_combo.currentFont().family(),
            size=self.size_spin.value(),
            color=QColor(self._text_color_hex),
            border_enabled=self.chk_border.isChecked(),
            border_width=self.border_width_spin.value(),
            border_color=QColor(self._border_color_hex),
            valign=getattr(self, "_text_valign", "center"),
            margin_top=self.spin_margin_top.value() if hasattr(self, "spin_margin_top") else 5,
            margin_bottom=self.spin_margin_bottom.value() if hasattr(self, "spin_margin_bottom") else 5,
        )

    def _set_text_valign(self, valign: str, apply: bool = True):
        """세로 위치 단추(위/가운데/아래)"""
        if valign not in TextStyle.VALIGNS:
            valign = "center"
        self._text_valign = valign
        for key, btn in self.valign_buttons.items():
            btn.blockSignals(True)
            btn.setChecked(key == valign)
            btn.blockSignals(False)
        # 가운데 정렬은 여백이 필요 없으므로 여백 칸을 감춘다 (값은 그대로 기억)
        uses_margin = valign != "center"
        for widget in (self.lbl_margin_top, self.spin_margin_top,
                       self.lbl_margin_bottom, self.spin_margin_bottom):
            widget.setVisible(uses_margin)
        if apply:
            self._on_style_changed()

    def _on_style_changed(self, *_):
        style = self._current_style()
        self.presenter.set_text_style(style)
        self.preview.set_style(style)
        self._save_style(style)
        # 스타일(글꼴/크기/색상/테두리)이 바뀌면 썸네일도 다시 그림
        self._rebuild_thumb_grid()

    def _pick_text_color(self):
        color = QColorDialog.getColor(self._text_color_hex, self, self.t("dialog_select_text_color"))
        if color.isValid():
            self._text_color_hex = color.name()
            self._set_chip_color(self.btn_text_color, color)
            self._on_style_changed()

    def _pick_border_color(self):
        color = QColorDialog.getColor(self._border_color_hex, self, self.t("dialog_select_border_color"))
        if color.isValid():
            self._border_color_hex = color.name()
            self._set_chip_color(self.btn_border_color, color)
            self._on_style_changed()

    @staticmethod
    def _set_chip_color(btn: QPushButton, color: QColor):
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {color.name()}; border: 1px solid #999; "
            f"border-radius: 4px; }}"
        )
        btn.setToolTip(color.name())

    def _save_style(self, style: TextStyle):
        s = self.settings
        s.setValue("style/font_family", style.font_family)
        s.setValue("style/size", style.size)
        s.setValue("style/color", style.color.name())
        s.setValue("style/border", style.border_enabled)
        s.setValue("style/border_width", style.border_width)
        s.setValue("style/border_color", style.border_color.name())
        s.setValue("style/valign", style.valign)
        s.setValue("style/margin_top", style.margin_top)
        s.setValue("style/margin_bottom", style.margin_bottom)

    # ------------------------------------------------------------------
    # 상태/미리보기 갱신
    # ------------------------------------------------------------------
    def _update_status(self):
        parts = [self.t("status_bg", self.current_bg_desc)]
        if self.presenter.content_active:
            state = self.presenter.content_state
            state_text = self.t(f"video_state_{state}") if state in ("playing", "paused", "ended") else state
            parts.append(self.t("status_video", os.path.basename(self.presenter.content_path), state_text))
        elif (getattr(self, "current_source_type", "text") == "direct_text"
              or (getattr(self, "current_source_type", "text") in ("video", "mix")
                  and getattr(self, "_live_source_type", "") == "direct_text")):
            parts.append(self.t("status_direct_presenting"))
        elif (getattr(self, "current_source_type", "text") == "mix"
              and getattr(self, "_live_source_path", "") == getattr(self, "current_source_path", "")
              and 0 <= getattr(self, "mix_index", -1) < len(getattr(self, "mix_entries", []))):
            parts.append(self.t("status_mix_presenting", self.mix_index + 1, len(self.mix_entries)))
        elif self.text_file_path and self.paragraph_index >= 0:
            parts.append(self.t("status_presenting", self.paragraph_index + 1, len(self.paragraphs)))
        elif not self.text_file_path or self.paragraph_index < 0:
            parts.append(self.t("status_blank"))
        self.lbl_status.setText("  ".join(parts))
        if hasattr(self, "preview_box"):
            self.preview_box.fit_child()     # 글자 줄 수가 바뀌면 미리보기 자리도 다시 맞춘다
        # 소스가 바뀌었을 수 있으므로 우측 패널(편집/스타일 ↔ 노트)을 맞춰 둔다
        self._update_side_panel_mode()

    def _on_presenter_media_state(self, state_str: str):
        if not hasattr(self, "lbl_playlist_state"):
            return
        if state_str == "playing":
            self.lbl_playlist_state.setStyleSheet("color: #2ecc71; font-weight: bold;")
        else:
            self.lbl_playlist_state.setStyleSheet("")

    def _on_playlist_item_changed(self, cur: int, total: int, name: str):
        # 미리보기는 동영상 프레임이 그대로 표시되므로 상태줄에만 표시
        self.current_bg_desc = self.t("playlist_status_desc", cur, total, name)
        self._update_status()

    @Slot(str, str)
    def _on_thumb_ready(self, file_path: str, thumb_path: str):
        if not thumb_path or not os.path.exists(thumb_path):
            return
        for lst in (self.list_images, self.list_videos):
            for i in range(lst.count()):
                item = lst.item(i)
                if item.data(USER_ROLE_PATH) == file_path:
                    item.setIcon(QIcon(thumb_path))
                    break

    # ------------------------------------------------------------------
    # 설정 복원
    # ------------------------------------------------------------------
    def _load_library_and_settings(self):
        s = self.settings

        # --- 색상 팔레트 (투명 + 기본 + 사용자 추가) ---
        item_transparent = QListWidgetItem(make_checker_pixmap(44, 28), self.t("transparent_swatch"))
        item_transparent.setData(USER_ROLE_PATH, "transparent")
        item_transparent.setData(USER_ROLE_KIND, "transparent")
        item_transparent.setToolTip(self.t("transparent_swatch_tip"))
        self.list_colors.addItem(item_transparent)

        for name, hex_color in PRESET_COLORS:
            color_key = PRESET_COLOR_KEYS.get(hex_color.lower())
            color_label = f"{self.t(color_key)} ({hex_color.upper()})" if color_key else f"{name} ({hex_color})"
            self._add_color_item(QColor(hex_color), color_label, kind="preset")
        self.custom_colors = list(s.value("lib/custom_colors", []) or [])
        for hex_str in self.custom_colors:
            self._add_color_item(QColor(hex_str), f"{self.t('color_custom_prefix')} {hex_str}", kind="custom")

        # --- 이미지 / 동영상 라이브러리 ---
        for path in list(s.value("lib/images", []) or []):
            if os.path.exists(path):
                self._add_image_item(path)
        checked_videos = set(list(s.value("video/checked", []) or []))
        for path in list(s.value("lib/videos", []) or []):
            if os.path.exists(path):
                self._add_video_item(path, checked=(path in checked_videos))

        # --- 텍스트 스타일 (시그널 차단 후 설정하여 중간 콜백으로 QSettings가 덮어써지지 않도록 보장) ---
        self.font_combo.blockSignals(True)
        self.size_spin.blockSignals(True)
        self.chk_border.blockSignals(True)
        self.border_width_spin.blockSignals(True)
        self.spin_margin_top.blockSignals(True)
        self.spin_margin_bottom.blockSignals(True)

        family = str(s.value("style/font_family", "Malgun Gothic") or "Malgun Gothic")
        self.font_combo.set_family(family)
        self.size_spin.setValue(int(s.value("style/size", 48)))
        self._text_color_hex = str(s.value("style/color", "#FFFFFF") or "#FFFFFF")
        self._set_chip_color(self.btn_text_color, QColor(self._text_color_hex))
        raw_border = s.value("style/border", True)
        is_border = str(raw_border).lower() in ("true", "1") if isinstance(raw_border, str) else bool(raw_border)
        self.chk_border.setChecked(is_border)
        self.border_width_spin.setValue(int(s.value("style/border_width", 3)))
        self._border_color_hex = str(s.value("style/border_color", "#000000") or "#000000")
        self._set_chip_color(self.btn_border_color, QColor(self._border_color_hex))
        self._set_text_valign(str(s.value("style/valign", "center") or "center"), apply=False)
        self.spin_margin_top.setValue(int(s.value("style/margin_top", 5) or 0))
        self.spin_margin_bottom.setValue(int(s.value("style/margin_bottom", 5) or 0))

        self.font_combo.blockSignals(False)
        self.size_spin.blockSignals(False)
        self.chk_border.blockSignals(False)
        self.border_width_spin.blockSignals(False)
        self.spin_margin_top.blockSignals(False)
        self.spin_margin_bottom.blockSignals(False)
        self._on_style_changed()

        # --- 문단 목록 글자 크기, 열 수 & 썸네일 크기 ---
        list_font_sz = int(s.value("text/list_font_size", 13))
        if hasattr(self, "spin_list_font_size"):
            self.spin_list_font_size.setValue(list_font_sz)
            self._apply_list_font_size(list_font_sz)

        list_cols = int(s.value("text/list_columns", 2))
        if hasattr(self, "spin_list_columns"):
            self.spin_list_columns.blockSignals(True)
            self.spin_list_columns.setValue(list_cols)
            self.spin_list_columns.blockSignals(False)

        thumb_sz = int(s.value("text/thumb_size", 200))
        if hasattr(self, "spin_thumb_size"):
            self.spin_thumb_size.setValue(thumb_sz)

        notes_font_sz = int(s.value("text/notes_font_size", 13))
        if hasattr(self, "spin_notes_font_size"):
            self.spin_notes_font_size.setValue(notes_font_sz)
            self._on_notes_font_size_changed(notes_font_sz)

        # --- 본문 동영상 소리/자막 크기, 음악 목록 ---
        video_volume = int(s.value("video/content_volume", 80) or 80)
        self.sld_video_volume.blockSignals(True)
        self.sld_video_volume.setValue(video_volume)
        self.sld_video_volume.blockSignals(False)
        self.lbl_video_volume_value.setText(str(video_volume))
        self.presenter.set_content_volume(video_volume)
        subtitle_size = int(s.value("video/subtitle_size", 44) or 44)
        self.spin_subtitle_size.blockSignals(True)
        self.spin_subtitle_size.setValue(subtitle_size)
        self.spin_subtitle_size.blockSignals(False)
        self.presenter.set_subtitle_size(subtitle_size)
        self.preview.set_subtitle_size(subtitle_size)
        self._restore_music_settings()

        # --- 텍스트 파일 라이브러리 (좌측 아래) ---
        self._library_font_size = int(s.value("text_files/list_font_size", 12))
        self._refresh_text_files_list()

        # --- 파일/폴더 열기 (시작 시에는 방송하지 않고 빈 화면으로 대기) ---
        def _load_any_content(path: str):
            if mix_bundle.is_mix_file(path):
                self._load_mix(path)
            elif os.path.isdir(path):
                self._load_image_folder(path, select_index=0, broadcast=False)
            elif ppt_engine.is_ppt_file(path):
                self._load_pptx(path, select_index=0, broadcast=False)
            elif is_video_file(path):
                self._load_video_item(path)
            else:
                self._load_text_file(path, select_index=0, broadcast=False)

        txt_path = s.value("text/file", "")
        if txt_path and os.path.exists(txt_path):
            _load_any_content(txt_path)
        elif self._get_registered_text_files():
            # 저장된 파일이 없거나 임시파일이면 등록된 목록의 첫 번째 항목 열기
            first_file = self._get_registered_text_files()[0]
            if os.path.exists(first_file):
                _load_any_content(first_file)

        # --- 썸네일 그리드 크기 및 문단 목록 레이아웃 적용 ---
        if hasattr(self, "spin_thumb_size"):
            self._on_thumb_size_changed(self.spin_thumb_size.value())
        self._relayout_paragraph_list()

        # 시작 시 송출 화면은 항상 투명 + 빈 텍스트로 대기한다.
        # 저장된 배경(bg/type, bg/value)은 지우지 않고, 첫 문단/직접 입력 송출 때 복원한다.
        # 주의: _set_transparent_bg()를 부르면 저장된 설정이 매번 지워지므로 화면만 바꾼다.
        self.presenter.set_transparent(True)
        self.preview.set_transparent(True)
        self.current_bg_desc = self.t("transparent")
        self._bg_needs_restore = True
        self._clear_text()
        self.paragraph_index = -1
        if hasattr(self, "list_paragraphs"):
            self.list_paragraphs.setCurrentRow(-1)

        # 언어 설정 반영
        self._retranslate_ui()

        # 지난번에 애니메이션 모드를 썼다면, 되살린 PPT 를 화면이 뜬 뒤 조금 있다가
        # 파워포인트에 미리 열어 둔다 (프로그램 시작은 늦추지 않고, 첫 모드 켜기를 앞당긴다)
        used = str(s.value("ppt/show_mode_used", "false")).lower() in ("true", "1")
        if used and self._is_pptx_mode():
            QTimer.singleShot(2500, self._prepare_restored_deck)

    def _prepare_restored_deck(self):
        path = getattr(self, "current_source_path", "")
        if (not self._is_pptx_mode() or not path or not os.path.exists(path)
                or path == getattr(self, "_show_prepared_path", "")
                or getattr(self, "_show_mode_active", False)):
            return
        self._show_prepared_path = path
        ppt_engine.prepare_show_async(path)

    def closeEvent(self, event):
        # 마우스로 조정한 창/패널 크기를 다음 실행을 위해 저장
        self._save_window_layout()
        # 우리가 띄운 파워포인트만 정리한다 (사용자가 열어 둔 창은 그대로)
        self._ppt_load_token += 1
        if getattr(self, "_show_mode_active", False):
            self._stop_slideshow(silent=True, resume_export=False)
        try:
            ppt_engine.shutdown()
        except Exception as e:
            print(f"ppt_engine 정리 실패: {e}")
        try:
            self.music.stop()
            self.presenter.stop_content_video()
        except Exception as e:
            print(f"재생 정리 실패: {e}")
        popup = getattr(self, "notes_popup", None)
        if popup is not None:
            popup.close()
        self.presenter.close()
        # 받아 둔 새 버전이 있으면 ([끌 때 바꾸기]) 프로그램이 꺼진 뒤 바꿔 끼운다
        self.updates.apply_on_exit()
        super().closeEvent(event)