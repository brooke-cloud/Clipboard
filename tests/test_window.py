import unittest
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from clipboard_app.models import ClipboardItem, InterviewNote
from clipboard_app.clipboard_service import ClipboardService
from clipboard_app.settings import AppSettings
from clipboard_app.storage import HistoryStore
from clipboard_app.window import ContentEditDialog, InterviewCard, InterviewEditDialog, ItemCard, MainWindow


class FavoriteMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def item(favorite: bool, kind: str = "text") -> ClipboardItem:
        now = datetime.now(timezone.utc)
        return ClipboardItem(
            id=1,
            kind=kind,
            content_hash="hash",
            text="original clipboard text",
            image_path=None,
            files=[],
            favorite=favorite,
            custom_title="面试模板" if favorite else None,
            favorite_order=1 if favorite else None,
            created_at=now,
            updated_at=now,
        )

    def test_modify_only_appears_for_favorite_text_records(self):
        favorite = ItemCard(self.item(True), favorite_view=True)
        regular = ItemCard(self.item(False), favorite_view=False)
        image = ItemCard(self.item(True, "image"), favorite_view=True)
        favorite_actions = [action.text() for action in favorite._create_actions_menu().actions()]
        regular_actions = [action.text() for action in regular._create_actions_menu().actions()]
        image_actions = [action.text() for action in image._create_actions_menu().actions()]
        self.assertIn("修改", favorite_actions)
        self.assertNotIn("修改", regular_actions)
        self.assertNotIn("修改", image_actions)

    def test_content_editor_prefills_actual_content_and_can_cancel(self):
        dialog = ContentEditDialog("original clipboard text")
        self.assertEqual("original clipboard text", dialog.content())
        dialog.editor.setPlainText("changed but cancelled")
        dialog.reject()
        self.assertEqual(QDialog.DialogCode.Rejected, dialog.result())

    def test_double_clicking_text_preview_requests_copy_without_selecting_text(self):
        card = ItemCard(self.item(True), favorite_view=True)
        requested = []
        card.copy_requested.connect(requested.append)
        card.show()
        self.app.processEvents()
        QTest.mouseDClick(card.content_label, Qt.LeftButton)
        self.app.processEvents()
        self.assertEqual([card.item.id], requested)
        self.assertEqual(Qt.NoTextInteraction, card.content_label.textInteractionFlags())


class WindowMinimizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_minimize_button_hides_to_tray_without_minimized_window_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory))
            service = ClipboardService(store)
            service.paused = True
            window = MainWindow(store, service, AppSettings())
            window.show()
            self.app.processEvents()
            window.title_bar.minimize_button.click()
            self.app.processEvents()
            self.assertFalse(window.isVisible())
            self.assertFalse(window.isMinimized())
            service.clipboard.dataChanged.disconnect(service._schedule)
            window.quit()
            store.close()


class InterviewUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_interview_dialog_prefills_title_and_content(self):
        dialog = InterviewEditDialog("面试模板", "回答内容")
        self.assertEqual(("面试模板", "回答内容"), dialog.values())
        dialog.close()
        dialog.deleteLater()

    def test_interview_card_exposes_edit_and_delete_actions(self):
        now = datetime.now(timezone.utc)
        note = InterviewNote(7, "重要面试题", "完整回答", now, now)
        card = InterviewCard(note)
        edited, deleted = [], []
        card.edit_requested.connect(edited.append)
        card.delete_requested.connect(deleted.append)
        card.edit_requested.emit(note.id)
        card.delete_requested.emit(note.id)
        self.assertEqual([7], edited)
        self.assertEqual([7], deleted)
        card.deleteLater()
        self.app.processEvents()

    def test_double_clicking_interview_content_requests_copy_without_selecting(self):
        now = datetime.now(timezone.utc)
        note = InterviewNote(8, "面试标题", "需要复制的面试回答", now, now)
        card = InterviewCard(note)
        requested = []
        card.copy_requested.connect(requested.append)
        card.show()
        self.app.processEvents()
        QTest.mouseDClick(card.content_label, Qt.LeftButton)
        self.app.processEvents()
        self.assertEqual([8], requested)
        self.assertEqual(Qt.NoTextInteraction, card.content_label.textInteractionFlags())
        card.deleteLater()

    def test_interview_copy_uses_body_only_and_requests_auto_paste(self):
        with tempfile.TemporaryDirectory() as directory:
            store = HistoryStore(Path(directory))
            note_id = store.add_interview_note("不要复制这个标题", "只复制这段正文")
            service = ClipboardService(store)
            service.paused = True
            window = MainWindow(store, service, AppSettings())
            paste_requests = []
            window.paste_requested.connect(lambda: paste_requests.append(True))
            window._copy_interview_note(note_id)
            self.assertEqual("只复制这段正文", service.clipboard.text())
            self.assertEqual([True], paste_requests)
            service.clipboard.dataChanged.disconnect(service._schedule)
            window.quit()
            store.close()

    def test_dialog_stays_above_pinned_owner_only(self):
        owner = QDialog()
        owner.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        pinned_dialog = InterviewEditDialog(parent=owner)
        self.assertTrue(pinned_dialog.windowFlags() & Qt.WindowStaysOnTopHint)
        self.assertEqual(Qt.WindowModal, pinned_dialog.windowModality())
        owner.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        normal_dialog = ContentEditDialog("content", owner)
        self.assertFalse(normal_dialog.windowFlags() & Qt.WindowStaysOnTopHint)
        pinned_dialog.close()
        normal_dialog.close()
        owner.close()


if __name__ == "__main__":
    unittest.main()
