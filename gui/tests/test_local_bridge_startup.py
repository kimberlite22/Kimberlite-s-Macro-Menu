from __future__ import annotations

from pathlib import Path


def test_engine_readiness_follows_initial_local_command_drain() -> None:
    """Keep the GUI readiness marker behind recovery of an offline command slot.

    AutoHotkey is intentionally not launched in the Python test suite. This source-level contract
    covers the cross-process startup ordering that the local file protocol depends on.
    """
    repo_root = Path(__file__).resolve().parents[2]
    macro_source = (repo_root / "macro" / "tower_defense_macro_gui.ahk").read_text(encoding="utf-8")
    bridge_source = (repo_root / "macro" / "local_bridge.ahk").read_text(encoding="utf-8")

    assert 'RemoteBridgeAtomicWrite(DataDir "\\engine_ready.txt", "")' not in macro_source

    drain = bridge_source.index("LocalBridgeProcessCommand()\nLocalBridgeWriteStatus()")
    timer = bridge_source.index("SetTimer(LocalBridgeTick, 125)", drain)
    ready = bridge_source.index('RemoteBridgeAtomicWrite(DataDir "\\engine_ready.txt", "")', timer)
    assert drain < timer < ready
