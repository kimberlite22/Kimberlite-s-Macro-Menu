Title: Zu den application stats soll session time, time spent in screen x und time spent repeating
       step x. Die stats sollen auch zur internet website geaddet werden. Du kannst in der gui die
       kommt wenn das macro aktiv ist die rechte untere box anpassen zu so ähnlich wie application
       stats nicht mehr nur raw text wie logs, zu den werten die geaddet werden sollen
Prio:  6

Goal:  Application stats gain three new tracked values: total session time, time spent in each
       screen, and time spent repeating each step. These new stats are also surfaced on the remote
       website alongside the existing status/log data. The bottom-right box shown in the GUI while
       the macro is running is redesigned from raw log text into a structured stats display
       (similar to today's existing application-stats presentation) showing these values.
Open:  Is "die rechte untere box" the log panel specifically, or the existing stats panel getting
       these fields added - should the raw log move elsewhere instead of being replaced outright?
       Does "time spent repeating step x" mean cumulative time across every visit to that step
       within a run, or time spent on the current repetition/loop only? What should the website
       surface: live values only, or historical/session history too? Relates to [[stats-reset]]
       (existing counters already reset on restart) for how these new time-based stats should behave
       across restarts and preset switches. Also relates to [[engine-status-remove-fields]] since
       some of the fields being removed from the top status strip may end up here instead.
