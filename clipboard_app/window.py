from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from PySide6.QtCore import QPoint, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTextEdit,
    QVBoxLayout, QWidget,
)

from .clipboard_service import ClipboardService
from .dialog_utils import keep_dialog_above_parent
from .models import ClipboardItem, InterviewNote
from .settings import AppSettings, stylesheet
from .storage import HistoryStore


class TitleBar(QFrame):
    pin_toggled = Signal(bool)
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(36)
        self._drag_offset: QPoint | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 4, 0)
        layout.setSpacing(2)
        icon = QLabel("C")
        icon.setObjectName("windowIcon")
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(20, 20)
        title = QLabel("Clipboard")
        title.setObjectName("windowTitle")
        layout.addWidget(icon)
        layout.addWidget(title)
        layout.addStretch()
        self.pin_button = QPushButton("固定")
        self.pin_button.setObjectName("titlePinButton")
        self.pin_button.setCheckable(True)
        self.pin_button.setFixedSize(52, 28)
        self.pin_button.setToolTip("固定窗口在其他窗口上方")
        self.minimize_button = QPushButton("—")
        self.maximize_button = QPushButton("□")
        self.close_button = QPushButton("×")
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            button.setObjectName("windowButton")
            button.setFixedSize(42, 32)
        self.close_button.setProperty("closeButton", True)
        layout.addWidget(self.pin_button)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)
        self.pin_button.toggled.connect(self.pin_toggled)
        self.minimize_button.clicked.connect(self.minimize_requested)
        self.maximize_button.clicked.connect(self.maximize_requested)
        self.close_button.clicked.connect(self.close_requested)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.window().frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.LeftButton and not self.window().isMaximized():
            self.window().move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.maximize_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ReorderHandle(QPushButton):
    drag_started = Signal()
    drag_moved = Signal(QPoint)
    drag_finished = Signal()

    def __init__(self):
        super().__init__("↕")
        self.setObjectName("actionButton")
        self._dragging = False
        self.setFixedSize(28, 24)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("按住并上下拖动收藏")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._dragging = True
            self.setCursor(Qt.ClosedHandCursor)
            self.drag_started.emit()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and event.buttons() & Qt.LeftButton:
            self.drag_moved.emit(event.globalPosition().toPoint())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        was_dragging = self._dragging
        self._dragging = False
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)
        if was_dragging and event.button() == Qt.LeftButton:
            self.drag_finished.emit()


class ElidedLabel(QLabel):
    def __init__(self, text: str):
        super().__init__()
        self.full_text = text
        self.setToolTip(text)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def resizeEvent(self, event) -> None:
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.ElideRight, max(20, self.width())))
        super().resizeEvent(event)


class ContentLabel(QLabel):
    double_clicked = Signal()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class ContentEditDialog(QDialog):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("修改收藏内容")
        self.resize(520, 360)
        self.setMinimumSize(380, 280)
        keep_dialog_above_parent(self, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(12)
        hint = QLabel("修改实际复制的文字内容")
        hint.setObjectName("muted")
        layout.addWidget(hint)
        self.editor = QTextEdit()
        self.editor.setPlainText(text)
        self.editor.setAcceptRichText(False)
        layout.addWidget(self.editor, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        confirm = QPushButton("确认")
        confirm.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)
        self.editor.setFocus()

    def content(self) -> str:
        return self.editor.toPlainText()


class InterviewEditDialog(QDialog):
    def __init__(self, title: str = "", content: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加面试内容" if not title and not content else "修改面试内容")
        self.resize(540, 410)
        self.setMinimumSize(390, 310)
        keep_dialog_above_parent(self, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(10)
        title_label = QLabel("标题")
        title_label.setObjectName("muted")
        layout.addWidget(title_label)
        self.title_edit = QLineEdit(title)
        self.title_edit.setMaxLength(80)
        self.title_edit.setPlaceholderText("例如：Amazon BQ 常用回答")
        layout.addWidget(self.title_edit)
        content_label = QLabel("内容")
        content_label.setObjectName("muted")
        layout.addWidget(content_label)
        self.content_edit = QTextEdit()
        self.content_edit.setAcceptRichText(False)
        self.content_edit.setPlainText(content)
        self.content_edit.setPlaceholderText("输入需要整理或复习的面试内容…")
        layout.addWidget(self.content_edit, 1)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton("取消")
        confirm = QPushButton("保存")
        confirm.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        confirm.clicked.connect(self.accept)
        buttons.addWidget(cancel)
        buttons.addWidget(confirm)
        layout.addLayout(buttons)
        self.title_edit.setFocus()

    def values(self) -> tuple[str, str]:
        return self.title_edit.text(), self.content_edit.toPlainText()


class InterviewCard(QFrame):
    copy_requested = Signal(int)
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    drag_started = Signal(int)
    drag_moved = Signal(int, QPoint)
    drag_finished = Signal()

    def __init__(self, note: InterviewNote, reorder_enabled: bool = True):
        super().__init__()
        self.note = note
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 10, 11)
        outer.setSpacing(7)
        header = QHBoxLayout()
        header.setSpacing(4)
        title = ElidedLabel(note.title)
        title.setObjectName("cardTitle")
        header.addWidget(title, 1)
        drag_handle = ReorderHandle()
        drag_handle.setEnabled(reorder_enabled)
        if not reorder_enabled:
            drag_handle.setToolTip("清除搜索内容后可调整顺序")
        drag_handle.drag_started.connect(lambda: self.drag_started.emit(note.id))
        drag_handle.drag_moved.connect(lambda position: self.drag_moved.emit(note.id, position))
        drag_handle.drag_finished.connect(self.drag_finished.emit)
        edit = QPushButton("✎")
        edit.setObjectName("actionButton")
        edit.setFixedSize(28, 24)
        edit.setToolTip("修改标题和内容")
        edit.clicked.connect(lambda: self.edit_requested.emit(note.id))
        more = QPushButton("•••")
        more.setObjectName("actionButton")
        more.setFixedSize(32, 24)
        more.setToolTip("更多操作")
        more.clicked.connect(self._show_menu)
        header.addWidget(drag_handle)
        header.addWidget(edit)
        header.addWidget(more)
        outer.addLayout(header)
        meta = QLabel("面试  ·  " + note.updated_at.astimezone().strftime("%m-%d %H:%M"))
        meta.setObjectName("muted")
        outer.addWidget(meta)
        content = ContentLabel(note.content)
        self.content_label = content
        content.setWordWrap(True)
        content.setMinimumWidth(0)
        content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        content.setMaximumHeight(150)
        content.setTextInteractionFlags(Qt.NoTextInteraction)
        content.setToolTip("双击复制并粘贴到之前的光标位置；完整内容可在修改窗口查看")
        content.double_clicked.connect(lambda: self.copy_requested.emit(note.id))
        outer.addWidget(content)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.copy_requested.emit(self.note.id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        edit = menu.addAction("修改")
        edit.triggered.connect(lambda: self.edit_requested.emit(self.note.id))
        menu.addSeparator()
        delete = menu.addAction("删除")
        delete.triggered.connect(lambda: self.delete_requested.emit(self.note.id))
        button = self.sender()
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()))


class ItemCard(QFrame):
    copy_requested = Signal(int)
    favorite_requested = Signal(int, bool)
    delete_requested = Signal(int)
    rename_requested = Signal(int, str)
    content_modified = Signal(int, str)
    drag_started = Signal(int)
    drag_moved = Signal(int, QPoint)
    drag_finished = Signal()

    def __init__(self, item: ClipboardItem, favorite_view: bool = False, reorder_enabled: bool = True):
        super().__init__()
        self.item = item
        self.favorite_view = favorite_view
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setCursor(Qt.PointingHandCursor)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 10, 11)
        outer.setSpacing(7)
        type_names = {"text": "文字", "image": "图片", "files": "文件"}
        self.header = QHBoxLayout()
        self.header.setSpacing(4)
        header_text = item.custom_title if favorite_view and item.custom_title else type_names[item.kind] + "  ·  " + item.updated_at.astimezone().strftime("%m-%d %H:%M")
        self.meta = ElidedLabel(header_text)
        self.meta.setObjectName("cardTitle" if favorite_view else "muted")
        self.header.addWidget(self.meta, 1)
        self.header_controls = []
        if favorite_view:
            drag_handle = ReorderHandle()
            drag_handle.setEnabled(reorder_enabled)
            if not reorder_enabled:
                drag_handle.setToolTip("清除搜索内容后可调整顺序")
            self.edit_title = QPushButton("✎")
            for button in (drag_handle, self.edit_title):
                button.setObjectName("actionButton")
                button.setFixedSize(28, 24)
                self.header.addWidget(button)
            self.edit_title.setToolTip("重命名收藏")
            drag_handle.drag_started.connect(lambda: self.drag_started.emit(item.id))
            drag_handle.drag_moved.connect(lambda position: self.drag_moved.emit(item.id, position))
            drag_handle.drag_finished.connect(self.drag_finished.emit)
            self.edit_title.clicked.connect(self._begin_rename)
            self.header_controls = [drag_handle, self.edit_title]
        else:
            favorite = QPushButton("★" if item.favorite else "☆")
            favorite.setObjectName("actionButton")
            favorite.setFixedSize(28, 24)
            favorite.setToolTip("取消收藏" if item.favorite else "收藏")
            favorite.clicked.connect(lambda: self.favorite_requested.emit(item.id, not item.favorite))
            self.header.addWidget(favorite)
            self.header_controls = [favorite]
        more = QPushButton("•••")
        more.setObjectName("actionButton")
        more.setFixedSize(32, 24)
        more.setToolTip("更多操作")
        more.clicked.connect(self._show_actions_menu)
        self.header.addWidget(more)
        self.header_controls.append(more)
        outer.addLayout(self.header)
        if item.kind == "image" and item.image_path:
            image_row = QHBoxLayout()
            image_row.setSpacing(12)
            label = QLabel()
            pixmap = QPixmap(item.image_path)
            label.setFixedSize(140, 96)
            label.setAlignment(Qt.AlignCenter)
            label.setPixmap(pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            label.setStyleSheet("border-radius: 7px; background: rgba(0,0,0,0.12);")
            try:
                size_text = f"{Path(item.image_path).stat().st_size / 1024:.1f} KB"
            except OSError:
                size_text = "本地副本不可用"
            details = QLabel(f"图片\n{pixmap.width()} × {pixmap.height()}\n{size_text}")
            details.setObjectName("muted")
            details.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            image_row.addWidget(label)
            image_row.addWidget(details, 1)
            outer.addLayout(image_row)
        else:
            if item.kind == "text":
                text = item.text or ""
            else:
                names = [Path(path).name or path for path in item.files]
                text = "\n".join(names + item.files[:1])
            label = ContentLabel(text or "")
            self.content_label = label
            label.setWordWrap(True)
            label.setMinimumWidth(0)
            label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            label.setTextInteractionFlags(Qt.NoTextInteraction)
            label.setMaximumHeight(112)
            label.setToolTip("双击复制；长内容可右键查看完整内容")
            label.double_clicked.connect(lambda: self.copy_requested.emit(self.item.id))
            outer.addWidget(label)

    def _create_actions_menu(self) -> QMenu:
        menu = QMenu(self)
        if self.item.favorite and self.item.kind == "text":
            modify = menu.addAction("修改")
            modify.triggered.connect(self._begin_content_edit)
            menu.addSeparator()
        if self.item.favorite:
            unfavorite = menu.addAction("取消收藏")
            unfavorite.triggered.connect(lambda: self.favorite_requested.emit(self.item.id, False))
        else:
            favorite = menu.addAction("收藏")
            favorite.triggered.connect(lambda: self.favorite_requested.emit(self.item.id, True))
        menu.addSeparator()
        delete = menu.addAction("删除记录")
        delete.triggered.connect(lambda: self.delete_requested.emit(self.item.id))
        return menu

    def _show_actions_menu(self) -> None:
        menu = self._create_actions_menu()
        button = self.sender()
        menu.exec(button.mapToGlobal(button.rect().bottomLeft()) if isinstance(button, QPushButton) else self.mapToGlobal(self.rect().center()))

    def _begin_content_edit(self) -> None:
        if self.item.kind != "text" or not self.item.favorite:
            return
        dialog = ContentEditDialog(self.item.text or "", self)
        if dialog.exec() == QDialog.Accepted:
            self.content_modified.emit(self.item.id, dialog.content())

    def _begin_rename(self) -> None:
        if hasattr(self, "title_edit"):
            self.title_edit.setFocus()
            return
        self.meta.hide()
        for button in self.header_controls:
            button.hide()
        self.title_edit = QLineEdit(self.item.custom_title or "")
        self.title_edit.setMaxLength(80)
        self.title_edit.selectAll()
        save = QPushButton("✓")
        cancel = QPushButton("×")
        for button in (save, cancel):
            button.setObjectName("actionButton")
            button.setFixedSize(28, 24)
        save.setToolTip("保存标题")
        cancel.setToolTip("取消修改")
        self.header.insertWidget(0, self.title_edit, 1)
        self.header.insertWidget(1, save)
        self.header.insertWidget(2, cancel)
        self.rename_widgets = [self.title_edit, save, cancel]
        save.clicked.connect(self._save_rename)
        cancel.clicked.connect(self._cancel_rename)
        self.title_edit.returnPressed.connect(self._save_rename)
        self.title_edit.setFocus()

    def _save_rename(self) -> None:
        title = self.title_edit.text().strip()
        if not title:
            QMessageBox.warning(self, "标题无效", "收藏标题不能为空。")
            self.title_edit.setFocus()
            return
        self.rename_requested.emit(self.item.id, title)

    def _cancel_rename(self) -> None:
        self.parentWidget().setFocus() if self.parentWidget() else self.setFocus()
        self.meta.show()
        for button in self.header_controls:
            button.show()
        for widget in self.rename_widgets:
            widget.hide()
            self.header.removeWidget(widget)
            widget.deleteLater()
        del self.rename_widgets
        del self.title_edit

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.copy_requested.emit(self.item.id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        if self.favorite_view:
            rename = menu.addAction("重命名")
            rename.triggered.connect(self._begin_rename)
        view = None
        if self.item.kind == "text" and self.item.text:
            view = menu.addAction("查看完整文本")
        elif self.item.kind == "image" and self.item.image_path:
            view = menu.addAction("预览图片")
        if view:
            view.triggered.connect(self._show_content)
        if not menu.isEmpty():
            menu.exec(event.globalPos())

    def _show_content(self) -> None:
        if self.item.kind == "text" and self.item.text:
            dialog = QDialog(self)
            dialog.setWindowTitle("完整文本")
            dialog.resize(520, 360)
            keep_dialog_above_parent(dialog, self)
            layout = QVBoxLayout(dialog)
            text = QLabel(self.item.text)
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(text)
            layout.addWidget(scroll)
            dialog.exec()
        elif self.item.kind == "image" and self.item.image_path:
            pixmap = QPixmap(self.item.image_path)
            if not pixmap.isNull():
                dialog = QDialog(self)
                dialog.setWindowTitle("图片预览")
                dialog.resize(min(900, max(480, pixmap.width())), min(700, max(360, pixmap.height())))
                keep_dialog_above_parent(dialog, self)
                layout = QVBoxLayout(dialog)
                label = QLabel()
                label.setPixmap(pixmap)
                label.setAlignment(Qt.AlignCenter)
                scroll = QScrollArea()
                scroll.setWidget(label)
                scroll.setWidgetResizable(False)
                layout.addWidget(scroll)
                dialog.exec()


class MainWindow(QMainWindow):
    pin_changed = Signal(bool)
    paste_requested = Signal()
    settings_requested = Signal()

    def __init__(self, store: HistoryStore, service: ClipboardService, settings: AppSettings):
        super().__init__()
        self.store, self.service, self.settings = store, service, settings
        self._allow_close = False
        self._render_generation = 0
        self._render_items: list[ClipboardItem | InterviewNote] = []
        self._render_index = 0
        self.filter_kind = "all"
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setWindowTitle("Clipboard")
        self.resize(420, 620)
        self.setMinimumSize(360, 440)
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        self.title_bar = TitleBar(self)
        self.title_bar.minimize_requested.connect(self._minimize_to_tray)
        self.title_bar.maximize_requested.connect(self._toggle_maximized)
        self.title_bar.close_requested.connect(self.close)
        self.title_bar.pin_toggled.connect(self._set_pinned)
        root_layout.addWidget(self.title_bar)
        body = QWidget()
        body.setObjectName("windowBody")
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 10, 12, 12)
        layout.setSpacing(11)
        root_layout.addWidget(body, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索剪贴板内容…")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumHeight(38)
        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.search, 1)
        self.settings_button = QPushButton("设置")
        self.settings_button.setObjectName("settingsButton")
        self.settings_button.setFixedSize(58, 38)
        self.settings_button.setToolTip("打开设置")
        self.settings_button.clicked.connect(self.settings_requested)
        top.addWidget(self.settings_button)
        layout.addLayout(top)
        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 4, 0)
        nav.setSpacing(8)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for label, kind in [("全部", "all"), ("收藏", "favorite"), ("面试", "interview")]:
            button = QPushButton(label)
            button.setObjectName("categoryButton")
            button.setCheckable(True)
            button.setProperty("kind", kind)
            self.group.addButton(button)
            nav.addWidget(button, 1)
            if kind == "all": button.setChecked(True)
        layout.addLayout(nav)
        self.interview_toolbar = QWidget()
        interview_tools = QHBoxLayout(self.interview_toolbar)
        interview_tools.setContentsMargins(0, 0, 4, 0)
        interview_tools.addStretch()
        self.add_interview_button = QPushButton("＋ 添加面试内容")
        self.add_interview_button.setObjectName("primary")
        self.add_interview_button.setToolTip("新建带标题的面试笔记")
        self.add_interview_button.clicked.connect(self._add_interview_note)
        interview_tools.addWidget(self.add_interview_button)
        self.interview_toolbar.hide()
        layout.addWidget(self.interview_toolbar)
        self.type_nav = QWidget()
        self.type_nav.setObjectName("subcategoryBar")
        type_nav_layout = QHBoxLayout(self.type_nav)
        type_nav_layout.setContentsMargins(18, 0, 18, 1)
        type_nav_layout.setSpacing(8)
        self.type_group = QButtonGroup(self)
        self.type_group.setExclusive(True)
        for label, kind in [("文字", "text"), ("图片", "image"), ("文件", "files")]:
            button = QPushButton(label)
            button.setObjectName("subcategoryButton")
            button.setCheckable(True)
            button.setProperty("kind", kind)
            self.type_group.addButton(button)
            type_nav_layout.addWidget(button, 1)
        layout.addWidget(self.type_nav)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setViewportMargins(0, 0, 3, 0)
        self.scroll.verticalScrollBar().valueChanged.connect(self._load_more_if_needed)
        self.container = QWidget()
        self.items_layout = QVBoxLayout(self.container)
        self.items_layout.setContentsMargins(0, 2, 5, 8)
        self.items_layout.setSpacing(8)
        self.items_layout.setAlignment(Qt.AlignTop)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)
        bottom = QHBoxLayout()
        self.status = QLabel("●  正在监听")
        self.status.setObjectName("muted")
        self.clear_button = QPushButton("清理普通历史")
        self.clear_button.clicked.connect(self._clear)
        bottom.addWidget(self.status)
        bottom.addStretch()
        bottom.addWidget(self.clear_button)
        bottom.setContentsMargins(2, 1, 4, 0)
        layout.addLayout(bottom)
        self.search.textChanged.connect(self.refresh)
        self.group.buttonClicked.connect(self._primary_filter)
        self.type_group.buttonClicked.connect(self._type_filter)
        self.service.history_changed.connect(self.refresh)
        self.service.error.connect(lambda msg: QMessageBox.warning(self, "Clipboard", msg))
        self.apply_settings(settings)
        self.pin_button = self.title_bar.pin_button
        self.pin_button.blockSignals(True)
        self.pin_button.setChecked(settings.always_on_top)
        self.pin_button.blockSignals(False)
        self._apply_pin_state(settings.always_on_top)
        self.refresh()

    def _toggle_maximized(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    def _minimize_to_tray(self) -> None:
        self.hide()

    def apply_settings(self, settings: AppSettings) -> None:
        self.settings = settings
        self.setStyleSheet(stylesheet(settings))

    def _set_pinned(self, pinned: bool) -> None:
        self._apply_pin_state(pinned)
        self.pin_changed.emit(pinned)

    def _apply_pin_state(self, pinned: bool) -> None:
        was_visible = self.isVisible()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, pinned)
        self.pin_button.setText("已固定" if pinned else "固定")
        self.pin_button.setToolTip("取消窗口置顶" if pinned else "固定窗口在其他窗口上方")
        if was_visible:
            self.show()
            self.raise_()

    def _primary_filter(self, button) -> None:
        kind = button.property("kind")
        self.type_nav.setVisible(kind == "all")
        self.interview_toolbar.setVisible(kind == "interview")
        self.clear_button.setVisible(kind != "interview")
        if kind == "all":
            self.type_group.setExclusive(False)
            for type_button in self.type_group.buttons():
                type_button.setChecked(False)
            self.type_group.setExclusive(True)
        self.filter_kind = kind
        self.refresh()

    def _type_filter(self, button) -> None:
        all_button = next(item for item in self.group.buttons() if item.property("kind") == "all")
        all_button.setChecked(True)
        self.type_nav.show()
        self.interview_toolbar.hide()
        self.clear_button.show()
        self.filter_kind = button.property("kind")
        self.refresh()

    def refresh(self) -> None:
        self._render_generation += 1
        generation = self._render_generation
        self._render_items = []
        self._render_index = 0
        while self.items_layout.count():
            child = self.items_layout.takeAt(0)
            if child.widget():
                child.widget().hide()
                child.widget().deleteLater()
        if self.filter_kind == "interview":
            items = self.store.list_interview_notes(self.search.text().strip())
        else:
            items = self.store.list_items(self.filter_kind, self.search.text().strip())
        if not items:
            empty = QLabel("暂无记录")
            empty.setObjectName("muted")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(120)
            self.items_layout.addWidget(empty)
            return
        self._render_items = items
        self._render_index = 0
        self._render_next_batch(generation)

    def _render_next_batch(self, generation: int) -> None:
        if generation != self._render_generation:
            return
        end = min(self._render_index + 12, len(self._render_items))
        for item in self._render_items[self._render_index:end]:
            if isinstance(item, InterviewNote):
                self.items_layout.addWidget(self._create_interview_card(item))
            else:
                self.items_layout.addWidget(self._create_item_card(item))
        self._render_index = end
        QTimer.singleShot(0, lambda current=generation: self._ensure_viewport_filled(current))

    def _ensure_viewport_filled(self, generation: int) -> None:
        if generation != self._render_generation or self._render_index >= len(self._render_items):
            return
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() == 0:
            self._render_next_batch(generation)

    def _load_more_if_needed(self, value: int) -> None:
        if self._render_index >= len(self._render_items):
            return
        bar = self.scroll.verticalScrollBar()
        if bar.maximum() - value <= 180:
            self._render_next_batch(self._render_generation)

    def _create_item_card(self, item: ClipboardItem) -> ItemCard:
        card = ItemCard(
            item,
            favorite_view=self.filter_kind == "favorite",
            reorder_enabled=not self.search.text().strip(),
        )
        card.copy_requested.connect(self._copy)
        card.favorite_requested.connect(self._favorite)
        card.delete_requested.connect(self._delete)
        card.rename_requested.connect(self._rename)
        card.content_modified.connect(self._modify_content)
        card.drag_started.connect(self._start_favorite_drag)
        card.drag_moved.connect(self._drag_favorite)
        card.drag_finished.connect(self._finish_favorite_drag)
        return card

    def _create_interview_card(self, note: InterviewNote) -> InterviewCard:
        card = InterviewCard(note, reorder_enabled=not self.search.text().strip())
        card.copy_requested.connect(self._copy_interview_note)
        card.edit_requested.connect(self._edit_interview_note)
        card.delete_requested.connect(self._delete_interview_note)
        card.drag_started.connect(self._start_interview_drag)
        card.drag_moved.connect(self._drag_interview)
        card.drag_finished.connect(self._finish_interview_drag)
        return card

    def _copy_interview_note(self, note_id: int) -> None:
        note = self.store.get_interview_note(note_id)
        if note and self.service.copy_text(note.content):
            self.status.setText("正在粘贴面试内容到光标位置…")
            self.paste_requested.emit()

    def _add_interview_note(self) -> None:
        dialog = InterviewEditDialog(parent=self)
        if dialog.exec() != QDialog.Accepted:
            return
        title, content = dialog.values()
        try:
            self.store.add_interview_note(title, content)
        except ValueError as exc:
            QMessageBox.warning(self, "无法添加面试内容", str(exc))
            return
        self.status.setText("面试内容已添加")
        self.refresh()

    def _edit_interview_note(self, note_id: int) -> None:
        note = self.store.get_interview_note(note_id)
        if note is None:
            self.refresh()
            return
        dialog = InterviewEditDialog(note.title, note.content, self)
        if dialog.exec() != QDialog.Accepted:
            return
        title, content = dialog.values()
        try:
            self.store.update_interview_note(note_id, title, content)
        except ValueError as exc:
            QMessageBox.warning(self, "无法修改面试内容", str(exc))
            return
        self.status.setText("面试内容已更新")
        self.refresh()

    def _delete_interview_note(self, note_id: int) -> None:
        self.store.delete_interview_note(note_id)
        self.status.setText("面试内容已删除")
        self.refresh()

    def _start_interview_drag(self, note_id: int) -> None:
        self._dragged_interview_id = note_id

    def _drag_interview(self, note_id: int, global_position: QPoint) -> None:
        if getattr(self, "_dragged_interview_id", None) != note_id:
            return
        cards = [
            self.items_layout.itemAt(index).widget()
            for index in range(self.items_layout.count())
        ]
        cards = [card for card in cards if isinstance(card, InterviewCard)]
        current = next((index for index, card in enumerate(cards) if card.note.id == note_id), -1)
        if current < 0:
            return
        local_y = self.container.mapFromGlobal(global_position).y()
        target = len(cards) - 1
        for index, card in enumerate(cards):
            if local_y < card.geometry().center().y():
                target = index
                break
        if target != current:
            layout_item = self.items_layout.takeAt(current)
            self.items_layout.insertWidget(target, layout_item.widget())
            self.items_layout.activate()

    def _finish_interview_drag(self) -> None:
        if not hasattr(self, "_dragged_interview_id"):
            return
        ordered_ids = [
            self.items_layout.itemAt(index).widget().note.id
            for index in range(self.items_layout.count())
            if isinstance(self.items_layout.itemAt(index).widget(), InterviewCard)
        ]
        try:
            self.store.reorder_interview_notes(ordered_ids)
            self.status.setText("面试顺序已保存")
        except ValueError as exc:
            QMessageBox.warning(self, "无法调整面试顺序", str(exc))
            self.refresh()
        del self._dragged_interview_id

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and not self.isMaximized():
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                frame = self.frameGeometry()
                border = 6
                left, right = x < frame.left() + border, x >= frame.right() - border
                top, bottom = y < frame.top() + border, y >= frame.bottom() - border
                if top and left: return True, 13
                if top and right: return True, 14
                if bottom and left: return True, 16
                if bottom and right: return True, 17
                if left: return True, 10
                if right: return True, 11
                if top: return True, 12
                if bottom: return True, 15
        return super().nativeEvent(event_type, message)

    def _copy(self, item_id: int) -> None:
        item = self.store.get(item_id)
        if item and self.service.restore(item):
            self.status.setText("正在粘贴到光标位置…")
            self.paste_requested.emit()

    def _favorite(self, item_id: int, favorite: bool) -> None:
        self.store.set_favorite(item_id, favorite)
        self.refresh()

    def _delete(self, item_id: int) -> None:
        self.store.delete(item_id)
        self.refresh()

    def _rename(self, item_id: int, title: str) -> None:
        try:
            self.store.rename_favorite(item_id, title)
        except ValueError as exc:
            QMessageBox.warning(self, "标题无效", str(exc))
            return
        self.refresh()

    def _modify_content(self, item_id: int, text: str) -> None:
        try:
            self.store.update_favorite_text(item_id, text)
        except ValueError as exc:
            QMessageBox.warning(self, "无法修改内容", str(exc))
            return
        self.status.setText("收藏内容已更新")
        self.refresh()

    def _start_favorite_drag(self, item_id: int) -> None:
        self._dragged_item_id = item_id

    def _drag_favorite(self, item_id: int, global_position: QPoint) -> None:
        if getattr(self, "_dragged_item_id", None) != item_id:
            return
        cards = [
            self.items_layout.itemAt(index).widget()
            for index in range(self.items_layout.count())
        ]
        cards = [card for card in cards if isinstance(card, ItemCard)]
        current = next((index for index, card in enumerate(cards) if card.item.id == item_id), -1)
        if current < 0:
            return
        local_y = self.container.mapFromGlobal(global_position).y()
        target = len(cards) - 1
        for index, card in enumerate(cards):
            if local_y < card.geometry().center().y():
                target = index
                break
        if target != current:
            layout_item = self.items_layout.takeAt(current)
            self.items_layout.insertWidget(target, layout_item.widget())
            self.items_layout.activate()

    def _finish_favorite_drag(self) -> None:
        if not hasattr(self, "_dragged_item_id"):
            return
        ordered_ids = [
            self.items_layout.itemAt(index).widget().item.id
            for index in range(self.items_layout.count())
            if isinstance(self.items_layout.itemAt(index).widget(), ItemCard)
        ]
        try:
            self.store.reorder_favorites(ordered_ids)
            self.status.setText("收藏顺序已保存")
        except ValueError as exc:
            QMessageBox.warning(self, "无法调整顺序", str(exc))
            self.refresh()
        del self._dragged_item_id

    def _clear(self) -> None:
        if QMessageBox.question(self, "清理历史", "删除全部未收藏记录？收藏内容会保留。") == QMessageBox.Yes:
            count = self.store.clear_unstarred()
            self.status.setText(f"已清理 {count} 条普通历史")
            self.refresh()

    def set_paused(self, paused: bool) -> None:
        self.service.paused = paused
        self.status.setText("●  监听已暂停" if paused else "●  正在监听")

    def closeEvent(self, event) -> None:
        if self._allow_close:
            event.accept()
        else:
            event.ignore()
            self.hide()

    def quit(self) -> None:
        self._allow_close = True
        self.close()

