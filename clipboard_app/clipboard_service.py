from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtCore import QMimeData

from .models import ClipboardItem
from .storage import HistoryStore


class ClipboardService(QObject):
    history_changed = Signal()
    error = Signal(str)

    def __init__(self, store: HistoryStore):
        super().__init__()
        self.store = store
        self.clipboard = QGuiApplication.clipboard()
        self.paused = False
        self._ignore_once = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self.capture)
        self.clipboard.dataChanged.connect(self._schedule)

    def _schedule(self) -> None:
        if self._ignore_once:
            self._ignore_once = False
            return
        if not self.paused:
            self._timer.start()

    def capture(self) -> None:
        if self.paused:
            return
        mime = self.clipboard.mimeData()
        try:
            item_id = None
            if mime.hasUrls() and all(url.isLocalFile() for url in mime.urls()):
                item_id = self.store.add_files([url.toLocalFile() for url in mime.urls()])
            elif mime.hasImage():
                image = self.clipboard.image()
                data = QByteArray()
                buffer = QBuffer(data)
                buffer.open(QIODevice.WriteOnly)
                image.save(buffer, "PNG")
                item_id = self.store.add_image(bytes(data))
            elif mime.hasText():
                item_id = self.store.add_text(mime.text())
            if item_id is not None:
                self.history_changed.emit()
        except Exception:
            self.error.emit("保存剪贴板内容失败，请检查本地数据目录")

    def restore(self, item: ClipboardItem) -> bool:
        try:
            self._ignore_once = True
            if item.kind == "text":
                self.clipboard.setText(item.text or "")
            elif item.kind == "image" and item.image_path:
                image = QImage(item.image_path)
                if image.isNull():
                    raise OSError("image unavailable")
                self.clipboard.setImage(image)
            elif item.kind == "files":
                valid = [path for path in item.files if Path(path).exists() and QUrl.fromLocalFile(path).isValid()]
                if not valid:
                    raise OSError("files unavailable")
                mime = QMimeData()
                mime.setUrls([QUrl.fromLocalFile(path) for path in valid])
                self.clipboard.setMimeData(mime)
            else:
                return False
            return True
        except Exception:
            self._ignore_once = False
            self.error.emit("无法恢复该内容；源文件可能已被移动或删除")
            return False

    def copy_text(self, text: str) -> bool:
        if not text:
            return False
        try:
            self._ignore_once = True
            self.clipboard.setText(text)
            return True
        except Exception:
            self._ignore_once = False
            self.error.emit("无法复制该文字内容")
            return False

