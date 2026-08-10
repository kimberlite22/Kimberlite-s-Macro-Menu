Title: Replace TextContainsPartialMatch's fixed 6-character substring-window fuzzy check with
       rapidfuzz-based edit-distance matching
Completed: 2026-08-10
Commit:    -

Result: Done, but on the AHK side and without rapidfuzz. The task's own open question (move the
        fuzzy check into ocr/ as a new protocol request type, or grow an edit-distance
        implementation in AHK) was settled for AHK: a new protocol round trip per comparison would
        have split one matching rule across two languages, which the OCR section of CLAUDE.md
        explicitly forbids, and would have added a stale-ocr_server.exe version problem. Matching
        now lives in macro/ocr_matching.ahk: normalization, confusable-glyph folding, an LCS
        partial-similarity score with a rolling multiset bound, and candidate ranking, behind one
        entry point (OcrMatchCandidates) that replaced five copies of the old rule. The threshold
        that replaced the hardcoded window is [General] OcrMatchThreshold (default 0.75). The
        frozen-baseline verification the task asked for is macro/tests/test_ocr_matching.ahk (47
        cases), plus the old rule kept as a fallback that can only ADD a match, so no detection
        that worked before can stop working.
