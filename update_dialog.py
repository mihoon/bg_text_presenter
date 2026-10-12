# -*- coding: utf-8 -*-
"""
새 버전 알림 창과 업데이트 진행 (화면 부분)

- 프로그램을 켜고 몇 초 뒤 GitHub 에 새 버전이 있는지 조용히 확인한다 (exe 로 실행할 때만).
  인터넷이 없거나 GitHub 이 응답하지 않으면 아무것도 띄우지 않는다.
- 새 버전이 있으면 업데이트 창을 띄운다. 단, 이미 송출 중이면 예배를 방해하지 않도록
  창 대신 상단의 [🔔 새 버전] 단추만 금색으로 바꿔 둔다 (누르면 창이 뜬다).
- [지금 업데이트] → 내려받기(진행 막대, 취소 가능) → "지금 다시 켤까요? / 끌 때 바꾸기"
  - 지금 다시 켜기: 프로그램을 끄고 새 파일로 바꾼 뒤 다시 켠다.
  - 끌 때 바꾸기: 예배를 마치고 프로그램을 끌 때 바꿔 둔다 (다시 켜지는 않는다).
- [이 버전 건너뛰기] 를 고르면 그 버전은 다시 알리지 않는다 (단추로 직접 확인하면 보여 줌).
"""
import os
import threading

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QProgressDialog,
    QPushButton, QTextBrowser, QVBoxLayout,
)

import updater
from version import APP_VERSION

TEXTS = {
    "ko": {
        "button": "🔄 업데이트 확인",
        "button_tip": "지금 버전 v{0} · GitHub 에 새 버전이 있는지 확인합니다",
        "button_new": "🔔 새 버전 v{0}",
        "button_new_tip": "새 버전 v{0} 이 나왔습니다 - 누르면 업데이트 창이 뜹니다",
        "title": "새 버전이 나왔습니다",
        "headline": "<b>새 버전 v{0}</b> 이 나왔습니다. (지금 쓰는 버전: v{1})",
        "changes": "바뀐 점",
        "no_notes": "(설명 없음)",
        "auto": "프로그램을 켤 때 새 버전 확인",
        "install": "⬇️ 지금 업데이트",
        "open_page": "🌐 내려받는 곳 열기",
        "later": "나중에",
        "skip": "이 버전 건너뛰기",
        "manual_hint": "이 프로그램은 exe 로 실행하고 있지 않거나, 지금 폴더에 쓸 수 없어서 "
                       "자동으로 바꿔 끼울 수 없습니다. 내려받는 곳에서 새 zip 을 받아 주세요.",
        "latest_title": "업데이트 확인",
        "latest": "지금 최신 버전(v{0})을 쓰고 있습니다.",
        "error_title": "업데이트 확인",
        "error": "새 버전을 확인하지 못했습니다.\n인터넷 연결을 확인해 주세요.\n\n({0})",
        "busy_status": "🔔 새 버전 v{0} 이 나왔습니다 - 송출을 마친 뒤 위의 [🔔 새 버전] 단추를 눌러 주세요",
        "downloading": "새 버전을 내려받는 중…",
        "busy_download": "앞서 취소한 내려받기를 멈추는 중입니다. 잠시 뒤 다시 눌러 주세요",
        "downloading_mb": "새 버전을 내려받는 중… {0:.1f} / {1:.1f} MB",
        "downloading_mb_unknown": "새 버전을 내려받는 중… {0:.1f} MB",
        "extracting": "내려받은 파일을 푸는 중…",
        "cancel": "취소",
        "download_failed": "새 버전을 내려받지 못했습니다.\n\n{0}",
        "ready_title": "업데이트 준비 완료",
        "ready": "새 버전 v{0} 을 받았습니다.\n\n"
                 "프로그램을 껐다가 새 버전으로 다시 켤까요?\n"
                 "(송출 중이라면 [끌 때 바꾸기] 를 누르고, 예배를 마친 뒤 프로그램을 끄면 바뀝니다)",
        "ready_busy": "⚠️ 지금 송출 중입니다. 다시 켜는 동안(몇 초) 송출 화면이 꺼집니다.",
        "restart_now": "🔄 지금 다시 켜기",
        "on_exit": "끌 때 바꾸기",
        "on_exit_status": "새 버전 v{0} 은 프로그램을 끌 때 바뀝니다",
        "updated_status": "✅ 새 버전 v{0} 으로 바뀌었습니다",
        "update_failed_title": "업데이트 실패",
        "update_failed": "새 버전으로 바꾸지 못했습니다. 예전 버전을 그대로 씁니다.\n\n"
                         "다른 프로그램이 파일을 쓰고 있었을 수 있습니다. 다시 해 보거나, "
                         "내려받는 곳에서 zip 을 받아 직접 풀어 주세요.\n\n기록: {0}",
    },
    "en": {
        "button": "🔄 Check for updates",
        "button_tip": "Current version v{0} · check GitHub for a new version",
        "button_new": "🔔 New v{0}",
        "button_new_tip": "Version v{0} is available - click to update",
        "title": "A new version is available",
        "headline": "<b>Version v{0}</b> is available. (You have v{1})",
        "changes": "What's new",
        "no_notes": "(no description)",
        "auto": "Check for a new version at startup",
        "install": "⬇️ Update now",
        "open_page": "🌐 Open download page",
        "later": "Later",
        "skip": "Skip this version",
        "manual_hint": "This copy is not running as the exe, or its folder is not writable, "
                       "so it cannot update itself. Please download the new zip from the page.",
        "latest_title": "Check for updates",
        "latest": "You are using the latest version (v{0}).",
        "error_title": "Check for updates",
        "error": "Could not check for a new version.\nPlease check the internet connection.\n\n({0})",
        "busy_status": "🔔 Version v{0} is available - click [🔔 New] at the top after the service",
        "downloading": "Downloading the new version…",
        "busy_download": "Stopping the cancelled download - please try again in a moment",
        "downloading_mb": "Downloading the new version… {0:.1f} / {1:.1f} MB",
        "downloading_mb_unknown": "Downloading the new version… {0:.1f} MB",
        "extracting": "Unpacking…",
        "cancel": "Cancel",
        "download_failed": "Could not download the new version.\n\n{0}",
        "ready_title": "Update ready",
        "ready": "Version v{0} has been downloaded.\n\n"
                 "Restart the program now with the new version?\n"
                 "(If you are presenting, choose [On exit]; it is replaced when you close the program.)",
        "ready_busy": "⚠️ You are presenting now. The output screen goes off for a few seconds.",
        "restart_now": "🔄 Restart now",
        "on_exit": "On exit",
        "on_exit_status": "Version v{0} will be installed when you close the program",
        "updated_status": "✅ Updated to v{0}",
        "update_failed_title": "Update failed",
        "update_failed": "The update could not be installed. The previous version is still in use.\n\n"
                         "Another program may have been using the files. Try again, or download the "
                         "zip from the page and unpack it yourself.\n\nLog: {0}",
    },
}


def text(lang, key, *args):
    s = TEXTS.get(lang, TEXTS["ko"]).get(key) or TEXTS["ko"].get(key, key)
    return s.format(*args) if args else s


class UpdateDialog(QDialog):
    """새 버전 알림 창. 닫힌 뒤 self.choice 가 install / open_page / skip / later"""

    def __init__(self, parent, info, lang="ko", can_install=True, auto_check=True):
        super().__init__(parent)
        self.info = info
        self.choice = "later"
        self.setWindowTitle(text(lang, "title"))
        self.resize(560, 420)

        lay = QVBoxLayout(self)
        head = QLabel(text(lang, "headline", info.version, APP_VERSION))
        head.setTextFormat(Qt.TextFormat.RichText)
        head.setStyleSheet("font-size: 15px; padding: 4px 0;")
        lay.addWidget(head)

        lay.addWidget(QLabel(text(lang, "changes")))
        self.notes = QTextBrowser(self)
        self.notes.setOpenExternalLinks(True)
        self.notes.setMarkdown(info.notes.strip() or text(lang, "no_notes"))
        lay.addWidget(self.notes, 1)

        if not can_install:
            hint = QLabel(text(lang, "manual_hint"))
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #c98a00;")
            lay.addWidget(hint)

        self.chk_auto = QCheckBox(text(lang, "auto"), self)
        self.chk_auto.setChecked(bool(auto_check))
        lay.addWidget(self.chk_auto)

        row = QHBoxLayout()
        self.btn_skip = QPushButton(text(lang, "skip"), self)
        self.btn_skip.clicked.connect(lambda: self._done("skip"))
        row.addWidget(self.btn_skip)
        row.addStretch(1)
        self.btn_later = QPushButton(text(lang, "later"), self)
        self.btn_later.clicked.connect(lambda: self._done("later"))
        row.addWidget(self.btn_later)
        can_download = can_install and bool(info.asset_url)
        self.btn_main = QPushButton(text(lang, "install" if can_download else "open_page"), self)
        self.btn_main.setDefault(True)
        self.btn_main.setStyleSheet("font-weight: bold; padding: 6px 14px;")
        self.btn_main.clicked.connect(lambda: self._done("install" if can_download else "open_page"))
        row.addWidget(self.btn_main)
        lay.addLayout(row)

    def _done(self, choice):
        self.choice = choice
        self.accept()


class UpdateController(QObject):
    """새 버전 확인 → 알림 창 → 내려받기 → 바꿔 끼우기 흐름"""

    check_done = Signal(object, str, bool)      # ReleaseInfo|None, 오류, 직접 확인했는지
    download_progress = Signal(object, object)  # 받은 바이트, 전체 바이트
    download_stage = Signal(str)                # "extract"
    download_done = Signal(str)                 # 새 파일이 풀린 폴더
    download_failed = Signal(str)               # 오류 ("" = 취소)

    SETTINGS_AUTO = "update/auto_check"
    SETTINGS_SKIP = "update/skipped_version"

    def __init__(self, window, settings, lang_getter, is_busy=lambda: False, status=None):
        super().__init__(window)
        self.window = window
        self.settings = settings
        self._lang = lang_getter
        self._is_busy = is_busy
        self._status = status or (lambda msg, ms=8000: None)
        self.button = None
        self.pending = None             # 알려진 새 버전
        self._checking = False
        self._cancel_event = None       # 내려받기마다 따로 (취소 뒤 다시 눌러도 섞이지 않게)
        self._download_thread = None
        self._session_ending = False    # 윈도우를 끄는 중이면 '끌 때 바꾸기'를 하지 않는다
        self._progress = None
        self.ready_dir = ""             # 받아서 풀어 둔 새 버전 폴더 (끌 때 바꾸기용)
        self.ready_version = ""
        # 바꿔치기 (시험에서 바꿔 끼운다)
        self.fetch = updater.check_for_update
        self.download_func = updater.download
        self.extract_func = updater.extract_package
        self.launch_func = updater.launch_updater
        self.can_self_update = updater.can_self_update
        self.installed_dir = updater.installed_dir
        self.open_url = lambda url: QDesktopServices.openUrl(QUrl(url))
        self.quit_app = self._quit_app

        app = QApplication.instance()
        if app is not None and hasattr(app, "commitDataRequest"):
            app.commitDataRequest.connect(self._on_session_ending)

        self.check_done.connect(self._on_check_done)
        self.download_progress.connect(self._on_progress)
        self.download_stage.connect(self._on_stage)
        self.download_done.connect(self._on_downloaded)
        self.download_failed.connect(self._on_download_failed)

    # ------------------------------------------------------------------
    def lang(self):
        try:
            return self._lang() or "ko"
        except Exception:
            return "ko"

    def t(self, key, *args):
        return text(self.lang(), key, *args)

    def auto_check_enabled(self) -> bool:
        return str(self.settings.value(self.SETTINGS_AUTO, "true")).lower() in ("true", "1")

    def set_auto_check(self, on: bool):
        self.settings.setValue(self.SETTINGS_AUTO, "true" if on else "false")

    def set_button(self, button):
        self.button = button
        button.clicked.connect(self.on_button_clicked)
        self.retranslate()

    def retranslate(self):
        if self.button is None:
            return
        if self.pending is not None:
            self.button.setText(self.t("button_new", self.pending.version))
            self.button.setToolTip(self.t("button_new_tip", self.pending.version))
            self.button.setStyleSheet("QPushButton { background: #ffd866; color: #222; font-weight: bold; }")
        else:
            self.button.setText(self.t("button"))
            self.button.setToolTip(self.t("button_tip", APP_VERSION))
            self.button.setStyleSheet("")

    # ------------------------------------------------------------------
    # 확인
    # ------------------------------------------------------------------
    def start_auto_check(self, delay_ms=4000, force=False):
        """켤 때 한 번 (exe 로 실행 중이고 설정이 켜져 있을 때만)"""
        if not force and (os.environ.get("BGPT_NO_UPDATE_CHECK") or not self.installed_dir()):
            return False
        if not self.auto_check_enabled():
            return False
        QTimer.singleShot(delay_ms, lambda: self.check(manual=False))
        return True

    def on_button_clicked(self):
        if self.pending is not None:
            self.show_dialog(self.pending)
        else:
            self.check(manual=True)

    def check(self, manual=False):
        if self._checking:
            return
        self._checking = True

        def work():
            info, error = None, ""
            try:
                info = self.fetch()
            except Exception as e:
                error = str(e) or e.__class__.__name__
            self.check_done.emit(info, error, manual)

        threading.Thread(target=work, name="update-check", daemon=True).start()

    def _on_check_done(self, info, error, manual):
        self._checking = False
        if error:
            print(f"[업데이트] 확인 실패: {error}")
            if manual:
                QMessageBox.warning(self.window, self.t("error_title"), self.t("error", error))
            return
        if info is None:
            print(f"[업데이트] 최신 버전 v{APP_VERSION}")
            if manual:
                self._show_latest_box()
            return
        print(f"[업데이트] 새 버전 v{info.version} (지금 v{APP_VERSION})")
        self.pending = info
        self.retranslate()
        if not manual:
            if str(self.settings.value(self.SETTINGS_SKIP, "") or "") == info.version:
                return
            if self._is_busy():
                self._status(self.t("busy_status", info.version), 15000)
                return
        self.show_dialog(info)

    def _show_latest_box(self):
        box = QMessageBox(self.window)
        box.setWindowTitle(self.t("latest_title"))
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(self.t("latest", APP_VERSION))
        chk = QCheckBox(self.t("auto"))
        chk.setChecked(self.auto_check_enabled())
        box.setCheckBox(chk)
        box.exec()
        self.set_auto_check(chk.isChecked())

    def can_install(self) -> bool:
        try:
            return bool(self.can_self_update())
        except Exception:
            return False

    def make_dialog(self, info):
        return UpdateDialog(self.window, info, self.lang(), self.can_install(), self.auto_check_enabled())

    def show_dialog(self, info):
        dlg = self.make_dialog(info)
        dlg.exec()
        self.set_auto_check(dlg.chk_auto.isChecked())
        choice = dlg.choice
        if choice == "skip":
            self.settings.setValue(self.SETTINGS_SKIP, info.version)
        elif choice == "open_page":
            self.open_url(info.page_url)
        elif choice == "install":
            self.start_install(info)
        return choice

    # ------------------------------------------------------------------
    # 내려받기
    # ------------------------------------------------------------------
    def start_install(self, info):
        if self.ready_dir and self.ready_version == info.version and os.path.isdir(self.ready_dir):
            self._on_downloaded(self.ready_dir)
            return
        if not info.asset_url or not self.can_install():
            self.open_url(info.page_url)
            return
        if self._download_thread is not None and self._download_thread.is_alive():
            self._status(self.t("busy_download"), 5000)    # 앞서 취소한 내려받기가 아직 멈추는 중
            return
        cancel = threading.Event()
        self._cancel_event = cancel
        self._installing = info
        dlg = QProgressDialog(self.t("downloading"), self.t("cancel"), 0, 0, self.window)
        dlg.setWindowTitle(self.t("title"))
        dlg.setWindowModality(Qt.WindowModality.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.canceled.connect(self._on_cancel)
        dlg.show()
        self._progress = dlg

        folder = updater.work_dir()

        def work():
            try:
                os.makedirs(folder, exist_ok=True)
                zip_path = os.path.join(folder, info.asset_name or "update.zip")
                self.download_func(info.asset_url, zip_path,
                                   progress=lambda d, t: self.download_progress.emit(d, t),
                                   cancelled=cancel.is_set)
                self.download_stage.emit("extract")
                new_dir = self.extract_func(zip_path, os.path.join(folder, "new"))
                try:
                    os.remove(zip_path)
                except OSError:
                    pass
                self.download_done.emit(new_dir)
            except updater.UpdateCancelled:
                self.download_failed.emit("")
            except Exception as e:
                self.download_failed.emit(str(e) or e.__class__.__name__)

        self._download_thread = threading.Thread(target=work, name="update-download", daemon=True)
        self._download_thread.start()

    def _on_cancel(self):
        if self._cancel_event is not None:
            self._cancel_event.set()

    def _on_progress(self, done, total):
        dlg = self._progress
        if dlg is None:
            return
        mb = 1024 * 1024
        if total:
            dlg.setMaximum(1000)
            dlg.setValue(int(done * 1000 / total))
            dlg.setLabelText(self.t("downloading_mb", done / mb, total / mb))
        else:
            dlg.setMaximum(0)
            dlg.setLabelText(self.t("downloading_mb_unknown", done / mb))

    def _on_stage(self, stage):
        if self._progress is not None and stage == "extract":
            self._progress.setMaximum(0)
            self._progress.setLabelText(self.t("extracting"))

    def _close_progress(self):
        if self._progress is not None:
            self._progress.canceled.disconnect(self._on_cancel)
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None

    def _on_download_failed(self, error):
        self._close_progress()
        if error:
            print(f"[업데이트] 내려받기 실패: {error}")
            QMessageBox.warning(self.window, self.t("title"), self.t("download_failed", error))

    def _on_downloaded(self, new_dir):
        self._close_progress()
        info = getattr(self, "_installing", None) or self.pending
        version = info.version if info else ""
        self.ready_dir, self.ready_version = new_dir, version
        box = QMessageBox(self.window)
        box.setWindowTitle(self.t("ready_title"))
        box.setIcon(QMessageBox.Icon.Question)
        msg = self.t("ready", version)
        if self._is_busy():
            msg += "\n\n" + self.t("ready_busy")
        box.setText(msg)
        btn_now = box.addButton(self.t("restart_now"), QMessageBox.ButtonRole.AcceptRole)
        btn_exit = box.addButton(self.t("on_exit"), QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(btn_exit if self._is_busy() else btn_now)
        box.exec()
        if box.clickedButton() is btn_now:
            self.apply_now()
        else:
            self._status(self.t("on_exit_status", version), 10000)
        return box.clickedButton() is btn_now

    # ------------------------------------------------------------------
    # 바꿔 끼우기
    # ------------------------------------------------------------------
    def _launch(self, restart):
        target = self.installed_dir()
        if not self.ready_dir or not target:
            return False
        try:
            self.launch_func(self.ready_dir, target, restart=restart)
        except Exception as e:
            print(f"[업데이트] 바꾸기 시작 실패: {e}")
            return False
        self.ready_dir = ""
        return True

    def apply_now(self):
        if self._launch(restart=True):
            self.quit_app()

    def apply_on_exit(self):
        """프로그램을 끌 때 부른다 - 받아 둔 새 버전이 있으면 바꿔 끼우기를 시작한다"""
        if self.ready_dir and not self._session_ending:
            self._launch(restart=False)

    def _on_session_ending(self, *_):
        # 윈도우 종료 중에 복사하다 끊기지 않도록, 이번에는 바꾸지 않는다 (다음에 다시 받음)
        self._session_ending = True

    def _quit_app(self):
        self.window.close()
        QApplication.quit()

    # ------------------------------------------------------------------
    # 업데이트 뒤 다시 켜졌을 때
    # ------------------------------------------------------------------
    def handle_startup_args(self, argv):
        result = updater.last_update_result()
        last_log = os.path.join(updater.work_dir(), "update_log.last.txt")
        if result:                      # 한 번만 알리도록 기록 이름을 바꿔 둔다
            try:
                os.replace(updater.update_log_path(), last_log)
            except OSError:
                pass
        if "--updated" in argv or result == "done":
            self._status(self.t("updated_status", APP_VERSION), 15000)
        if "--update-failed" in argv or result == "failed":
            QTimer.singleShot(500, lambda: QMessageBox.warning(
                self.window, self.t("update_failed_title"), self.t("update_failed", last_log)))
            return                      # 실패 기록은 이번에는 남겨 둔다 (다음에 켤 때 지움)
        # 지난번 업데이트가 남긴 임시 파일(수백 MB)은 조금 있다 지운다
        if os.path.isdir(updater.work_dir()):
            QTimer.singleShot(15000, self._cleanup_if_idle)

    def _cleanup_if_idle(self):
        if self._progress is None and not self.ready_dir:
            updater.cleanup_work_dir()
