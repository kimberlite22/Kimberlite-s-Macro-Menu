Title:     there is still one checkmark in general -> tower loadout -> click after each tower placed
Completed: 2026-08-02
Commit:    a8048a9

Result: The General tab's Tower Loadout "click after each tower placed" checkbox now follows the label-first visual pattern applied in the earlier checkbox-order-follow-up task: the checkbox text moved into a QLabel with setBuddy() for accessibility, and the checkbox is now bare, matching the established pattern across the GUI. All GUI tests pass.
