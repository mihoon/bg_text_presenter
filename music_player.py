# -*- coding: utf-8 -*-
"""
음악 재생 (상단 툴바의 🎵 음악)

- mp3 / aac / m4a / wav / flac / ogg / wma 등 여러 파일을 골라 차례로 재생한다
- 재생 방식 두 가지
    · 연속 재생(continuous): 한 곡이 끝나면 다음 곡을 이어서 재생한다.
      목록 끝까지 재생하면 '반복'이 켜져 있으면 처음부터, 꺼져 있으면 멈춘다
    · 한 곡씩(single): 한 곡이 끝나면 멈추고 다음 곡을 준비만 해 둔다 (▶ 를 눌러야 재생).
      '반복'이 켜져 있으면 그 한 곡을 되풀이한다
- 재생할 수 없는 파일은 건너뛴다 (전부 안 되면 멈춘다)
- 플레이어는 처음 재생할 때 만든다 (프로그램 시작 시간을 늘리지 않기 위해)
"""
import os

from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

MODES = ("continuous", "single")
MUSIC_EXTS = (".mp3", ".aac", ".m4a", ".wav", ".flac", ".ogg", ".oga", ".opus", ".wma")


def is_music_file(path) -> bool:
    return bool(path) and os.path.splitext(str(path))[1].lower() in MUSIC_EXTS


class MusicController(QObject):
    state_changed = Signal(str)             # "playing" / "paused" / "stopped"
    track_changed = Signal(int, int, str)   # 순번(0부터), 전체 곡 수, 파일 이름
    playlist_changed = Signal()
    error = Signal(str)                     # 건너뛴 파일 이름 등 안내
    position_changed = Signal(int, int)     # 재생 위치(ms), 곡 길이(ms) - 시간 표시용

    def __init__(self, parent=None):
        super().__init__(parent)
        self.playlist = []
        self.index = -1
        self.repeat = True
        self.mode = "continuous"
        self._volume = 70
        self._state = "stopped"
        self._failures_in_row = 0
        self._load_serial = 0       # 곡을 불러올 때마다 1씩 (같은 곡 오류를 두 번 세지 않게)
        self._skipped_serial = -1
        self.player = None
        self.audio = None

    # --- 내부 ---
    def _ensure_player(self):
        if self.player is not None:
            return
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(self._volume / 100.0)
        self.player.setAudioOutput(self.audio)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.playbackStateChanged.connect(self._on_playback)
        self.player.errorOccurred.connect(self._on_error)
        self.player.positionChanged.connect(self._emit_position)
        self.player.durationChanged.connect(self._emit_position)

    def _emit_position(self, *_):
        self.position_changed.emit(self.position(), self.duration())

    def position(self) -> int:
        return int(self.player.position()) if self.player is not None else 0

    def duration(self) -> int:
        return int(self.player.duration()) if self.player is not None else 0

    def _set_state(self, state: str):
        if state != self._state:
            self._state = state
            self.state_changed.emit(state)

    def _emit_track(self):
        name = os.path.basename(self.playlist[self.index]) if 0 <= self.index < len(self.playlist) else ""
        self.track_changed.emit(self.index, len(self.playlist), name)

    def _load(self, index: int, autoplay: bool = True):
        if not self.playlist:
            return
        self._ensure_player()
        self.index = max(0, min(index, len(self.playlist) - 1))
        path = self.playlist[self.index]
        self._load_serial += 1
        self.player.setSource(QUrl.fromLocalFile(path))
        self._emit_track()
        if autoplay:
            self.player.play()

    def _on_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._failures_in_row = 0
            self._advance(from_end=True)
        elif status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._failures_in_row = 0
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._skip_broken()

    def _on_playback(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._set_state("playing")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._set_state("paused")
        else:
            self._set_state("stopped")

    def _on_error(self, err, message=""):
        if err == QMediaPlayer.Error.NoError:
            return
        self._skip_broken()

    def _skip_broken(self):
        if not (0 <= self.index < len(self.playlist)):
            return
        # 오류 신호와 '잘못된 파일' 상태가 한 곡에 대해 둘 다 올 수 있다 - 한 번만 건너뛴다
        if self._skipped_serial == self._load_serial:
            return
        self._skipped_serial = self._load_serial
        self.error.emit(os.path.basename(self.playlist[self.index]))
        self._failures_in_row += 1
        if self._failures_in_row >= len(self.playlist):
            self._failures_in_row = 0
            self.stop()
            return
        if self.mode == "single":
            # 한 곡씩: 다른 곡을 멋대로 재생하지 않고 다음 곡만 준비해 둔다
            self._cue((self.index + 1) % len(self.playlist))
            return
        self._advance(from_end=True)

    def _cue(self, index: int):
        """곡을 불러 두기만 하고 멈춘 상태로 둔다"""
        self._load(index, autoplay=False)
        if self.player is not None:
            self.player.stop()
        self._set_state("stopped")

    def _advance(self, from_end: bool):
        if not self.playlist:
            return
        if self.mode == "single" and from_end:
            if self.repeat:
                # 한 곡 반복 - 같은 곡을 처음부터
                self.player.setPosition(0)
                self.player.play()
                return
            # 다음 곡을 준비만 해 둔다 (마지막 곡이면 첫 곡)
            self._cue((self.index + 1) % len(self.playlist))
            return
        nxt = self.index + 1
        if nxt >= len(self.playlist):
            if not self.repeat and from_end:
                # 목록 끝 - 첫 곡에 맞춰 두고 멈춘다
                self._load(0, autoplay=False)
                self.player.stop()
                self._set_state("stopped")
                return
            nxt = 0
        self._load(nxt)

    # --- 목록 ---
    def set_playlist(self, paths, start_index: int = 0, autoplay: bool = True):
        self.playlist = [p for p in paths if p]
        self.index = -1
        self._failures_in_row = 0
        self.playlist_changed.emit()
        if not self.playlist:
            self.stop()
            self._emit_track()
            return
        if autoplay:
            self._load(start_index)
        else:
            self.index = max(0, min(start_index, len(self.playlist) - 1))
            self._emit_track()

    def add(self, paths):
        new = [p for p in paths if p and p not in self.playlist]
        if not new:
            return
        was_empty = not self.playlist
        self.playlist.extend(new)
        self.playlist_changed.emit()
        if was_empty:
            self.index = 0
        self._emit_track()

    def clear(self):
        self.stop()
        self.playlist = []
        self.index = -1
        self.playlist_changed.emit()
        self._emit_track()

    # --- 조작 ---
    def is_playing(self) -> bool:
        return self._state == "playing"

    @property
    def state(self) -> str:
        return self._state

    def play(self, index: int = None):
        if not self.playlist:
            return
        self._ensure_player()
        if index is not None and index != self.index:
            self._load(index)
            return
        if self.index < 0 or self.player.source().isEmpty():
            self._load(max(0, self.index))
            return
        self.player.play()

    def pause(self):
        if self.player is not None and self._state == "playing":
            self.player.pause()

    def toggle(self):
        if self._state == "playing":
            self.pause()
        else:
            self.play()

    def stop(self):
        if self.player is not None:
            self.player.stop()
        self._set_state("stopped")

    def _manual_autoplay(self) -> bool:
        """이전/다음 단추: 연속 재생이면 늘 재생, 한 곡씩이면 재생 중일 때만 재생
        (멈춰 있을 때 누르면 곡만 고른다)"""
        return self.mode != "single" or self._state == "playing"

    def next(self):
        if self.playlist:
            autoplay = self._manual_autoplay()
            if autoplay:
                self._load((self.index + 1) % len(self.playlist), autoplay=True)
            else:
                self._cue((self.index + 1) % len(self.playlist))

    def previous(self):
        if not self.playlist:
            return
        # 3초 넘게 들었으면 그 곡을 처음부터, 아니면 앞 곡으로
        autoplay = self._manual_autoplay()
        if self.player is not None and self.player.position() > 3000:
            self.player.setPosition(0)
            if self._state != "playing" and autoplay:
                self.player.play()
            return
        if autoplay:
            self._load((self.index - 1) % len(self.playlist), autoplay=True)
        else:
            self._cue((self.index - 1) % len(self.playlist))

    def set_volume(self, volume_0_100: int):
        self._volume = max(0, min(100, int(volume_0_100)))
        if self.audio is not None:
            self.audio.setVolume(self._volume / 100.0)

    def set_repeat(self, enabled: bool):
        self.repeat = bool(enabled)

    def set_mode(self, mode: str):
        """'continuous'(연속 재생) 또는 'single'(한 곡씩) - 지금 재생 중인 곡은 그대로 둔다"""
        self.mode = mode if mode in MODES else "continuous"
