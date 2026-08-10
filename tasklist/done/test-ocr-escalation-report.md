Title: update die detection confirmation beim TES OCR button. Er soll korrekt reporten ob ja oder
       nein detected werden soll und auch welche staffelung es erkannt hat, damit ist gemeint
       wieviel rand geadddet werden musste bis es erkannt wurde
Completed: 2026-08-10
Commit:    7e1d276

Result: The button always reported "no detection" because LocalBridgeWriteAck serialized a
        hardcoded field whitelist that TEST_OCR's "stage" was not on; that whitelist now iterates
        the result's own properties, RunOcrEscalating reports its ladder trace, and one renderer in
        ipc/protocol.py states the verdict plus the framing that matched (no border, or a
        black/white border of N% per side, with its position in the ladder).
