Title: yes its way faster but still the first time i start the built .exe one stray gui.exe remains
       in the background
Completed: 2026-08-12
Commit:    -

Result: Closed by the user, who reports the stray gui.exe no longer appears on the first launch of a
        freshly built exe, so no code change was made for it. The two leads the task had listed are
        therefore still untouched should the symptom ever return: gui/app/self_install.py:182 still
        relaunches the installed copy with subprocess.Popen(command,
        creationflags=DETACHED_PROCESS) and no explicit stdio redirect (step 3), and a brand-new
        onefile exe's first-run AV scan (step 4) was never ruled out as the real cause.
