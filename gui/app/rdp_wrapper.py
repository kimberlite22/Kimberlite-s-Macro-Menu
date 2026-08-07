"""Report whether RDP Wrapper can create the background session this app needs.

Windows client editions normally allow one interactive session for a user.  The background-session
workflow needs a second session for that same account, so this module separates the four things a
user must have configured: Remote Desktop enabled, Windows allowed to create another session for
the user, RDP Wrapper loaded by the service, and an rdpwrap.ini section for a readable Windows
build version.  It only reads Windows state.  The GUI can turn these results into instructions
without needing to know about ctypes, the registry, or RDP Wrapper's file layout.
"""

from __future__ import annotations

import ctypes
import os
import re
import sys
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_REG_SZ = 1
_REG_EXPAND_SZ = 2
_REG_DWORD = 4
_TERMINAL_SERVER_KEY = r"SYSTEM\CurrentControlSet\Control\Terminal Server"
_TERMSERVICE_PARAMETERS_KEY = r"SYSTEM\CurrentControlSet\Services\TermService\Parameters"
_VS_FFI_SIGNATURE = 0xFEEF04BD


@dataclass(frozen=True)
class CheckResult:
    """Represent one setup verdict without treating an unreadable setting as a failed setting.

    ok means confirmed good. A false result without undetermined is a genuine negative.
    """

    name: str
    ok: bool
    detail: str
    remediation: str
    undetermined: bool = False


@dataclass(frozen=True)
class SetupStatus:
    checks: tuple[CheckResult, ...]

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    @property
    def can_start(self) -> bool:
        return all(check.ok or check.undetermined for check in self.checks)

    @property
    def undetermined(self) -> bool:
        return any(check.undetermined for check in self.checks)

    @property
    def remediations(self) -> tuple[str, ...]:
        return tuple(check.remediation for check in self.checks if not check.ok and check.remediation)


class _VS_FIXEDFILEINFO(ctypes.Structure):
    _fields_ = [
        ("dwSignature", wintypes.DWORD),
        ("dwStrucVersion", wintypes.DWORD),
        ("dwFileVersionMS", wintypes.DWORD),
        ("dwFileVersionLS", wintypes.DWORD),
        ("dwProductVersionMS", wintypes.DWORD),
        ("dwProductVersionLS", wintypes.DWORD),
        ("dwFileFlagsMask", wintypes.DWORD),
        ("dwFileFlags", wintypes.DWORD),
        ("dwFileOS", wintypes.DWORD),
        ("dwFileType", wintypes.DWORD),
        ("dwFileSubtype", wintypes.DWORD),
        ("dwFileDateMS", wintypes.DWORD),
        ("dwFileDateLS", wintypes.DWORD),
    ]


def _versiondll() -> Any:
    """Return version.dll with the three file-version functions typed, or None when unavailable."""
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.windll.version
        library.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
        library.GetFileVersionInfoSizeW.restype = wintypes.DWORD
        library.GetFileVersionInfoW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
        ]
        library.GetFileVersionInfoW.restype = wintypes.BOOL
        library.VerQueryValueW.argtypes = [
            wintypes.LPCVOID,
            wintypes.LPCWSTR,
            ctypes.POINTER(wintypes.LPVOID),
            ctypes.POINTER(ctypes.c_uint),
        ]
        library.VerQueryValueW.restype = wintypes.BOOL
        return library
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def _termsrv_version_resource() -> tuple[Any, object] | None:
    """Return version.dll and termsrv.dll's version resource, or None when either cannot be read."""
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        return None
    library = _versiondll()
    if library is None:
        return None
    path = str(Path(system_root) / "System32" / "termsrv.dll")
    handle = wintypes.DWORD()
    try:
        size = library.GetFileVersionInfoSizeW(path, ctypes.byref(handle))
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not library.GetFileVersionInfoW(path, 0, size, buffer):
            return None
        return library, buffer
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def termsrv_binary_version() -> str | None:
    """Return termsrv.dll's fixed binary version, or None when Windows cannot provide it."""
    version_resource = _termsrv_version_resource()
    if version_resource is None:
        return None
    library, buffer = version_resource
    try:
        value = wintypes.LPVOID()
        length = ctypes.c_uint()
        if not library.VerQueryValueW(buffer, "\\", ctypes.byref(value), ctypes.byref(length)):
            return None
        if length.value < ctypes.sizeof(_VS_FIXEDFILEINFO):
            return None
        fixed_info = ctypes.cast(value, ctypes.POINTER(_VS_FIXEDFILEINFO)).contents
    except (AttributeError, ImportError, OSError, ValueError):
        return None
    if fixed_info.dwSignature != _VS_FFI_SIGNATURE:
        return None
    return ".".join(
        str(part)
        for part in (
            fixed_info.dwFileVersionMS >> 16,
            fixed_info.dwFileVersionMS & 0xFFFF,
            fixed_info.dwFileVersionLS >> 16,
            fixed_info.dwFileVersionLS & 0xFFFF,
        )
    )


def _normalise_termsrv_string_version(value: str) -> str | None:
    """Return FileVersion's leading four-part version so metadata suffixes do not affect matching."""
    match = re.match(
        r"\s*(\d+)\s*[.,]\s*(\d+)\s*[.,]\s*(\d+)\s*[.,]\s*(\d+)(?=\s|$)",
        value.rstrip("\0"),
    )
    if match is None:
        return None
    return ".".join(str(int(part)) for part in match.groups())


def termsrv_string_version() -> str | None:
    """Return FileVersion through its declared translations, or None when Windows has no usable value."""
    version_resource = _termsrv_version_resource()
    if version_resource is None:
        return None
    library, buffer = version_resource
    try:
        translations_value = wintypes.LPVOID()
        translations_length = ctypes.c_uint()
        if not library.VerQueryValueW(
            buffer,
            "\\VarFileInfo\\Translation",
            ctypes.byref(translations_value),
            ctypes.byref(translations_length),
        ):
            return None
        if not translations_value.value or translations_length.value < 4:
            return None
        if translations_length.value % 4:
            return None
        translation_count = translations_length.value // 4
        translations = ctypes.cast(
            translations_value,
            ctypes.POINTER(wintypes.WORD * (translation_count * 2)),
        ).contents
        for index in range(0, translation_count * 2, 2):
            language, codepage = translations[index], translations[index + 1]
            value = wintypes.LPVOID()
            length = ctypes.c_uint()
            sub_block = f"\\StringFileInfo\\{language:04X}{codepage:04X}\\FileVersion"
            if not library.VerQueryValueW(
                buffer, sub_block, ctypes.byref(value), ctypes.byref(length)
            ):
                continue
            if not value.value or not length.value:
                continue
            version = _normalise_termsrv_string_version(ctypes.wstring_at(value, length.value))
            if version is not None:
                return version
    except (AttributeError, ImportError, OSError, ValueError):
        return None
    return None


def _registry_value(key_path: str, value_name: str) -> tuple[object, int] | None:
    """Read one value from the 64-bit HKLM registry view, or None when it is unavailable."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            key_path,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            return winreg.QueryValueEx(key, value_name)
    except (AttributeError, ImportError, OSError, ValueError):
        return None


def service_dll_path() -> str | None:
    """Return TermService's expanded ServiceDll path, or None when it cannot be read."""
    result = _registry_value(_TERMSERVICE_PARAMETERS_KEY, "ServiceDll")
    if result is None:
        return None
    value, value_type = result
    # Windows stores this as REG_EXPAND_SZ, but a plain REG_SZ is accepted too: an installer that
    # wrote the path without the expandable type would otherwise be reported as "RDP Wrapper not
    # installed", sending the user to reinstall something that is already there. expandvars on a
    # string with nothing to expand is a no-op, so accepting both costs nothing.
    if value_type not in (_REG_SZ, _REG_EXPAND_SZ) or not isinstance(value, str):
        return None
    return os.path.expandvars(value)


def terminal_server_flag(name: str) -> int | None:
    """Return a Terminal Server DWORD flag, or None when it cannot be read."""
    result = _registry_value(_TERMINAL_SERVER_KEY, name)
    if result is None:
        return None
    value, value_type = result
    if value_type != _REG_DWORD or not isinstance(value, int):
        return None
    return value


def rdpwrap_ini_path(service_dll: str | None) -> Path | None:
    """Return the rdpwrap.ini next to a service DLL, but only when it exists."""
    if service_dll is None:
        return None
    try:
        path = Path(service_dll).with_name("rdpwrap.ini")
        return path if path.is_file() else None
    except (OSError, ValueError):
        return None


def ini_supports_version(ini_path: Path | str, version: str) -> bool:
    """Whether rdpwrap.ini has an exact section for the supplied termsrv.dll version."""
    try:
        with Path(ini_path).open(encoding="utf-8", errors="replace") as ini_file:
            return any(line.strip() == f"[{version}]" for line in ini_file)
    except (OSError, ValueError):
        return False


def _rdp_wrapper_is_active(service_dll: str | None) -> bool:
    if service_dll is None:
        return False
    try:
        path = Path(service_dll)
        return path.is_file() and path.name.casefold() == "rdpwrap.dll"
    except (OSError, ValueError):
        return False


def _install_remediation() -> str:
    return (
        "Install RDP Wrapper from github.com/stascorp/rdpwrap with administrator rights, then reboot; "
        "this app deliberately does not bundle it because several antivirus products flag it as riskware."
    )


def check_remote_desktop() -> CheckResult:
    """Report whether Windows is accepting incoming Remote Desktop connections."""
    flag = terminal_server_flag("fDenyTSConnections")
    if flag == 0:
        return CheckResult("Remote Desktop", True, "Remote Desktop is enabled.", "")
    remediation = "Open Settings > System > Remote Desktop and turn on Remote Desktop."
    if flag is None:
        detail = "The Remote Desktop setting could not be read."
        remediation += " Its current setting could not be confirmed."
    else:
        detail = "Remote Desktop is disabled."
    return CheckResult("Remote Desktop", False, detail, remediation, undetermined=flag is None)


def check_multiple_sessions_per_user() -> CheckResult:
    """Report whether Windows can create a second session for the same account."""
    flag = terminal_server_flag("fSingleSessionPerUser")
    if flag == 0:
        return CheckResult(
            "Multiple sessions per user",
            True,
            "Windows can create a new session for the same account.",
            "",
        )
    if flag is None:
        detail = "The same-user session setting could not be read."
    else:
        detail = "Windows is configured to hand the same account back its existing session instead of a new one."
    return CheckResult(
        "Multiple sessions per user",
        False,
        detail,
        "Set fSingleSessionPerUser to 0 so a correctly installed RDP Wrapper creates a new session "
        "instead of handing back the existing one; both sessions here run as the same Windows account.",
        undetermined=flag is None,
    )


def check_rdp_wrapper_installed() -> CheckResult:
    """Report whether TermService is configured to load an installed rdpwrap.dll."""
    service_dll = service_dll_path()
    if _rdp_wrapper_is_active(service_dll):
        return CheckResult(
            "RDP Wrapper installed",
            True,
            "Remote Desktop is configured to load the installed rdpwrap.dll.",
            "",
        )
    if service_dll is None:
        detail = "The Remote Desktop service DLL path could not be read."
    else:
        detail = "Remote Desktop is not configured to load an installed rdpwrap.dll."
    return CheckResult(
        "RDP Wrapper installed",
        False,
        detail,
        _install_remediation(),
        undetermined=service_dll is None,
    )


def check_rdp_wrapper_supports_windows_build() -> CheckResult:
    """Report whether rdpwrap.ini has a section for the installed termsrv.dll build."""
    service_dll = service_dll_path()
    if not _rdp_wrapper_is_active(service_dll):
        return CheckResult(
            "RDP Wrapper supports this Windows build",
            False,
            "RDP Wrapper is not installed or active, so its Windows-build support cannot be checked.",
            "Install and activate RDP Wrapper before checking its Windows-build support.",
        )
    binary_version = termsrv_binary_version()
    string_version = termsrv_string_version()
    if binary_version is None:
        detail = (
            "The fixed binary version of Windows termsrv.dll could not be read, so RDP Wrapper "
            "support could not be checked."
        )
        if string_version is not None:
            detail += (
                f" Windows reports FileVersion {string_version}, but RDP Wrapper keys rdpwrap.ini "
                "lookups on the unreadable binary version."
            )
        return CheckResult(
            "RDP Wrapper supports this Windows build",
            False,
            detail,
            "Check that Windows termsrv.dll is present, then update rdpwrap.ini for this Windows build.",
            undetermined=True,
        )
    if string_version is None:
        version_context = " The FileVersion metadata could not be read."
    elif string_version != binary_version:
        version_context = (
            f" Windows reports FileVersion {string_version}, but RDP Wrapper keys its rdpwrap.ini "
            f"lookup on binary version {binary_version}."
        )
    else:
        version_context = ""
    ini_path = rdpwrap_ini_path(service_dll)
    if ini_path is None:
        return CheckResult(
            "RDP Wrapper supports this Windows build",
            False,
            f"No rdpwrap.ini was found next to rdpwrap.dll.{version_context}",
            "Update rdpwrap.ini with autoupdate.bat from the RDP Wrapper project or a community-maintained rdpwrap.ini.",
        )
    if ini_supports_version(ini_path, binary_version):
        return CheckResult(
            "RDP Wrapper supports this Windows build",
            True,
            f"rdpwrap.ini contains a section for binary Windows build {binary_version}.{version_context}",
            "",
        )
    return CheckResult(
        "RDP Wrapper supports this Windows build",
        False,
        f"rdpwrap.ini has no section for binary Windows build {binary_version}.{version_context}",
        f"Update rdpwrap.ini with autoupdate.bat from the RDP Wrapper project or a community-maintained "
        f"rdpwrap.ini that supports binary Windows build {binary_version}.",
    )


def check_setup() -> SetupStatus:
    """Run the four setup checks in the order the GUI presents them."""
    return SetupStatus(
        (
            check_remote_desktop(),
            check_multiple_sessions_per_user(),
            check_rdp_wrapper_installed(),
            check_rdp_wrapper_supports_windows_build(),
        )
    )
