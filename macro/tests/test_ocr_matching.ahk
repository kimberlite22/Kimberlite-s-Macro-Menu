#Requires AutoHotkey v2.0
#SingleInstance Off
#Warn All, Off

; Table-driven tests for the OCR text matching rule (macro/ocr_matching.ahk).
;
; Why this exists: the rule decides whether the macro can see the screen at all, and until it was
; split out of tower_defense_macro_gui.ahk there was no way to exercise it without launching the
; whole application. Every case below is a (recognized text, expected text(s)) pair with the
; outcome it must produce, so a change to the threshold, the folding table or the ranking can be
; judged against concrete behavior instead of by reading.
;
; Run it:
;     "C:\Program Files\AutoHotkey\v2\AutoHotkey64.exe" macro\tests\test_ocr_matching.ahk [outfile]
; Exit code is the number of failures, so a caller can gate on it. With an outfile argument the
; per-case report is written there as well (AutoHotkey64.exe is a GUI subsystem binary, so its
; stdout is only usable when the caller redirects it).
;
; NOT wired into .github/workflows/ci.yml: that runner has no AutoHotkey and installing one is its
; own decision. Run it locally after touching ocr_matching.ahk.

#Include ..\ocr_matching.ahk

; --- Stubs for the two helpers ocr_matching.ahk borrows from the main script -------------------
; TestThreshold stands in for [General] OcrMatchThreshold so a case can pin the threshold it needs.

global TestThreshold := 0.75

Cfg(section, key, def := "") {
    global TestThreshold
    if (key = "OcrMatchThreshold")
        return TestThreshold
    return def
}

; Copied verbatim from tower_defense_macro_gui.ahk so the stub cannot drift into being more
; forgiving than the real thing.
SafeNum(val, def := 0.0) {
    s := Trim(String(val))
    if (s = "")
        return def
    s := StrReplace(s, ",", ".")
    if !IsNumber(s)
        return def
    return Number(s)
}

; --- Tiny assert harness -----------------------------------------------------------------------

global Failures := 0
global Report := ""

Check(label, got, want) {
    global Failures, Report
    ok := (String(got) = String(want))
    if !ok
        Failures += 1
    Report .= (ok ? "PASS  " : "FAIL  ") label
        . (ok ? "" : "   (got " (got = "" ? "<empty>" : got) ", want " (want = "" ? "<empty>" : want) ")")
        . "`n"
}

Candidates(names*) {
    list := []
    for n in names
        list.Push({Name: n})
    return list
}

; Name of the matched candidate, or "-" when nothing matched. Collapses the match record down to
; the one thing most cases care about.
MatchName(text, cands) {
    info := OcrMatchCandidates(text, cands)
    return IsObject(info) ? info.Candidate.Name : "-"
}

MatchReason(text, cands) {
    info := OcrMatchCandidates(text, cands)
    return IsObject(info) ? info.Reason : "-"
}

; --- Normalization -----------------------------------------------------------------------------

Check("normalize collapses runs of whitespace", NormalizeOcrText("  Round`n`tEnd  "), "round end")
Check("normalize lowercases", NormalizeOcrText("VICTORY"), "victory")
Check("normalize of empty text", NormalizeOcrText(""), "")

; --- Similarity --------------------------------------------------------------------------------

Check("identical strings score 1", OcrSimilarity("victory", "victory"), 1.0)
Check("containment scores 1", OcrSimilarity("hard kings tomb wave 5", "kings tomb"), 1.0)
Check("empty needle scores 0", OcrSimilarity("victory", ""), 0)
Check("confusable-only match scores 0.98", OcrSimilarity("vict0ry", "victory"), 0.98)
Check("unrelated short text scores low", OcrSimilarity("menu", "victory") < 0.5, 1)

; The partial-ratio path is the one piece here that is real algorithm rather than string plumbing,
; so it gets exact hand-checked values. A range assertion would have been satisfied by an
; implementation that always returned 0.
Check("LCS of the textbook example", OcrLcsLength("abcde", "ace"), 3)
Check("LCS with an empty string", OcrLcsLength("", "abc"), 0)
Check("LCS is order-sensitive, not a bag of characters", OcrLcsLength("edcba", "ace"), 1)
; One substituted character out of five: LCS "abde" = 4, so 2*4/(5+5).
Check("partial ratio, one substitution", OcrPartialRatio("abzde", "abcde"), 0.8)
; The needle sits inside a longer haystack, so the sliding window has to FIND it to score 1.
Check("partial ratio finds the right window", OcrPartialRatio("xxabcdexx", "abcde"), 1.0)
Check("partial ratio of nothing in common", OcrPartialRatio("xxxxx", "abcde"), 0.0)

; --- The single-expected-text case (Round End / Ingame / Custom detection, disconnect watchdog) --

Check("exact word in a longer read", MatchName("VICTORY!", Candidates("VICTORY")), "VICTORY")
Check("case is ignored", MatchName("victory!", Candidates("VICTORY")), "VICTORY")

; The regression this whole change was worth making for: WinRT keeps the region's line breaks, so a
; two-word expected text used to fail against a read that wrapped between the words.
Check("expected text split across OCR lines", MatchName("Round`nEnd", Candidates("Round End")), "Round End")
Check("expected text split across lines, legacy rule alone would miss it",
    TextContainsPartialMatch("Round`nEnd", "Round End", 6), 0)

; A single misread glyph inside a short word left no intact 6-character window, so the old rule
; failed on exactly the reads the escalation ladder was added to rescue.
Check("confusable glyph misread still matches", MatchName("VICT0RY", Candidates("VICTORY")), "VICTORY")
Check("confusable glyph misread, legacy rule alone would miss it",
    TextContainsPartialMatch("VICT0RY", "VICTORY", 6), 0)

; "m" misread as "rn", the classic OCR substitution. The legacy rule happens to survive this one on
; the intact "kings " window; the score path resolves it outright instead of by luck.
Check("a misread inside the name still matches", MatchName("Kings Tornb", Candidates("Kings Tomb")), "Kings Tomb")
Check("and it is a score match, not the legacy fallback",
    MatchReason("Kings Tornb", Candidates("Kings Tomb")), "score")

; A dropped space, which is what a tight crop against the glyphs tends to produce. One error in the
; middle of a ten-character expected text breaks EVERY six-character window at once, so the old
; rule had nothing left to match on; the partial-ratio score carries it.
Check("a dropped space still matches", MatchName("Kingstomb", Candidates("Kings Tomb")), "Kings Tomb")
Check("carried by the score, not by the legacy fallback",
    MatchReason("Kingstomb", Candidates("Kings Tomb")), "score")
Check("the legacy rule alone would miss it",
    TextContainsPartialMatch("Kingstomb", "Kings Tomb", 6), 0)

Check("unrelated text does not match", MatchName("MENU", Candidates("VICTORY")), "-")
Check("empty read does not match", MatchName("", Candidates("VICTORY")), "-")

; Folding buys tolerance against the length of the expected text, and one character has none to
; buy it with. "O" against a read of "0" must NOT match: neither the old exact test nor its
; 6-character fallback produced that, so accepting it would be a brand new false positive.
Check("a one-character expected text does not match its confusable",
    MatchName("0", Candidates("O")), "-")
Check("a two-character expected text does not match its confusable",
    MatchName("10", Candidates("IO")), "-")
Check("but a short expected text still matches itself exactly",
    MatchName("Menu 0", Candidates("0")), "0")

; InStr throws a ValueError on an empty Needle in AHK v2, so an unconfigured expected text reaching
; the legacy pass used to be a crash, not a miss.
Check("empty expected text does not match and does not throw", MatchName("VICTORY", Candidates("")), "-")
Check("no candidates at all", MatchName("VICTORY", []), "-")

; --- Ranking across several candidates (map profiles, advanced outcomes) ------------------------
; "Kings Tomb" and "Rose Kingdom" both contain "king". The old code depended on running an exact
; pass over ALL candidates before any fuzzy pass; scoring makes the outcome independent of order.

Check("contained name beats a fuzzy overlap",
    MatchName("Rose Kingdom", Candidates("Kings Tomb", "Rose Kingdom")), "Rose Kingdom")
Check("same, candidates in the other order",
    MatchName("Rose Kingdom", Candidates("Rose Kingdom", "Kings Tomb")), "Rose Kingdom")
Check("the other map, first order",
    MatchName("Kings Tomb", Candidates("Kings Tomb", "Rose Kingdom")), "Kings Tomb")
Check("the other map, second order",
    MatchName("Kings Tomb", Candidates("Rose Kingdom", "Kings Tomb")), "Kings Tomb")

; Both are contained, so both score 1.00: the more specific (longer) one is the right answer.
Check("longer expected text wins a tie",
    MatchName("Rose Kingdom", Candidates("King", "Rose Kingdom")), "Rose Kingdom")
Check("longer expected text wins a tie, other order",
    MatchName("Rose Kingdom", Candidates("Rose Kingdom", "King")), "Rose Kingdom")

Check("surrounding label lines do not prevent a match",
    MatchName("HARD`nKings Tomb`nWave 5", Candidates("Kings Tomb", "Rose Kingdom")), "Kings Tomb")

; --- The legacy non-regression floor ------------------------------------------------------------
; A needle long enough that one intact 6-character window is a small fraction of it scores well
; below the threshold, but the old rule accepted it. It must keep matching, and must be reported as
; "legacy" so the log shows the compatibility pass is still load-bearing.

Check("legacy rule still rescues a low-scoring match",
    MatchName("frozen", Candidates("zzzzzzfrozenzzzzzz")), "zzzzzzfrozenzzzzzz")
Check("and is reported as the legacy fallback",
    MatchReason("frozen", Candidates("zzzzzzfrozenzzzzzz")), "legacy")
Check("a true score match is not reported as legacy",
    MatchReason("VICTORY!", Candidates("VICTORY")), "score")

; --- The threshold setting ----------------------------------------------------------------------

TestThreshold := 0.99
Check("a threshold above the folding score rejects a confusable-only match",
    MatchName("VICT0RY", Candidates("VICTORY")), "-")
Check("a true containment still matches at any threshold",
    MatchName("VICTORY!", Candidates("VICTORY")), "VICTORY")

TestThreshold := "not a number"
Check("an unparseable threshold falls back to the default", OcrMatchThreshold(), 0.75)
TestThreshold := 5
Check("an out-of-range threshold falls back to the default", OcrMatchThreshold(), 0.75)
TestThreshold := 0.5
Check("an in-range threshold is honored", OcrMatchThreshold(), 0.5)
TestThreshold := 0.75

; --- Report --------------------------------------------------------------------------------------

total := StrSplit(Trim(Report, "`n"), "`n").Length
summary := Report "`n" (Failures = 0 ? "OK" : "FAILED") ": " (total - Failures) "/" total " passed`n"
if (A_Args.Length >= 1)
    FileAppend(summary, A_Args[1], "UTF-8-RAW")
try FileAppend(summary, "*")
ExitApp(Failures)
