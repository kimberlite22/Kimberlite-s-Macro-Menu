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
detection mode, and CI-automating the PyInstaller build are all explicitly deferred to a
separate follow-up. This change is a 1:1 protocol-compatible replacement only.

## Shadow OCR benchmark build

Shadow mode compares real gameplay samples with alternate OCR engines without changing the
macro response. `ocr_server.exe` continues to run only the small production WinRT engine.
When shadow mode is enabled, it writes bounded, rate-limited samples to
`<DataDir>\ocr_benchmark_spool\`. The separate `ocr_benchmark.exe` watches that directory,
runs pytesseract, EasyOCR, and PaddleOCR, then appends comparison records to
`<DataDir>\ocr_benchmark_log.jsonl`.

This is deliberately two processes. EasyOCR and PaddleOCR bring roughly gigabyte-scale
deep-learning frameworks. Including them in the onefile `ocr_server.exe`, which is embedded
inside the AHK engine and then the GUI installer, would create a multi-gigabyte nested release
asset and make the helper self-extract for about a minute on every launch.

Build the benchmark bundle in its own environment. Do not install the `benchmark` dependency
group for a normal production OCR build.

```
cd ocr
python -m venv .venv-benchmark
.venv-benchmark\Scripts\activate
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -e .[benchmark,dev]
pyinstaller --onedir --name ocr_benchmark ^
  --collect-all easyocr --collect-all paddleocr --collect-all pytesseract ^
  --distpath dist --workpath build --specpath build ocr_helper/benchmark_cli.py
```

Install CPU PyTorch explicitly, and before the extra: EasyOCR depends on `torch`, and letting
pip resolve it on its own can pull a CUDA build that is several gigabytes larger for no benefit
on a machine that will run this on the CPU anyway. The `--collect-all` flags are not optional
either. All three engines load model definitions and config files at runtime that PyInstaller's
static import analysis cannot see, so leaving them out produces an executable that starts fine
and then fails on its first sample.

Use `--onedir`, not `--onefile`: a gigabyte-scale onefile bundle would have to self-extract on
every startup. Ship the resulting `dist\ocr_benchmark\` directory as a separate zipped release
asset, never inside `ocr_server.exe` or the macro installer.

Tesseract itself is a native executable, not a pip dependency. To bundle it next to the
benchmark executable, add its directory to the PyInstaller command:

```
pyinstaller --onedir --name ocr_benchmark --add-data "C:\path\to\tesseract;tesseract" ocr_helper/benchmark_cli.py
```

The wrapper first honors `AEM_TESSERACT_EXE`; otherwise it uses the bundled
`tesseract\tesseract.exe` and its `tesseract\tessdata` directory, then falls back to PATH.
EasyOCR and PaddleOCR may download model weights on first use.

For a local experiment, enable sampling with `ocr_server.exe --shadow-ocr` or
`AEM_OCR_SHADOW=1`. The experimental release workflow
`.github/workflows/release-experimental.yml` enables it by changing the build-time default in
`ocr_helper/build_config.py` before PyInstaller runs, which is the only way to reach the shipped
binary: the AHK macro launches `ocr_server.exe --dir "<DataDir>"` and passes nothing else.

Run the benchmark with `ocr_benchmark.exe`. With no `--dir` it watches the installed app's own
DataDir (`%LOCALAPPDATA%\Kimberlite's Anime Expedition Macro`), so it can simply be
double-clicked; pass `--dir` for a source checkout or a test root, and `--once` to drain what is
already spooled and exit. Stop it cleanly with Ctrl+C or by creating
`<DataDir>\ocr_benchmark_stop.txt`.
