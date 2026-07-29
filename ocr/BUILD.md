# Building ocr_server.exe

This folder is a Python replacement for `macro/ocr_server.ps1` and `macro/ocr_region.ps1`
(see `CLAUDE.md`, "Python migration initiative" -> "Phase 1 implementation plan"). One
PyInstaller onefile executable covers both of the old scripts' modes (server mode and
one-shot mode), selected by which CLI flags are passed.

## Dev setup

```
cd ocr
python -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
```

## Running the tests

```
pytest
```

`tests/test_protocol.py` drives the file protocol in isolation (temp dirs only, no OCR
engine involved). `tests/test_engine.py` compares the Python engine's recognized text
against today's PowerShell/WinRT output (`macro/ocr_region.ps1`) for the same saved
fixture images in `tests/fixtures/` -- this is the actual "no accuracy regression" proof
for this migration. It is skipped automatically on a machine that can't run
`powershell.exe` or doesn't have Windows OCR language packs installed.

## Building the executable

```
cd ocr
pyinstaller --onefile --name ocr_server --distpath dist --workpath build --specpath build ocr_helper/cli.py
```

This produces `ocr/dist/ocr_server.exe`. Copy it to `macro/ocr_server.exe` before
compiling the AHK app:

```
copy dist\ocr_server.exe ..\macro\ocr_server.exe
```

`macro/ocr_server.exe` is a build artifact (gitignored, like `remote/agent/*.exe`), not
committed source. A **source/dev run** of `tower_defense_macro_gui.ahk` (not compiled
with Ahk2Exe) reads `ocr_server.exe` straight from `macro/` (`RuntimeDir` is
`A_ScriptDir` when `!A_IsCompiled`, so `EnsureBundledRuntimeFiles()`'s `FileInstall`
calls do not run) -- so it must be built and copied there once before you can use OCR
detection features from a source checkout, exactly like `remote/agent/` needs its own
`go build -o animeexpedition-agent.exe .` for a dev run of the remote bridge (see
`remote/README.md`).

The **compiled release EXE** embeds `macro/ocr_server.exe` at Ahk2Exe compile time via
`FileInstall` and extracts it next to itself on first run, so an end user never needs
Python or PyInstaller installed. `.github/workflows/release.yml` runs this build step
automatically before the Ahk2Exe compile step.

## Verifying the standalone build works

Run the built exe directly (no dev Python on PATH) to confirm PyInstaller bundled
everything it needs:

```
mkdir smoke-test-dir
dist\ocr_server.exe --dir smoke-test-dir --x 0 --y 0 --width 200 --height 80
type smoke-test-dir\ocr_result.txt
```

This should exit quickly and print whatever text (possibly empty) is visible in the
top-left 200x80 pixels of the primary screen.

## What is deliberately NOT in this change (Phase 1b)

`rapidfuzz`-based fuzzy matching (replacing `TextContainsPartialMatch`'s substring-window
heuristic in `tower_defense_macro_gui.ahk`), OpenCV template/color matching as a new
detection mode, benchmarking alternate OCR engines, and CI-automating the PyInstaller
build are all explicitly deferred to a separate follow-up. This change is a 1:1 protocol-
compatible replacement only.
