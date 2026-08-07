Title: Wenn das möglich ist dann, ändere auch das desktop icon von der remote verbindung zu dem app
       icon was wir normal benutzen und den namen auch (wobei ich hab zweifel ob das geht)
Prio:  6

Goal:  The background session connection presents itself as this app rather than as a generic
       Remote Desktop connection: the app's own icon and name.

Open:  - Two separate things, with different odds. A desktop/Start Menu entry is fully ours if the
         app creates a shortcut (.lnk, which carries its own icon and name) instead of handing the
         user a bare .rdp file, which always shows the Remote Desktop icon. That half is
         straightforward, and assets/app.ico already exists (see app_icon_path in
         gui/app/launcher_paths.py).
       - The title bar and taskbar entry of the RUNNING mstsc window are another program's window.
         They can be overwritten after launch through SetWindowText plus WM_SETICON, but that is a
         fragile trick against a window this app does not own, and it has to find the right window
         handle first. The user already expects this half may not work; decide whether it is worth
         doing at all, or whether the shortcut alone satisfies the request.
       - Does the app even need to place a desktop shortcut for this, given Start/Show already
         launch the session from inside the GUI? Possibly the real deliverable is only the mstsc
         window half, which is the fragile one.
