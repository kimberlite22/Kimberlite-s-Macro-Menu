Title: Die jetzt removed gui soll in die python gui migrieren, ein neuer tab mit Live-Stats soll
       reinkommen in dem die stats jetzt leben werden mit allem was vorher drin war.

Completed: 2026-08-08
Commit:    d552a56

Result: A "Live Stats" tab now carries everything the AHK overlay's panels showed (Application
        Stats with its Copy button, the Screen Time table, the live log), the local bridge grew
        currentStepTimeMs, and the engine's session/screen/step clocks were fixed to start at 0 and
        freeze when a run ends instead of free-running off the system uptime.
