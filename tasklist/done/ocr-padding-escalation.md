Title: manchmal wenn die region etwas kleiner ist dann gibt ocr gar keinen wert zurueck, wenn wir
       den confidence schwellenwert nich modifiyen koennen dann mach es erstmal so. Remove alle
       modifikationen die aktuell mit dem image gemacht werden bevor ocr es scannt. Danach wenn
       wenn ocr keinen wert zurueckgibt oder das ergebnis nicht matched, dann soll das bild was an
       ocr gesendet wird umrahmt werden mit einmal einem schwarzen und weissen kasten in stufen:
       erstmal 10% von der original image grosse am rand dazu und dann 25 und dann 50. Eine regel
       das image am ende darf nicht groesser als 500x500px sein wenn es ist dann soll es abbrechen.
       Wenn man auf den button drueckt soll dann ausserdem angezeigt werden mit welcher staffelung
       es detected wurde.
       (und remove alle aenderung am bild vor ocr ausser die neuen, bevor ich die hatte hat es
       immer problemlos funktioniert und jetzt habe ich immer probleme)
Completed: 2026-08-08
Commit:    -

Result: The 2x bicubic upscale is deleted from ocr/ocr_helper/engine.py, so captures now reach WinRT
        completely unmodified, and a single OCR scan became an escalation ladder: rung 0 is the raw
        capture, then solid black and white borders at +10/+25/+50 percent per side and per axis,
        first matching rung wins, and a rung whose padded result would exceed 750x750 ends the
        ladder (750 rather than the 500 first asked for, decided with the user from the benchmark
        log: the most-scanned region is 395x250 at 87% of 16406 samples, for which 500 would have
        skipped every rung above +10%). The Python helper stays pure mechanism, applying exactly
        the border it is told to through three new protocol fields (pad_x/pad_y/color, with the old
        five-field request still accepted as an unpadded scan so a stale ocr_server.exe degrades
        instead of rejecting everything); all policy lives in AHK's new OcrEscalationStages() /
        RunOcrEscalating(), because the expected text and TextContainsPartialMatch are AHK's and
        splitting the matching rule across two languages was not worth it. The ladder is wired into
        every detection path: IsTextDetectedInRegion, DetectMapProfileInRegion, Advanced Detection's
        named outcomes, and CheckDisconnectTick. Two two-pass exact-then-partial resolvers were
        extracted so the ladder can ask "would anything match?" without duplicating the ordering
        (MapProfileFromOcrText, OutcomeFromOcrText). TEST_OCR now takes the window's expected text
        and returns the winning rung, which both Test OCR buttons display as
        "OCR result: <text>  (detected at: black border +25%)". Notably the frozen PowerShell/WinRT
        baseline in ocr/tests/test_engine.py did NOT need re-freezing: five of its six fixtures were
        small enough to have been upscaled before, and all six still recognize byte-for-byte
        identically without it, which is direct evidence the upscale was not what produced those
        results. Codex review caught one real regression (the ladder overwrote the reported text on
        every non-matching rung, so TrackVictoryDefeat could lose a raw "Victory" read to a later
        padded one); a match now reports its own rung's text and a failure reports the FIRST
        non-empty read, which is what the single raw scan used to be. ocr/ 45 passed, gui/ 582
        passed, AutoHotkey /validate clean.
