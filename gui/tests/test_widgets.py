from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QDialog, QWidget

from app.widgets import (
    NoScrollComboBox,
    NoScrollDoubleSpinBox,
    NoScrollSpinBox,
    make_independently_minimizable,
)


def _wheel_event(widget, delta: int = 120) -> QWheelEvent:
    center = QPointF(widget.rect().center())
    return QWheelEvent(
        center,
        widget.mapToGlobal(center.toPoint()),
        QPoint(0, 0),
        QPoint(0, delta),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )


def test_no_scroll_spinbox_ignores_wheel_until_clicked(qtbot):
    box = NoScrollSpinBox()
    box.setRange(0, 100)
    box.setValue(5)
    qtbot.addWidget(box)
    box.show()
    qtbot.waitExposed(box)

    box.clearFocus()
    QApplication.sendEvent(box, _wheel_event(box))
    assert box.value() == 5

    box.setFocus()
    qtbot.waitUntil(box.hasFocus)
    QApplication.sendEvent(box, _wheel_event(box))
    assert box.value() == 6


def test_no_scroll_double_spinbox_ignores_wheel_until_clicked(qtbot):
    box = NoScrollDoubleSpinBox()
    box.setRange(0.0, 100.0)
    box.setValue(5.0)
    qtbot.addWidget(box)
    box.show()
    qtbot.waitExposed(box)

    box.clearFocus()
    QApplication.sendEvent(box, _wheel_event(box))
    assert box.value() == 5.0

    box.setFocus()
    qtbot.waitUntil(box.hasFocus)
    QApplication.sendEvent(box, _wheel_event(box))
    assert box.value() == 6.0


def test_no_scroll_combo_box_ignores_wheel_until_clicked(qtbot):
    combo = NoScrollComboBox()
    combo.addItems(["a", "b", "c"])
    qtbot.addWidget(combo)
    combo.show()
    qtbot.waitExposed(combo)

    combo.clearFocus()
    QApplication.sendEvent(combo, _wheel_event(combo))
    assert combo.currentIndex() == 0

    combo.setFocus()
    qtbot.waitUntil(combo.hasFocus)
    QApplication.sendEvent(combo, _wheel_event(combo, delta=-120))
    assert combo.currentIndex() == 1


def test_make_independently_minimizable_adds_only_the_minimize_hint(qtbot) -> None:
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = QDialog(parent)
    qtbot.addWidget(dialog)
    flags_before = dialog.windowFlags()
    assert not (flags_before & Qt.WindowMinimizeButtonHint)

    make_independently_minimizable(dialog)

    assert dialog.windowFlags() & Qt.WindowMinimizeButtonHint
    # Every other flag bit is untouched: only the minimize hint bit was added.
    assert dialog.windowFlags() == (flags_before | Qt.WindowMinimizeButtonHint)
    # This helper only adds the minimize-button hint; it does not touch (and is not what
    # decouples) any Qt parent relationship. Production callers separately construct their
    # secondary windows with parent=None to avoid the native Windows "owned window" auto-hide
    # behavior a Qt parent would otherwise cause - see the docstring above and
    # make_independently_minimizable's callers in app/main_window.py and app/edit_preset_window.py.
    assert dialog.parent() is parent
    assert dialog.isWindow()
