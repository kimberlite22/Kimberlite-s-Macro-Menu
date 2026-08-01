"""Search helpers for settings shown across the PySide6 GUI."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from PySide6.QtWidgets import QAbstractButton, QFormLayout, QGroupBox, QLabel, QWidget


@dataclass(frozen=True)
class SettingsSearchEntry:
    """One visible setting label and the action that opens its location."""

    display_label: str
    navigate: Callable[[], None]


def match_settings(
    entries: Iterable[SettingsSearchEntry], query: str,
) -> list[SettingsSearchEntry]:
    """Return case-insensitive substring matches with prefix matches first.

    This deliberately contains no Qt-specific behavior so callers can test the
    search ordering with simple callbacks and labels.
    """
    normalized_query = query.strip().casefold()
    if not normalized_query:
        return []

    matches: list[tuple[int, str, int, SettingsSearchEntry]] = []
    for position, entry in enumerate(entries):
        normalized_label = entry.display_label.casefold()
        if normalized_query not in normalized_label:
            continue
        rank = 0 if normalized_label.startswith(normalized_query) else 1
        matches.append((rank, normalized_label, position, entry))
    return [entry for _, _, _, entry in sorted(matches)]


class SettingsIndex:
    """A small collection of setting labels with search navigation callbacks."""

    def __init__(self) -> None:
        self.entries: list[SettingsSearchEntry] = []

    def add(self, display_label: str, navigate: Callable[[], None]) -> None:
        label = display_label.strip()
        if label:
            self.entries.append(SettingsSearchEntry(label, navigate))

    def search(self, query: str) -> list[SettingsSearchEntry]:
        return match_settings(self.entries, query)


def labeled_widgets(root: QWidget) -> list[tuple[str, QWidget]]:
    """Return text-bearing widgets that a user can recognize in *root*."""
    result: list[tuple[str, QWidget]] = []
    form_fields: dict[int, QWidget] = {}
    for layout in root.findChildren(QFormLayout):
        for row in range(layout.rowCount()):
            label_item = layout.itemAt(row, QFormLayout.ItemRole.LabelRole)
            field_item = layout.itemAt(row, QFormLayout.ItemRole.FieldRole)
            label = label_item.widget() if label_item is not None else None
            field = field_item.widget() if field_item is not None else None
            if isinstance(label, QLabel) and isinstance(field, QWidget):
                form_fields[id(label)] = field
    for widget in [root, *root.findChildren(QWidget)]:
        if not isinstance(widget, (QLabel, QGroupBox, QAbstractButton)):
            continue
        text = _widget_text(widget)
        if text:
            result.append((text, form_fields.get(id(widget), widget)))
    return result


def secondary_window_labels(client: Any) -> dict[str, list[str]]:
    """Collect static labels from representative secondary-window instances.

    The production windows require a selected preset or map profile before they
    can be shown. Temporary, never-shown instances let the main search present
    those choices before a selection exists, while navigation still enforces the
    same selection checks as the normal buttons.
    """
    from app.advanced_outcomes_window import AdvancedOutcomesWindow
    from app.edit_preset_window import EditPresetWindow
    from app.map_advanced_window import MapAdvancedWindow
    from app.step_edit_window import StepEditWindow
    from ipc.config_reader import GeneralConfig, MapProfileConfig, PresetConfig

    edit_window = EditPresetWindow(PresetConfig("Search"), client, [], [])
    map_window = MapAdvancedWindow(
        "Search", client, profile=MapProfileConfig("Search"), general=GeneralConfig(),
    )
    step_window = StepEditWindow(client)
    outcomes_window = AdvancedOutcomesWindow("", [])
    windows = {
        "edit_preset": edit_window,
        "option_availability": edit_window.option_availability_window,
        "map_advanced": map_window,
        "step_edit": step_window,
        "advanced_outcomes": outcomes_window,
    }
    try:
        return {
            name: [label for label, _ in labeled_widgets(window)]
            for name, window in windows.items()
        }
    finally:
        unique_windows: list[QWidget] = []
        for window in windows.values():
            if all(window is not existing for existing in unique_windows):
                unique_windows.append(window)
        for window in unique_windows:
            window.close()
            window.deleteLater()


def _widget_text(widget: QWidget) -> str:
    # QGroupBox has no text(): its caption is title(). Using text() unconditionally here
    # raised AttributeError on every group box, which made labeled_widgets() (and therefore
    # the whole search index) blow up the instant any tab or window containing a QGroupBox
    # (i.e. all of them) was indexed.
    if isinstance(widget, QGroupBox):
        return widget.title().strip()
    if isinstance(widget, (QLabel, QAbstractButton)):
        return widget.text().strip()
    return ""
