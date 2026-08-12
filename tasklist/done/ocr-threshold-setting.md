Title:     Give [General] OcrMatchThreshold a field in the GUI
Completed: 2026-08-12
Commit:    -

Result: The General tab has a new "Text Detection" group box with a "Match threshold" spin box
        (30% to 100%, 5% steps), so the OCR match threshold no longer needs a text editor. It sits
        in its own box rather than inside "Disconnect Detection" because it governs every text
        detection, not just the reconnect watchdog. config.ini keeps storing the engine's
        0.30..1.00 fraction under the unchanged [General] OcrMatchThreshold key, and the matching
        rule, its clamp and its scoring are untouched: percent is a display unit only. Every
        user-visible score moved to that same percent, so the field and the numbers it is compared
        against read alike: OcrMatchNote/OcrMissNote in macro/ocr_matching.ahk now log
        "(best 'Victory' 61% < 75%)", and the Test OCR result says "score 100%, needs 75%"
        (gui/ipc/protocol.py). The conversion lives in one place, protocol.ocr_score_percent(),
        rounding half away from zero to agree with AHK's Round(); a second copy is exactly how the
        field and the log would end up a percent apart. New config_reader._ocr_match_threshold()
        reproduces the engine's OcrMatchThreshold() fallback exactly (missing, unparseable,
        non-finite or outside 0.30..1.00 gives 0.75) rather than reading through _number(): the key
        is absent from every existing config because nothing ever wrote it, and _number()'s 0 would
        have clamped the spin box to 30% and silently replaced the user's effective threshold on
        the next save. Tests: gui/ 703 passed, macro/tests/test_ocr_matching.ahk 47/47.
