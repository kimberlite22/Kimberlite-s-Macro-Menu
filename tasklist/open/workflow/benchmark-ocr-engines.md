Title: Benchmark alternate OCR engines against the current WinRT engine
Prio:  2

Goal:  A written comparison (accuracy and speed against ocr/tests/fixtures/baseline_manifest.json's
       known cases, plus startup/dependency cost) of the current winsdk/WinRT engine
       (ocr/ocr_helper/engine.py) versus alternatives such as pytesseract, EasyOCR, or PaddleOCR,
       to decide whether switching is worth the accuracy/dependency tradeoff. Research only; no
       engine switch happens as part of this task unless the comparison clearly justifies one.
Open:  Which alternative engines are actually worth benchmarking (winsdk was originally chosen over
       pytesseract/EasyOCR/PaddleOCR specifically to avoid bundling model files and keep startup
       fast, see the "OCR helper" section of CLAUDE.md - does that reasoning still hold, or is it
       worth re-checking now that the migration is done)? Where do results get written down: a new
       ocr/BENCHMARKS.md, or inline in this task file once done? May inform the threshold work in
       [[rapidfuzz-fuzzy-matching]] if a candidate engine returns confidence scores the current one
       doesn't.
