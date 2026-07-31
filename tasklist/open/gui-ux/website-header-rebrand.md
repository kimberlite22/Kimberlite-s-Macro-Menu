Title: Auf der live website sollte oben links nicht mehr Anime Expedition stehen sondern Kimberlites
       Macro menu bei beiden vorkommen
Prio:  1

Goal:  The live remote-access website's top-left branding text reads "Kimberlite's Macro Menu"
       instead of "Anime Expedition" everywhere it currently says the old name in that spot.
Files: remote/server/web/index.html (the <title> tag, the shared header's .top-nav-title span and
       .top-nav-mark "AE" badge, the login-view and dashboard-view brand-mark badges), possibly
       remote/server/web/style.css if the new string needs a layout check (top-nav-brand flex
       sizing).
Steps: 1. Confirm with the user which spots count as the "two occurrences" the note refers to. The
          strongest literal reading of "oben links" (top left) is the browser tab <title> (line 7,
          currently "Anime Expedition Remote") and the shared header's .top-nav-title span (line 17,
          currently "Anime Expedition Remote"), both of which sit top-left of the window/page.
       2. Update the confirmed spot(s) to "Kimberlite's Macro Menu" (or a shortened site-appropriate
          variant for the tab title), matching whatever short form the broader
          [[project-rename]] task settles on for the rest of the app.
       3. Check the "AE" initials badges (.top-nav-mark at line 16, .brand-mark at lines 33/68) for
          the same reason since they are also top-left; update if they should reflect the new name.
       4. Verify no layout break from the new string length (top-nav-brand flex sizing in
          style.css).
       5. Leave the centered "Anime Expedition" <h1> headings inside the login/dashboard cards
          (lines 35, 90) and the docs-brand-name (line 270) to [[project-rename]] unless the user
          confirms those also count as "top left".
Open:  Which exact two spots the user means by "beiden Vorkommen" (see Steps 1). Also whether this
       should just be folded into [[project-rename]] instead of shipped separately, since both touch
       the same file.
