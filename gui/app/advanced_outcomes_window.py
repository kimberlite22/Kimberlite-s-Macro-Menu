"""Editor for a Custom Detection step's named OCR outcomes."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
)

from app.widgets import NoScrollComboBox, make_independently_minimizable


@dataclass(frozen=True)
class DetectionOutcome:
    name: str
    screen: str


def parse_outcomes(value: str) -> list[DetectionOutcome]:
    """Parse AHK's deliberately unescaped ``Name=Screen|...`` representation."""
    if not value:
        return []
    outcomes: list[DetectionOutcome] = []
    for part in value.split("|"):
        if "=" not in part:
            continue
        name, screen = part.split("=", 1)
        outcomes.append(DetectionOutcome(name, screen))
    return outcomes


def serialize_outcomes(outcomes: list[DetectionOutcome]) -> str:
    """Serialize outcomes exactly as ``SerializeOutcomes`` in the AHK GUI does."""
    return "|".join(f"{outcome.name}={outcome.screen}" for outcome in outcomes)


class AdvancedOutcomesWindow(QDialog):
    """Keep outcome edits local until the caller accepts this dialog."""

    def __init__(self, outcomes_raw: str, screen_names: list[str], parent=None) -> None:
        super().__init__(parent)
        make_independently_minimizable(self)
        self.setWindowTitle("Advanced Detection Outcomes")
        self.resize(620, 390)
        self._outcomes = parse_outcomes(outcomes_raw)
        if not self._outcomes:
            self._outcomes = [
                DetectionOutcome("True", "(continue)"),
                DetectionOutcome("False", "(continue)"),
            ]
        self._screen_names = list(screen_names)
        self.result_outcomes_raw = outcomes_raw

        layout = QVBoxLayout(self)
        help_text = QLabel(
            "Each outcome name is the OCR expected text. Outcomes are checked top to bottom; "
            "the first match selects its target."
        )
        help_text.setWordWrap(True)
        layout.addWidget(help_text)

        self.outcomes_list = QListWidget()
        self.outcomes_list.setObjectName("advanced_outcomes_list")
        self.outcomes_list.currentRowChanged.connect(self._load_selected)
        layout.addWidget(self.outcomes_list, 1)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("advanced_outcome_name")
        self.screen_combo = NoScrollComboBox()
        self.screen_combo.setObjectName("advanced_outcome_screen")
        self.screen_combo.addItems(["(continue)", "(Repeat)", "(Stop Macro)", *self._screen_names])
        form.addRow("Name / Expected Text", self.name_edit)
        form.addRow("Screen ->", self.screen_combo)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.add_button = QPushButton("Add")
        self.update_button = QPushButton("Update Selected")
        self.delete_button = QPushButton("Delete Selected")
        self.move_up_button = QPushButton("Move Up")
        self.move_down_button = QPushButton("Move Down")
        for button in (self.add_button, self.update_button, self.delete_button, self.move_up_button, self.move_down_button):
            actions.addWidget(button)
        layout.addLayout(actions)

        self.message_label = QLabel()
        self.message_label.setObjectName("advanced_outcomes_message")
        layout.addWidget(self.message_label)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.ok_button = QPushButton("OK")
        self.cancel_button = QPushButton("Cancel")
        buttons.addWidget(self.ok_button)
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)

        self.add_button.clicked.connect(self._add)
        self.update_button.clicked.connect(self._update)
        self.delete_button.clicked.connect(self._delete)
        self.move_up_button.clicked.connect(lambda: self._move(-1))
        self.move_down_button.clicked.connect(lambda: self._move(1))
        self.ok_button.clicked.connect(self._accept)
        self.cancel_button.clicked.connect(self.reject)
        self._render()

    def _render(self, select_row: int | None = None) -> None:
        self.outcomes_list.clear()
        for index, outcome in enumerate(self._outcomes, 1):
            item = QListWidgetItem(f"{index}. {outcome.name} -> {outcome.screen}")
            item.setData(Qt.ItemDataRole.UserRole, outcome)
            self.outcomes_list.addItem(item)
        if select_row is not None and 0 <= select_row < len(self._outcomes):
            self.outcomes_list.setCurrentRow(select_row)

    def _load_selected(self, row: int) -> None:
        if not 0 <= row < len(self._outcomes):
            return
        outcome = self._outcomes[row]
        self.name_edit.setText(outcome.name)
        self.screen_combo.setCurrentText(outcome.screen)

    def _outcome_from_fields(self) -> DetectionOutcome | None:
        name = self.name_edit.text().strip()
        if not name:
            self.message_label.setText("Enter a name/expected text first.")
            return None
        return DetectionOutcome(name, self.screen_combo.currentText())

    def _add(self) -> None:
        outcome = self._outcome_from_fields()
        if outcome is None:
            return
        self._outcomes.append(outcome)
        self._render(len(self._outcomes) - 1)

    def _update(self) -> None:
        row = self.outcomes_list.currentRow()
        outcome = self._outcome_from_fields()
        if outcome is None:
            return
        if not 0 <= row < len(self._outcomes):
            self.message_label.setText("No outcome selected.")
            return
        self._outcomes[row] = outcome
        self._render(row)

    def _delete(self) -> None:
        row = self.outcomes_list.currentRow()
        if not 0 <= row < len(self._outcomes):
            return
        del self._outcomes[row]
        self._render(min(row, len(self._outcomes) - 1))

    def _move(self, offset: int) -> None:
        row = self.outcomes_list.currentRow()
        target = row + offset
        if not 0 <= row < len(self._outcomes) or not 0 <= target < len(self._outcomes):
            return
        self._outcomes[row], self._outcomes[target] = self._outcomes[target], self._outcomes[row]
        self._render(target)

    def _accept(self) -> None:
        self.result_outcomes_raw = serialize_outcomes(self._outcomes)
        self.accept()
