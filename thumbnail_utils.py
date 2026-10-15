# -*- coding: utf-8 -*-
"""
이미지/동영상 썸네일 생성 및 캐싱 (dual_presenter/thumbnail_loader.py 패턴 재사용)
"""
import os
import hashlib
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

from PySide6.QtCore import QObject, Signal, QRunnable
from PySide6.QtGui import QPixmap, QColor, QPainter

THUMB_CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "BgTextPresenter" / "thumb_cache"
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif', '.tiff', '.ico'}
VIDEO_EXTS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.webm', '.flv', '.m4v', '.mpg', '.mpeg', '.ts', '.m2ts'}


def _get_cache_path(file_path: str, width: int, height: int, variant: str = "") -> str:
    stat = os.stat(file_path)
    raw = f"{file_path}_{stat.st_mtime}_{stat.st_size}_{width}x{height}{variant}"
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return str(THUMB_CACHE_DIR / f"{h}.png")


def _add_play_badge(pil_img):
    """비디오 썸네일에 재생 버튼 뱃지 추가"""
    w, h = pil_img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = w // 2, h // 2
    r = min(w, h) // 5
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, 160), outline=(255, 255, 255, 220), width=2)
    tri = r * 0.6
    draw.polygon([
        (cx - tri * 0.4, cy - tri * 0.7),
        (cx - tri * 0.4, cy + tri * 0.7),
        (cx + tri * 0.8, cy)
    ], fill=(255, 255, 255, 230))
    return Image.alpha_composite(pil_img.convert("RGBA"), overlay)


def generate_image_thumb(file_path: str, width=96, height=72) -> str:
    out = _get_cache_path(file_path, width, height)
    if os.path.exists(out):
        return out
    try:
        with Image.open(file_path) as img:
            # JPEG는 축소 배율을 미리 알려 주면 훨씬 빨리 읽힌다
            # (슬라이드를 원본 크기로 내보내면 그림이 커지므로 차이가 크다)
            try:
                img.draft("RGB", (width, height))
            except Exception:
                pass
            img = img.convert("RGB")
            img.thumbnail((width, height), Image.Resampling.LANCZOS)
            tw, th = img.size
            canvas = Image.new("RGB", (width, height), (30, 30, 30))
            canvas.paste(img, ((width - tw) // 2, (height - th) // 2))
            canvas.save(out, "PNG")
        return out
    except Exception as e:
        print(f"Error making image thumb for {file_path}: {e}")
        return ""


def generate_video_thumb(file_path: str, width=96, height=72, badge=True) -> str:
    """동영상 썸네일. badge=False 면 재생 단추 없이 장면만 (단추는 화면에서 따로 그린다)"""
    out = _get_cache_path(file_path, width, height, "" if badge else "_plain")
    if os.path.exists(out):
        return out
    try:
        import cv2
        cap = cv2.VideoCapture(file_path)
        if not cap.isOpened():
            return ""
        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        target = min(int(fps * 1.0), max(0, int(total // 2)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            return ""
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(frame_rgb)
        pil.thumbnail((width, height), Image.Resampling.LANCZOS)
        tw, th = pil.size
        canvas = Image.new("RGB", (width, height), (20, 20, 20))
        canvas.paste(pil, ((width - tw) // 2, (height - th) // 2))
        (_add_play_badge(canvas) if badge else canvas).save(out, "PNG")
        return out
    except Exception as e:
        print(f"Error making video thumb for {file_path}: {e}")
        return ""


def get_thumbnail(file_path: str, width=96, height=72, badge=True) -> str:
    if not file_path or not os.path.exists(file_path):
        return ""
    ext = os.path.splitext(file_path)[1].lower()
    if ext in IMAGE_EXTS:
        return generate_image_thumb(file_path, width, height)
    elif ext in VIDEO_EXTS:
        return generate_video_thumb(file_path, width, height, badge=badge)
    return ""


def image_is_readable(file_path: str) -> bool:
    """그림을 실제로 읽을 수 있는지 (저장·동기화 중이라 아직 비어 있거나 잠긴 파일을 거른다).
    작게 줄여 읽으므로(JPEG 는 1/8 로 풀기) 큰 사진도 빠르다."""
    try:
        from PySide6.QtGui import QImageReader
        from PySide6.QtCore import QSize
        reader = QImageReader(file_path)
        size = reader.size()
        if not size.isValid() or size.width() <= 0:
            return False
        reader.setScaledSize(QSize(max(1, size.width() // 8), max(1, size.height() // 8)))
        return not reader.read().isNull()
    except Exception:
        return False


def is_video_file(path) -> bool:
    return bool(path) and os.path.splitext(str(path))[1].lower() in VIDEO_EXTS


def image_has_transparency(file_path: str) -> bool:
    """이미지 파일이 실제로 투명한(완전 불투명하지 않은) 픽셀을 포함하는지 검사.

    배경이 제거된(배경 없는) PNG처럼 동영상/배경 이미지 위에 겹쳐 그릴
    오버레이 이미지인지 판별하는 데 사용한다. 알파 채널이 있어도 전부
    불투명(255)이면 오버레이로 취급하지 않는다.
    """
    try:
        with Image.open(file_path) as img:
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                alpha = img.convert("RGBA").getchannel("A")
                return alpha.getextrema()[0] < 255
    except Exception as e:
        print(f"Error checking transparency for {file_path}: {e}")
    return False


def make_color_swatch_pixmap(color: QColor, width=48, height=36) -> QPixmap:
    """색상 목록/버튼에 사용할 단색 견본 픽셀맵"""
    pm = QPixmap(width, height)
    pm.fill(QColor(color))
    return pm


def make_checker_pixmap(width=48, height=36, tile=6) -> QPixmap:
    """투명 배경을 나타내는 체커보드 견본 픽셀맵"""
    pm = QPixmap(width, height)
    painter = QPainter(pm)
    c1 = QColor("#d8d8d8")
    c2 = QColor("#8a8a8a")
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            fill = c1 if ((x // tile) + (y // tile)) % 2 == 0 else c2
            painter.fillRect(x, y, tile, tile, fill)
    painter.end()
    return pm


class WorkerSignals(QObject):
    finished = Signal(str, str)  # file_path, thumb_path


class ThumbnailTask(QRunnable):
    def __init__(self, file_path: str, width=96, height=72, badge=True):
        super().__init__()
        self.file_path = file_path
        self.width = width
        self.height = height
        self.badge = badge
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    def run(self):
        try:
            thumb = get_thumbnail(self.file_path, self.width, self.height, badge=self.badge)
            self.signals.finished.emit(self.file_path, thumb)
        except (RuntimeError, AttributeError):
            pass


def _natural_sort_key(s: str):
    import re
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]


def scan_folder_images(folder_path: str) -> list:
    """폴더 내의 지원되는 이미지 파일들을 파일명 기준 자연 정렬하여 반환"""
    if not folder_path or not os.path.isdir(folder_path):
        return []
    images = []
    try:
        for entry in os.listdir(folder_path):
            full_path = os.path.join(folder_path, entry)
            if os.path.isfile(full_path):
                ext = os.path.splitext(entry)[1].lower()
                low = entry.lower()
                # 다른 프로그램이 저장하다 남긴 임시 파일은 사진 목록에 넣지 않는다
                # (ppt2jpg: "Slide_01.jpg.tmp.jpg", 이 프로그램: ".bgpt_note_*.tmp")
                if ".tmp." in low or low.endswith(".tmp") or low.startswith(".bgpt_note_"):
                    continue
                if ext in IMAGE_EXTS:
                    images.append(full_path)
    except Exception as e:
        print(f"Error scanning folder images for {folder_path}: {e}")
        return []

    images.sort(key=lambda p: _natural_sort_key(os.path.basename(p)))
    return images