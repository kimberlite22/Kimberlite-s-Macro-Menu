"""Input widgets that ignore mouse wheel scrolling until clicked into.

Qt's QSpinBox/QDoubleSpinBox/QComboBox change their value on any wheel scroll,
even while unfocused - which both edits the field by accident and swallows the
scroll event that would otherwise reach an enclosing QScrollArea. These
subclasses require the widget to already have focus (i.e. be clicked into
first) before a wheel event changes anything; otherwise the event is ignored
so it propagates to the parent (typically scrolling the page instead).
"""

from __future__ import annotations

from PySide6.QtCore import QLocale, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QBrush, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import QLabel, QComboBox, QDoubleSpinBox, QFormLayout, QProxyStyle, QSpinBox, QStyle, QWidget


FORM_LAYOUT_HORIZONTAL_SPACING = 10


class FormLayout(QFormLayout):
    """Use the app-wide label-to-field spacing for form layouts only."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setHorizontalSpacing(FORM_LAYOUT_HORIZONTAL_SPACING)


class CheckmarkProxyStyle(QProxyStyle):
    """Draw dark-theme check indicators and make all labels mouse-selectable.

    Qt's stylesheet engine cannot draw a custom glyph inside ``::indicator`` without
    an external image asset or a custom style. Removing the indicator QSS rules and
    handling these primitives here avoids new asset files and PyInstaller packaging
    changes. Both checkbox and item-view primitives are overridden so future
    checkable list/table items receive the same treatment as ``QCheckBox``.

    ``polish()`` is the single global choke point for making every ``QLabel``
    mouse-selectable, including labels Qt creates internally for APIs such as
    ``QFormLayout.addRow(str, widget)``, without touching individual call sites.
    """

    def polish(self, widget) -> None:
        super().polish(widget)
        if isinstance(widget, QLabel):
            widget.setTextInteractionFlags(
                widget.textInteractionFlags() | Qt.TextInteractionFlag.TextSelectableByMouse
            )
        # QGroupBox titles are painted style primitives, not QLabel widgets, and cannot use text interaction flags.

    def drawPrimitive(self, element, option, painter, widget=None) -> None:
        indicator_elements = {
            QStyle.PrimitiveElement.PE_IndicatorCheckBox,
            QStyle.PrimitiveElement.PE_IndicatorItemViewItemCheck,
        }
        if element not in indicator_elements:
            super().drawPrimitive(element, option, painter, widget)
            return

        state = option.state
        enabled = bool(state & QStyle.StateFlag.State_Enabled)
        partially_checked = bool(state & QStyle.StateFlag.State_NoChange)
        checked = bool(state & QStyle.StateFlag.State_On)
        hovered = enabled and bool(state & QStyle.StateFlag.State_MouseOver)

        if enabled:
            if checked or partially_checked:
                fill = QColor("#8a7dfa" if hovered else "#7869ef")
                border = QColor("#9489ff")
                glyph = QColor("#f5f3ff")
            else:
                fill = QColor("#111621")
                border = QColor("#8b7dff" if hovered else "#536078")
                glyph = None
        elif checked or partially_checked:
            fill = QColor("#4a4570")
            border = QColor("#373e4d")
            glyph = QColor("#9aa2b5")
        else:
            fill = QColor("#292e3b")
            border = QColor("#373e4d")
            glyph = None

        rect = QRectF(option.rect).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(border, 1.0))
        painter.setBrush(QBrush(fill))
        painter.drawRoundedRect(rect, min(3.0, rect.width() / 4), min(3.0, rect.height() / 4))

        if glyph is not None:
            stroke_width = max(1.6, min(rect.width(), rect.height()) * 0.14)
            pen = QPen(glyph, stroke_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if partially_checked:
                y = rect.center().y()
                painter.drawLine(
                    QPointF(rect.left() + rect.width() * 0.28, y),
                    QPointF(rect.right() - rect.width() * 0.28, y),
                )
            else:
                path = QPainterPath()
                path.moveTo(rect.left() + rect.width() * 0.24, rect.top() + rect.height() * 0.53)
                path.lineTo(rect.left() + rect.width() * 0.43, rect.bottom() - rect.height() * 0.25)
                path.lineTo(rect.right() - rect.width() * 0.20, rect.top() + rect.height() * 0.27)
                painter.drawPath(path)
        painter.restore()


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
        self.setLocale(QLocale(QLocale.Language.C))

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
