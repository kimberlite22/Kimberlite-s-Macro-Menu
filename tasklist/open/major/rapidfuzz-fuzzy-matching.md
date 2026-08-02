Title: Replace TextContainsPartialMatch's fixed 6-character substring-window fuzzy check with
       rapidfuzz-based edit-distance matching
Prio:  9

Goal:  OCR expected-text comparisons (`TextContainsPartialMatch` in tower_defense_macro_gui.ahk,
       currently a fixed-length substring-window heuristic) use a real edit-distance/similarity
       score instead, so match quality no longer depends on a hardcoded window size.
Open:  rapidfuzz is a Python library; TextContainsPartialMatch is AHK code. Does the fuzzy check
       move into ocr/ (a new request type in the ocr_req.txt/ocr_resp.txt protocol) so AHK stays a
       thin client, or does AHK grow its own edit-distance implementation? What similarity threshold
       replaces the current 6-character window without regressing existing detection accuracy -
       needs the same kind of frozen-baseline verification ocr/tests/test_engine.py already does for
       the WinRT engine? [[ocr-expected-variants]] deliberately left this out of scope; that task's
       own notes are the origin of this one.
