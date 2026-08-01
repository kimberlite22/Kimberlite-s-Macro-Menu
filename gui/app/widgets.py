"""Input widgets that ignore mouse wheel scrolling until clicked into.

Qt's QSpinBox/QDoubleSpinBox/QComboBox change their value on any wheel scroll,
even while unfocused - which both edits the field by accident and swallows the
scroll event that would otherwise reach an enclosing QScrollArea. These
subclasses require the widget to already have focus (i.e. be clicked into
first) before a wheel event changes anything; otherwise the event is ignored
so it propagates to the parent (typically scrolling the page instead).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QSpinBox, QWidget


def make_independently_minimizable(window: QWidget) -> None:
    """Give a secondary top-level QDialog its own minimize button.

    Qt::Dialog's default flags omit a minimize button, so without this a secondary
    window has no way to be minimized on its own. This is one half of decoupling a
    secondary window's minimize state from the main window's: the other half is that
    its caller must NOT also pass a Qt parent. On Windows, a top-level QDialog
    constructed with a parent widget gets a native OS "owner" handle (independent of
    any window-flag hint, including this one), and Windows automatically hides an
    owned window whenever its owner is minimized and restores it when the owner is
    restored - so the two windows would still appear to minimize together even with
    this flag set. Call this on every secondary window regardless, and construct each
    one with parent=None (the default) in production code.
    """
    window.setWindowFlag(Qt.WindowMinimizeButtonHint, True)


class NoScrollSpinBox(QSpinBox):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoScrollDoubleSpinBox(QDoubleSpinBox):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class NoScrollComboBox(QComboBox):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()
