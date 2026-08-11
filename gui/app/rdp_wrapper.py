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
import time
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

# The RemoteApp published-application allow list. termsrv validates an RDP client's requested
# initial program ("alternate shell") against it before anything is launched, so on a machine where
# the list is enforced but holds no applications - Windows' own default - the lookup misses and the
# session comes up with no shell at all. See initial_program_allow_list_disabled below.
_TSAPPALLOWLIST_KEY = (
    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Terminal Server\TSAppAllowList"
)
_ALLOW_LIST_DISABLED_VALUE = "fDisabledAllowList"
# The Remote Desktop CLIENT's own per-user settings, read by mstsc when it connects.
_TERMINAL_SERVER_CLIENT_KEY = r"Software\Microsoft\Terminal Server Client"
_SUPPRESS_WHEN_MINIMIZED_VALUE = "RemoteDesktop_SuppressWhenMinimized"
# The documented "keep the session rendering" setting. Not a boolean: the value is absent by
# default, and 2 is the specific number the client checks for, so anything else means "suppress".
_SUPPRESS_WHEN_MINIMIZED_OFF = 2
# ShellExecuteW's "the user declined the elevation prompt" result.
_SE_ERR_ACCESSDENIED = 5
# Anything above 32 means ShellExecuteW managed to start the program.
_SHELL_EXECUTE_SUCCESS_THRESHOLD = 32


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


# ---------------------------------------------------------------------------------------------
# RemoteApp allow list: whether an RDP session may be given an initial program at all
#
# Deliberately NOT one of the four checks above. Those gate Start itself, and a background session
# runs perfectly well without this: it simply comes up with a normal Windows desktop. This only
# decides WHICH route the "boot straight into the macro" option can take, so folding it into
# check_setup would disable Start entirely over an option that is not required.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ElevatedChangeResult:
    ok: bool
    message: str


def initial_program_allow_list_disabled() -> bool | None:
    """Whether RemoteApp's published-application allow list is switched off.

    This single DWORD decides whether an RDP client's requested initial program can start at all.
    termsrv validates that program against the allow list first (rdpcorets!VerifyAppAllowed, which
    returns early when IsAllowListDisabled() is true and otherwise looks the program up in
    TSAppAllowList\\Applications). With the list enforced but empty, which is how Windows ships, the
    lookup misses and the initial program is never launched - and because the directive was consumed
    rather than ignored, no shell runs at all, not even Explorer.

    Verified empirically on the reporting machine, judged only by a marker file the target program
    wrote itself: with the value at 0 the program did not run, at 1 it did, and back at 0 it did not
    again.

    Returns None when the setting cannot be read. Callers must treat that as "not available" rather
    than guessing, because guessing "available" wrongly produces a background session with no shell.
    """
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            _TSAPPALLOWLIST_KEY,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            try:
                value, value_type = winreg.QueryValueEx(key, _ALLOW_LIST_DISABLED_VALUE)
            except FileNotFoundError:
                # The key exists and carries no override, which is Windows' own default and means
                # the allow list IS enforced. A confirmed answer, not an unreadable one.
                return False
    except (AttributeError, ImportError, OSError, ValueError):
        return None
    if value_type != _REG_DWORD or not isinstance(value, int):
        return None
    return value != 0


def _system_directory() -> Path | None:
    """Return Windows' own system directory, asked of Windows rather than of the environment.

    Deliberately NOT os.environ["SystemRoot"]. Any process can be started with a forged environment
    block, and the one caller of this hands the resulting path to ShellExecuteW with "runas": a
    redirected path there would mean elevating an attacker's executable, which is a far worse
    outcome than the read-only version query elsewhere in this module could ever produce.
    """
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.windll.kernel32
        library.GetSystemDirectoryW.argtypes = [wintypes.LPWSTR, wintypes.UINT]
        library.GetSystemDirectoryW.restype = wintypes.UINT
        buffer = ctypes.create_unicode_buffer(260)
        length = library.GetSystemDirectoryW(buffer, len(buffer))
        if not length or length >= len(buffer):
            return None
    except (AttributeError, ImportError, OSError, ValueError):
        return None
    return Path(buffer.value)


def _reg_exe_path() -> str | None:
    system_directory = _system_directory()
    if system_directory is None:
        return None
    path = system_directory / "reg.exe"
    return str(path) if path.is_file() else None


def _shell_execute_runas(file: str, parameters: str) -> int:
    """Run one program elevated, returning ShellExecuteW's own result code.

    "runas" is what raises the UAC prompt. ShellExecuteW does not come back until that prompt has
    been answered, so a result here already reflects the user's decision.
    """
    try:
        library = ctypes.windll.shell32
        library.ShellExecuteW.argtypes = [
            wintypes.HWND,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            ctypes.c_int,
        ]
        library.ShellExecuteW.restype = ctypes.c_void_p
        # SW_HIDE: reg.exe has nothing to show, and a console window flashing up during an
        # elevation the user just approved reads as something having gone wrong.
        result = library.ShellExecuteW(None, "runas", file, parameters, None, 0)
    except (AttributeError, ImportError, OSError, ValueError):
        return 0
    return int(result or 0)


def set_initial_program_allow_list_disabled(
    disabled: bool,
    *,
    execute: Any = None,
    read: Any = None,
    sleep: Any = None,
    attempts: int = 20,
) -> ElevatedChangeResult:
    """Switch the RemoteApp allow list off (or back on) behind one elevation prompt.

    Machine-wide and administrator-only, so it is never silent: the Background Session tab calls
    this only from Start, and only when the machine does not already match the no-desktop checkbox
    the user ticked themselves. One UAC prompt, a way back through the same checkbox, and the user
    never has to hand-craft a registry change.

    Two properties make delegating this to reg.exe safe. Every argument is a compile-time constant
    except the 0/1 this function derives from a bool, so nothing a user can type reaches the command
    line and there is no injection surface. And reg.exe is a signed Windows component, so no script
    file has to be dropped on disk for an elevated process to read.

    The outcome is confirmed by READING THE VALUE BACK rather than by trusting a launch result: a
    declined UAC prompt, an administrator policy, or a reg.exe that failed for its own reasons all
    have to end up reported as "not changed".
    """
    if read is None:
        read = initial_program_allow_list_disabled
    if sleep is None:
        sleep = time.sleep
    if read() is disabled:
        return ElevatedChangeResult(True, "That setting was already in place; nothing was changed.")

    if execute is None:
        reg_exe = _reg_exe_path()
        if reg_exe is None:
            return ElevatedChangeResult(
                False, "Windows' own reg.exe could not be located, so the setting was not changed."
            )
        execute = _shell_execute_runas
    else:
        reg_exe = _reg_exe_path() or "reg.exe"

    parameters = (
        f'add "HKLM\\{_TSAPPALLOWLIST_KEY}" /v {_ALLOW_LIST_DISABLED_VALUE} '
        f"/t REG_DWORD /d {1 if disabled else 0} /f /reg:64"
    )
    result = execute(reg_exe, parameters)
    if result == _SE_ERR_ACCESSDENIED:
        return ElevatedChangeResult(
            False, "The administrator prompt was declined, so nothing was changed."
        )
    if result <= _SHELL_EXECUTE_SUCCESS_THRESHOLD:
        return ElevatedChangeResult(
            False, "The elevated helper could not be started, so nothing was changed."
        )
    # ShellExecuteW returns once the elevated process has been STARTED, not once reg.exe has
    # finished writing, so poll for the value the change was made for.
    for attempt in range(max(1, attempts)):
        if read() is disabled:
            break
        if attempt + 1 < max(1, attempts):
            sleep(0.1)
    if read() is not disabled:
        return ElevatedChangeResult(
            False, "The setting did not change. It may be controlled by an administrator policy."
        )
    if disabled:
        return ElevatedChangeResult(
            True,
            "Done. The background session can now boot straight into the macro with no Windows "
            "desktop.",
        )
    return ElevatedChangeResult(
        True,
        "Restored the Windows default. The background session will keep a normal Windows desktop "
        "from now on.",
    )


# ---------------------------------------------------------------------------------------------
# Remote Desktop client: whether a minimized window keeps its session rendering
#
# Windows pauses a Remote Desktop session's rendering while the client window showing it is
# minimized. That is a saving everywhere else and a defect here: the macro's whole perception layer
# is screen based, and ocr_server.exe runs INSIDE the background session, so a paused session hands
# OCR a frozen or black picture for as long as the window stays minimized. One client-side value
# switches the suppression off.
#
# Two differences from the allow list above, and both are why this is written directly rather than
# through an elevated reg.exe: the value is per-user (HKCU), so it needs no administrator rights,
# and it belongs to the CLIENT, so it is read by mstsc when a connection is made. A client that is
# already connected keeps behaving the way it started; the change reaches the next connection.
# ---------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SettingChangeResult:
    ok: bool
    message: str
    # Whether this call actually wrote something. "Already in place" and "written just now" mean
    # opposite things for a Remote Desktop client that is connected RIGHT NOW: the second one is
    # proof that the running client was started before the setting existed, so it cannot be
    # behaving under it and has to reconnect before anything relies on it.
    changed: bool = False


def minimize_suppression_disabled() -> bool | None:
    """Whether a minimized client keeps its session rendering, or None when unreadable.

    Both "the value is not there" and "the key is not there" are confirmed FALSE rather than
    unreadable: Windows ships without either, and that default is exactly the suppressing behavior.
    """
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _TERMINAL_SERVER_CLIENT_KEY, 0, winreg.KEY_READ
        ) as key:
            value, value_type = winreg.QueryValueEx(key, _SUPPRESS_WHEN_MINIMIZED_VALUE)
    except FileNotFoundError:
        return False
    except (AttributeError, ImportError, OSError, ValueError):
        return None
    if value_type != _REG_DWORD or not isinstance(value, int):
        return None
    return value == _SUPPRESS_WHEN_MINIMIZED_OFF


def _write_minimize_suppression_disabled(disabled: bool) -> bool:
    """Write (or remove) the client value, reporting only whether the registry call went through.

    Restoring the default DELETES the value instead of writing a 0. The suppressing behavior is the
    absence of the value, not a second documented number, so removing it is the only change that
    leaves the machine in a state Windows itself would have produced.
    """
    try:
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, _TERMINAL_SERVER_CLIENT_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if disabled:
                winreg.SetValueEx(
                    key,
                    _SUPPRESS_WHEN_MINIMIZED_VALUE,
                    0,
                    winreg.REG_DWORD,
                    _SUPPRESS_WHEN_MINIMIZED_OFF,
                )
                return True
            try:
                winreg.DeleteValue(key, _SUPPRESS_WHEN_MINIMIZED_VALUE)
            except FileNotFoundError:
                # Already absent, which is the state this branch exists to reach.
                pass
            return True
    except (AttributeError, ImportError, OSError, ValueError):
        return False


def set_minimize_suppression_disabled(
    disabled: bool, *, read: Any = None, write: Any = None
) -> SettingChangeResult:
    """Make the client keep (or stop keeping) a minimized session rendered.

    Like its elevated neighbour, the outcome is confirmed by READING THE VALUE BACK rather than by
    trusting the write: a registry policy or a redirected hive has to end up reported as "not
    changed" instead of as a fix the user then relies on.
    """
    if read is None:
        read = minimize_suppression_disabled
    if write is None:
        write = _write_minimize_suppression_disabled
    if read() is disabled:
        return SettingChangeResult(True, "")
    if not write(disabled):
        return SettingChangeResult(
            False, "The Remote Desktop client setting could not be written, so nothing was changed."
        )
    if read() is not disabled:
        return SettingChangeResult(
            False,
            "The Remote Desktop client setting did not change. It may be controlled by an "
            "administrator policy.",
        )
    if disabled:
        return SettingChangeResult(
            True,
            "The background session will now keep running its screen while its window is "
            "minimized.",
            changed=True,
        )
    return SettingChangeResult(
        True,
        "Restored the Windows default: minimizing the background session's window pauses its "
        "screen again.",
        changed=True,
    )
