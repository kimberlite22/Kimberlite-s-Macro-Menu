Title:     Remote agent setup soll einen eigenen tab bekommen
Completed: 2026-08-01
Commit:    -

Result: Remote Agent Setup is now a permanent top-level tab (RemoteAgentTab, a QWidget in
gui/app/remote_agent_tab.py, renamed from remote_agent_window.py) in MainWindow's tab bar, instead
of a QDialog opened from a bottom-strip button. The "Enable remote bridge" checkbox moved into
this new tab too (resolved decision), aliased in MainWindow so _populate_general/_general_payload
are unchanged. Pairing / start / stop / credentials-file logic in _pair, _start_agent, _stop_agent
and _send_lifecycle_command is untouched, only the container class changed (QDialog -> QWidget).
