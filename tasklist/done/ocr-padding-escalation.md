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
Prio:  1

Goal:  A detection that comes back empty or unmatched retries the same region through an escalating
       ladder of framed variants instead of giving up after one scan, and the image handed to OCR
       is otherwise completely unmodified. Windows OCR needs a quiet zone around text; a region
       captured tight against its content is exactly the case that returns nothing today. The
       existing 2x bicubic upscale is deleted, not kept as a fallback: the user reports detection
       worked reliably before it existed and has been unreliable since, so it is the suspect rather
       than a safety net. The Test OCR button reports which rung produced the hit, so the ladder is
       observable instead of a black box.

       Ladder, in order, first hit wins:

           0  raw capture, no modification at all
           1  black frame, +10% per side      2  white frame, +10% per side
           3  black frame, +25% per side      4  white frame, +25% per side
           5  black frame, +50% per side      6  white frame, +50% per side

       Padding is per axis and per side: padX = round(w * pct / 100), padY = round(h * pct / 100),
       so a stage's result is w + 2*padX by h + 2*padY. A stage whose result would exceed 750x750
       is skipped, and the ladder ends there. Decided with the user against the 500x500 first
       proposed: the benchmark log shows the most-scanned region is 395x250 (14308 of 16406
       samples, 87%), for which 500x500 would have killed every stage above +10%. At 750x750 that
       region reaches stage 4 (+25% gives 592x375) and stops before stage 5 (+50% gives 790x500).

Files: ocr/ocr_helper/engine.py     delete maybe_upscale and _maybe_upscale (and their constants);
                                   add pad_image(image, pad_x, pad_y, color); recognize_region
                                   gains pad_x/pad_y/color
       ocr/ocr_helper/protocol.py   ScanRequest gains pad_x, pad_y, color; read_next_request
                                   accepts BOTH the 5-field legacy line and the new 8-field one
       ocr/ocr_helper/cli.py        both handle_scan variants forward the new fields; the shadow
                                   spooler's prepare_image=maybe_upscale hookup goes away with it
       ocr/tests/                   test_engine.py's frozen upscale baseline no longer describes
                                   this engine; keep the old manifest as the historical record and
                                   assert against a new no-upscale one. New padding tests.
       macro/tower_defense_macro_gui.ahk
                                   RunOcrOnRegion / RunOcrOneShot gain padX/padY/color; new
                                   OcrEscalationStages() table and RunOcrEscalating(x,y,w,h,
                                   matcher, &stageUsed); IsTextDetectedInRegion and
                                   DetectMapProfileInRegion drive the ladder
       macro/local_bridge.ahk       TEST_OCR returns the stage label alongside the text
       gui/                         the Test OCR result text shows the stage
       CLAUDE.md                    the OCR protocol section documents the new request shape

Steps: 1. Python mechanism only, no policy: add padding to the engine, delete the upscale, widen
          the protocol line, keep the 5-field form working so a mismatched pair of binaries during
          an upgrade degrades to stage 0 instead of breaking.
       2. AHK owns all policy: the stage table, the 750x750 rule, the match test, stop-on-first-hit.
          Deliberately NOT in Python: the expected text lives in AHK (TextContainsPartialMatch),
          and pushing it down would duplicate the matching rule across two languages.
       3. Wire the ladder into IsTextDetectedInRegion and DetectMapProfileInRegion. The map
          detection polls up to ~16 times in 5s, so run the ladder once per poll, not per attempt.
       4. Surface the stage through TEST_OCR and into the GUI's result message.
       5. Tests: ocr/ padding and protocol round trip; gui/ the stage reaches the message.

Open:  -
