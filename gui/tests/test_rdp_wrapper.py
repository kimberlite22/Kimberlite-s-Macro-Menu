from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path

from app import rdp_wrapper


def test_remote_desktop_check_passes_when_windows_allows_connections(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: 0)

    result = rdp_wrapper.check_remote_desktop()

    assert result.ok is True
    assert result.remediation == ""


def test_remote_desktop_check_is_undetermined_when_its_registry_value_cannot_be_read(
    monkeypatch,
) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: None)

    result = rdp_wrapper.check_remote_desktop()

    assert result.ok is False
    assert result.undetermined is True
    assert "could not be read" in result.detail
    assert "Settings > System > Remote Desktop" in result.remediation


def test_remote_desktop_check_fails_when_windows_denies_connections(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: 1)

    result = rdp_wrapper.check_remote_desktop()

    assert result.ok is False
    assert result.undetermined is False
    assert "disabled" in result.detail


def test_multiple_sessions_check_passes_when_windows_allows_the_same_user_twice(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: 0)

    result = rdp_wrapper.check_multiple_sessions_per_user()

    assert result.ok is True
    assert result.remediation == ""


def test_multiple_sessions_check_is_undetermined_when_its_registry_value_cannot_be_read(
    monkeypatch,
) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: None)

    result = rdp_wrapper.check_multiple_sessions_per_user()

    assert result.ok is False
    assert result.undetermined is True
    assert "could not be read" in result.detail
    assert "same Windows account" in result.remediation


def test_multiple_sessions_check_explains_why_an_existing_session_is_not_enough(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "terminal_server_flag", lambda _: 1)

    result = rdp_wrapper.check_multiple_sessions_per_user()

    assert result.ok is False
    assert result.undetermined is False
    assert "existing session" in result.detail
    assert "same Windows account" in result.remediation


def test_rdp_wrapper_installed_check_passes_for_an_installed_rdpwrap_dll(
    monkeypatch, tmp_path: Path
) -> None:
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
    assert result.undetermined is False
    assert "github.com/stascorp/rdpwrap" in result.remediation


def test_rdp_wrapper_installed_check_fails_when_the_dll_path_cannot_be_read(monkeypatch) -> None:
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: None)

    result = rdp_wrapper.check_rdp_wrapper_installed()

    assert result.ok is False
    assert result.undetermined is True
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
    monkeypatch.setattr(rdp_wrapper, "termsrv_string_version", lambda: "10.0.26100.8875")
    monkeypatch.setattr(rdp_wrapper, "rdpwrap_ini_path", lambda _: ini_path)

    result = rdp_wrapper.check_rdp_wrapper_supports_windows_build()

    assert result.ok is True
    assert result.remediation == ""
    assert "10.0.26100.8875" in result.detail


def test_build_support_check_is_a_genuine_negative_when_only_string_version_has_a_section(
    monkeypatch, tmp_path: Path
) -> None:
    service_dll = tmp_path / "rdpwrap.dll"
    service_dll.touch()
    ini_path = tmp_path / "rdpwrap.ini"
    ini_path.write_text("[10.0.26100.8875]\n", encoding="utf-8")
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: str(service_dll))
    monkeypatch.setattr(rdp_wrapper, "termsrv_binary_version", lambda: "10.0.26100.4484")
    monkeypatch.setattr(rdp_wrapper, "termsrv_string_version", lambda: "10.0.26100.8875")
    monkeypatch.setattr(rdp_wrapper, "rdpwrap_ini_path", lambda _: ini_path)

    result = rdp_wrapper.check_rdp_wrapper_supports_windows_build()

    assert result.ok is False
    assert result.undetermined is False
    assert "10.0.26100.4484" in result.detail
    assert "10.0.26100.8875" in result.detail
    assert "10.0.26100.4484" in result.remediation


def test_build_support_check_is_undetermined_when_binary_version_cannot_be_read_even_if_string_version_can(
    monkeypatch, tmp_path: Path
) -> None:
    service_dll = tmp_path / "rdpwrap.dll"
    service_dll.touch()
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: str(service_dll))
    monkeypatch.setattr(rdp_wrapper, "termsrv_binary_version", lambda: None)
    monkeypatch.setattr(rdp_wrapper, "termsrv_string_version", lambda: "10.0.26100.8875")

    result = rdp_wrapper.check_rdp_wrapper_supports_windows_build()

    assert result.ok is False
    assert result.undetermined is True
    assert "could not be read" in result.detail
    assert "10.0.26100.8875" in result.detail


def test_build_support_check_is_a_genuine_negative_when_binary_version_has_no_section(
    monkeypatch, tmp_path: Path
) -> None:
    service_dll = tmp_path / "rdpwrap.dll"
    service_dll.touch()
    ini_path = tmp_path / "rdpwrap.ini"
    ini_path.touch()
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: str(service_dll))
    monkeypatch.setattr(rdp_wrapper, "termsrv_binary_version", lambda: "10.0.26100.4484")
    monkeypatch.setattr(rdp_wrapper, "termsrv_string_version", lambda: "10.0.26100.8875")
    monkeypatch.setattr(rdp_wrapper, "rdpwrap_ini_path", lambda _: ini_path)
    monkeypatch.setattr(rdp_wrapper, "ini_supports_version", lambda *_: False)

    result = rdp_wrapper.check_rdp_wrapper_supports_windows_build()

    assert result.ok is False
    assert result.undetermined is False
    assert "10.0.26100.4484" in result.remediation
    assert "10.0.26100.8875" in result.detail


def test_build_support_check_fails_clearly_when_rdp_wrapper_is_not_active(monkeypatch, tmp_path: Path) -> None:
    service_dll = tmp_path / "termsrv.dll"
    service_dll.touch()
    monkeypatch.setattr(rdp_wrapper, "service_dll_path", lambda: str(service_dll))

    result = rdp_wrapper.check_rdp_wrapper_supports_windows_build()

    assert result.ok is False
    assert result.undetermined is False
    assert "cannot be checked" in result.detail


def test_ini_support_requires_an_exact_section_header(tmp_path: Path) -> None:
    ini_path = tmp_path / "rdpwrap.ini"
    ini_path.write_text("[10.0.26100.44840]\n", encoding="utf-8")

    assert rdp_wrapper.ini_supports_version(ini_path, "10.0.26100.4484") is False
    assert rdp_wrapper.ini_supports_version(ini_path, "10.0.26100.448") is False

    ini_path.write_text(" [10.0.26100.4484] \n", encoding="utf-8")

    assert rdp_wrapper.ini_supports_version(ini_path, "10.0.26100.4484") is True


class _StringVersionResource:
    def __init__(self, values: tuple[str, ...]) -> None:
        self.translations = (wintypes.WORD * (len(values) * 2))(
            *(part for index in range(len(values)) for part in (0x0409, 0x04B0 + index))
        )
        self.values = tuple(ctypes.create_unicode_buffer(value) for value in values)

    def VerQueryValueW(self, _buffer, sub_block, value_pointer, length_pointer) -> bool:
        value = ctypes.cast(value_pointer, ctypes.POINTER(wintypes.LPVOID)).contents
        length = ctypes.cast(length_pointer, ctypes.POINTER(ctypes.c_uint)).contents
        if sub_block == "\\VarFileInfo\\Translation":
            value.value = ctypes.cast(self.translations, wintypes.LPVOID).value
            length.value = ctypes.sizeof(self.translations)
            return True
        for index, string_value in enumerate(self.values):
            expected = f"\\StringFileInfo\\0409{0x04B0 + index:04X}\\FileVersion"
            if sub_block == expected:
                value.value = ctypes.cast(string_value, wintypes.LPVOID).value
                length.value = len(string_value.value) + 1
                return True
        return False


def test_termsrv_string_version_normalises_a_leading_dotted_number(monkeypatch) -> None:
    resource = _StringVersionResource(("10.0.26100.8875 (WinBuild.160101.0800)",))
    monkeypatch.setattr(rdp_wrapper, "_termsrv_version_resource", lambda: (resource, object()))

    assert rdp_wrapper.termsrv_string_version() == "10.0.26100.8875"


def test_termsrv_string_version_accepts_commas_and_falls_back_to_another_translation(
    monkeypatch,
) -> None:
    resource = _StringVersionResource(("not a version", "10, 0, 26100, 8875"))
    monkeypatch.setattr(rdp_wrapper, "_termsrv_version_resource", lambda: (resource, object()))

    assert rdp_wrapper.termsrv_string_version() == "10.0.26100.8875"


def test_termsrv_string_version_returns_none_for_a_junk_value(monkeypatch) -> None:
    resource = _StringVersionResource(("not a version",))
    monkeypatch.setattr(rdp_wrapper, "_termsrv_version_resource", lambda: (resource, object()))

    assert rdp_wrapper.termsrv_string_version() is None


def test_setup_status_distinguishes_undetermined_from_a_genuine_negative() -> None:
    first = rdp_wrapper.CheckResult("First", False, "First failed.", "Do first.")
    second = rdp_wrapper.CheckResult("Second", True, "Second passed.", "")
    third = rdp_wrapper.CheckResult(
        "Third", False, "Third could not be read.", "Do third.", True
    )

    status = rdp_wrapper.SetupStatus((first, second, third))

    assert status.ok is False
    assert status.can_start is False
    assert status.undetermined is True
    assert status.remediations == ("Do first.", "Do third.")
    all_clear = rdp_wrapper.SetupStatus((second,))
    warnings_only = rdp_wrapper.SetupStatus((second, third))
    assert all_clear.ok is True
    assert all_clear.can_start is True
    assert all_clear.undetermined is False
    assert warnings_only.ok is False
    assert warnings_only.can_start is True
    assert warnings_only.undetermined is True


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
