"""Background Session tab: start, show and stop the hidden background Windows session."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app import (
    background_session,
    engine_process,
    rdp_wrapper,
    session_autostart,
    session_shell,
    window_branding,
)
from app.launcher_paths import APP_NAME, app_icon_path, install_dir
from app.widgets import FormLayout


# How a background session is made to come up running the macro. The two working routes differ in
# what they cost the user, not in what they achieve, so the tab picks the best AVAILABLE one rather
# than making the user choose between mechanisms they would have to understand first.
BOOT_ROUTE_SHELL = "shell"
BOOT_ROUTE_AUTOSTART = "autostart"
BOOT_ROUTE_NONE = "none"


class BackgroundSessionTab(QWidget):
    """Lets the user run the macro in a second, hidden Windows session, physical desktop free."""

    def __init__(
        self,
        data_dir: Path,
        parent: QWidget | None = None,
        *,
        entry_file: Path | None = None,
        check_setup: object | None = None,
        thread_starter: object = threading.Thread,
        confirm_stop_engine: object | None = None,
    ) -> None:
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self._entry_file = entry_file
        self._branding_cancel: threading.Event | None = None
        self._branding_thread: threading.Thread | None = None
        self._branding_process: object | None = None
        # Injectable so the tab's own tests can drive every setup verdict without needing the real
        # machine to be in that state; production always uses the real detection.
        self._check_setup = check_setup or rdp_wrapper.check_setup
        # Injectable so tests do not start a real worker while they verify the tab's lifecycle.
        self._thread_starter = thread_starter
        # Injectable so tests can choose the handoff without opening a modal dialog.
        self._confirm_stop_engine = confirm_stop_engine
        self._can_start = False
        # None until the first _refresh_boot_mode, which is how it tells "render this for the first
        # time" from "the user has since had a say in the checkbox".
        self._boot_route_value: str | None = None
        # The machine setting the no-desktop checkbox was last rendered from, for the same reason:
        # it separates "the machine changed under us" from "the user ticked the box themselves".
        self._no_desktop_machine_value: bool | None = None
        self._build_ui()
        self._refresh_setup()
        self._refresh_boot_mode()
        self._refresh_status()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        description = QLabel(
            "Runs the macro in a second Windows session so the physical desktop stays free for "
            "other work. This needs RDP Wrapper, a third-party tool that is deliberately not "
            "bundled with this app: several antivirus products flag it, which would break the "
            "app's own updates. Installing it needs administrator rights and a reboot. Note that "
            "running several sessions at once on a Windows client edition goes beyond what "
            "Microsoft's licensing intends."
        )
        description.setWordWrap(True)
        root.addWidget(description)

        setup = QGroupBox("Setup")
        setup_layout = QVBoxLayout(setup)
        self.setup_summary_label = QLabel()
        self.setup_summary_label.setObjectName("background_session_setup_summary_label")
        self.setup_summary_label.setWordWrap(True)
        setup_layout.addWidget(self.setup_summary_label)
        self.setup_details_label = QLabel()
        self.setup_details_label.setObjectName("background_session_setup_details_label")
        self.setup_details_label.setWordWrap(True)
        setup_layout.addWidget(self.setup_details_label)
        recheck_row = QHBoxLayout()
        self.recheck_button = QPushButton("Re-check")
        self.recheck_button.setObjectName("background_session_recheck_button")
        self.recheck_button.setToolTip(
            "Runs the four setup checks again. Use it after installing RDP Wrapper and rebooting, "
            "or after changing one of the settings named above."
        )
        recheck_row.addWidget(self.recheck_button)
        recheck_row.addStretch(1)
        setup_layout.addLayout(recheck_row)
        root.addWidget(setup)

        credentials = QGroupBox("Sign-in credential")
        credentials_layout = QVBoxLayout(credentials)
        form = FormLayout()
        self.username_edit = QLineEdit(os.environ.get("USERNAME", ""))
        self.username_edit.setObjectName("background_session_username_edit")
        self.username_edit.setToolTip(
            "The Windows account to sign in to the background session with - normally this "
            "account, already filled in."
        )
        form.addRow("Username", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setObjectName("background_session_password_edit")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setToolTip(
            "Only needed once: click Save Credential to store it in Windows Credential Manager, "
            "then leave this blank. Never written to config.ini or anywhere else this app persists."
        )
        form.addRow("Password", self.password_edit)
        credentials_layout.addLayout(form)

        credential_actions = QHBoxLayout()
        self.save_credential_button = QPushButton("Save Credential")
        self.save_credential_button.setObjectName("background_session_save_credential_button")
        self.forget_credential_button = QPushButton("Forget Credential")
        self.forget_credential_button.setObjectName("background_session_forget_credential_button")
        credential_actions.addWidget(self.save_credential_button)
        credential_actions.addWidget(self.forget_credential_button)
        credential_actions.addStretch(1)
        credentials_layout.addLayout(credential_actions)
        root.addWidget(credentials)

        self.status_label = QLabel("Background session: unknown.")
        self.status_label.setObjectName("background_session_status_label")
        self.status_label.setWordWrap(True)
        root.addWidget(self.status_label)

        self.minimal_shell_checkbox = QCheckBox()
        self.minimal_shell_checkbox.setObjectName("background_session_minimal_shell")
        self.minimal_shell_label = QLabel("Boot straight into the macro")
        self.minimal_shell_label.setObjectName("background_session_minimal_shell_label")
        self.minimal_shell_label.setBuddy(self.minimal_shell_checkbox)
        minimal_shell_row = QHBoxLayout()
        minimal_shell_row.addWidget(self.minimal_shell_label)
        minimal_shell_row.addWidget(self.minimal_shell_checkbox)
        minimal_shell_row.addStretch(1)
        root.addLayout(minimal_shell_row)

        # Says which of the two routes this machine will actually use, and offers the one-time
        # administrator action that unlocks the better one. The option itself never silently
        # produces a broken session: whichever route is offered is one that works here.
        self.boot_mode_label = QLabel()
        self.boot_mode_label.setObjectName("background_session_boot_mode_label")
        self.boot_mode_label.setWordWrap(True)
        root.addWidget(self.boot_mode_label)

        # A checkbox rather than a button, and deliberately without a handler: ticking it only
        # records what the user wants. The machine-wide change and its administrator prompt happen
        # as part of Start (see _apply_no_desktop_setting), so the elevation the user is asked for
        # always belongs to a session they are starting right now, instead of arriving out of
        # nowhere while they are still setting the tab up.
        no_desktop_row = QHBoxLayout()
        self.no_desktop_checkbox = QCheckBox()
        self.no_desktop_checkbox.setObjectName("background_session_no_desktop_checkbox")
        self.no_desktop_label = QLabel("Run without a Windows desktop (administrator)")
        self.no_desktop_label.setObjectName("background_session_no_desktop_label")
        self.no_desktop_label.setBuddy(self.no_desktop_checkbox)
        no_desktop_tooltip = (
            "Ticked, the background session runs with no Windows desktop at all, so it costs less "
            "memory and CPU. That needs one machine-wide Windows setting changed, so Windows asks "
            "for administrator rights when you press Start. Unticked, Windows' own default is "
            "restored and the session keeps a normal desktop. Either way the change only happens "
            "at Start, and only when this box no longer matches the machine."
        )
        self.no_desktop_checkbox.setToolTip(no_desktop_tooltip)
        self.no_desktop_label.setToolTip(no_desktop_tooltip)
        no_desktop_row.addWidget(self.no_desktop_label)
        no_desktop_row.addWidget(self.no_desktop_checkbox)
        no_desktop_row.addStretch(1)
        root.addLayout(no_desktop_row)

        session_actions = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.setObjectName("background_session_start_button")
        self.start_button.setToolTip(
            "Creates the background session and disconnects it immediately, so it keeps running "
            "with no window open. Can take up to a minute the first time a session logs on."
        )
        self.show_button = QPushButton("Show")
        self.show_button.setObjectName("background_session_show_button")
        self.show_button.setToolTip("Reconnects to the running background session for a look.")
        self.stop_button = QPushButton("Stop")
        self.stop_button.setObjectName("background_session_stop_button")
        self.stop_button.setToolTip("Ends the background session outright (signs it out).")
        session_actions.addWidget(self.start_button)
        session_actions.addWidget(self.show_button)
        session_actions.addWidget(self.stop_button)
        session_actions.addStretch(1)
        root.addLayout(session_actions)

        self.result_text = QPlainTextEdit()
        self.result_text.setObjectName("background_session_result_text")
        self.result_text.setReadOnly(True)
        self.result_text.setMinimumHeight(90)
        root.addWidget(self.result_text, 1)

        self.save_credential_button.clicked.connect(self._save_credential)
        self.forget_credential_button.clicked.connect(self._forget_credential)
        self.recheck_button.clicked.connect(self._recheck)
        self.start_button.clicked.connect(self._start)
        self.show_button.clicked.connect(self._show)
        self.stop_button.clicked.connect(self._stop)

    def _save_credential(self) -> None:
        username = self.username_edit.text().strip()
        password = self.password_edit.text()
        if not username:
            self._set_result("Enter the username first.")
            return
        if not password:
            self._set_result("Enter the password first.")
            return
        ok = background_session.store_credential(background_session.TARGET_ADDRESS, username, password)
        self.password_edit.clear()
        self._set_result(
            "Credential saved." if ok else "Could not save the credential to Windows Credential Manager."
        )

    def _forget_credential(self) -> None:
        result = background_session.forget_credential(background_session.TARGET_ADDRESS)
        self._set_result(result.message)

    def _start(self) -> None:
        # The real gate. A disabled button only hides the action from a mouse click; this is what
        # actually keeps a start off a machine with a genuine setup problem.
        if not self._can_start:
            self._set_result(
                "Setup is not ready yet. Resolve the points in the Setup box above, then press "
                "Re-check."
            )
            return
        username = self.username_edit.text().strip()
        if not username:
            self._set_result("Enter the username first.")
            return
        # These are cheap, non-destructive refusals. Let the session helper give its canonical
        # message before offering to stop a local macro that could otherwise keep running.
        if (
            background_session.is_background_session_active(self.data_dir)
            or not background_session.credential_exists(background_session.TARGET_ADDRESS)
        ):
            self._start_background_session(username)
            return
        # The GUI starts the engine that would otherwise make Start unreachable from a cold state,
        # so a confirmed local engine must hand over to the background session instead of blocking it.
        engines = engine_process.find_engine_processes()
        local_engine_message = (
            "The macro engine is running on this desktop right now. Stop it first: starting a "
            "background session while it runs would leave two engines sharing one config."
        )
        if engines:
            own_session = engine_process.current_session_id()
            if own_session is None or any(engine.session_id is None for engine in engines):
                self._set_result(local_engine_message)
                return
            local_engines = [engine for engine in engines if engine.session_id == own_session]
        else:
            local_engines = []
        if local_engines:
            prompt = (
                "The macro engine is running on this desktop. It will be stopped so the "
                "background session can take over. Any macro run in progress here will be stopped."
            )
            if self._confirm_stop_engine is None:
                confirmed = (
                    QMessageBox.question(
                        self,
                        "Stop macro engine on this desktop?",
                        prompt,
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    == QMessageBox.StandardButton.Yes
                )
            else:
                confirmed = bool(self._confirm_stop_engine())
            if not confirmed:
                self._set_result("Nothing was changed. The background session was not started.")
                return
            # A modal confirmation can remain open for an arbitrary time. Re-enumerate only once
            # the user confirms, so every PID passed to the shutdown helper is still current.
            own_session = engine_process.current_session_id()
            engines = engine_process.find_engine_processes()
            if engines and (
                own_session is None or any(engine.session_id is None for engine in engines)
            ):
                self._set_result(local_engine_message)
                return
            local_engines = (
                [engine for engine in engines if engine.session_id == own_session]
                if own_session is not None
                else []
            )
            # Do not use local_status.json here. It can outlive its engine, so stale state could
            # either block Start forever or silently stop a live macro. The user makes this call.
            for engine in local_engines:
                engine_process.stop_engine_by_pid(engine.pid)
            remaining_engines = engine_process.find_engine_processes()
            if any(engine.session_id == own_session for engine in remaining_engines):
                self._set_result("The macro engine on this desktop could not be stopped.")
                return
        self._start_background_session(username)

    def boot_route(self) -> str:
        """Return how this machine can make a background session come up running the macro.

        The order is a preference, not a fallback chain that hides failures. The alternate shell is
        better when it is available (the session then holds only Roblox and the engine, with no
        desktop to pay for), but Windows only launches it when the RemoteApp allow list is switched
        off, and that is an administrator-only machine setting. Autostart achieves the same user
        outcome with a normal desktop and needs no rights at all, so it is what an ordinary machine
        gets.

        Note the strict ``is True``: an allow-list setting that could not be READ must not be
        treated as available. Guessing wrong in that direction produces a session with no shell at
        all, which is precisely the failure this whole task exists to remove.
        """
        if (
            session_shell.session_shell_available()
            and rdp_wrapper.initial_program_allow_list_disabled() is True
        ):
            return BOOT_ROUTE_SHELL
        if session_autostart.autostart_available():
            return BOOT_ROUTE_AUTOSTART
        return BOOT_ROUTE_NONE

    def _refresh_boot_mode(self) -> None:
        """Render what the option will actually do here, and offer the way to improve it."""
        route = self.boot_route()
        available = route != BOOT_ROUTE_NONE
        previous_route = self._boot_route_value
        self._boot_route_value = route
        self.minimal_shell_checkbox.setEnabled(available)
        if not available:
            self.minimal_shell_checkbox.setChecked(False)
        elif previous_route in (None, BOOT_ROUTE_NONE):
            # Default the option on the first time it can do anything at all (the initial render,
            # or right after the user unlocked a route). A later refresh deliberately leaves the box
            # alone: by then its state is the user's own choice, not a default.
            self.minimal_shell_checkbox.setChecked(True)

        if route == BOOT_ROUTE_SHELL:
            self.minimal_shell_label.setText("Boot straight into the macro, with no Windows desktop")
            tooltip = (
                "Starts the background session with this app as its Windows shell instead of "
                "Explorer, so the session holds only Roblox and the macro engine: no desktop, no "
                "start menu, less memory and CPU used in the background. A small control window "
                "inside that session can bring Explorer back if you ever need to fix something "
                "there."
            )
            self.boot_mode_label.setText(
                "This machine can run the background session with no Windows desktop at all."
            )
        elif route == BOOT_ROUTE_AUTOSTART:
            self.minimal_shell_label.setText("Boot straight into the macro")
            tooltip = (
                "Starts Roblox and the macro engine automatically as soon as the background "
                "session logs on, so you only press Start. The session keeps a normal Windows "
                "desktop, which costs some memory and CPU in the background."
            )
            self.boot_mode_label.setText(
                "The background session will keep a normal Windows desktop. Running it without one "
                "needs a Windows setting that only an administrator can change; Windows blocks a "
                "Remote Desktop session's start-up program until then."
            )
        else:
            self.minimal_shell_label.setText("Boot straight into the macro")
            tooltip = (
                "Unavailable here: this launch has no installed copy of the app for the background "
                "session to start, so the session comes up with a normal Windows desktop and "
                "nothing running in it."
            )
            self.boot_mode_label.setText(
                "Unavailable from a source checkout: there is no installed copy of the app for the "
                "background session to start."
            )
        self.minimal_shell_checkbox.setToolTip(tooltip)
        self.minimal_shell_label.setToolTip(tooltip)

        # The option is only worth showing when acting on it would change something: there has to be
        # an installed shell executable for the no-desktop route to point at in the first place.
        allow_list_disabled = rdp_wrapper.initial_program_allow_list_disabled()
        applies = session_shell.session_shell_available() and allow_list_disabled is not None
        self.no_desktop_checkbox.setVisible(applies)
        self.no_desktop_label.setVisible(applies)
        if not applies:
            # Forget the machine value rather than remembering it. The box was never rendered from
            # it here, so remembering it would make the next render that CAN show the box see "no
            # change" and leave the box on its unchecked default while the machine is switched on.
            # Start would then read that stale default as the user asking to restore the default.
            self._no_desktop_machine_value = None
            return
        # Follow the machine only when the machine itself moved (including the very first render,
        # where the remembered value is still None). A later refresh that finds the same setting
        # leaves the box alone: by then its state is the user's own pending choice, and re-syncing
        # it here would silently undo a tick they have not pressed Start on yet.
        if allow_list_disabled is not self._no_desktop_machine_value:
            self.no_desktop_checkbox.setChecked(bool(allow_list_disabled))
        self._no_desktop_machine_value = allow_list_disabled

    def _no_desktop_setting_applies(self) -> bool:
        """Whether the checkbox's state means anything on this machine right now.

        Same condition the rendering uses, and deliberately not ``isVisible()``: a widget reports
        itself invisible whenever an ancestor is hidden, so an unopened tab would be read as "the
        option does not apply here" and Start would quietly skip a setting the user did tick.
        """
        return (
            session_shell.session_shell_available()
            and rdp_wrapper.initial_program_allow_list_disabled() is not None
        )

    def _apply_no_desktop_setting(self) -> str:
        """Make the machine match the checkbox, and return what to tell the user (or "").

        Called by Start, which is where the administrator prompt the user sees comes from. A
        declined prompt is reported and then deliberately ignored: the setting only decides whether
        the session can boot WITHOUT a desktop, and a session with one still works, so refusing the
        elevation must cost the user their session no more than not offering it at all would.
        """
        if not self._no_desktop_setting_applies():
            return ""
        wanted = self.no_desktop_checkbox.isChecked()
        if rdp_wrapper.initial_program_allow_list_disabled() is wanted:
            return ""
        result = rdp_wrapper.set_initial_program_allow_list_disabled(wanted)
        # Re-render before the route is picked, so the tab is not left describing the boot mode the
        # machine had a moment ago.
        self._refresh_boot_mode()
        return result.message

    def _start_background_session(self, username: str) -> None:
        # Before anything reads the boot route: this is the call that can change which route is
        # available, so picking one first would start the session in the mode the machine was in a
        # moment ago rather than the one the user asked for.
        no_desktop_message = self._apply_no_desktop_setting()
        self._set_result(
            f"{no_desktop_message}\nStarting background session..."
            if no_desktop_message
            else "Starting background session..."
        )
        self._set_buttons_enabled(False)
        alternate_shell = None
        shell_working_directory = None
        before_launch = None
        armed = False
        # A list rather than a bare name, because before_launch runs inside the helper and needs
        # somewhere to leave its outcome that this frame can still read afterwards. It records
        # SUCCESS rather than failure on purpose: the helper calls before_launch inside a
        # catch-everything block, so an arm() that RAISED would leave a failure-flag list empty and
        # be read as success. An empty success list means "no confirmed arm", which is the answer
        # that matters, whether the reason was a False return or an exception nobody saw.
        arm_results: list[bool] = []
        route = self.boot_route() if self.minimal_shell_checkbox.isChecked() else BOOT_ROUTE_NONE
        if route == BOOT_ROUTE_SHELL:
            alternate_shell = session_shell.session_shell_command()
            shell_working_directory = str(install_dir())
        elif route == BOOT_ROUTE_AUTOSTART and session_autostart.install_autostart_entry():

            def arm_autostart() -> None:
                # Armed at the last possible moment rather than up here, so a refusal inside the
                # helper cannot leave an authorisation lying around for an unrelated RDP logon.
                arm_results.append(bool(session_autostart.arm(self.data_dir)))

            before_launch = arm_autostart
            armed = True
        try:
            result = background_session.start_background_session(
                self.data_dir, background_session.TARGET_ADDRESS, username,
                alternate_shell=alternate_shell,
                shell_working_directory=shell_working_directory,
                before_launch=before_launch,
                pump=QApplication.processEvents,
            )
        finally:
            self._set_buttons_enabled(True)
        message = result.message
        # "It ran and said yes", so an empty list (before_launch never got there, or raised inside
        # the helper's catch-everything block) is correctly NOT a confirmation.
        arm_confirmed = bool(arm_results) and all(arm_results)
        if armed and not result.ok and result.session_id is None:
            # No session came up, so nothing will ever claim what was armed. Retract it now rather
            # than leaving it to expire, or an RDP logon the user makes in the next few minutes
            # would be met with a macro starting itself.
            session_autostart.disarm(self.data_dir)
            session_autostart.remove_autostart_entry()
        elif armed and not arm_confirmed:
            # The session is coming up, but nothing in it will start the macro. That is a working
            # Windows session with an empty desktop, which looks enough like success to be worth
            # saying out loud rather than leaving the user to discover it.
            session_autostart.remove_autostart_entry()
            message += (
                " The session will not start the macro by itself, because the file that authorises "
                "it could not be written. Start Roblox and the macro inside the session instead, or "
                "press Show to look at it."
            )
        # Kept in front of the session's own outcome rather than dropped: a declined administrator
        # prompt is the reason a session came up with a desktop it was not supposed to have, and
        # that explanation is worth more here than the intermediate "Starting..." line it replaces.
        if no_desktop_message:
            message = f"{no_desktop_message}\n{message}"
        self._set_result(message)
        self._refresh_status()

    def _show(self) -> None:
        self._stop_window_branding()
        username = self.username_edit.text().strip()
        if not username:
            self._set_result("Enter the username first.")
            return
        # Pumping keeps the window responsive while Show waits for an active session to release,
        # but also makes this handler reentrant. Keep all session actions unavailable until it ends.
        self._set_buttons_enabled(False)
        try:
            result = background_session.show_background_session(
                self.data_dir, username, pump=QApplication.processEvents
            )
        finally:
            self._set_buttons_enabled(True)
        if result.ok and result.client_pid is not None and result.client_process is not None:
            try:
                self._start_window_branding(result.client_pid, result.client_process)
            except Exception:
                pass
        self._set_result(result.message)
        self._refresh_status()

    def _start_window_branding(self, client_pid: int, client_process: object) -> None:
        """Retry Win32 window branding while mstsc is still replacing its connecting title."""
        self._stop_window_branding()
        icon = app_icon_path(self._entry_file) if self._entry_file is not None else None
        title = f"{APP_NAME} - Background Session"
        cancel = threading.Event()
        thread = self._thread_starter(
            target=window_branding.run_branding_loop,
            args=(client_pid, title, icon, cancel),
            # Handed to the worker as well, not only held here: see run_branding_loop's own
            # docstring for why the reference has to live on the worker's frame.
            kwargs={"keep_alive": client_process},
            daemon=True,
        )
        self._branding_cancel = cancel
        self._branding_thread = thread
        # Deliberately kept for its side effect: its open process handle reserves client_pid.
        # No method is called on it.
        self._branding_process = client_process
        thread.start()

    def _stop_window_branding(self) -> None:
        if self._branding_cancel is not None:
            self._branding_cancel.set()
        self._branding_cancel = None
        self._branding_thread = None
        self._branding_process = None

    def _stop(self) -> None:
        # Once the session is stopped, mstsc is going away, and a recycled pid could otherwise
        # have an unrelated program's window branded.
        self._stop_window_branding()
        # Buttons off for the same reason _start does it: pumping Qt events to keep the window
        # responsive also lets a second click land INSIDE this call. A reentrant Stop would log
        # off twice, and a Start reaching in here could have its brand new session's marker
        # cleared by the stop that is still finishing.
        self._set_buttons_enabled(False)
        try:
            result = background_session.stop_background_session(
                self.data_dir, pump=QApplication.processEvents
            )
        finally:
            self._set_buttons_enabled(True)
        self._set_result(result.message)
        self._refresh_status()

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for button in (self.start_button, self.show_button, self.stop_button):
            button.setEnabled(enabled)
        if enabled:
            # Never re-enable Start past the can-start gate: _start's own finally block runs
            # through here, and without this a failed attempt would leave Start clickable again
            # on a machine with a genuine setup problem.
            self.start_button.setEnabled(self._can_start)

    def _recheck(self) -> None:
        """Re-run everything the Setup box reports, including which boot route is available.

        One button for both: the settings behind them are changed in the same places (an elevated
        prompt, an install, a reboot), so re-checking one without the other would leave the tab
        showing a mix of fresh and stale answers.
        """
        self._refresh_setup()
        self._refresh_boot_mode()

    def _refresh_setup(self) -> None:
        """Re-run the setup checks and render them, gating Start on the outcome."""
        status = self._check_setup()
        self._can_start = bool(status.can_start)
        if status.ok and not status.undetermined:
            self.setup_summary_label.setText("Setup: ready. All four checks passed.")
        elif self._can_start:
            self.setup_summary_label.setText(
                "Setup: could not be fully confirmed. Start is enabled anyway. Only start with "
                "warnings if you know what you are doing."
            )
        else:
            self.setup_summary_label.setText(
                "Setup: not ready. Start stays disabled until the points below are resolved."
            )
        lines = []
        for check in status.checks:
            prefix = "OK" if check.ok else "Warning" if check.undetermined else "Needs attention"
            lines.append(f"{prefix}: {check.name} - {check.detail}")
            if not check.ok and check.remediation:
                lines.append(f"    {check.remediation}")
        self.setup_details_label.setText("\n".join(lines))
        self.start_button.setEnabled(self._can_start)

    def _refresh_status(self) -> None:
        marker, status = background_session._resolve_marker(self.data_dir)
        if marker is None or status == "none":
            self.status_label.setText("Background session: not running.")
            return
        session = background_session.find_session_by_id(marker.session_id)
        if session is None:
            self.status_label.setText("Background session: not running.")
            return
        try:
            state = background_session.SessionState(session.state).name.lower()
        except ValueError:
            state = "unknown"
        self.status_label.setText(f"Background session: running ({state}).")

    def _set_result(self, message: str) -> None:
        self.result_text.setPlainText(message)
