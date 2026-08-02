Title: Alle kommazahlen sollen als xx.xxx angegeben werden nicht wie jetzt xx,xxx
Prio:  13

Goal:  Decimal numbers displayed anywhere in the GUI (spin boxes, labels, tooltips) use a period as
       the decimal separator (e.g. "12.500") instead of a comma, regardless of the Windows/German
       system locale Qt would otherwise pick up.
Open:  SafeInt/SafeNum on the AHK engine side still accepts a comma on input per CLAUDE.md; confirm
       this task is display-only (the GUI shows/exports dot-formatted numbers) and does not also
       require the engine or config.ini storage format to change.
