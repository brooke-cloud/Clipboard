from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings


THEMES = {
    "white": ("#f5f7fb", "#ffffff", "#182033", "#64748b"),
    "gray": ("#e8edf3", "#f8fafc", "#182033", "#64748b"),
    "dark": ("#171a21", "#242833", "#f1f5f9", "#aab4c3"),
}


@dataclass(slots=True)
class AppSettings:
    font_size: int = 14
    theme: str = "dark"
    custom_color: str = ""
    hotkey: str = "Ctrl+Shift+V"
    hotkey_enabled: bool = True
    always_on_top: bool = False


class SettingsStore:
    def __init__(self, data_dir: Path):
        self.qsettings = QSettings(str(Path(data_dir) / "settings.ini"), QSettings.IniFormat)

    def load(self) -> AppSettings:
        return AppSettings(
            font_size=max(11, min(20, int(self.qsettings.value("appearance/font_size", 14)))),
            theme=str(self.qsettings.value("appearance/theme", "dark")),
            custom_color=str(self.qsettings.value("appearance/custom_color", "")),
            hotkey=str(self.qsettings.value("hotkey/sequence", "Ctrl+Shift+V")),
            hotkey_enabled=self.qsettings.value("hotkey/enabled", True, type=bool),
            always_on_top=self.qsettings.value("window/always_on_top", False, type=bool),
        )

    def save(self, value: AppSettings) -> None:
        self.qsettings.setValue("appearance/font_size", value.font_size)
        self.qsettings.setValue("appearance/theme", value.theme)
        self.qsettings.setValue("appearance/custom_color", value.custom_color)
        self.qsettings.setValue("hotkey/sequence", value.hotkey)
        self.qsettings.setValue("hotkey/enabled", value.hotkey_enabled)
        self.qsettings.setValue("window/always_on_top", value.always_on_top)
        self.qsettings.sync()


def stylesheet(settings: AppSettings) -> str:
    bg, card, fg, muted = THEMES.get(settings.theme, THEMES["white"])
    if settings.theme == "custom" and settings.custom_color:
        bg = settings.custom_color
    scroll_track = "#171b24" if settings.theme == "dark" else bg
    scroll_handle = "#465166" if settings.theme == "dark" else "#a8b1bf"
    return f"""
        QWidget {{ color: {fg}; font-family: 'Segoe UI', 'Microsoft YaHei UI'; font-size: {settings.font_size}px; }}
        QMainWindow, QDialog, #root, #windowBody {{ background: {bg}; }}
        QFrame#titleBar {{ background: {card}; border-bottom: 1px solid rgba(128,140,160,0.22); }}
        QLabel#windowIcon {{ color: white; background: #2563eb; border-radius: 4px; font-weight: 700; }}
        QLabel#windowTitle {{ font-size: 12px; }}
        QFrame#card {{ background: {card}; border: 1px solid rgba(128,140,160,0.20); border-radius: 11px; }}
        QLineEdit, QTextEdit, QComboBox, QSpinBox, QKeySequenceEdit {{ background: {card}; border: 1px solid rgba(128,140,160,0.25); border-radius: 9px; padding: 8px 10px; }}
        QLineEdit:focus, QTextEdit:focus, QKeySequenceEdit:focus {{ border-color: #2563eb; }}
        QPushButton {{ border: none; border-radius: 8px; padding: 7px 10px; background: transparent; }}
        QPushButton:hover {{ background: rgba(37,99,235,0.12); }}
        QPushButton:checked, QPushButton#primary {{ color: white; background: #2563eb; }}
        QPushButton#pinButton {{ color: {muted}; border: 1px solid rgba(128,140,160,0.20); background: {card}; }}
        QPushButton#pinButton:hover {{ color: {fg}; border-color: rgba(37,99,235,0.65); }}
        QPushButton#pinButton:checked {{ color: white; background: #2563eb; border-color: #2563eb; }}
        QPushButton#settingsButton {{ color: {muted}; border: 1px solid rgba(128,140,160,0.20); background: {card}; }}
        QPushButton#settingsButton:hover {{ color: {fg}; border-color: rgba(37,99,235,0.65); }}
        QPushButton#titlePinButton, QPushButton#windowButton {{ padding: 0; border-radius: 5px; color: {muted}; }}
        QPushButton#titlePinButton:hover, QPushButton#windowButton:hover {{ color: {fg}; background: rgba(128,140,160,0.18); }}
        QPushButton#titlePinButton:checked {{ color: white; background: #2563eb; }}
        QPushButton#windowButton[closeButton="true"]:hover {{ color: white; background: #dc2626; }}
        QPushButton#categoryButton {{ min-height: 22px; }}
        QWidget#subcategoryBar {{ background: transparent; }}
        QPushButton#subcategoryButton {{ min-height: 20px; color: {muted}; border: 1px solid rgba(128,140,160,0.16); }}
        QPushButton#subcategoryButton:hover {{ color: {fg}; border-color: rgba(37,99,235,0.55); }}
        QPushButton#subcategoryButton:checked {{ color: white; background: #2563eb; border-color: #2563eb; }}
        QPushButton#actionButton {{ padding: 0; border-radius: 6px; color: {muted}; }}
        QPushButton#actionButton:hover {{ color: {fg}; background: rgba(37,99,235,0.16); }}
        QLabel#muted {{ color: {muted}; }}
        QLabel#cardTitle {{ color: {fg}; font-weight: 600; }}
        QScrollArea {{ border: none; background: transparent; }}
        QScrollArea > QWidget > QWidget {{ background: {bg}; }}
        QScrollBar:vertical {{ background: {scroll_track}; width: 7px; margin: 2px 0; border: none; }}
        QScrollBar::handle:vertical {{ background: {scroll_handle}; min-height: 30px; border-radius: 3px; }}
        QScrollBar::handle:vertical:hover {{ background: #64748b; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; background: none; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
        QMenu {{ background: {card}; border: 1px solid rgba(128,140,160,0.30); padding: 5px; }}
        QMenu::item {{ padding: 7px 22px 7px 10px; border-radius: 5px; }}
        QMenu::item:selected {{ background: #2563eb; color: white; }}
        QToolTip {{ color: {fg}; background: {card}; border: 1px solid #94a3b8; }}
    """

