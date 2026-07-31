Title: uhh und nach ein bisschen testen kommt gerade bei mir: unhandled error :1934 glaube ich ich
       bin mir aber nicht sicher die message war schnell weg
Prio:  4

Goal:  Find and fix whatever throws the unhandled error the user glimpsed during testing (an
       "Unhandled error" MsgBox mentioning line 1934, dismissed by its own 20s timeout before it
       could be read in full - see ReportUnhandledError in macro/tower_defense_macro_gui.ahk,
       registered via OnError near the top of the file).
Open:  Not yet reproduced - checked the installed copy's macro_log.txt
       ("C:\Users\<user>\AppData\Local\Kimberlite's Anime Expedition Macro\macro_log.txt", the
       %LOCALAPPDATA% install ReportUnhandledError logs to) for a line starting "Unhandled error:"
       (ReportUnhandledError always appends the full message plus file:line there regardless of
       whether the MsgBox was seen), but the log's last entry predates when the user saw the
       error, so the exact file/line/message were not recoverable from it this time. Needs either
       a fresh repro with the log checked immediately after, or the user reading the MsgBox text
       before its 20s auto-dismiss. Once reproduced, the log line gives the exact file:line
       without needing to guess.
