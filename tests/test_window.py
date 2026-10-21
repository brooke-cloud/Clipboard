import unittest
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from clipboard_app.models import ClipboardItem
from clipboard_app.window import ContentEditDialog, ItemCard


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


if __name__ == "__main__":
    unittest.main()
