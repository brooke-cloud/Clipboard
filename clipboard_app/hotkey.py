from __future__ import annotations

import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal
from PySide6.QtGui import QKeySequence

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes


MODIFIERS = {"CTRL": 0x0002, "SHIFT": 0x0004, "ALT": 0x0001, "META": 0x0008, "WIN": 0x0008}


class HotkeyError(ValueError):
    pass


def parse_hotkey(sequence: str) -> tuple[int, int]:
    parts = [p.strip().upper() for p in sequence.replace(" ", "").split("+") if p.strip()]
    if len(parts) < 2:
        raise HotkeyError("快捷键必须包含 Ctrl、Alt、Shift 或 Win 修饰键")
    modifiers = 0
    for part in parts[:-1]:
        if part not in MODIFIERS:
            raise HotkeyError(f"不支持的修饰键：{part}")
        modifiers |= MODIFIERS[part]
    key = parts[-1]
    if len(key) == 1 and (key.isalpha() or key.isdigit()):
        vk = ord(key)
    elif key.startswith("F") and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise HotkeyError("仅支持字母、数字或 F1–F24 作为主键")
    if not modifiers:
        raise HotkeyError("快捷键至少需要一个修饰键")
    return modifiers, vk


class NativeHotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        if sys.platform == "win32" and event_type in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam == GlobalHotkey.HOTKEY_ID:
                self.callback()
                return True, 0
        return False, 0


class GlobalHotkey(QObject):
    activated = Signal()
    HOTKEY_ID = 0xC1A0

    def __init__(self, app):
        super().__init__()
        self._registered = False
        self._sequence = ""
        self._filter = NativeHotkeyFilter(self.activated.emit)
        app.installNativeEventFilter(self._filter)

    @property
    def sequence(self) -> str:
        return self._sequence

    def register(self, sequence: str) -> tuple[bool, str]:
        try:
            modifiers, key = parse_hotkey(sequence)
        except HotkeyError as exc:
            return False, str(exc)
        if sys.platform != "win32":
            return False, "全局快捷键仅支持 Windows"
        previous = self._sequence if self._registered else ""
        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
            self._registered = False
        if ctypes.windll.user32.RegisterHotKey(None, self.HOTKEY_ID, modifiers | 0x4000, key):
            self._registered, self._sequence = True, sequence
            return True, ""
        if previous:
            old_mod, old_key = parse_hotkey(previous)
            self._registered = bool(ctypes.windll.user32.RegisterHotKey(None, self.HOTKEY_ID, old_mod | 0x4000, old_key))
            self._sequence = previous if self._registered else ""
        return False, "快捷键已被其他程序占用，已保留原快捷键"

    def unregister(self) -> None:
        if self._registered and sys.platform == "win32":
            ctypes.windll.user32.UnregisterHotKey(None, self.HOTKEY_ID)
        self._registered, self._sequence = False, ""

