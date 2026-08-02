Title: Mache allen text in der gui copy und pasetable also halt markierbar
Prio:  16

Goal:  Static text labels across the GUI (QLabel instances that currently cannot be selected, e.g.
       group box titles, form row labels, status text) become selectable/copyable with the mouse,
       the way a text field already is, without turning them into editable inputs.
Open:  Qt.TextInteractionFlags.TextSelectableByMouse on every QLabel is the direct mechanism;
       confirm whether this should reach truly every label (including tiny column headers) or is
       meant for the more useful cases (status values, error/log text) rather than every decorative
       label in the app.
