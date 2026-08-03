Title: presets -> todays challenge usage, remove the lone "option" at the top right of the widget,
Prio:  2

Goal:  In the Presets tab's "Today's Challenge Usage" group box (gui/app/main_window.py:490), remove
       the "Option" header label in the usage grid's top row. It is the only place in the whole
       gui/app codebase where the bare word "Option" appears (grep confirms no other match), and it
       is redundant: the three rows right below it already read "Option 1"/"Option 2"/"Option 3", so
       the header adds nothing.
Open:  -
