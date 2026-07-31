Title: Remote agent setup soll einen eigenen tab bekommen
Prio:  6

Goal:  Remote agent setup lives in a top-level tab instead of a separate window reached from the
       bottom strip.
Files: gui/app/main_window.py (tab bar), gui/app/remote_agent_window.py,
       gui/tests/test_remote_agent_window.py
Steps: 1. Turn the window content into a plain widget and mount it as a tab.
       2. Keep pairing / start / stop logic untouched, including the agent-side argument quoting
          and the credentials-file handling (security relevant, must not be regressed).
       3. Remove or redirect the old button, update the tests and the Documentation tab.
Open:  Does the "Enable remote bridge" checkbox move into the new tab as well, or stay in the
       bottom strip?
