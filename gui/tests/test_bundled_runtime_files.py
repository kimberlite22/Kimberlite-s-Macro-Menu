from __future__ import annotations

from pathlib import Path


def test_only_this_active_existing_ocr_helper_can_survive_a_fileinstall_failure() -> None:
    """Keep OCR recovery limited to the expected live helper holding its regular executable."""
    repo_root = Path(__file__).resolve().parents[2]
    source = (repo_root / "macro" / "tower_defense_macro_gui.ahk").read_text(encoding="utf-8")
    function = source[source.index("EnsureBundledRuntimeFiles() {") : source.index("\nHttpGetText(")]

    assert 'FileInstall "ocr_server.exe", ocrServerPath, 1' in function
    assert 'existingOcrHelper := FileExist(ocrServerPath) && !DirExist(ocrServerPath)' in function
    assert 'activeOcrHelper := ProcessExist("ocr_server.exe")' in function
    assert 'if (activeOcrHelper && existingOcrHelper)' in function
    assert 'Using the existing copy.' in function
    assert function.index('if (activeOcrHelper && existingOcrHelper)') < function.index("} else {")
    assert function.index("ExitApp") > function.index("} else {")
