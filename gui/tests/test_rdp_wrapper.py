from __future__ import annotations

from pathlib import Path

from app import rdp_wrapper


def test_remote_desktop_check_passes_when_windows_allows_connections(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: 0)

    result = rdp_wrapper.check_remote_desktop()

    assert result.ok is True
    assert result.remediation == ""


def test_remote_desktop_check_fails_closed_when_its_registry_value_cannot_be_read(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: None)

    result = rdp_wrapper.check_remote_desktop()

    assert result.ok is False
    assert "could not be read" in result.detail
    assert "Settings > System > Remote Desktop" in result.remediation


def test_remote_desktop_check_fails_when_windows_denies_connections(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: 1)

    result = rdp_wrapper.check_remote_desktop()

    assert result.ok is False
    assert "disabled" in result.detail


def test_multiple_sessions_check_passes_when_windows_allows_the_same_user_twice(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: 0)

    result = rdp_wrapper.check_multiple_sessions_per_user()

    assert result.ok is True
    assert result.remediation == ""


def test_multiple_sessions_check_fails_closed_when_its_registry_value_cannot_be_read(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: None)

    result = rdp_wrapper.check_multiple_sessions_per_user()

    assert result.ok is False
    assert "could not be read" in result.detail
    assert "same Windows account" in result.remediation


def test_multiple_sessions_check_explains_why_an_existing_session_is_not_enough(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: 1)

    result = rdp_wrapper.check_multiple_sessions_per_user()

    assert result.ok is False
    assert "existing session" in result.detail
    assert "same Windows account" in result.remediation


def test_rdp_wrapper_installed_check_passes_for_an_installed_rdpwrap_dll(monkeypatch, tmp_path: Path) -> None:
    service_dll = tmp_path / "rdpwrap.dll"
    service_dll.touch()
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: str(service_dll))

    result = rdp_wrapper.check_rdp_wrapper_installed()

    assert result.ok is True
    assert result.remediation == ""


def test_rdp_wrapper_installed_check_rejects_the_stock_termsrv_dll(monkeypatch, tmp_path: Path) -> None:
    service_dll = tmp_path / "termsrv.dll"
    service_dll.touch()
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: str(service_dll))

    result = rdp_wrapper.check_rdp_wrapper_installed()

    assert result.ok is False
    assert "github.com/stascorp/rdpwrap" in result.remediation


def test_rdp_wrapper_installed_check_fails_when_the_dll_path_cannot_be_read(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: None)

    result = rdp_wrapper.check_rdp_wrapper_installed()

    assert result.ok is False
    assert "could not be read" in result.detail


def test_build_support_check_passes_when_the_ini_has_the_fixed_binary_version(
    monkeypatch, tmp_path: Path
) -> None:
    service_dll = tmp_path / "rdpwrap.dll"
    service_dll.touch()
    ini_path = tmp_path / "rdpwrap.ini"
    ini_path.write_text("[10.0.26100.4484]\n", encoding="utf-8")
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: str(service_dll))
    monkeypatch.setattr(rdp_wrapper, "termsrv_binary_version", lambda: "10.0.26100.4484")
    monkeypatch.setattr(rdp_wrapper, "rdpwrap_ini_path", lambda _: ini_path)

    result = rdp_wrapper.check_rdp_wrapper_supports_windows_build()

    assert result.ok is True
    assert result.remediation == ""


def test_build_support_check_fails_when_the_ini_lacks_the_detected_version(monkeypatch, tmp_path: Path) -> None:
    service_dll = tmp_path / "rdpwrap.dll"
    service_dll.touch()
    ini_path = tmp_path / "rdpwrap.ini"
    ini_path.touch()
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: str(service_dll))
    monkeypatch.setattr(rdp_wrapper, "termsrv_binary_version", lambda: "10.0.26100.4484")
    monkeypatch.setattr(rdp_wrapper, "rdpwrap_ini_path", lambda _: ini_path)
    monkeypatch.setattr(rdp_wrapper, "ini_supports_version", lambda *_: False)

    result = rdp_wrapper.check_rdp_wrapper_supports_windows_build()

    assert result.ok is False
    assert "10.0.26100.4484" in result.remediation


def test_build_support_check_fails_clearly_when_rdp_wrapper_is_not_active(monkeypatch, tmp_path: Path) -> None:
    service_dll = tmp_path / "termsrv.dll"
    service_dll.touch()
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: str(service_dll))

    result = rdp_wrapper.check_rdp_wrapper_supports_windows_build()

    assert result.ok is False
    assert "cannot be checked" in result.detail


def test_ini_support_requires_an_exact_section_header(tmp_path: Path) -> None:
    ini_path = tmp_path / "rdpwrap.ini"
    ini_path.write_text("[10.0.26100.44840]\n", encoding="utf-8")

    assert rdp_wrapper.ini_supports_version(ini_path, "10.0.26100.4484") is False
    assert rdp_wrapper.ini_supports_version(ini_path, "10.0.26100.448") is False

    ini_path.write_text(" [10.0.26100.4484] \n", encoding="utf-8")

    assert rdp_wrapper.ini_supports_version(ini_path, "10.0.26100.4484") is True


def test_setup_status_aggregates_only_failing_remediations_in_order() -> None:
    first = rdp_wrapper.CheckResult("First", False, "First failed.", "Do first.")
    second = rdp_wrapper.CheckResult("Second", True, "Second passed.", "")
    third = rdp_wrapper.CheckResult("Third", False, "Third failed.", "Do third.")

    status = rdp_wrapper.SetupStatus((first, second, third))

    assert status.ok is False
    assert status.remediations == ("Do first.", "Do third.")
    assert rdp_wrapper.SetupStatus((second,)).ok is True


def test_check_setup_returns_the_documented_four_checks_in_order(monkeypatch) -> None:
    monkeypatch.setattr(
        rdp_wrapper,
        "check_remote_desktop",
        lambda: rdp_wrapper.CheckResult("Remote Desktop", True, "Enabled.", ""),
    )
    monkeypatch.setattr(
        rdp_wrapper,
        "check_multiple_sessions_per_user",
        lambda: rdp_wrapper.CheckResult("Multiple sessions per user", True, "Enabled.", ""),
    )
    monkeypatch.setattr(
        rdp_wrapper,
        "check_rdp_wrapper_installed",
        lambda: rdp_wrapper.CheckResult("RDP Wrapper installed", True, "Installed.", ""),
    )
    monkeypatch.setattr(
        rdp_wrapper,
        "check_rdp_wrapper_supports_windows_build",
        lambda: rdp_wrapper.CheckResult("RDP Wrapper supports this Windows build", True, "Supported.", ""),
    )

    status = rdp_wrapper.check_setup()

    assert [check.name for check in status.checks] == [
        "Remote Desktop",
        "Multiple sessions per user",
        "RDP Wrapper installed",
        "RDP Wrapper supports this Windows build",
    ]
