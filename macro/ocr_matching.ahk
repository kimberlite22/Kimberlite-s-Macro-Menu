; ============================================================
; OCR TEXT MATCHING
; ============================================================
; The rule that decides whether an OCR read means the configured "expected text". It lives in its
; own file for two reasons. It used to exist as five near-identical copies (the plain detection
; matcher, the disconnect watchdog's, the local bridge's Test OCR matcher, and the two-pass
; resolvers for map profiles and advanced outcomes), and any change to the rule had to be made in
; every copy, so the copy that got missed became a silent behavior split between the Test OCR
; button and the real detection. And a rule that decides whether the macro can see the screen
; deserves tests, which is only possible if it can be loaded WITHOUT the application: #Include
; splices this file into tower_defense_macro_gui.ahk textually (one shared global namespace,
; exactly like local_bridge.ahk), while macro/tests/test_ocr_matching.ahk includes just this file
; plus its own stubs for Cfg()/SafeNum() and runs a table of cases against it.
;
; Everything here is pure string work. No OCR round trips, no config writes, no GUI. Keep it that
; way: the escalation ladder, the region geometry and the logging belong to the caller.

; Returns true if any run of `minLen` consecutive characters from `needle` appears
; somewhere in `haystack` (case-insensitive). This is more forgiving than a full
; substring match, since OCR output can include extra lines (e.g. a difficulty
; label or category above/below the actual map name) or misread a stray character
; such as an apostrophe.
TextContainsPartialMatch(haystack, needle, minLen := 4) {
    haystackLower := StrLower(haystack)
    needleLower := StrLower(Trim(needle))
    len := StrLen(needleLower)
    if (len = 0)
        return false
    if (len <= minLen)
        return InStr(haystackLower, needleLower) > 0
    Loop len - minLen + 1 {
        chunk := SubStr(needleLower, A_Index, minLen)
        if InStr(haystackLower, chunk)
            return true
    }
    return false
}

/*
WinRT OCR preserves line breaks from the scanned region. Collapsing whitespace lets an expected
multi-word string such as "Round End" match a read of "Round`nEnd", and keeps every scored
comparison on the same lowercase representation.
*/
NormalizeOcrText(text) {
    return StrLower(Trim(RegExReplace(String(text), "\s+", " ")))
}

/*
Windows OCR routinely confuses these glyph pairs. Keeping the replacements in one function-local
static array makes the tolerance easy to adjust without scattering substitutions through matching code.
*/
FoldOcrConfusables(normText) {
    static pairs := [["o", "0"], ["l", "1"], ["i", "1"], ["s", "5"], ["b", "8"]]
    folded := normText
    for pair in pairs
        folded := StrReplace(folded, pair[1], pair[2])
    return folded
}

/*
Partial OCR matches need a character-order-aware score, but the full dynamic-programming matrix is
unnecessary here. Retaining only the previous and current rows keeps the LCS calculation practical
inside the OCR poll loop.
*/
OcrLcsLength(a, b) {
    lenA := StrLen(a)
    lenB := StrLen(b)
    previous := []
    Loop lenB + 1
        previous.Push(0)

    Loop lenA {
        charA := SubStr(a, A_Index, 1)
        current := [0]
        Loop lenB {
            j := A_Index
            if (charA = SubStr(b, j, 1))
                current.Push(previous[j] + 1)
            else
                current.Push(Max(previous[j + 1], current[j]))
        }
        previous := current
    }
    return previous[lenB + 1]
}

/*
OCR may include surrounding labels, so compare the expected string with each same-length section of
the recognized text. A rolling character-count intersection is an upper bound for LCS because every
common subsequence is also a common sub-multiset. When that bound cannot beat the current best score,
the expensive LCS calculation for that window is safely skipped.
*/
OcrPartialRatio(hay, needle) {
    if (hay = "" || needle = "")
        return 0

    n := StrLen(hay)
    if (n > 4000) {
        hay := SubStr(hay, 1, 4000)
        n := 4000
    }
    m := StrLen(needle)
    if (n <= m)
        return 2 * OcrLcsLength(hay, needle) / (n + m)

    needleCounts := Map()
    Loop m {
        char := SubStr(needle, A_Index, 1)
        needleCounts[char] := needleCounts.Get(char, 0) + 1
    }

    windowCounts := Map()
    intersection := 0
    Loop m {
        char := SubStr(hay, A_Index, 1)
        count := windowCounts.Get(char, 0)
        if (count < needleCounts.Get(char, 0))
            intersection += 1
        windowCounts[char] := count + 1
    }

    bestScore := 0
    windowTotal := n - m + 1
    Loop windowTotal {
        offset := A_Index
        if (intersection / m > bestScore) {
            window := SubStr(hay, offset, m)
            score := 2 * OcrLcsLength(window, needle) / (2 * m)
            if (score > bestScore)
                bestScore := score
        }

        if (offset = windowTotal)
            continue

        removed := SubStr(hay, offset, 1)
        count := windowCounts.Get(removed, 0)
        if (count <= needleCounts.Get(removed, 0))
            intersection -= 1
        windowCounts[removed] := count - 1

        added := SubStr(hay, offset + m, 1)
        count := windowCounts.Get(added, 0)
        if (count < needleCounts.Get(added, 0))
            intersection += 1
        windowCounts[added] := count + 1
    }
    return bestScore
}

/*
True containment is the strongest OCR evidence. Confusable folding recovers common glyph mistakes,
but receives a deliberately lower score so an unmodified exact candidate always ranks first.
*/
OcrSimilarity(hayNorm, needleNorm) {
    if (needleNorm = "")
        return 0
    if InStr(hayNorm, needleNorm)
        return 1.0
    ; Below this length, containment is the only thing that may count. Folding is a tolerance
    ; bought against the length of the expected text, and on one or two characters there is no
    ; length to buy it with: a one-character expected "O" would otherwise score 0.98 against a read
    ; of "0", which is a match neither the old exact test nor its 6-character fallback would ever
    ; have produced. Such a text can still match through the legacy pass in OcrMatchCandidates,
    ; exactly as it did before, so this only removes a NEW false positive.
    if (StrLen(needleNorm) < OcrMinFuzzyLength())
        return 0
    foldedHay := FoldOcrConfusables(hayNorm)
    foldedNeedle := FoldOcrConfusables(needleNorm)
    if InStr(foldedHay, foldedNeedle)
        return 0.98
    return OcrPartialRatio(foldedHay, foldedNeedle)
}

OcrMinFuzzyLength() => 3

/*
The score threshold is user-configurable, but a malformed or extreme setting should not make OCR
matching unexpectedly permissive or impossible. Invalid values therefore return the stable default.
*/
OcrMatchThreshold() {
    threshold := SafeNum(Cfg("General", "OcrMatchThreshold", "0.75"), 0.75)
    if (threshold < 0.30 || threshold > 1.0)
        return 0.75
    return threshold
}

/*
Score all configured candidates so the most specific strong OCR match wins deterministically. The
legacy exact-then-partial passes remain a non-regression floor for existing detections, and their
"legacy" reason can be logged until evidence shows that compatibility fallback never fires.
*/
; `threshold` below 0 means "use the configured one". Passing 0 explicitly turns this into a pure
; ranking query that always returns the best-scoring candidate, which is how the miss path gets the
; numbers for its log line without a second copy of the ranking logic.
OcrMatchCandidates(text, candidates, expectedKey := "Name", threshold := -1) {
    if (threshold < 0)
        threshold := OcrMatchThreshold()
    textNorm := NormalizeOcrText(text)
    scoresByIndex := Map()
    best := ""
    runnerUp := ""

    Loop candidates.Length {
        i := A_Index
        expected := candidates[i].%expectedKey%
        if (expected = "")
            continue
        expectedNorm := NormalizeOcrText(expected)
        score := OcrSimilarity(textNorm, expectedNorm)
        scoresByIndex[i] := score
        record := {Index: i, Candidate: candidates[i], Expected: expected, ExpectedLen: StrLen(expectedNorm), Score: score}
        if (best = "" || score > best.Score
            || (score = best.Score && (record.ExpectedLen > best.ExpectedLen
                || (record.ExpectedLen = best.ExpectedLen && i < best.Index)))) {
            runnerUp := best
            best := record
        } else if (runnerUp = "" || score > runnerUp.Score
            || (score = runnerUp.Score && (record.ExpectedLen > runnerUp.ExpectedLen
                || (record.ExpectedLen = runnerUp.ExpectedLen && i < runnerUp.Index)))) {
            runnerUp := record
        }
    }

    if (best != "" && best.Score >= threshold) {
        return {Index: best.Index, Candidate: best.Candidate, Expected: best.Expected, Score: best.Score,
            Reason: "score", RunnerUpExpected: runnerUp != "" ? runnerUp.Expected : "",
            RunnerUpScore: runnerUp != "" ? runnerUp.Score : 0}
    }

    ; The empty-expected guard is not optional: InStr throws a ValueError on an empty Needle in
    ; AHK v2 (verified, it does not simply return 0), so an unconfigured candidate reaching this
    ; loop would take down the calling thread instead of just failing to match. The call sites this
    ; replaces guarded it the same way, each in its own copy of the rule.
    Loop candidates.Length {
        i := A_Index
        expected := candidates[i].%expectedKey%
        if (expected = "")
            continue
        if InStr(text, expected) {
            return {Index: i, Candidate: candidates[i], Expected: expected, Score: scoresByIndex.Get(i, 0),
                Reason: "legacy", RunnerUpExpected: "", RunnerUpScore: 0}
        }
    }
    Loop candidates.Length {
        i := A_Index
        expected := candidates[i].%expectedKey%
        if (expected = "")
            continue
        if TextContainsPartialMatch(text, expected, 6) {
            return {Index: i, Candidate: candidates[i], Expected: expected, Score: scoresByIndex.Get(i, 0),
                Reason: "legacy", RunnerUpExpected: "", RunnerUpScore: 0}
        }
    }
    return ""
}

; The score, the rung and the runner-up in one parenthesised note, appended to whatever the caller
; already logs. This exists so every "why did it (not) detect" question is answerable from the log
; alone: before scoring, the log could only say "detected" or "not detected", which told the user
; nothing about whether the region, the expected text or the threshold was the problem.
OcrMatchNote(info, stageLabel := "") {
    if !IsObject(info)
        return ""
    note := "score " Format("{:.2f}", info.Score)
    if (info.Reason = "legacy")
        note .= ", legacy fallback"          ; deletable once logs show this never fires
    if (stageLabel != "" && stageLabel != "raw")
        note .= ", " stageLabel
    ; Only worth showing when it was nearly a coin flip; a distant runner-up is just noise.
    if (info.RunnerUpExpected != "" && info.Score - info.RunnerUpScore < 0.10)
        note .= ", close runner-up '" info.RunnerUpExpected "' " Format("{:.2f}", info.RunnerUpScore)
    return " (" note ")"
}

; The best-ranked candidate for `text` REGARDLESS of the threshold, which is what a failed match
; needs in order to report how close it came. A threshold of 0 turns OcrMatchCandidates into a pure
; ranking query, so the diagnostic path shares the ranking rule instead of copying it.
OcrBestCandidate(text, candidates, expectedKey := "Name") {
    if (text = "")
        return ""
    return OcrMatchCandidates(text, candidates, expectedKey, 0)
}

OcrBestCandidateScore(text, candidates, expectedKey := "Name") {
    diag := OcrBestCandidate(text, candidates, expectedKey)
    return IsObject(diag) ? diag.Score : 0
}

; The same for a failed match: what the best candidate actually scored, against the threshold it
; needed to clear.
OcrMissNote(text, candidates, expectedKey := "Name") {
    diag := OcrBestCandidate(text, candidates, expectedKey)
    if !IsObject(diag)
        return ""
    return " (best '" diag.Expected "' " Format("{:.2f}", diag.Score)
        . " < " Format("{:.2f}", OcrMatchThreshold()) ")"
}

; The candidate list IsTextDetectedInRegion builds internally, so a caller can ask OcrMissNote for
; the same numbers after a failed detection without rebuilding it by hand.
OcrSingleCandidate(expected) {
    return [{Name: expected}]
}

; --- Sample image naming -----------------------------------------------------------------------
; A saved sample image records the raw pixels behind one detection region, so a future change to
; the matching rule can be judged against real screens instead of invented strings.
;
; A sample is keyed by the EXPECTED TEXT, not by the detection that captured it. Two detections
; configured with the same expected text are looking for the same thing on screen, so the second
; one should find the first one's sample already there rather than needing its own. That is why the
; name is derived here, from the text alone, and not from a step name, a preset or a region.
;
; The slug is the normalized text reduced to filename-safe characters, plus a short hash of the
; FULL normalized text. The readable part is what makes the folder browsable in Explorer; the hash
; is what stops two different expected texts that reduce to the same characters ("Round End" and
; "Round-End" both reduce to "round-end") from silently sharing one image.
OcrSampleSlug(expected) {
    norm := NormalizeOcrText(expected)
    if (norm = "")
        return ""
    safe := Trim(RegExReplace(norm, "[^a-z0-9]+", "-"), "-")
    if (StrLen(safe) > 48)
        safe := Trim(SubStr(safe, 1, 48), "-")
    if (safe = "")
        safe := "text"      ; an expected text made entirely of punctuation still needs a name
    return safe "-" OcrTextHash(norm)
}

; FNV-1a, masked to 32 bits at every step. Not a security hash, just a short stable fingerprint:
; the only requirement is that the same expected text always produces the same eight characters,
; on every machine and across restarts, so a sample saved once keeps being found.
OcrTextHash(s) {
    hash := 2166136261
    Loop Parse s {
        hash := (hash ^ Ord(A_LoopField)) & 0xFFFFFFFF
        hash := (hash * 16777619) & 0xFFFFFFFF
    }
    return Format("{:08x}", hash)
}

