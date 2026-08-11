Title: Ok aber true oder false soll schon funktionieren also wenn eine map erkannt wird oder nicht
Completed: 2026-08-11
Commit:    -

Result: The True/False branching itself was intact and is unchanged: DetectMapProfileInRegion
        returns a profile name or "", RunSteps derives mapDetected from that, and LogicJumpTarget
        picks OnTrueScreen/OnFalseScreen. Verified end to end, including that the step editor
        persists both branches for a Detect Map step. What was wrong was pacing, introduced by
        test-ocr-map-candidates: the new "no map profile has an expected text" early return made a
        failed detection instant, and "(Repeat)" has no delay of its own, so that case span the CPU
        and flooded the log instead of retrying once every few seconds. Both impossible-to-succeed
        paths now wait out the detection's own timeout (MapDetectionCannotRun), and the "(Repeat)"
        branch gained a backstop that refuses to loop faster than once a second when a whole step
        attempt took under 50ms, which also covers the same pre-existing hazard in
        IsTextDetectedInRegion (unset region or empty expected text).
