import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QColor, QGuiApplication, QImage
from PySide6.QtWidgets import QApplication

from clipboard_app.clipboard_service import ClipboardService
from clipboard_app.storage import HistoryStore


class ClipboardServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = HistoryStore(Path(self.temp.name))
        self.service = ClipboardService(self.store)
        self.service.paused = True

    def tearDown(self):
        self.service.clipboard.dataChanged.disconnect(self.service._schedule)
        self.store.close()
        self.temp.cleanup()

    def test_text_capture_and_restore(self):
        self.service.clipboard.setText("line one\nline two")
        self.service.paused = False
        self.service.capture()
        item = self.store.list_items()[0]
        self.assertEqual("text", item.kind)
        self.assertEqual("line one\nline two", item.text)
        self.service.clipboard.clear()
        self.assertTrue(self.service.restore(item))
        self.assertEqual(item.text, self.service.clipboard.text())

    def test_image_capture_and_restore(self):
        image = QImage(24, 12, QImage.Format_ARGB32)
        image.fill(QColor("#2563eb"))
        self.service.clipboard.setImage(image)
        self.service.paused = False
        self.service.capture()
        item = self.store.list_items()[0]
        self.assertEqual("image", item.kind)
        self.assertTrue(Path(item.image_path).exists())
        self.service.clipboard.clear()
        self.assertTrue(self.service.restore(item))
        restored = self.service.clipboard.image()
        self.assertEqual((24, 12), (restored.width(), restored.height()))

    def test_files_capture_and_restore(self):
        source = Path(self.temp.name) / "example.txt"
        source.write_text("test", encoding="utf-8")
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(source))])
        self.service.clipboard.setMimeData(mime)
        self.service.paused = False
        self.service.capture()
        item = self.store.list_items()[0]
        self.assertEqual("files", item.kind)
        self.service.clipboard.clear()
        self.assertTrue(self.service.restore(item))
        self.assertEqual(source.resolve(), Path(self.service.clipboard.mimeData().urls()[0].toLocalFile()).resolve())

    def test_missing_file_does_not_restore(self):
        source = Path(self.temp.name) / "gone.txt"
        source.write_text("test", encoding="utf-8")
        item_id = self.store.add_files([str(source)])
        source.unlink()
        self.assertFalse(self.service.restore(self.store.get(item_id)))


if __name__ == "__main__":
    unittest.main()
