# -*- coding: utf-8 -*-
"""
이미지/동영상 썸네일 생성 및 캐싱 (dual_presenter/thumbnail_loader.py 패턴 재사용)
"""
import os
import time
import hashlib
import tempfile
from collections import OrderedDict
from pathlib import Path

from PIL import Image, ImageDraw

from PySide6.QtCore import QObject, Signal, QRunnable, Qt
from PySide6.QtGui import QPixmap, QColor, QPainter, QImage, QImageReader
from PySide6.QtCore import QSize

THUMB_CACHE_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "BgTextPresenter" / "thumb_cache"
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.webp', '.gif', '.tiff', '.ico'}
VIDEO_EXTS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.webm', '.flv', '.m4v', '.mpg', '.mpeg', '.ts', '.m2ts'}


def _file_signature(file_path: str) -> str:
    """파일을 구별하는 값. 수정 시각·크기에 더해 파일 번호(st_ino)·만든 시각까지 넣어,
    폴더를 지우고 같은 이름으로 다시 만든 파일은 (시각·크기가 같더라도) 다른 파일로 본다."""
    st = os.stat(file_path)
    return f"{st.st_mtime_ns}_{st.st_size}_{getattr(st, 'st_ino', 0)}_{getattr(st, 'st_ctime_ns', 0)}"


def _get_cache_path(file_path: str, width: int, height: int, variant: str = "") -> str:
    raw = f"v2_{os.path.abspath(file_path)}_{_file_signature(file_path)}_{width}x{height}{variant}"
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


def _file_info(file_path: str) -> str:
    try:
        st = os.stat(file_path)
        with open(file_path, "rb") as f:
            head = f.read(4).hex()
        return f"{st.st_size}바이트, 머리 {head}"
    except Exception as e:
        return f"열 수 없음: {e.__class__.__name__}: {e}"


def qt_read_image(file_path: str, max_w: int = 0, max_h: int = 0):
    """Qt 로 그림 읽기 (큰 그림은 읽으면서 줄인다 - JPEG 는 빠르게 줄여 푼다). 실패하면 (None, 이유)"""
    reader = QImageReader(file_path)
    reader.setAutoTransform(True)
    size = reader.size()
    if max_w > 0 and max_h > 0 and size.isValid() and (size.width() > max_w or size.height() > max_h):
        scaled = size.scaled(max_w, max_h, Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(QSize(max(1, scaled.width()), max(1, scaled.height())))
    img = reader.read()
    if img.isNull():
        return None, reader.errorString() or "알 수 없는 오류"
    return img, ""


def pil_read_image(file_path: str, max_w: int = 0, max_h: int = 0):
    """PIL 로 그림 읽기 (Qt 가 못 읽을 때 대신). 실패하면 (None, 이유)"""
    try:
        with Image.open(file_path) as im:
            if max_w > 0 and max_h > 0:
                try:
                    im.draft("RGB", (max_w, max_h))
                except Exception:
                    pass
            has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
            im = im.convert("RGBA" if has_alpha else "RGB")
            if max_w > 0 and max_h > 0:
                im.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
            data = im.tobytes()
            fmt = QImage.Format.Format_RGBA8888 if has_alpha else QImage.Format.Format_RGB888
            bpl = im.width * (4 if has_alpha else 3)
            return QImage(data, im.width, im.height, bpl, fmt).copy(), ""
    except Exception as e:
        return None, f"{e.__class__.__name__}: {e}"


def read_image(file_path: str, max_w: int = 0, max_h: int = 0, label: str = "그림"):
    """Qt → 안 되면 PIL. 둘 다 안 되면 실행 기록에 이유를 남기고 None"""
    if not file_path or not os.path.exists(file_path):
        return None
    img, qt_err = qt_read_image(file_path, max_w, max_h)
    if img is not None:
        return img
    img, pil_err = pil_read_image(file_path, max_w, max_h)
    if img is not None:
        print(f"[{label}] Qt 로 못 읽어 PIL 로 읽음: {file_path} (Qt: {qt_err})")
        return img
    print(f"[{label}] 읽기 실패: {file_path} ({_file_info(file_path)}) - Qt: {qt_err} / PIL: {pil_err}")
    return None


_DISPLAY_CACHE = OrderedDict()      # (경로, 파일 구별 값, 최대 크기) → QPixmap  (송출 창·미리보기가 같은 그림을 두 번 읽지 않게)


def load_display_pixmap(file_path: str, max_w: int = 3840, max_h: int = 2160):
    """송출·미리보기용 그림. 화면보다 큰 그림은 줄여서 읽는다 (빠르고 메모리를 덜 쓴다).
    읽을 수 없으면 None (까만 화면 대신 부르는 쪽에서 지금 화면을 그대로 둔다)."""
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        key = (os.path.abspath(file_path), _file_signature(file_path), max_w, max_h)
    except OSError:
        return None
    pm = _DISPLAY_CACHE.get(key)
    if pm is not None:
        _DISPLAY_CACHE.move_to_end(key)
        return pm
    img = read_image(file_path, max_w, max_h, label="송출 그림")
    if img is None:
        return None
    pm = QPixmap.fromImage(img)
    if pm.isNull():
        print(f"[송출 그림] 화면용 그림으로 바꾸지 못함: {file_path} ({img.width()}x{img.height()})")
        return None
    _DISPLAY_CACHE[key] = pm
    while len(_DISPLAY_CACHE) > 6:
        _DISPLAY_CACHE.popitem(last=False)
    return pm


def runtime_info() -> str:
    """실행 환경 (실행 기록 첫 줄에 남겨 문제를 찾을 때 쓴다)"""
    try:
        import PySide6
        import PIL
        from PySide6.QtCore import qVersion
        fmts = {bytes(f).decode() for f in QImageReader.supportedImageFormats()}
        return (f"PySide6 {PySide6.__version__} / Qt {qVersion()} / Pillow {PIL.__version__} / "
                f"Qt 그림 형식 jpg={'jpg' in fmts} png={'png' in fmts} webp={'webp' in fmts}")
    except Exception as e:
        return f"실행 환경 확인 실패: {e}"


def generate_image_thumb(file_path: str, width=96, height=72) -> str:
    out = _get_cache_path(file_path, width, height)
    if os.path.exists(out):
        return out
    started = time.perf_counter()
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
        took = time.perf_counter() - started
        if took > 3:
            print(f"[썸네일] {took:.1f}초 걸림: {file_path}")
        return out
    except Exception as e:
        pil_err = f"{e.__class__.__name__}: {e}"
    # PIL 이 못 읽으면 Qt 로 한 번 더
    img, qt_err = qt_read_image(file_path, width, height)
    if img is not None:
        canvas = QImage(width, height, QImage.Format.Format_RGB32)
        canvas.fill(QColor(30, 30, 30))
        p = QPainter(canvas)
        p.drawImage((width - img.width()) // 2, (height - img.height()) // 2, img)
        p.end()
        if canvas.save(out, "PNG"):
            print(f"[썸네일] PIL 로 못 읽어 Qt 로 만듦: {file_path} (PIL: {pil_err})")
            return out
    print(f"[썸네일] 만들기 실패: {file_path} ({_file_info(file_path)}) - PIL: {pil_err} / Qt: {qt_err}")
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
    작게 줄여 읽으므로 큰 사진도 빠르다. Qt 가 못 읽어도 PIL 로 읽히면 읽을 수 있는 것으로 본다."""
    try:
        return read_image(file_path, 400, 400, label="읽기 확인") is not None
    except Exception:
        return False


def forget_thumbnails(paths, sizes):
    """이 파일들의 썸네일·송출 그림 저장분을 지운다 (다시 만들게)"""
    removed = 0
    for p in paths:
        for (w, h) in sizes:
            for variant in ("", "_plain"):
                try:
                    out = _get_cache_path(p, w, h, variant)
                except OSError:
                    continue
                if os.path.exists(out):
                    try:
                        os.remove(out)
                        removed += 1
                    except OSError:
                        pass
    for key in [k for k in _DISPLAY_CACHE if k[0] in {os.path.abspath(p) for p in paths}]:
        _DISPLAY_CACHE.pop(key, None)
    return removed


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
        except Exception as e:
            print(f"[썸네일] 예상하지 못한 오류: {self.file_path} - {e.__class__.__name__}: {e}")
            thumb = ""
        try:
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