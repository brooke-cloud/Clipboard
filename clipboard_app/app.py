from __future__ import annotations

import ctypes
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QStandardPaths, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QPixmap, QPainter, QColor
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .clipboard_service import ClipboardService
from .hotkey import GlobalHotkey
from .settings import SettingsStore
from .settings_dialog import SettingsDialog
from .storage import HistoryStore
from .window import MainWindow


class SingleInstanceGuard(QObject):
    activate_requested = Signal()

    def __init__(self, server_name: str = "ClipboardV1.SingleInstance"):
        super().__init__()
        self.server_name = server_name
        self.server: QLocalServer | None = None
        self.is_primary = not self._notify_existing()
        if not self.is_primary:
            return
        QLocalServer.removeServer(server_name)
        self.server = QLocalServer(self)
        if not self.server.listen(server_name):
            self.is_primary = False
            self._notify_existing()
            return
        self.server.newConnection.connect(self._accept_activation)

    def _notify_existing(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(self.server_name)
        if not socket.waitForConnected(250):
            return False
        socket.write(b"ACTIVATE")
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        return True

    def _accept_activation(self) -> None:
        if self.server is None:
            return
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            socket.disconnectFromServer()
            socket.deleteLater()
        self.activate_requested.emit()


class ClipboardApplication:
    def __init__(self, app: QApplication, data_dir: Path | None = None):
        self.app = app
        self.app.setQuitOnLastWindowClosed(False)
        override_dir = os.environ.get("CLIPBOARD_DATA_DIR")
        base = data_dir or (Path(override_dir) if override_dir else Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)))
        self.store = HistoryStore(base)
        self.settings_store = SettingsStore(base)
        self.settings = self.settings_store.load()
        self.service = ClipboardService(self.store)
        self.window = MainWindow(self.store, self.service, self.settings)
        self.window.pin_changed.connect(self._save_pin_state)
        self.window.paste_requested.connect(self.paste_to_previous_window)
        self.window.settings_requested.connect(self.open_settings)
        self._paste_target_hwnd = 0
        self.hotkey = GlobalHotkey(app)
        self.hotkey.activated.connect(self.toggle_window)
        self.tray = self._create_tray()
        self._foreground_timer = QTimer(self.app)
        self._foreground_timer.setInterval(250)
        self._foreground_timer.timeout.connect(self._remember_foreground_window)
        self._foreground_timer.start()
        if self.settings.hotkey_enabled:
            ok, error = self.hotkey.register(self.settings.hotkey)
            if not ok:
                self.show_action.setText("打开 Clipboard（快捷键不可用）")
                self.tray.showMessage("Clipboard 快捷键", error, QSystemTrayIcon.Warning, 5000)

    def _icon(self) -> QIcon:
        pix = QPixmap(64, 64)
        pix.fill(QColor("#2563eb"))
        painter = QPainter(pix)
        painter.setPen(QColor("white"))
        font = painter.font(); font.setBold(True); font.setPixelSize(36); painter.setFont(font)
        painter.drawText(pix.rect(), 0x84, "C")
        painter.end()
        return QIcon(pix)

    def _create_tray(self) -> QSystemTrayIcon:
        tray = QSystemTrayIcon(self._icon(), self.app)
        tray.setToolTip("Clipboard")
        menu = QMenu()
        shortcut_label = self.settings.hotkey if self.settings.hotkey_enabled else "快捷键已关闭"
        self.show_action = QAction(f"打开 Clipboard（{shortcut_label}）", menu)
        self.show_action.triggered.connect(self.show_window)
        self.pause_action = QAction("暂停监听", menu); self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self._pause)
        settings = QAction("设置", menu); settings.triggered.connect(self.open_settings)
        quit_action = QAction("退出", menu); quit_action.triggered.connect(self.quit)
        menu.addAction(self.show_action); menu.addAction(self.pause_action); menu.addSeparator(); menu.addAction(settings); menu.addSeparator(); menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: self.toggle_window() if reason == QSystemTrayIcon.Trigger else None)
        tray.show()
        return tray

    def show_window(self) -> None:
        self._remember_foreground_window()
        if self.window.isMinimized():
            self.window.showNormal()
        self.window.show(); self.window.raise_(); self.window.activateWindow()

    def toggle_window(self) -> None:
        self.window.hide() if self.window.isVisible() else self.show_window()

    def _remember_foreground_window(self) -> None:
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        hwnd = int(user32.GetForegroundWindow())
        if not hwnd or hwnd == int(self.window.winId()) or not user32.IsWindow(hwnd):
            return
        process_id = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        if process_id.value == os.getpid():
            return
        class_name = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(hwnd, class_name, len(class_name))
        if class_name.value in {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "NotifyIconOverflowWindow"}:
            return
        self._paste_target_hwnd = hwnd

    def paste_to_previous_window(self) -> None:
        if sys.platform != "win32":
            self.window.status.setText("已复制；自动粘贴仅支持 Windows")
            return
        hwnd = self._paste_target_hwnd
        user32 = ctypes.windll.user32
        if not hwnd or not user32.IsWindow(hwnd) or hwnd == int(self.window.winId()):
            self.window.status.setText("已复制；未找到可粘贴的目标窗口")
            return
        QTimer.singleShot(120, lambda: self._send_paste(hwnd))

    def _send_paste(self, hwnd: int) -> None:
        user32 = ctypes.windll.user32
        if not user32.IsWindow(hwnd):
            return
        user32.ShowWindow(hwnd, 9)
        if not user32.SetForegroundWindow(hwnd):
            self.window.status.setText("已复制；无法激活目标窗口")
            self.show_window()
            return
        user32.keybd_event(0x11, 0, 0, 0)
        user32.keybd_event(ord("V"), 0, 0, 0)
        user32.keybd_event(ord("V"), 0, 0x0002, 0)
        user32.keybd_event(0x11, 0, 0x0002, 0)
        self.window.status.setText("已粘贴到光标位置")

    def _pause(self, paused: bool) -> None:
        self.window.set_paused(paused)
        self.pause_action.setText("恢复监听" if paused else "暂停监听")

    def open_settings(self) -> None:
        original = self.settings_store.load()
        dialog = SettingsDialog(self.settings, self._apply_settings, self._apply_hotkey, self.window)
        if dialog.exec() != dialog.Accepted:
            self.settings = original
            self.window.apply_settings(original)

    def _apply_settings(self, settings, persist: bool) -> None:
        self.settings = settings
        self.window.apply_settings(settings)
        if persist: self.settings_store.save(settings)

    def _save_pin_state(self, pinned: bool) -> None:
        self.settings.always_on_top = pinned
        self.settings_store.save(self.settings)

    def _apply_hotkey(self, sequence: str, enabled: bool) -> bool:
        if not enabled:
            self.hotkey.unregister()
            self.show_action.setText("打开 Clipboard（快捷键已关闭）")
            return True
        ok, error = self.hotkey.register(sequence)
        if not ok: QMessageBox.warning(self.window, "快捷键注册失败", error)
        else: self.show_action.setText(f"打开 Clipboard（{sequence}）")
        return ok

    def quit(self) -> None:
        self._foreground_timer.stop()
        self.hotkey.unregister()
        self.service.clipboard.dataChanged.disconnect(self.service._schedule)
        self.tray.hide()
        self.window.quit()
        self.store.close()
        self.app.quit()


def run() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Clipboard")
    app.setOrganizationName("Clipboard")
    instance = SingleInstanceGuard()
    if not instance.is_primary:
        return 0
    controller = ClipboardApplication(app)
    instance.activate_requested.connect(controller.show_window)
    controller.show_window()
    return app.exec()

