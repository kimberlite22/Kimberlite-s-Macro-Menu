Title: Normalerweise ist bei feldern der text dann doppelpunkt und dann das feld. Remove den
       doppelpunkt.
Prio:  12

Goal:  Field label text across the GUI (the "Label:" then field convention used throughout
       gui/app/*.py, mostly QFormLayout addRow calls) no longer has a trailing colon; labels read as
       plain text immediately followed by their field.
Open:  Whether this also applies to non-form-row colon labels, e.g. the standalone "Search:" label
       (gui/app/main_window.py:236) and status labels like "Runs on Start: -"
       (gui/app/main_window.py:455), or is scoped specifically to the label-then-field form pattern
       the request describes.
