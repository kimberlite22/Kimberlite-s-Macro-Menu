Title:     Alle kommazahlen sollen als xx.xxx angegeben werden nicht wie jetzt xx,xxx
Completed: 2026-08-02
Commit:    -

Result: NoScrollDoubleSpinBox (gui/app/widgets.py), the single class every decimal spin box in the
GUI is built through, now sets its own C locale via setLocale(), so decimal fields always display
and parse a period separator regardless of the system locale, without touching AHK's SafeInt/SafeNum
or config.ini's storage format.
