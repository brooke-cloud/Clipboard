from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QWidget


def keep_dialog_above_parent(dialog: QDialog, parent: QWidget | None = None) -> QDialog:
    """Keep app dialogs above an always-on-top owner without changing normal dialogs."""
    owner = parent or dialog.parentWidget()
    if owner is None:
        return dialog
    owner_window = owner.window()
    dialog.setWindowModality(Qt.WindowModal)
    dialog.setWindowFlag(
        Qt.WindowStaysOnTopHint,
        bool(owner_window.windowFlags() & Qt.WindowStaysOnTopHint),
    )
    # Changing window flags recreates the native window and can drop its Win32 owner.
    # Restore the transient relationship so the dialog follows and stays above its owner.
    owner_window.winId()
    dialog.winId()
    if dialog.windowHandle() is not None and owner_window.windowHandle() is not None:
        dialog.windowHandle().setTransientParent(owner_window.windowHandle())
    return dialog
