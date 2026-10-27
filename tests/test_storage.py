import tempfile
import time
import unittest
import sqlite3
from pathlib import Path

from clipboard_app.storage import HistoryStore


class HistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = HistoryStore(Path(self.temp.name))

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_deduplicate_and_move_to_top(self):
        first = self.store.add_text("one")
        second = self.store.add_text("two")
        time.sleep(0.002)
        duplicate = self.store.add_text("one")
        self.assertEqual(first, duplicate)
        self.assertEqual([first, second], [x.id for x in self.store.list_items()])

    def test_mixed_items_share_one_order(self):
        text_id = self.store.add_text("hello")
        image_id = self.store.add_image(b"fake-png")
        files_id = self.store.add_files([str(Path(self.temp.name) / "file.txt")])
        self.assertEqual([files_id, image_id, text_id], [x.id for x in self.store.list_items()])

    def test_search_filter_favorite_and_clear(self):
        keep = self.store.add_text("keep me")
        self.store.add_text("remove me")
        self.store.set_favorite(keep, True)
        self.assertEqual([keep], [x.id for x in self.store.list_items("favorite")])
        self.assertEqual([keep], [x.id for x in self.store.list_items(search="keep")])
        self.assertEqual(1, self.store.clear_unstarred())
        self.assertEqual([keep], [x.id for x in self.store.list_items()])

    def test_delete_removes_image_file(self):
        item_id = self.store.add_image(b"image-bytes")
        path = Path(self.store.get(item_id).image_path)
        self.assertTrue(path.exists())
        self.store.delete(item_id)
        self.assertFalse(path.exists())

    def test_favorite_gets_default_title_for_each_type(self):
        item_ids = [
            self.store.add_text("text"),
            self.store.add_image(b"image"),
            self.store.add_files([str(Path(self.temp.name) / "folder")]),
        ]
        for item_id in item_ids:
            self.store.set_favorite(item_id, True)
        titles = [self.store.get(item_id).custom_title for item_id in item_ids]
        self.assertTrue(titles[0].startswith("文字收藏 "))
        self.assertTrue(titles[1].startswith("图片收藏 "))
        self.assertTrue(titles[2].startswith("文件收藏 "))

    def test_rename_persists_without_changing_sort_or_content(self):
        first = self.store.add_text("original content")
        second = self.store.add_text("newer content")
        self.store.set_favorite(first, True)
        self.store.set_favorite(second, True)
        before = [item.id for item in self.store.list_items("favorite")]
        updated_at = self.store.get(first).updated_at
        self.assertEqual("项目 Alpha #1", self.store.rename_favorite(first, "  项目 Alpha #1  "))
        self.assertEqual(before, [item.id for item in self.store.list_items("favorite")])
        renamed = self.store.get(first)
        self.assertEqual("项目 Alpha #1", renamed.custom_title)
        self.assertEqual("original content", renamed.text)
        self.assertEqual(updated_at, renamed.updated_at)
        self.store.close()
        self.store = HistoryStore(Path(self.temp.name))
        self.assertEqual("项目 Alpha #1", self.store.get(first).custom_title)

    def test_rename_validation_and_title_search(self):
        item_id = self.store.add_text("content without keyword")
        self.store.set_favorite(item_id, True)
        with self.assertRaises(ValueError):
            self.store.rename_favorite(item_id, "   ")
        with self.assertRaises(ValueError):
            self.store.rename_favorite(item_id, "x" * 81)
        self.store.rename_favorite(item_id, "中文 Search-42")
        self.assertEqual([item_id], [item.id for item in self.store.list_items("favorite", "Search-42")])

    def test_unfavorite_and_refavorite_preserves_custom_title(self):
        item_id = self.store.add_text("content")
        self.store.set_favorite(item_id, True)
        self.store.rename_favorite(item_id, "保留这个标题")
        self.store.set_favorite(item_id, False)
        self.store.set_favorite(item_id, True)
        self.assertEqual("保留这个标题", self.store.get(item_id).custom_title)

    def test_favorites_can_move_up_and_down_without_changing_history_order(self):
        first = self.store.add_text("first")
        second = self.store.add_text("second")
        third = self.store.add_text("third")
        for item_id in (first, second, third):
            self.store.set_favorite(item_id, True)
        self.assertEqual([third, second, first], [item.id for item in self.store.list_items("favorite")])
        history_order = [item.id for item in self.store.list_items("all")]
        timestamps = {item.id: item.updated_at for item in self.store.list_items("all")}

        self.assertTrue(self.store.move_favorite(first, -1))
        self.assertEqual([third, first, second], [item.id for item in self.store.list_items("favorite")])
        self.assertTrue(self.store.move_favorite(third, 1))
        self.assertEqual([first, third, second], [item.id for item in self.store.list_items("favorite")])
        self.assertFalse(self.store.move_favorite(first, -1))
        self.assertEqual(history_order, [item.id for item in self.store.list_items("all")])
        self.assertEqual(timestamps, {item.id: item.updated_at for item in self.store.list_items("all")})

        self.store.close()
        self.store = HistoryStore(Path(self.temp.name))
        self.assertEqual([first, third, second], [item.id for item in self.store.list_items("favorite")])

    def test_move_rejects_invalid_direction_and_nonfavorite(self):
        item_id = self.store.add_text("not favorite")
        with self.assertRaises(ValueError):
            self.store.move_favorite(item_id, 0)
        self.assertFalse(self.store.move_favorite(item_id, -1))

    def test_drag_order_can_be_saved_as_one_persistent_order(self):
        item_ids = [self.store.add_text(value) for value in ("one", "two", "three")]
        for item_id in item_ids:
            self.store.set_favorite(item_id, True)
        dragged_order = [item_ids[0], item_ids[2], item_ids[1]]
        self.store.reorder_favorites(dragged_order)
        self.assertEqual(dragged_order, [item.id for item in self.store.list_items("favorite")])
        self.store.close()
        self.store = HistoryStore(Path(self.temp.name))
        self.assertEqual(dragged_order, [item.id for item in self.store.list_items("favorite")])

    def test_drag_order_rejects_missing_or_duplicate_records(self):
        first = self.store.add_text("one")
        second = self.store.add_text("two")
        self.store.set_favorite(first, True)
        self.store.set_favorite(second, True)
        with self.assertRaises(ValueError):
            self.store.reorder_favorites([first])
        with self.assertRaises(ValueError):
            self.store.reorder_favorites([first, first])

    def test_modify_favorite_text_updates_actual_content_and_persists(self):
        item_id = self.store.add_text("old clipboard content")
        self.store.set_favorite(item_id, True)
        self.store.rename_favorite(item_id, "保留的收藏标题")
        before = self.store.get(item_id)
        self.store.update_favorite_text(item_id, "new clipboard content\nsecond line")
        updated = self.store.get(item_id)
        self.assertEqual("new clipboard content\nsecond line", updated.text)
        self.assertEqual("保留的收藏标题", updated.custom_title)
        self.assertNotEqual(before.content_hash, updated.content_hash)
        self.assertEqual(before.updated_at, updated.updated_at)
        self.store.close()
        self.store = HistoryStore(Path(self.temp.name))
        self.assertEqual("new clipboard content\nsecond line", self.store.get(item_id).text)

    def test_modify_content_validates_type_favorite_empty_and_duplicates(self):
        favorite = self.store.add_text("favorite")
        regular = self.store.add_text("regular")
        image = self.store.add_image(b"image")
        self.store.set_favorite(favorite, True)
        self.store.set_favorite(image, True)
        with self.assertRaises(ValueError):
            self.store.update_favorite_text(favorite, "   ")
        with self.assertRaises(ValueError):
            self.store.update_favorite_text(regular, "changed")
        with self.assertRaises(ValueError):
            self.store.update_favorite_text(image, "changed")
        with self.assertRaises(ValueError):
            self.store.update_favorite_text(favorite, "regular")

    def test_interview_notes_add_edit_search_delete_and_restart(self):
        note_id = self.store.add_interview_note(
            "  Amazon BQ 模板  ",
            "Situation\nTask\nAction\nResult",
        )
        note = self.store.get_interview_note(note_id)
        self.assertEqual("Amazon BQ 模板", note.title)
        self.assertEqual("Situation\nTask\nAction\nResult", note.content)
        self.assertEqual([note_id], [item.id for item in self.store.list_interview_notes("Amazon")])
        self.store.update_interview_note(note_id, "系统设计复习", "缓存、分片和一致性")
        self.assertEqual("系统设计复习", self.store.get_interview_note(note_id).title)
        self.store.close()
        self.store = HistoryStore(Path(self.temp.name))
        self.assertEqual("缓存、分片和一致性", self.store.get_interview_note(note_id).content)
        self.store.delete_interview_note(note_id)
        self.assertIsNone(self.store.get_interview_note(note_id))

    def test_interview_note_validation_and_clear_history_isolation(self):
        with self.assertRaises(ValueError):
            self.store.add_interview_note("", "content")
        with self.assertRaises(ValueError):
            self.store.add_interview_note("title", "   ")
        with self.assertRaises(ValueError):
            self.store.add_interview_note("x" * 81, "content")
        note_id = self.store.add_interview_note("独立内容", "不会被清理")
        self.store.add_text("ordinary history")
        self.assertEqual(1, self.store.clear_unstarred())
        self.assertIsNotNone(self.store.get_interview_note(note_id))

    def test_interview_notes_drag_order_persists_and_validates(self):
        ids = [
            self.store.add_interview_note(title, f"{title} content")
            for title in ("one", "two", "three")
        ]
        dragged = [ids[0], ids[2], ids[1]]
        self.store.reorder_interview_notes(dragged)
        self.assertEqual(dragged, [note.id for note in self.store.list_interview_notes()])
        self.store.update_interview_note(ids[2], "three updated", "updated content")
        self.assertEqual(dragged, [note.id for note in self.store.list_interview_notes()])
        self.store.close()
        self.store = HistoryStore(Path(self.temp.name))
        self.assertEqual(dragged, [note.id for note in self.store.list_interview_notes()])
        with self.assertRaises(ValueError):
            self.store.reorder_interview_notes([ids[0]])
        with self.assertRaises(ValueError):
            self.store.reorder_interview_notes([ids[0], ids[0], ids[1]])


class HistoryMigrationTests(unittest.TestCase):
    def test_existing_database_is_migrated(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            connection = sqlite3.connect(path / "clipboard.db")
            connection.execute("""
                CREATE TABLE history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL,
                    content_hash TEXT NOT NULL UNIQUE,
                    text_content TEXT,
                    image_path TEXT,
                    files_json TEXT,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            connection.commit()
            connection.close()
            store = HistoryStore(path)
            columns = {row[1] for row in store._db.execute("PRAGMA table_info(history)")}
            self.assertIn("custom_title", columns)
            self.assertIn("favorite_order", columns)
            tables = {row[0] for row in store._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertIn("interview_notes", tables)
            interview_columns = {
                row[1] for row in store._db.execute("PRAGMA table_info(interview_notes)")
            }
            self.assertIn("interview_order", interview_columns)
            store.close()


if __name__ == "__main__":
    unittest.main()

