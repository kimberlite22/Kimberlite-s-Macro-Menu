Title:     Mache allen text in der gui copy und pasetable also halt markierbar
Completed: 2026-08-02
Commit:    -

Result: Every QLabel in the GUI (explicit and Qt-internal, e.g. via QFormLayout.addRow) is now
mouse-selectable/copyable via a polish() override on the existing app-wide CheckmarkProxyStyle
(gui/app/widgets.py); QGroupBox titles are not QLabel instances and have no text-interaction API,
so they are explicitly out of scope.
