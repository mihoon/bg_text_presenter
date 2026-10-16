# -*- coding: utf-8 -*-
"""
듀얼 모니터 송출 창
- 배경: 단색 / 이미지 / 동영상(재생목록 자동 반복) / 투명(데스크톱 표시)
- 이미지·동영상은 화면을 꽉 채우도록 확대-크롭(cover) 렌더링
- 위에 중앙 정렬 텍스트(문단) + 글자 테두리(외곽선) 렌더링

창 표시 방식:
- OS 전체화면(showFullScreen)은 Windows에서 불안정하므로 사용하지 않고,
  프레임 없는(Frameless) 창을 화면 해상도와 동일한 크기로 채워 전체 화면처럼 표시한다.
- 투명 배경은 네이티브 창 속성이므로 창을 숨긴 뒤 속성/플래그를 적용하고 다시 표시한다.
"""
import os
import sys
from PySide6.QtCore import Qt, QUrl, Signal, QPoint, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QFont, QFontMetrics, QPen, QBrush,
    QPainterPath, QIcon, QImage,
)
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
from thumbnail_utils import load_display_pixmap


class TextStyle:
    """텍스트 표시 스타일 (글꼴/크기/색상/테두리)"""

    VALIGNS = ("top", "center", "bottom")
    MAX_MARGIN = 45          # 위/아래 여백 최대 (화면 높이의 %)

    def __init__(self, font_family="Malgun Gothic", size=48,
                 color=None, border_enabled=True, border_width=3, border_color=None,
                 valign="center", margin_top=5, margin_bottom=5):
        self.font_family = font_family
        self.size = size
        self.color = color if color is not None else QColor("#FFFFFF")
        self.border_enabled = border_enabled
        self.border_width = border_width
        self.border_color = border_color if border_color is not None else QColor("#000000")
        # 세로 위치: "top"(위) / "center"(가운데) / "bottom"(아래)
        self.valign = valign if valign in self.VALIGNS else "center"
        # 위/아래 여백 - 화면 높이에 대한 비율(%). 모니터 해상도가 달라도 같은 자리에 온다
        self.margin_top = max(0, min(self.MAX_MARGIN, int(margin_top)))
        self.margin_bottom = max(0, min(self.MAX_MARGIN, int(margin_bottom)))

    def make_font(self) -> QFont:
        f = QFont(self.font_family)
        f.setPointSize(max(4, int(self.size)))
        return f


def _split_long_word(fm: QFontMetrics, word: str, max_width: int) -> list:
    """폭을 넘는 한 단어(띄어쓰기 없는 긴 문자열, URL 등)를 글자 단위로 나눈다."""
    parts = []
    cur = ""
    for ch in word:
        candidate = cur + ch
        if fm.horizontalAdvance(candidate) <= max_width or not cur:
            cur = candidate
        else:
            parts.append(cur)
            cur = ch
    if cur:
        parts.append(cur)
    return parts or [""]


def wrap_text_lines(font: QFont, text: str, max_width: int) -> list:
    """단어 단위로 줄바꿈(하드 줄바꿈 유지)한 줄 리스트 반환

    한 단어가 max_width 보다 넓으면 글자 단위로 나누어 화면 밖으로 넘치지 않게 한다.
    """
    fm = QFontMetrics(font)
    lines = []
    for hard_line in text.split("\n"):
        words = hard_line.split(" ")
        cur = ""
        for w in words:
            if fm.horizontalAdvance(w) > max_width:
                # 폭을 넘는 단어: 현재 줄을 끝내고 글자 단위로 분할
                if cur:
                    lines.append(cur)
                pieces = _split_long_word(fm, w, max_width)
                lines.extend(pieces[:-1])
                cur = pieces[-1]
                continue
            candidate = w if not cur else cur + " " + w
            if fm.horizontalAdvance(candidate) <= max_width or not cur:
                cur = candidate
            else:
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def text_area(rect, style: TextStyle):
    """위/아래 여백을 뺀 글자 영역의 (위쪽 y, 높이).

    가운데 정렬은 여백 없이 화면 전체의 가운데에 놓는다 (여백은 위/아래 정렬 때만).
    """
    height = rect.height()
    if getattr(style, "valign", "center") == "center":
        return rect.top(), height
    top = rect.top() + int(round(height * getattr(style, "margin_top", 0) / 100.0))
    bottom = rect.top() + height - int(round(height * getattr(style, "margin_bottom", 0) / 100.0))
    if bottom - top < 20:                     # 여백을 너무 크게 잡은 경우의 안전장치
        middle = (top + bottom) // 2
        top, bottom = middle - 10, middle + 10
    return top, bottom - top


def draw_text_overlay(painter: QPainter, rect, text: str, style: TextStyle, margin_ratio=0.06):
    """테두리(외곽선) 있는 텍스트를 가로 가운데에, 세로는 위/가운데/아래 중 고른 곳에 그린다.

    위/아래 여백(화면 높이의 %)을 뺀 영역 안에 놓으며, 전체 텍스트가 그 영역에
    들어오지 않으면 글자 크기를 자동으로 줄인다.
    """
    if not text or not text.strip():
        return
    font = style.make_font()
    fm = QFontMetrics(font)
    max_w = max(50, int(rect.width() * (1 - 2 * margin_ratio)))
    lines = wrap_text_lines(font, text, max_w)
    area_top, area_h = text_area(rect, style)

    # 전체 텍스트가 영역에 다 보이도록 필요시 자동 축소 (최소 10pt)
    while fm.lineSpacing() * len(lines) > area_h and font.pointSize() > 10:
        font.setPointSize(font.pointSize() - 2)
        fm = QFontMetrics(font)
        lines = wrap_text_lines(font, text, max_w)

    line_h = fm.lineSpacing()
    total_h = line_h * len(lines)
    valign = getattr(style, "valign", "center")
    if valign == "top":
        y = area_top
    elif valign == "bottom":
        y = area_top + area_h - total_h
    else:
        y = area_top + (area_h - total_h) / 2
    y = int(max(rect.top(), y))

    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    for line in lines:
        w = fm.horizontalAdvance(line)
        x = int(rect.left() + max(0, (rect.width() - w) / 2))
        baseline = y + fm.ascent()
        path = QPainterPath()
        path.addText(QPointF(x, baseline), font, line)
        if style.border_enabled and style.border_width > 0:
            pen = QPen(style.border_color, style.border_width,
                       Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.strokePath(path, pen)
        painter.fillPath(path, QBrush(style.color))
        y += line_h
    painter.restore()


SUBTITLE_FONT_FAMILY = "Malgun Gothic"
SUBTITLE_BASE_HEIGHT = 1080      # 자막 크기는 1080줄 화면 기준 픽셀 (화면 크기에 비례해 그린다)


def draw_subtitle(painter: QPainter, rect, text: str, size_px: int,
                  color: QColor = None, outline: QColor = None):
    """동영상 자막을 화면 아래쪽 가운데에 테두리 있는 글자로 그린다.

    size_px 는 1080줄 화면에서의 글자 높이(픽셀)이며, 실제 화면 높이에 비례해
    키우거나 줄인다 - 송출 창과 미리보기에서 같은 비율로 보이게 하기 위해서다.
    """
    if not text or not text.strip() or rect.height() <= 0:
        return
    scale = rect.height() / float(SUBTITLE_BASE_HEIGHT)
    px = max(8, int(round(size_px * scale)))
    font = QFont(SUBTITLE_FONT_FAMILY)
    font.setPixelSize(px)
    font.setBold(True)
    fm = QFontMetrics(font)
    max_w = max(50, int(rect.width() * 0.9))
    lines = wrap_text_lines(font, text, max_w)
    line_h = fm.lineSpacing()
    bottom_gap = int(rect.height() * 0.06)
    y = int(rect.bottom() - bottom_gap - line_h * len(lines))
    y = max(int(rect.top()), y)

    pen = QPen(outline if outline is not None else QColor(0, 0, 0),
               max(2.0, px / 9.0), Qt.PenStyle.SolidLine,
               Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    brush = QBrush(color if color is not None else QColor(255, 255, 255))
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    for line in lines:
        w = fm.horizontalAdvance(line)
        x = int(rect.left() + max(0, (rect.width() - w) / 2))
        path = QPainterPath()
        path.addText(QPointF(x, y + fm.ascent()), font, line)
        painter.strokePath(path, pen)
        painter.fillPath(path, brush)
        y += line_h
    painter.restore()


def fit_rect(image_w: int, image_h: int, area_w: int, area_h: int) -> QRectF:
    """그림을 비율을 지키며 영역 안에 맞췄을 때의 위치 (남는 곳은 여백)"""
    if image_w <= 0 or image_h <= 0 or area_w <= 0 or area_h <= 0:
        return QRectF(0, 0, max(0, area_w), max(0, area_h))
    scale = min(area_w / float(image_w), area_h / float(image_h))
    w, h = image_w * scale, image_h * scale
    return QRectF((area_w - w) / 2.0, (area_h - h) / 2.0, w, h)


def render_thumbnail(width: int, height: int,
                     bg_color: QColor, bg_pixmap: QImage = None,
                     text: str = "", style: TextStyle = None) -> QPixmap:
    """송출 화면을 작은 박스로 미리 렌더링한 썸네일 생성

    - 배경: 단색 또는 이미지(cover) 또는 QImage
    - 텍스트: draw_text_overlay와 동일한 알고리즘으로 그림
    """
    pix = QPixmap(width, height)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    rect = pix.rect()

    if bg_pixmap is not None and not bg_pixmap.isNull():
        scaled = bg_pixmap.scaled(
            rect.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (rect.width() - scaled.width()) // 2
        y = (rect.height() - scaled.height()) // 2
        p.drawImage(x, y, scaled)
    else:
        p.fillRect(rect, bg_color)

    if text and style is not None:
        draw_text_overlay(p, rect, text, style)

    p.end()
    return pix


class TextOverlayLabel(QWidget):
    """배경/동영상 위에 얹히는 투명 텍스트 오버레이"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._text = ""
        self._style = TextStyle()

    def set_text(self, text: str):
        self._text = text or ""
        self.update()

    def text(self) -> str:
        return self._text

    def clear_text(self):
        self._text = ""
        self.update()

    def set_style(self, style: TextStyle):
        self._style = style
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        draw_text_overlay(painter, self.rect(), self._text, self._style)
        painter.end()


def extract_video_first_frame(file_path: str) -> QImage:
    """비디오의 첫 프레임을 QImage로 즉시 추출 (재생 지연 또는 코덱 버퍼링 시 검은 화면 방지)"""
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        import cv2
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return None
        ret, frame = cap.read()
        cap.release()
        if ret and frame is not None:
            h, w, ch = frame.shape
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            bytes_per_line = ch * w
            return QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
    except Exception as e:
        print(f"Error extracting video first frame for {file_path}: {e}")
    return None


class PresenterWindow(QWidget):
    """듀얼 디스플레이(또는 창 모드) 송출 창"""

    media_state_changed = Signal(str)          # "playing", "paused", "stopped"
    playlist_item_changed = Signal(int, int, str)  # (현재 순번, 전체 개수, 파일명)
    video_frame_updated = Signal(object)       # 현재 동영상 프레임 (QImage) - 미리보기용

    # 본문 동영상 (라이브러리에서 고른 동영상 - 배경이 아니라 그 자체가 송출 내용)
    content_state_changed = Signal(str)          # "playing" / "paused" / "stopped" / "ended"
    content_position_changed = Signal(int, int)  # 재생 위치(ms), 전체 길이(ms)
    content_frame_updated = Signal(object)       # 현재 프레임 (QImage) - 미리보기용
    content_subtitle_changed = Signal(str)       # 지금 보이는 자막
    content_error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("배경 텍스트 프리젠터 - 송출 화면")
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self.resize(1280, 720)

        # 창 상태
        self.is_transparent = False   # 배경 투명 모드 (그리기로만 전환)
        self.fill_screen = True       # 화면 전체 채움(프레임 없는 창)
        self.target_screen = None     # 표시할 모니터

        # 투명 배경 지원: 창은 항상 프레임 없는 + 투명(ARGB) 창으로 생성한다.
        # WA_TranslucentBackground는 네이티브 창 생성 전에만 적용되므로,
        # 런타임에 플래그를 바꾸지 않고 투명/불투명을 그리기로만 전환한다.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background: transparent;")

        # 배경 상태
        self.bg_color = QColor(0, 0, 0)
        self.bg_image_path = ""
        self._bg_pixmap = None
        self.bg_image_mode = "cover"  # "cover" 또는 "fit"

        # 오버레이 이미지 상태 (배경 위에 겹쳐 그리는 투명 PNG 등)
        # 배경(색상/이미지/동영상)은 그대로 둔 채 이 위에 알파 채널을 살려 그린다.
        self.overlay_image_path = ""
        self._overlay_pixmap = None

        # 동영상 상태 (QVideoSink로 프레임을 직접 받아 화면을 꽉 채워 그림)
        self._video_active = False
        self._video_image = None

        # 재생목록 상태
        self.playlist = []
        self.playlist_index = 0

        self._dragging = False
        self._drag_start_pos = QPoint()

        # 본문 동영상 상태 (플레이어는 처음 재생할 때 만든다 - 시작 시간 절약)
        self.content_player = None
        self.content_audio = None
        self.content_sink = None
        self.content_path = ""
        self._content_active = False       # 화면을 본문 동영상이 차지하고 있는지
        self._content_image = None
        self._content_state = "stopped"
        self._content_subs = None          # subtitles.SubtitleTrack
        self._subtitle_text = ""
        self._content_volume = 80
        self._content_duration = 0
        self._bg_paused_for_content = False
        self.subtitle_size = 44

        self.text_overlay = TextOverlayLabel(self)
        self.text_overlay.setGeometry(0, 0, self.width(), self.height())

        self._init_media_player()

    def _init_media_player(self):
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(0.7)
        self.player.setAudioOutput(self.audio_output)
        # QVideoSink를 통해 비디오 프레임을 직접 받아 화면에 cover 형태로 렌더링
        self.video_sink = QVideoSink(self)
        self.player.setVideoSink(self.video_sink)
        self.video_sink.videoFrameChanged.connect(self._on_video_frame)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.playbackStateChanged.connect(self._on_playback_state)
        self.player.errorOccurred.connect(self._on_player_error)

    def _on_player_error(self, error, error_string=""):
        print(f"[PresenterWindow] QMediaPlayer error: {error} - {error_string}")

    def _on_video_frame(self, frame):
        img = frame.toImage()
        if not img.isNull():
            self._video_image = img
            self.video_frame_updated.emit(img)
            self.update()

    # ---------------- 창 상태 (프레임 없는 전체 채움 / 투명) ----------------
    def _apply_geometry(self):
        """현재 상태(전체채움/창모드)에 맞게 창 크기와 위치를 적용한다."""
        if self.fill_screen and self.target_screen is not None:
            # 네이티브 핸들 생성 후 스크린 지정 (Windows에서 setScreen이 적용되도록)
            handle = self.windowHandle()
            if handle is not None:
                handle.setScreen(self.target_screen)
            self.setScreen(self.target_screen)
            self.setGeometry(self.target_screen.geometry())
        elif self.target_screen is not None:
            # 창 모드: 대상 화면 중앙에 배치
            geo = self.target_screen.geometry()
            w = min(self.width(), geo.width())
            h = min(self.height(), geo.height())
            self.setGeometry(
                geo.x() + max(0, (geo.width() - w) // 2),
                geo.y() + max(0, (geo.height() - h) // 2),
                w, h,
            )
        self.text_overlay.setGeometry(0, 0, self.width(), self.height())
        self.text_overlay.raise_()
        self.update()

    def set_target_screen(self, screen):
        """표시할 모니터 지정"""
        self.target_screen = screen
        if screen is not None and self.fill_screen and self.isVisible():
            handle = self.windowHandle()
            if handle is not None:
                handle.setScreen(screen)
            self.setScreen(screen)
            self.setGeometry(screen.geometry())
            self.update()

    def set_fill_screen(self, enabled: bool):
        """True: 화면 전체를 프레임 없는 창으로 채움 / False: 일반 창"""
        self.fill_screen = bool(enabled)
        if not self.isVisible():
            self.show()
        self._apply_geometry()

    def set_transparent(self, enabled: bool):
        """투명 배경 모드 전환 (창 속성은 그대로 두고 그리기만 바꾼다)"""
        enabled = bool(enabled)
        self.is_transparent = enabled
        if enabled:
            self._stop_video_playback()
            self.bg_image_path = ""
            self._bg_pixmap = None
        self.update()

    # ---------------- 배경: 색상 / 이미지 ----------------
    def set_color_background(self, color: QColor):
        self.set_transparent(False)
        self._stop_video_playback()
        self.bg_color = QColor(color)
        self.bg_image_path = ""
        self._bg_pixmap = None
        self.update()

    def set_image_background(self, file_path: str, fit_mode="cover", transparent=False):
        self.set_transparent(transparent)
        self._stop_video_playback()
        self.bg_image_mode = fit_mode
        self.bg_image_path = file_path
        self._bg_pixmap = load_display_pixmap(file_path, *self._display_limit())
        self.update()

    def _display_limit(self):
        """송출 화면 크기 (그보다 큰 그림은 줄여서 읽는다)"""
        try:
            screen = self.screen()
            g = screen.geometry()
            ratio = screen.devicePixelRatio() or 1.0
            return max(1280, int(g.width() * ratio)), max(720, int(g.height() * ratio))
        except Exception:
            return 3840, 2160

    # ---------------- 배경: 동영상 재생목록 ----------------
    def play_playlist(self, paths: list, start_index=0):
        """동영상 재생목록 재생. 끝나면 처음부터 다시 반복."""
        self.set_transparent(False)
        self.playlist = [p for p in paths if p and os.path.exists(p)]
        if not self.playlist:
            return
        self.playlist_index = max(0, min(start_index, len(self.playlist) - 1))
        self.bg_image_path = ""
        self._bg_pixmap = None
        self._video_active = True
        self._video_image = None

        self.text_overlay.raise_()
        self._load_current_video()

    def stop_playlist(self):
        self._stop_video_playback()
        self.playlist = []
        self.playlist_index = 0

    def _stop_video_playback(self):
        if self.player.playbackState() != QMediaPlayer.PlaybackState.StoppedState:
            self.player.stop()
        self._video_active = False
        self._video_image = None
        self.update()

    def _load_current_video(self):
        if not (0 <= self.playlist_index < len(self.playlist)):
            return
        path = self.playlist[self.playlist_index]
        # 첫 프레임을 즉시 추출하여 화면 및 미리보기에 설정 (재생 대기 시간 동안 검은 화면 방지)
        first_frame = extract_video_first_frame(path)
        if first_frame is not None and not first_frame.isNull():
            self._video_image = first_frame
            self.video_frame_updated.emit(first_frame)
        self.player.setSource(QUrl.fromLocalFile(path))
        if self._content_active:
            # 본문 동영상이 화면을 차지하고 있다 - 소리가 섞이지 않게 멈춰 두었다가
            # 본문 동영상을 내리면 이어서 재생한다
            self._bg_paused_for_content = True
        else:
            self.player.play()
        self.playlist_item_changed.emit(
            self.playlist_index + 1, len(self.playlist), os.path.basename(path))
        self.update()

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._advance_playlist()

    def _advance_playlist(self):
        """재생목록 끝까지 재생되면 다시 처음부터 반복"""
        if not self.playlist:
            return
        if self.playlist_index + 1 < len(self.playlist):
            self.playlist_index += 1
        else:
            self.playlist_index = 0
        self._load_current_video()

    def _on_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.media_state_changed.emit("playing")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self.media_state_changed.emit("paused")
        else:
            self.media_state_changed.emit("stopped")

    # ---------------- 본문 동영상 (재생 단추를 눌러야 시작) ----------------
    def _ensure_content_player(self):
        if self.content_player is not None:
            return
        self.content_player = QMediaPlayer(self)
        self.content_audio = QAudioOutput(self)
        self.content_audio.setVolume(self._content_volume / 100.0)
        self.content_player.setAudioOutput(self.content_audio)
        self.content_sink = QVideoSink(self)
        self.content_player.setVideoSink(self.content_sink)
        self.content_sink.videoFrameChanged.connect(self._on_content_frame)
        self.content_player.positionChanged.connect(self._on_content_position)
        self.content_player.durationChanged.connect(self._on_content_duration)
        self.content_player.mediaStatusChanged.connect(self._on_content_status)
        self.content_player.playbackStateChanged.connect(self._on_content_playback)
        self.content_player.errorOccurred.connect(self._on_content_error)

    @property
    def content_active(self) -> bool:
        return self._content_active

    @property
    def content_state(self) -> str:
        return self._content_state

    def content_position(self) -> int:
        return int(self.content_player.position()) if self.content_player else 0

    def content_duration(self) -> int:
        if self._content_duration <= 0 and self.content_player is not None:
            return int(self.content_player.duration())
        return int(self._content_duration)

    def play_content_video(self, path: str, subtitles=None) -> bool:
        """본문 동영상을 재생한다 (같은 파일이 멈춰 있었다면 이어서 재생)."""
        if not path or not os.path.exists(path):
            return False
        self._ensure_content_player()
        same = (path == self.content_path and self._content_active)
        self.content_path = path
        self._content_subs = subtitles

        # 배경 동영상은 가려지므로 잠시 멈춘다 (소리가 섞이지 않게) - 끝나면 이어서 재생
        if (self._video_active and not self._bg_paused_for_content
                and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState):
            self.player.pause()
            self._bg_paused_for_content = True

        self._content_active = True
        if not same:
            self._set_subtitle_text("")
            first = extract_video_first_frame(path)
            self._content_image = first if (first is not None and not first.isNull()) else None
            if self._content_image is not None:
                self.content_frame_updated.emit(self._content_image)
            url = QUrl.fromLocalFile(path)
            if self.content_player.source() != url:
                self._content_duration = 0
                self.content_player.setSource(url)
            else:
                # 같은 파일을 내렸다가 다시 트는 경우 - Qt 는 같은 주소로 setSource 하면
                # 다시 읽지 않아(길이 알림도 다시 오지 않는다) 처음으로 되감기만 한다
                self._content_duration = int(self.content_player.duration())
                self.content_player.setPosition(0)
        elif self._content_state == "ended":
            self.content_player.setPosition(0)
        self.text_overlay.raise_()
        self.content_player.play()
        self.update()
        return True

    def pause_content_video(self):
        if self.content_player is not None and self._content_active:
            self.content_player.pause()

    def toggle_content_video(self):
        """재생 ↔ 일시정지 (끝난 뒤에는 처음부터 다시)"""
        if self.content_player is None or not self._content_active:
            return
        if self._content_state == "playing":
            self.content_player.pause()
        else:
            if self._content_state == "ended":
                self.content_player.setPosition(0)
            self.content_player.play()

    def stop_content_video(self):
        """본문 동영상을 내리고, 멈춰 두었던 배경 동영상을 이어서 재생한다."""
        was_active = self._content_active
        self._content_active = False
        if self.content_player is not None:
            self.content_player.stop()
        self._content_image = None
        self._set_subtitle_text("")
        if self._bg_paused_for_content:
            self._bg_paused_for_content = False
            if self._video_active:
                self.player.play()
        if was_active:
            self._set_content_state("stopped")
        self.update()

    def seek_content_video(self, position_ms: int):
        if self.content_player is not None and self._content_active:
            self.content_player.setPosition(max(0, int(position_ms)))

    def set_content_volume(self, volume_0_100: int):
        self._content_volume = max(0, min(100, int(volume_0_100)))
        if self.content_audio is not None:
            self.content_audio.setVolume(self._content_volume / 100.0)

    def set_content_subtitles(self, track):
        """자막을 바꾼다 (None 이면 자막 없음) - 재생 중에도 바로 반영"""
        self._content_subs = track
        self._refresh_subtitle(self.content_position())

    def set_subtitle_size(self, size_px: int):
        self.subtitle_size = max(8, int(size_px))
        self.update()

    def subtitle_text(self) -> str:
        return self._subtitle_text

    def _set_content_state(self, state: str):
        if state != self._content_state:
            self._content_state = state
            self.content_state_changed.emit(state)

    def _set_subtitle_text(self, text: str):
        if text != self._subtitle_text:
            self._subtitle_text = text
            self.content_subtitle_changed.emit(text)
            self.update()

    def _refresh_subtitle(self, position_ms: int):
        track = self._content_subs
        self._set_subtitle_text(track.text_at(position_ms) if (track and self._content_active) else "")

    def _on_content_frame(self, frame):
        if not self._content_active:
            return
        img = frame.toImage()
        if not img.isNull():
            self._content_image = img
            self.content_frame_updated.emit(img)
            self.update()

    def _on_content_position(self, position):
        self._refresh_subtitle(int(position))
        self.content_position_changed.emit(int(position), int(self._content_duration))

    def _on_content_duration(self, duration):
        self._content_duration = int(duration)
        self.content_position_changed.emit(self.content_position(), int(duration))

    def _on_content_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self._content_active:
            # 끝나면 마지막 장면을 그대로 두고(ESC나 다른 송출로 내린다) 자막만 지운다
            self._set_subtitle_text("")
            self._set_content_state("ended")
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            self._on_content_error(None, "재생할 수 없는 동영상 형식입니다.")

    def _on_content_playback(self, state):
        if not self._content_active:
            return
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._set_content_state("playing")
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._set_content_state("paused")
        elif (self.content_player is not None
              and self.content_player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia):
            self._set_content_state("ended")

    def _on_content_error(self, error, error_string=""):
        message = error_string or (self.content_player.errorString() if self.content_player else "")
        print(f"[PresenterWindow] 본문 동영상 오류: {error} - {message}")
        self.content_error.emit(message or "동영상을 재생하지 못했습니다.")

    # ---------------- 오버레이 이미지 (배경 유지, 위에 겹쳐 그리기) ----------------
    def set_overlay_image(self, file_path: str):
        """현재 배경(동영상/이미지/색상)은 그대로 둔 채 이미지를 그 위에 겹쳐 그린다.

        배경이 제거된(투명) PNG를 동영상이나 배경 이미지 위에 띄울 때 사용한다.
        set_image_background()와 달리 재생 중인 동영상을 멈추지 않는다.
        """
        self.overlay_image_path = file_path or ""
        self._overlay_pixmap = load_display_pixmap(file_path, *self._display_limit())
        self.update()

    def clear_overlay_image(self):
        self.overlay_image_path = ""
        self._overlay_pixmap = None
        self.update()

    # ---------------- 텍스트 오버레이 ----------------
    def set_text(self, text: str):
        self.text_overlay.set_text(text)

    def clear_text(self):
        self.text_overlay.clear_text()

    def has_text(self) -> bool:
        """지금 화면에 텍스트가 떠 있는지 (ESC 단계 판단용)"""
        try:
            return bool((self.text_overlay.text() or "").strip())
        except RuntimeError:
            return False

    def set_text_style(self, style: TextStyle):
        self.text_overlay.set_style(style)

    def set_volume(self, volume_0_100: int):
        self.audio_output.setVolume(max(0, min(100, volume_0_100)) / 100.0)

    # ---------------- 렌더링 ----------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        # 본문 동영상이 화면을 다 덮을 때는 가려질 배경을 그리지 않는다
        # (큰 배경 사진을 프레임마다 다시 그리면 동영상이 끊길 수 있다)
        if self._content_active:
            painter.fillRect(self.rect(), QColor(0, 0, 0))
            image = self._content_image
            if image is not None and not image.isNull():
                painter.drawImage(
                    fit_rect(image.width(), image.height(), self.width(), self.height()), image)
            if self._subtitle_text:
                draw_subtitle(painter, self.rect(), self._subtitle_text, self.subtitle_size)
            painter.end()
            return

        # 1. 배경
        if self.is_transparent:
            # 완전 투명 (데스크톱이 비침)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 0))
            if self.bg_image_path and self._bg_pixmap and not self._bg_pixmap.isNull():
                self._draw_cover(painter, self._bg_pixmap)
        else:
            painter.fillRect(self.rect(), self.bg_color)

            # 배경 이미지 (화면을 꽉 채우도록 확대-크롭)
            if self.bg_image_path and self._bg_pixmap and not self._bg_pixmap.isNull():
                self._draw_cover(painter, self._bg_pixmap)
            # 동영상 프레임 (화면을 꽉 채우도록 확대-크롭)
            elif self._video_active and self._video_image is not None and not self._video_image.isNull():
                self._draw_cover(painter, self._video_image)

        # 2. 오버레이 이미지 (배경 위에 알파 채널을 살려 겹쳐 그림)
        if self.overlay_image_path and self._overlay_pixmap and not self._overlay_pixmap.isNull():
            self._draw_overlay_image(painter, self._overlay_pixmap)

        painter.end()

    def _draw_cover(self, painter: QPainter, image):
        """화면 전체에 비율 유지 렌더링 (cover: 확대-크롭, fit: 화면 안에 맞춤)"""
        mode = (
            Qt.AspectRatioMode.KeepAspectRatio
            if getattr(self, "bg_image_mode", "cover") == "fit"
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
            painter.drawPixmap(x, y, scaled)
        else:
            scaled = image.scaled(
                self.size(),
                mode,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawImage(x, y, scaled)

    def _draw_overlay_image(self, painter: QPainter, pixmap: QPixmap):
        """오버레이 이미지를 화면 안에 비율 유지로 맞춰(fit) 중앙에 그린다.

        cover(확대-크롭)와 달리 잘리지 않게 하여 투명 PNG의 여백이
        그대로 배경(동영상/이미지)을 비추도록 한다.
        """
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (self.width() - scaled.width()) // 2
        y = (self.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.text_overlay.setGeometry(0, 0, self.width(), self.height())

    # 창 이동(드래그) & 더블클릭 전체 화면 토글
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging and event.buttons() & Qt.MouseButton.LeftButton and not self.fill_screen:
            self.move(event.globalPosition().toPoint() - self._drag_start_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._dragging = False

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.set_fill_screen(not self.fill_screen)
            event.accept()