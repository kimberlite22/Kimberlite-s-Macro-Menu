Title:     do you know why vscode run build task doesnt work
Completed: 2026-08-07
Commit:    eace9ae

Result: The VS Code build task died in PyInstaller's EXE assemble step with "PermissionError:
        [WinError 5] Access is denied" on gui\dist\gui.exe, because a gui.exe left running by the
        PREVIOUS run of tools/build-local-exe.ps1 still held the image lock. Root cause: the
        script's smoke test starts gui.exe with Start-Process -PassThru and stops it with
        Stop-Process -Id, but PyInstaller --onefile runs a bootloader process that spawns a separate
        child process on the same exe image, so Start-Process reports only the bootloader PID and
        Stop-Process orphaned the child (confirmed on the machine: taskkill named the survivor a
        child process of the already dead bootloader). Same two-PID behavior CLAUDE.md already
        documents for ocr_server.exe, where StopOcrServer() uses taskkill /F /T for this reason.
        Fixed in two layers: Stop-ProcessTree kills the whole tree via taskkill /F /T and polls
        until the PID is gone (now used by the smoke test's finally block), and
        Stop-ProcessesUsingFile stops any process whose image path equals a build output before that
        output is rewritten (macro\ocr_server.exe, dist\AEMEngine.exe, gui\dist\gui.exe,
        dist\Kimberlites-Macro-Menu.exe), so an interrupted run or a manually launched build cannot
        block the next build either. Both helpers were verified against real processes, including a
        reproduction of the same access-denied error that then cleared, 10 of 10 checks passing. The
        identical Stop-Process -Id pattern in the three GitHub workflows was left alone on purpose:
        a CI runner is discarded after one build, so an orphan there cannot cause a failure.
