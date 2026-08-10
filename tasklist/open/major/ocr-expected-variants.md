Title: mehrere felder in expected hinzufügen die man kann, gegen die seperat gecheckt wird,
       ausserdem dazu noch das wenn man auf test ocr drückt ein neuer button kommt: "Add as
       expected" oder so ähnlich
Prio:  8

Goal:  Any "expected text" field used for OCR matching supports several independent text variants
       instead of a single string, each scored separately so the best matching variant counts as
       detected. Wherever a "Test OCR" button already exists for such a field, a new button next to
       it (working label "Add as expected") adds the just-recognized text as a new variant.
Open:  Which expected-text fields get this: Map Profile ExpectedText (DetectMapProfileInRegion),
       Logic step Label, Option Availability Check DetText, Advanced Outcomes Name, and Disconnect
       Detection - all of them, or a subset first? How is the variant list stored in config.ini
       (repeated numbered keys vs. one key with a delimiter the config format doesn't otherwise
       use) so existing single-value configs keep working unmigrated? How does the GUI edit
       multiple variants for a field that is a single-line text field today (Edit Preset / Map
       Advanced / Step Editor / General's Disconnect Detection) - a small list widget with
       add/remove, one row per variant? Should "Add as expected" dedupe against variants already
       present, and should it stay disabled while the OCR test hasn't produced any recognized text
       yet?
       The ENGINE half of this is now nearly free, which was not true when this task was written.
       Every detection site already funnels through OcrMatchCandidates(text, candidates, ...) in
       macro/ocr_matching.ahk, which scores a LIST of candidates and returns the best. Variants are
       just more entries in that list, so the remaining work is config storage plus the GUI, not
       matching. The out-of-scope note this task used to carry (replacing the fixed 6-character
       fuzzy window with a real similarity score) is done, see done/rapidfuzz-fuzzy-matching.md.
