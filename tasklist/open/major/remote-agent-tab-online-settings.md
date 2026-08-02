Title: Reworke den remote agent tab, der text der das erklärt soll removed werden, der tab soll zu
       Online Settings umbenannt werden. Und die ganzen sachen da soll nur anmelden un pair sein.
       Agent executable soll automatisch detected werden. Die url ist immer gleich ->
       kimberlitemacro.duckdns.org usw. (mach das als priom low gerade nicht gebraucht aber gut für
       zukunft)
Prio:  8

Goal:  The "Remote Agent" tab (gui/app/remote_agent_tab.py) is renamed to "Online Settings", drops
       its explanatory text, and is trimmed down to just sign-in and pair; the agent executable path
       field is replaced by automatic detection instead of manual entry, and the server URL is fixed
       to kimberlitemacro.duckdns.org instead of being user-entered. Explicitly deprioritized by the
       user: not needed right now, kept for later.
Open:  What happens to "Start Agent"/"Stop Agent" and the "Enable remote bridge" checkbox currently
       in this tab (see "Pairing and agent bundling" in CLAUDE.md) - stay, move elsewhere, or get
       removed along with the explanatory text? DefaultRemoteAgentPath() already resolves a
       bundled/dev path automatically; confirm this task means dropping the manual override field
       entirely rather than just defaulting it.
