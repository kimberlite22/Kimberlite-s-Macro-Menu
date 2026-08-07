Title: Haven't checked the PySide6 version yet. Confirmed I was hovering a freshly rebuilt exe
       (closed everything, rebuilt, launched the new dist/gui.exe directly) and tooltips still
       never show. Haven't tried a plain source run yet. Checked Windows's tooltip/hover settings
       and third-party mouse software - nothing unusual found.
Prio:  1

Goal:  Follow-up from general-parentheses-tooltips-follow-up-4: the user confirmed a freshly
       rebuilt exe (not a stale instance) still shows no tooltips and found nothing unusual in
       Windows's own tooltip/hover settings or third-party mouse software, but has not yet reported
       the exact PySide6 version their build resolved or tried a plain source run
       (`python -m app.main`) to isolate whether this is frozen-build-specific. This round should
       get those two remaining answers and act on them (pin an exact PySide6 version in
       gui/pyproject.toml if a version mismatch turns out to be the cause).
Open:  -
