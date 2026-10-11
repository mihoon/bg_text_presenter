# -*- coding: utf-8 -*-
"""
음악 재생 방식(연속 재생 / 한 곡씩) 테스트 - python test_music_mode.py

- 연속 재생: 한 곡이 끝나면 다음 곡을 이어서 재생
- 한 곡씩: 한 곡이 끝나면 멈추고 다음 곡을 준비만 해 둠 (▶ 를 눌러야 재생)
- 한 곡씩 + 반복: 같은 곡을 되풀이
- 한 곡씩일 때 멈춰 있는 상태에서 ⏭ 는 곡만 고름
- 툴바 단추로 바꾸고, 다시 켜도 설정 유지
"""
import os
import shutil
import struct
import sys
import tempfile
import time
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_TMP = tempfile.mkdtemp(prefix="bgpt_music_mode_")
os.environ["BGPT_SETTINGS_DIR"] = os.path.join(_TMP, "settings")

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop

FAILURES = []


def check(label, condition, detail=""):
    if condition:
        print(f"   OK   {label}")
    else:
        print(f"   실패 {label}  {detail}")
        FAILURES.append(label)


def make_wav(path, seconds=0.8):
    with wave.open(path, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"".join(struct.pack("<h", 0) for _ in range(int(22050 * seconds))))


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    def pump(sec):
        end = time.time() + sec
        while time.time() < end:
            app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            time.sleep(0.01)

    def wait_for(cond, timeout=6.0):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            pump(0.05)
        return cond()

    songs = []
    for i in range(3):
        path = os.path.join(_TMP, f"찬양{i + 1}.wav")
        make_wav(path)
        songs.append(path)

    from main_window import MainWindow
    w = MainWindow()
    w.show()
    pump(0.3)
    m = w.music

    print("1) 기본은 연속 재생")
    check("처음에는 연속 재생", m.mode == "continuous")
    check("단추 글자", w.btn_music_mode.text() == w.t("music_mode_continuous"), w.btn_music_mode.text())
    w.btn_music_repeat.setChecked(False)
    check("반복 끔", m.repeat is False)
    m.set_playlist(songs, 0, autoplay=True)
    check("첫 곡 재생", wait_for(lambda: m.state == "playing"), m.state)
    check("끝나면 다음 곡을 이어서 재생", wait_for(lambda: m.index == 1 and m.state == "playing"),
          f"{m.index} {m.state}")
    m.stop()
    pump(0.2)

    print("\n2) 한 곡씩으로 바꾸기")
    w.btn_music_mode.click()
    check("단추를 누르면 한 곡씩", m.mode == "single")
    check("단추 글자 바뀜", w.btn_music_mode.text() == w.t("music_mode_single"), w.btn_music_mode.text())
    check("반복 단추는 '한 곡 반복' 모양", w.btn_music_repeat.text() == "🔂")
    m.play(0)
    check("고른 곡 재생", wait_for(lambda: m.state == "playing" and m.index == 0), f"{m.index} {m.state}")
    check("곡이 끝나면 멈춤", wait_for(lambda: m.state == "stopped"), m.state)
    pump(1.0)
    check("다음 곡은 재생하지 않고 준비만", m.state == "stopped" and m.index == 1, f"{m.index} {m.state}")
    check("곡 표시도 다음 곡", w.btn_music_list.text().startswith("2/3"), w.btn_music_list.text())
    w._on_music_play_clicked()
    check("▶ 를 누르면 준비된 곡 재생", wait_for(lambda: m.state == "playing" and m.index == 1),
          f"{m.index} {m.state}")
    check("그 곡도 끝나면 멈춤", wait_for(lambda: m.state == "stopped"), m.state)

    print("\n3) 한 곡씩일 때 ⏭ / ⏮ (멈춰 있으면 곡만 고름)")
    idx = m.index
    m.next()
    pump(0.3)
    check("⏭ - 곡만 바뀌고 재생은 안 함", m.index == (idx + 1) % 3 and m.state == "stopped", f"{m.index} {m.state}")
    m.previous()
    pump(0.3)
    check("⏮ - 곡만 바뀌고 재생은 안 함", m.index == idx and m.state == "stopped", f"{m.index} {m.state}")

    print("\n4) 마지막 곡이 끝나면 첫 곡을 준비")
    m.play(2)
    check("마지막 곡 재생", wait_for(lambda: m.state == "playing" and m.index == 2))
    check("끝나면 멈추고 첫 곡 준비", wait_for(lambda: m.state == "stopped" and m.index == 0),
          f"{m.index} {m.state}")

    print("\n5) 한 곡씩 + 반복 = 그 곡만 되풀이")
    w.btn_music_repeat.setChecked(True)
    check("반복 켬", m.repeat is True)
    m.play(1)
    check("재생", wait_for(lambda: m.state == "playing" and m.index == 1))
    pump(2.2)       # 0.8초짜리 곡이 두세 번 돌 시간
    check("같은 곡을 계속 재생", m.state == "playing" and m.index == 1, f"{m.index} {m.state}")
    m.stop()
    pump(0.2)

    print("\n5-1) 재생 시간 / 남은 시간")
    from main_window import format_play_time
    check("시간 글자 모양", format_play_time(83000) == "1:23" and format_play_time(3725000) == "1:02:05")
    long_song = os.path.join(_TMP, "긴곡.wav")
    make_wav(long_song, seconds=4.0)
    w.btn_music_repeat.setChecked(False)
    w.btn_music_mode.click() if m.mode == "single" else None
    m.set_playlist([long_song], 0, autoplay=True)
    check("재생 시작", wait_for(lambda: m.state == "playing"))
    pump(1.3)
    text = w.lbl_music_time.text()
    print(f"   (시간 표시: {text})")
    check("곡 길이가 보임", "/ 0:04" in text, text)
    check("재생한 시간이 흐름", text.startswith("0:01") or text.startswith("0:02"), text)
    check("남은 시간이 보임", "-0:0" in text and "-0:04" not in text, text)
    m.stop()
    pump(0.3)
    check("멈추면 처음으로", w.lbl_music_time.text().startswith("0:00"), w.lbl_music_time.text())
    check("재생 단추는 그림으로 크게", not w.btn_music_play.icon().isNull()
          and w.btn_music_play.width() >= 40 and w.btn_music_play.height() >= 30)
    m.clear()
    pump(0.1)
    check("곡이 없으면 --:--", w.lbl_music_time.text() == "--:-- / --:--", w.lbl_music_time.text())
    m.set_playlist(songs, 0, autoplay=False)
    w.btn_music_mode.click() if m.mode == "continuous" else None

    print("\n6) 다시 켜도 유지")
    grab_path = os.path.join(_TMP, "toolbar.png")
    w.grab().save(grab_path)
    w.close()
    pump(0.2)
    w2 = MainWindow()
    pump(0.2)
    check("한 곡씩 유지", w2.music.mode == "single" and w2.btn_music_mode.text() == w2.t("music_mode_single"))
    w2.btn_music_mode.click()
    check("다시 누르면 연속 재생", w2.music.mode == "continuous" and w2.btn_music_repeat.text() == "🔁")
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
