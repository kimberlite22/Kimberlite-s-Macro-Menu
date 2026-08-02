Title: Benchmark alternate OCR engines against the current WinRT engine
Completed: 2026-08-02
Commit:    403e1f3

Result: Built the live shadow-mode harness the user asked for instead of a written comparison:
        ocr_server.exe now optionally spools the exact frames the production WinRT engine
        recognized (at most one every two seconds, at most fifty pending, encoded and written on
        a worker thread), and a separate ocr_benchmark.exe re-runs pytesseract, EasyOCR and
        PaddleOCR on those same pixels into ocr_benchmark_log.jsonl. Two processes because those
        engines pull in gigabyte-scale deep learning frameworks and ocr_server.exe is embedded
        inside the AHK engine exe inside gui.exe. Shadow mode is OFF in this repo and only
        .github/workflows/release-experimental.yml turns it on, publishing the experimental build
        as a PRE-RELEASE so the self-updater's releases/latest/download/ path keeps serving the
        real production release. Nothing is decided yet: the macro still acts only on the WinRT
        result, and the engine choice waits on the user's own roughly ten hour real-world test of
        pre-release tag v0.4.16-dev1 and the ocr_benchmark_log.jsonl it produces.
