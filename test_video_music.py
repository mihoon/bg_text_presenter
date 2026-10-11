# -*- coding: utf-8 -*-
"""
본문 동영상(라이브러리) + 자막 + 음악 재생 테스트

    python test_video_music.py

- 라이브러리에 동영상을 넣으면 바로 재생되지 않는지 (재생 단추를 눌러야 시작)
- 같은 이름의 .srt 자막을 자동으로 찾아 시각에 맞게 보여 주는지
- 자막 끄기 / 직접 고른 자막 / 자막 크기 / 소리 크기
- 더블클릭해도 재생→곧바로 멈춤이 되지 않는지
- 문단이나 ESC 로 다른 것을 송출하면 동영상이 내려가는지
- 음악 목록이 저장되고, 다시 켰을 때 재생하지 않고 목록만 되살리는지
"""
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="bgpt_video_test_")
os.environ["BGPT_SETTINGS_DIR"] = os.path.join(_TMP, "settings")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop

import cv2
import numpy as np

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"   OK   {label}")
    else:
        print(f"   실패 {label}  {detail}")
        FAILURES.append(label)


def make_video(path, seconds=4.0, fps=25):
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 180))
    for i in range(int(seconds * fps)):
        frame = np.zeros((180, 320, 3), np.uint8)
        frame[:] = (40, 120, (i * 4) % 255)
        writer.write(frame)
    writer.release()


SRT = """1
00:00:00,300 --> 00:00:03,500
자동 자막 한 줄

"""
SRT_MANUAL = """1
00:00:00,000 --> 00:00:09,000
직접 고른 자막
"""


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    def pump(sec):
        end = time.time() + sec
        while time.time() < end:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            time.sleep(0.01)

    media = os.path.join(_TMP, "media")
    os.makedirs(media)
    video = os.path.join(media, "주일 광고.mp4")
    make_video(video)
    with open(os.path.join(media, "주일 광고.srt"), "w", encoding="utf-8") as f:
        f.write(SRT)
    manual_sub = os.path.join(media, "다른자막.srt")
    with open(manual_sub, "w", encoding="utf-8") as f:
        f.write(SRT_MANUAL)
    text_file = os.path.join(media, "찬양.txt")
    with open(text_file, "w", encoding="utf-8") as f:
        f.write("첫째 문단\n\n둘째 문단")

    from main_window import MainWindow
    w = MainWindow()
    w.show()
    pump(0.3)

    print("1) 라이브러리에 동영상 넣기 - 곧바로 재생하지 않음")
    w._handle_text_files_dropped([video])
    pump(0.3)
    check("동영상이 라이브러리에 등록됨", video in w._get_registered_text_files())
    check("가운데가 동영상 화면으로 바뀜", w.current_source_type == "video")
    check("재생은 시작하지 않음", not w.presenter.content_active)
    check("조작 막대가 보임", w.video_bar.isVisible())
    check("글자 크기/열 수 조절은 숨김", not w.spin_list_columns.isVisible())
    check("카드 하나", w.list_paragraphs.count() == 1)
    check("같은 이름 자막을 자동으로 찾음",
          "주일 광고.srt" in w.lbl_subtitle_state.text(), w.lbl_subtitle_state.text())

    print("\n2) 카드(재생 단추)를 누르면 듀얼 화면에서 재생 + 자막")
    item = w.list_paragraphs.item(0)
    w._on_paragraph_list_clicked(item)
    w._on_paragraph_list_clicked(item)      # 더블클릭의 두 번째 클릭 신호
    pump(1.2)
    check("재생 중", w.presenter.content_active and w.presenter.content_state == "playing",
          w.presenter.content_state)
    check("더블클릭해도 곧바로 멈추지 않음", w.presenter.content_state == "playing")
    check("자막이 시각에 맞게 나옴", w.presenter.subtitle_text() == "자동 자막 한 줄",
          repr(w.presenter.subtitle_text()))
    check("미리보기에도 자막", w.preview._subtitle == "자동 자막 한 줄", repr(w.preview._subtitle))
    check("미리보기가 동영상 화면", w.preview._content_active)
    check("버튼이 '일시정지'로 바뀜", w.btn_video_play.text() == w.t("video_pause"), w.btn_video_play.text())
    check("재생 위치 막대가 움직임", w.sld_video_pos.value() > 0, str(w.sld_video_pos.value()))
    check("상태 표시줄에 동영상", "주일 광고.mp4" in w.lbl_status.text(), w.lbl_status.text())

    print("\n3) 자막 끄기 / 직접 고르기 / 크기, 소리")
    w._set_subtitle_choice("off")
    pump(0.3)
    check("자막 끔 → 화면에서 사라짐", w.presenter.subtitle_text() == "", repr(w.presenter.subtitle_text()))
    w._set_subtitle_choice(manual_sub)
    pump(0.3)
    check("직접 고른 자막으로 바뀜", w.presenter.subtitle_text() == "직접 고른 자막",
          repr(w.presenter.subtitle_text()))
    w.spin_subtitle_size.setValue(70)
    check("자막 크기 반영", w.presenter.subtitle_size == 70 and w.preview._subtitle_size == 70)
    w.sld_video_volume.setValue(35)
    check("소리 크기 반영", w.presenter._content_volume == 35)
    w._set_subtitle_choice(None)            # 자동으로 되돌림

    print("\n4) 일시정지 / 계속 / 5초 이동")
    w._video_play_toggle()
    pump(0.3)
    check("일시정지", w.presenter.content_state == "paused", w.presenter.content_state)
    before = w.presenter.content_position()
    w._handle_video_key(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Key.Key_Left)
    pump(0.3)
    check("← 로 뒤로 이동", w.presenter.content_position() <= max(0, before - 900),
          f"{before} → {w.presenter.content_position()}")
    w._video_play_toggle()
    pump(0.3)
    check("다시 재생", w.presenter.content_state == "playing", w.presenter.content_state)

    print("\n4-1) 동영상 화면에서의 안전장치")
    size_before = os.path.getsize(video)
    w.txt_editor.setPlainText("이 글자가 동영상 파일에 쓰이면 안 된다")
    w._apply_edit()
    check("편집기 '적용'이 동영상 파일을 덮어쓰지 않음", os.path.getsize(video) == size_before,
          f"{size_before} → {os.path.getsize(video)}")
    check("동영상 화면에서는 텍스트 편집 칸을 숨김", not w.grp_edit.isVisible())
    other_bg = os.path.join(media, "배경.mp4")
    make_video(other_bg, seconds=2.0)
    w.presenter.play_playlist([other_bg])
    pump(0.5)
    from PySide6.QtMultimedia import QMediaPlayer
    check("본문 동영상 중에 배경 동영상을 골라도 소리가 겹치지 않음 (배경은 대기)",
          w.presenter.player.playbackState() != QMediaPlayer.PlaybackState.PlayingState)
    w.presenter.stop_playlist()
    saved_state = (w.current_source_type, list(w.media_slides))
    w.current_source_type = "folder"
    w.media_slides = [os.path.join(media, "아직없는슬라이드.jpg")]
    w._present_media_slide(0)
    check("아직 준비 안 된 슬라이드를 눌러도 동영상은 계속", w.presenter.content_active)
    w.current_source_type, w.media_slides = saved_state[0], saved_state[1]
    w._broadcast_direct_text("잠시 광고 말씀")
    pump(0.2)
    check("직접 입력을 송출하면 동영상은 내려감", not w.presenter.content_active)
    check("동영상 화면(카드)은 그대로 쓸 수 있음", w.current_source_type == "video" and w.video_bar.isVisible())
    w._video_play_toggle()
    pump(0.4)
    check("다시 재생 단추가 동작", w.presenter.content_active and w.presenter.content_state == "playing",
          w.presenter.content_state)

    print("\n5) 다른 것을 송출하면 동영상은 내려감")
    w._register_text_file(text_file)
    w._load_text_file(text_file, broadcast=False)     # 라이브러리에서 클릭 = 구경만
    pump(0.2)
    check("텍스트를 구경만 할 때는 계속 재생", w.presenter.content_active)
    w._broadcast_paragraph(0)
    pump(0.2)
    check("문단을 송출하면 동영상이 내려감", not w.presenter.content_active)
    check("미리보기도 동영상 해제", not w.preview._content_active)

    print("\n6) 끝까지 재생하면 마지막 장면에서 멈춤 → ESC 로 내림")
    w._load_video_item(video)
    w._video_play_toggle()
    pump(0.4)
    duration = w.presenter.content_duration()
    w.presenter.seek_content_video(max(0, duration - 300))
    pump(1.5)
    check("재생 끝 상태 (화면은 유지)", w.presenter.content_state == "ended" and w.presenter.content_active,
          w.presenter.content_state)
    check("버튼이 '처음부터'", w.btn_video_play.text() == w.t("video_replay"), w.btn_video_play.text())
    w._on_escape_action()
    pump(0.2)
    check("ESC 로 내려감", not w.presenter.content_active)

    print("\n7) 음악 목록 저장 / 다시 켰을 때 자동 재생하지 않음")
    songs = []
    for name in ("찬양1.wav", "찬양2.wav"):
        path = os.path.join(media, name)
        import wave
        import struct
        with wave.open(path, "w") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(b"".join(struct.pack("<h", 0) for _ in range(22050)))
        songs.append(path)
    w.music.set_playlist(songs, 0, autoplay=False)
    w._music_settings_save()
    w.sld_music_volume.setValue(33)
    check("곡 표시", "찬양1.wav" in w.btn_music_list.text(), w.btn_music_list.text())
    check("목록 메뉴에 두 곡 + 추가/비우기",
          len([a for a in w.music_menu.actions() if not a.isSeparator()]) == 4,
          str([a.text() for a in w.music_menu.actions()]))
    grab_path = os.path.join(_TMP, "main_window.png")
    w.grab().save(grab_path)
    w.close()
    pump(0.2)

    w2 = MainWindow()
    pump(0.2)
    check("음악 목록이 되살아남", w2.music.playlist == songs, str(w2.music.playlist))
    check("다시 켜도 음악을 재생하지 않음", w2.music.state == "stopped")
    check("음악 소리 크기 유지", w2.sld_music_volume.value() == 33)
    check("마지막으로 보던 동영상 화면이 되살아나도 재생은 안 함",
          w2.current_source_type in ("video", "text") and not w2.presenter.content_active)
    check("동영상 소리 크기 유지", w2.sld_video_volume.value() == 35)
    check("자막 크기 유지", w2.spin_subtitle_size.value() == 70)
    w2.close()

    print(f"\n(화면 캡처: {grab_path})")
    print()
    if FAILURES:
        print(f"실패 {len(FAILURES)}건: {FAILURES}")
        return 1
    print("전부 통과")
    return 0


if __name__ == "__main__":
    code = main()
    if not os.environ.get("BGPT_KEEP_TMP"):
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
