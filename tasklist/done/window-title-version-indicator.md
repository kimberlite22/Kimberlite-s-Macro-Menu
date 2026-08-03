Title:     display current version and wether or not this is a local built .exe in the window bar
           above the application window
Completed: 2026-08-03
Commit:    -

Result: The main window's title bar now reads "APP_NAME vX.Y.Z" with a provenance suffix. Added a
        release-only marker file (RELEASE_BUILD, written by .github/workflows/release.yml right next
        to the bundled VERSION file, using the same --add-data mechanism) that a local/manual
        PyInstaller build (gui/BUILD.md, tools/build-local-exe.ps1) never produces. New
        launcher_paths.is_release_build(entry_file) checks for that marker; new
        update_check.build_window_title(entry_file) composes the title: no suffix for an official
        release (the expected case), " (local build)" for a frozen bundle missing the marker,
        " (source)" for a non-frozen source run, and a bare APP_NAME fallback if VERSION cannot be
        read at all. MainWindow gained an entry_file keyword (defaulting to None, preserving the old
        plain-APP_NAME title for every caller that omits it); main.py passes its own Path(__file__)
        into both MainWindow(...) call sites, matching the existing entry-script-only resolution
        pattern already used for read_current_version/app_icon_path. Added tests in
        gui/tests/test_update_check.py (four provenance cases) and gui/tests/test_main_window.py
        (title reflects entry_file; default omission still yields plain APP_NAME), and fixed four
        now-stale MagicMock call assertions in gui/tests/test_launcher_paths.py. Full gui/ suite:
        282 passed.
