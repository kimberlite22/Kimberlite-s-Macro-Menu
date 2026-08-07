Title: in background session mach den current restore the windows default eine checkmark. Wenn man
       dann auf start drueckt dann soll erst das admin confirmation window kommen

Prio:  2

Goal:  The Background Session tab's machine-wide no-desktop setting is a checkbox instead of a push
       button, and its elevation prompt moves to Start. Today gui/app/background_session_tab.py's
       no_desktop_button (see _refresh_boot_mode and _toggle_no_desktop_mode) is a button that reads
       "Enable no-desktop mode (administrator)" or "Restore the Windows default (administrator)"
       depending on rdp_wrapper.initial_program_allow_list_disabled(), and pressing it runs the
       registry change plus its UAC prompt immediately. After this task the user only ticks or
       unticks a checkbox, which records the wanted state, and the administrator confirmation window
       appears when Start is pressed, as part of starting the session.

Open:  Several decisions the implementation cannot make alone:
       - What happens when the user declines the UAC prompt at Start: start the session anyway with a
         normal Windows desktop, or abort the start and say why?
       - Does an unticked checkbox actively restore the Windows default at Start (which would prompt
         for administrator rights on every Start until the machine setting is back to its default),
         or does it only ever mean "do not enable it now"?
       - How this relates to the existing "Boot straight into the macro" checkbox
         (minimal_shell_checkbox), which already reflects the same route: two checkboxes about the
         same underlying choice may be one too many, so decide whether they merge into one control
         or stay separate with clearly different wording.
