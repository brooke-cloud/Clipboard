from __future__ import annotations

from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QKeySequenceEdit, QLabel, QMessageBox, QPushButton, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)

from .settings import AppSettings


class SettingsDialog(QDialog):
    def __init__(self, settings: AppSettings, apply_callback, hotkey_callback, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.apply_callback = apply_callback
        self.hotkey_callback = hotkey_callback
        self.setWindowTitle("设置")
        self.setMinimumWidth(390)
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        layout.addWidget(tabs)

        appearance = QWidget()
        form = QFormLayout(appearance)
        self.font_size = QSpinBox()
        self.font_size.setRange(11, 20)
        self.font_size.setSuffix(" px")
        self.font_size.setValue(settings.font_size)
        self.theme = QComboBox()
        self.theme.addItem("白色", "white")
        self.theme.addItem("浅灰", "gray")
        self.theme.addItem("深色", "dark")
        self.theme.addItem("自定义", "custom")
        self.theme.setCurrentIndex(max(0, self.theme.findData(settings.theme)))
        color_row = QHBoxLayout()
        self.color_label = QLabel(settings.custom_color or "未选择")
        choose = QPushButton("选择颜色")
        choose.clicked.connect(self._choose_color)
        color_row.addWidget(self.color_label, 1)
        color_row.addWidget(choose)
        form.addRow("字体大小", self.font_size)
        form.addRow("背景主题", self.theme)
        form.addRow("自定义颜色", color_row)
        tabs.addTab(appearance, "外观")

        hotkey = QWidget()
        hot_form = QFormLayout(hotkey)
        self.hotkey_enabled = QCheckBox("启用全局快捷键")
        self.hotkey_enabled.setChecked(settings.hotkey_enabled)
        self.hotkey_edit = QKeySequenceEdit(QKeySequence(settings.hotkey))
        self.hotkey_edit.setClearButtonEnabled(True)
        hot_form.addRow(self.hotkey_enabled)
        hot_form.addRow("打开 / 隐藏", self.hotkey_edit)
        hot_form.addRow(QLabel("快捷键需包含修饰键，支持字母、数字及 F1–F24。"))
        tabs.addTab(hotkey, "快捷键")

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        save = QPushButton("保存")
        save.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        save.clicked.connect(self._save)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)
        self.font_size.valueChanged.connect(self._preview)
        self.theme.currentIndexChanged.connect(self._preview)

    def _choose_color(self) -> None:
        color = QColorDialog.getColor(QColor(self.settings.custom_color or "#f5f7fb"), self, "选择背景颜色")
        if color.isValid():
            self.settings.custom_color = color.name()
            self.color_label.setText(color.name())
            self.theme.setCurrentIndex(self.theme.findData("custom"))
            self._preview()

    def _preview(self) -> None:
        self.settings.font_size = self.font_size.value()
        self.settings.theme = self.theme.currentData()
        self.apply_callback(self.settings, False)

    def _save(self) -> None:
        sequence = self.hotkey_edit.keySequence().toString(QKeySequence.PortableText)
        enabled = self.hotkey_enabled.isChecked()
        if enabled and not sequence:
            QMessageBox.warning(self, "快捷键无效", "请录入快捷键组合，或关闭全局快捷键。")
            return
        old_enabled, old_sequence = self.settings.hotkey_enabled, self.settings.hotkey
        if not self.hotkey_callback(sequence, enabled):
            self.settings.hotkey_enabled, self.settings.hotkey = old_enabled, old_sequence
            return
        self.settings.font_size = self.font_size.value()
        self.settings.theme = self.theme.currentData()
        self.settings.hotkey_enabled = enabled
        self.settings.hotkey = sequence
        self.apply_callback(self.settings, True)
        self.accept()

    def reject(self) -> None:
        self.apply_callback(self.settings, False)
        super().reject()

