from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class ClipboardItem:
    id: int
    kind: str
    content_hash: str
    text: str | None
    image_path: str | None
    files: list[str]
    favorite: bool
    custom_title: str | None
    favorite_order: int | None
    created_at: datetime
    updated_at: datetime

    @property
    def title(self) -> str:
        if self.kind == "text":
            return self.text or ""
        if self.kind == "image":
            return "图片"
        if not self.files:
            return "文件"
        first = Path(self.files[0]).name
        return first if len(self.files) == 1 else f"{first} 等 {len(self.files)} 项"


@dataclass(slots=True)
class InterviewNote:
    id: int
    title: str
    content: str
    created_at: datetime
    updated_at: datetime

