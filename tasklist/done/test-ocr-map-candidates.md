Title: Und bei dem step map detection steht einfach kein expected text set was ja auch sein soll
       weil der expected text die maps sind. Funktioniert das verfahren dort auch gleich und bei
       test ocr steht es einfach nicht oder es funktioniert nicht so? Fixe beide cases, das test
       ocr richtig das ergebnis anzeigt oder das map detection nicht wie erwartet funktioniert
Completed: 2026-08-11
Commit:    -

Result: Both cases were real. Test OCR always sent the step's Name field as the one expected text,
        so on a "Detect Map" step (which matches the map profiles' own ExpectedText) and on an
        Advanced Detection (which matches its outcome names, and whose Name field is hidden) it
        tested something the macro never matches on. TEST_OCR now takes a `source`
        ("maps"/"outcomes"/single text) and builds the same candidate list the real detection uses,
        reporting which candidate won so the result can name the map profile or outcome. Separately,
        map detection itself was reading a MapProfileNames global that InitMapProfiles() filled once
        at startup and nothing refreshed, while the Qt GUI writes config.ini directly, so a map
        profile added while the app was running was invisible until the engine restarted; the global
        is gone and MapProfileCandidates() reads the list live.
