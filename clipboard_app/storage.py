from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .models import ClipboardItem, InterviewNote


class HistoryStore:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.image_dir = self.data_dir / "images"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.data_dir / "clipboard.db", check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def _migrate(self) -> None:
        with self._db:
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK(kind IN ('text','image','files')),
                    content_hash TEXT NOT NULL UNIQUE,
                    text_content TEXT,
                    image_path TEXT,
                    files_json TEXT,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    custom_title TEXT,
                    favorite_order INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            columns = {row["name"] for row in self._db.execute("PRAGMA table_info(history)")}
            if "custom_title" not in columns:
                self._db.execute("ALTER TABLE history ADD COLUMN custom_title TEXT")
            if "favorite_order" not in columns:
                self._db.execute("ALTER TABLE history ADD COLUMN favorite_order INTEGER")
            unordered = self._db.execute(
                "SELECT id FROM history WHERE favorite=1 AND favorite_order IS NULL ORDER BY updated_at ASC, id ASC"
            ).fetchall()
            next_order = self._db.execute(
                "SELECT COALESCE(MAX(favorite_order), 0) FROM history"
            ).fetchone()[0]
            for row in unordered:
                next_order += 1
                self._db.execute("UPDATE history SET favorite_order=? WHERE id=?", (next_order, row["id"]))
            self._db.execute("CREATE INDEX IF NOT EXISTS idx_history_updated ON history(updated_at DESC)")
            self._db.execute("""
                CREATE TABLE IF NOT EXISTS interview_notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    interview_order INTEGER,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            interview_columns = {
                row["name"] for row in self._db.execute("PRAGMA table_info(interview_notes)")
            }
            if "interview_order" not in interview_columns:
                self._db.execute("ALTER TABLE interview_notes ADD COLUMN interview_order INTEGER")
            unordered_notes = self._db.execute(
                "SELECT id FROM interview_notes WHERE interview_order IS NULL "
                "ORDER BY updated_at ASC, id ASC"
            ).fetchall()
            next_note_order = self._db.execute(
                "SELECT COALESCE(MAX(interview_order), 0) FROM interview_notes"
            ).fetchone()[0]
            for row in unordered_notes:
                next_note_order += 1
                self._db.execute(
                    "UPDATE interview_notes SET interview_order=? WHERE id=?",
                    (next_note_order, row["id"]),
                )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_interview_notes_updated "
                "ON interview_notes(updated_at DESC)"
            )

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds")

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(("text\0" + text).encode("utf-8")).hexdigest()

    @staticmethod
    def hash_files(files: list[str]) -> str:
        canonical = [str(Path(p).resolve()).casefold() for p in files]
        return hashlib.sha256(("files\0" + "\0".join(canonical)).encode("utf-8")).hexdigest()

    @staticmethod
    def hash_image(data: bytes) -> str:
        return hashlib.sha256(b"image\0" + data).hexdigest()

    def _upsert(self, kind: str, digest: str, *, text: str | None = None,
                image_path: str | None = None, files: list[str] | None = None) -> int:
        now = self._now()
        files_json = json.dumps(files, ensure_ascii=False) if files is not None else None
        with self._lock, self._db:
            row = self._db.execute("SELECT id FROM history WHERE content_hash=?", (digest,)).fetchone()
            if row:
                self._db.execute("UPDATE history SET updated_at=? WHERE id=?", (now, row["id"]))
                return int(row["id"])
            cur = self._db.execute(
                "INSERT INTO history(kind,content_hash,text_content,image_path,files_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                (kind, digest, text, image_path, files_json, now, now),
            )
            return int(cur.lastrowid)

    def add_text(self, text: str) -> int | None:
        if not text:
            return None
        return self._upsert("text", self.hash_text(text), text=text)

    def add_files(self, files: list[str]) -> int | None:
        clean = [str(Path(p)) for p in files if p]
        if not clean:
            return None
        return self._upsert("files", self.hash_files(clean), files=clean)

    def add_image(self, png_data: bytes) -> int | None:
        if not png_data:
            return None
        digest = self.hash_image(png_data)
        path = self.image_dir / f"{digest}.png"
        if not path.exists():
            path.write_bytes(png_data)
        return self._upsert("image", digest, image_path=str(path))

    def list_items(self, kind: str = "all", search: str = "") -> list[ClipboardItem]:
        clauses, args = [], []
        if kind == "favorite":
            clauses.append("favorite=1")
        elif kind in {"text", "image", "files"}:
            clauses.append("kind=?")
            args.append(kind)
        if search:
            clauses.append("(text_content LIKE ? ESCAPE '\\' OR files_json LIKE ? ESCAPE '\\' OR custom_title LIKE ? ESCAPE '\\')")
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            args.extend([f"%{escaped}%", f"%{escaped}%", f"%{escaped}%"])
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        order_by = "favorite_order DESC, updated_at DESC, id DESC" if kind == "favorite" else "updated_at DESC, id DESC"
        with self._lock:
            rows = self._db.execute("SELECT * FROM history" + where + " ORDER BY " + order_by, args).fetchall()
        return [self._row(row) for row in rows]

    def get(self, item_id: int) -> ClipboardItem | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM history WHERE id=?", (item_id,)).fetchone()
        return self._row(row) if row else None

    def set_favorite(self, item_id: int, favorite: bool) -> None:
        with self._lock, self._db:
            row = self._db.execute("SELECT kind, favorite, custom_title, favorite_order FROM history WHERE id=?", (item_id,)).fetchone()
            if not row:
                return
            title = row["custom_title"]
            if favorite and not title:
                names = {"text": "文字收藏", "image": "图片收藏", "files": "文件收藏"}
                title = f"{names[row['kind']]} {datetime.now().strftime('%m-%d %H:%M')}"
            order = row["favorite_order"]
            if favorite and not row["favorite"]:
                order = self._db.execute("SELECT COALESCE(MAX(favorite_order), 0) + 1 FROM history").fetchone()[0]
            self._db.execute(
                "UPDATE history SET favorite=?, custom_title=?, favorite_order=? WHERE id=?",
                (int(favorite), title, order, item_id),
            )

    def rename_favorite(self, item_id: int, title: str) -> str:
        normalized = " ".join(title.split())
        if not normalized:
            raise ValueError("收藏标题不能为空")
        if len(normalized) > 80:
            raise ValueError("收藏标题不能超过 80 个字符")
        with self._lock, self._db:
            row = self._db.execute("SELECT favorite FROM history WHERE id=?", (item_id,)).fetchone()
            if not row or not row["favorite"]:
                raise ValueError("只能重命名收藏记录")
            self._db.execute("UPDATE history SET custom_title=? WHERE id=?", (normalized, item_id))
        return normalized

    def update_favorite_text(self, item_id: int, text: str) -> None:
        if not text.strip():
            raise ValueError("复制内容不能为空")
        if len(text) > 1_000_000:
            raise ValueError("复制内容不能超过 100 万个字符")
        digest = self.hash_text(text)
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT kind, favorite FROM history WHERE id=?", (item_id,)
            ).fetchone()
            if not row or not row["favorite"] or row["kind"] != "text":
                raise ValueError("只能修改已收藏的文字内容")
            duplicate = self._db.execute(
                "SELECT id FROM history WHERE content_hash=? AND id<>?", (digest, item_id)
            ).fetchone()
            if duplicate:
                raise ValueError("相同的文字内容已经存在")
            self._db.execute(
                "UPDATE history SET text_content=?, content_hash=? WHERE id=?",
                (text, digest, item_id),
            )

    def move_favorite(self, item_id: int, direction: int) -> bool:
        if direction not in {-1, 1}:
            raise ValueError("移动方向必须是上移或下移")
        with self._lock, self._db:
            rows = self._db.execute(
                "SELECT id, favorite_order FROM history WHERE favorite=1 "
                "ORDER BY favorite_order DESC, updated_at DESC, id DESC"
            ).fetchall()
            ids = [int(row["id"]) for row in rows]
            if item_id not in ids:
                return False
            current = ids.index(item_id)
            target = current - 1 if direction == -1 else current + 1
            if target < 0 or target >= len(rows):
                return False
            current_row, target_row = rows[current], rows[target]
            self._db.execute("UPDATE history SET favorite_order=? WHERE id=?", (target_row["favorite_order"], current_row["id"]))
            self._db.execute("UPDATE history SET favorite_order=? WHERE id=?", (current_row["favorite_order"], target_row["id"]))
        return True

    def reorder_favorites(self, ordered_ids: list[int]) -> None:
        if len(ordered_ids) != len(set(ordered_ids)):
            raise ValueError("收藏顺序中存在重复记录")
        with self._lock, self._db:
            existing = {
                int(row[0]) for row in self._db.execute("SELECT id FROM history WHERE favorite=1")
            }
            if set(ordered_ids) != existing:
                raise ValueError("收藏顺序与当前记录不一致")
            total = len(ordered_ids)
            for index, item_id in enumerate(ordered_ids):
                self._db.execute(
                    "UPDATE history SET favorite_order=? WHERE id=?",
                    (total - index, item_id),
                )

    def delete(self, item_id: int) -> None:
        with self._lock, self._db:
            row = self._db.execute("SELECT image_path FROM history WHERE id=?", (item_id,)).fetchone()
            self._db.execute("DELETE FROM history WHERE id=?", (item_id,))
        self._remove_orphan(row["image_path"] if row else None)

    def clear_unstarred(self) -> int:
        with self._lock, self._db:
            paths = [r[0] for r in self._db.execute("SELECT image_path FROM history WHERE favorite=0 AND image_path IS NOT NULL")]
            cur = self._db.execute("DELETE FROM history WHERE favorite=0")
        for path in paths:
            self._remove_orphan(path)
        return cur.rowcount

    @staticmethod
    def _validate_interview_note(title: str, content: str) -> tuple[str, str]:
        normalized_title = " ".join(title.split())
        if not normalized_title:
            raise ValueError("面试内容标题不能为空")
        if len(normalized_title) > 80:
            raise ValueError("面试内容标题不能超过 80 个字符")
        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("面试内容不能为空")
        if len(normalized_content) > 1_000_000:
            raise ValueError("面试内容不能超过 100 万个字符")
        return normalized_title, normalized_content

    def add_interview_note(self, title: str, content: str) -> int:
        title, content = self._validate_interview_note(title, content)
        now = self._now()
        with self._lock, self._db:
            order = self._db.execute(
                "SELECT COALESCE(MAX(interview_order), 0) + 1 FROM interview_notes"
            ).fetchone()[0]
            cursor = self._db.execute(
                "INSERT INTO interview_notes(title,content,interview_order,created_at,updated_at) "
                "VALUES(?,?,?,?,?)",
                (title, content, order, now, now),
            )
        return int(cursor.lastrowid)

    def list_interview_notes(self, search: str = "") -> list[InterviewNote]:
        sql = "SELECT * FROM interview_notes"
        args: list[str] = []
        if search:
            escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql += " WHERE title LIKE ? ESCAPE '\\' OR content LIKE ? ESCAPE '\\'"
            args.extend([f"%{escaped}%", f"%{escaped}%"])
        sql += " ORDER BY interview_order DESC, updated_at DESC, id DESC"
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [self._interview_row(row) for row in rows]

    def get_interview_note(self, note_id: int) -> InterviewNote | None:
        with self._lock:
            row = self._db.execute("SELECT * FROM interview_notes WHERE id=?", (note_id,)).fetchone()
        return self._interview_row(row) if row else None

    def update_interview_note(self, note_id: int, title: str, content: str) -> None:
        title, content = self._validate_interview_note(title, content)
        with self._lock, self._db:
            cursor = self._db.execute(
                "UPDATE interview_notes SET title=?, content=?, updated_at=? WHERE id=?",
                (title, content, self._now(), note_id),
            )
        if cursor.rowcount == 0:
            raise ValueError("面试内容不存在或已被删除")

    def delete_interview_note(self, note_id: int) -> None:
        with self._lock, self._db:
            self._db.execute("DELETE FROM interview_notes WHERE id=?", (note_id,))

    def reorder_interview_notes(self, ordered_ids: list[int]) -> None:
        if len(ordered_ids) != len(set(ordered_ids)):
            raise ValueError("面试顺序中存在重复记录")
        with self._lock, self._db:
            existing = {
                int(row[0]) for row in self._db.execute("SELECT id FROM interview_notes")
            }
            if set(ordered_ids) != existing:
                raise ValueError("面试顺序与当前记录不一致")
            total = len(ordered_ids)
            for index, note_id in enumerate(ordered_ids):
                self._db.execute(
                    "UPDATE interview_notes SET interview_order=? WHERE id=?",
                    (total - index, note_id),
                )

    def _remove_orphan(self, path: str | None) -> None:
        if not path:
            return
        with self._lock:
            used = self._db.execute("SELECT 1 FROM history WHERE image_path=?", (path,)).fetchone()
        if not used:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _row(row: sqlite3.Row) -> ClipboardItem:
        return ClipboardItem(
            id=row["id"], kind=row["kind"], content_hash=row["content_hash"],
            text=row["text_content"], image_path=row["image_path"],
            files=json.loads(row["files_json"] or "[]"), favorite=bool(row["favorite"]),
            custom_title=row["custom_title"],
            favorite_order=row["favorite_order"],
            created_at=datetime.fromisoformat(row["created_at"]), updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _interview_row(row: sqlite3.Row) -> InterviewNote:
        return InterviewNote(
            id=row["id"], title=row["title"], content=row["content"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def close(self) -> None:
        with self._lock:
            self._db.close()

