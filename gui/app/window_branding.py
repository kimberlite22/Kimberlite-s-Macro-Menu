"""Best-effort Win32 branding for the visible Remote Desktop client window."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable


GW_OWNER = 4
WM_SETTEXT = 0x000C
WM_GETICON = 0x007F
WM_SETICON = 0x0080
ICON_SMALL = 0
ICON_BIG = 1
IMAGE_ICON = 1
LR_LOADFROMFILE = 0x00000010
SMTO_ABORTIFHUNG = 0x0002
SEND_MESSAGE_TIMEOUT_MS = 200
SM_CXICON = 11
SM_CYICON = 12
SM_CXSMICON = 49
SM_CYSMICON = 50

_HWND = getattr(wintypes, "HWND", wintypes.HANDLE)
# LPARAM, WPARAM and LRESULT carry handles in this module, so keep them pointer-sized on 64-bit
# Windows instead of relying on older ctypes.wintypes definitions that use a 32-bit c_long.
_WPARAM = ctypes.c_size_t
_LPARAM = ctypes.c_ssize_t
_LRESULT = ctypes.c_ssize_t
_enum_windows_proc = getattr(ctypes, "WINFUNCTYPE", ctypes.CFUNCTYPE)(
    wintypes.BOOL, _HWND, _LPARAM
)

# WM_SETICON does not copy the icon, so these handles must live for this process's entire
# lifetime. Destroying them would leave the Remote Desktop window pointing at a freed handle.
_icon_handles: tuple[int, int] | None = None


def _user32() -> Any:
    """Return typed user32 bindings, or None when this platform cannot provide them."""
    if sys.platform != "win32":
        return None
    try:
        library = ctypes.windll.user32
        library.EnumWindows.argtypes = [_enum_windows_proc, _LPARAM]
        library.EnumWindows.restype = wintypes.BOOL
        library.GetWindowThreadProcessId.argtypes = [_HWND, ctypes.POINTER(wintypes.DWORD)]
        library.GetWindowThreadProcessId.restype = wintypes.DWORD
        library.IsWindowVisible.argtypes = [_HWND]
        library.IsWindowVisible.restype = wintypes.BOOL
        library.GetWindow.argtypes = [_HWND, wintypes.UINT]
        library.GetWindow.restype = _HWND
        library.GetWindowTextLengthW.argtypes = [_HWND]
        library.GetWindowTextLengthW.restype = ctypes.c_int
        library.GetWindowTextW.argtypes = [_HWND, wintypes.LPWSTR, ctypes.c_int]
        library.GetWindowTextW.restype = ctypes.c_int
        library.SendMessageTimeoutW.argtypes = [
            _HWND,
            wintypes.UINT,
            _WPARAM,
            _LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        library.SendMessageTimeoutW.restype = _LRESULT
        library.LoadImageW.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        library.LoadImageW.restype = wintypes.HANDLE
        library.GetSystemMetrics.argtypes = [ctypes.c_int]
        library.GetSystemMetrics.restype = ctypes.c_int
        return library
    except (AttributeError, ImportError, OSError, TypeError, ValueError):
        return None


def _send_message_timeout(
    library: Any, hwnd: int, message: int, wparam: int, lparam: int
) -> int | None:
    """Send a cross-process message without allowing a hung target to block the GUI."""
    try:
        result = ctypes.c_size_t()
        sent = library.SendMessageTimeoutW(
            hwnd,
            message,
            wparam,
            lparam,
            SMTO_ABORTIFHUNG,
            SEND_MESSAGE_TIMEOUT_MS,
            ctypes.byref(result),
        )
        if not sent:
            return None
        return int(result.value)
    except Exception:
        return None


def _handle_value(handle: object) -> int:
    """Normalize ctypes handles and callback values to an integer Win32 handle."""
    try:
        return int(getattr(handle, "value", handle) or 0)
    except (TypeError, ValueError):
        return 0


def top_level_windows_for_process(pid: int) -> list[int]:
    """Return visible, unowned top-level window handles belonging to ``pid``.

    This is deliberately the sole EnumWindows wrapper. Callers can replace it in tests without
    having to recreate a ctypes callback or any Win32 structures.
    """
    try:
        library = _user32()
        if library is None:
            return []
        matches: list[int] = []

        @_enum_windows_proc
        def collect(hwnd: int, _lparam: int) -> bool:
            try:
                window_pid = wintypes.DWORD()
                library.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                if int(window_pid.value) != pid:
                    return True
                if not library.IsWindowVisible(hwnd):
                    return True
                if _handle_value(library.GetWindow(hwnd, GW_OWNER)) != 0:
                    return True
                matches.append(_handle_value(hwnd))
            except Exception:
                pass
            return True

        if not library.EnumWindows(collect, 0):
            return []
        return matches
    except Exception:
        return []


def _load_icon_handles(library: Any, icon_path: Path | str | None) -> tuple[int, int] | None:
    """Load and retain the small and large application icons needed by WM_SETICON."""
    global _icon_handles

    try:
        path = Path(icon_path) if icon_path is not None else None
        if path is None or not path.is_file():
            return None
        if _icon_handles is not None:
            return _icon_handles
        small = _handle_value(
            library.LoadImageW(
                None,
                str(path),
                IMAGE_ICON,
                library.GetSystemMetrics(SM_CXSMICON),
                library.GetSystemMetrics(SM_CYSMICON),
                LR_LOADFROMFILE,
            )
        )
        big = _handle_value(
            library.LoadImageW(
                None,
                str(path),
                IMAGE_ICON,
                library.GetSystemMetrics(SM_CXICON),
                library.GetSystemMetrics(SM_CYICON),
                LR_LOADFROMFILE,
            )
        )
        if not small or not big:
            return None
        _icon_handles = (small, big)
        return _icon_handles
    except Exception:
        return None


def _window_text(library: Any, hwnd: int) -> str | None:
    """Read a window title, preserving an empty title as a valid result."""
    try:
        length = max(0, int(library.GetWindowTextLengthW(hwnd)))
        buffer = ctypes.create_unicode_buffer(length + 1)
        library.GetWindowTextW(hwnd, buffer, len(buffer))
        return buffer.value
    except Exception:
        return None


def apply_branding(pid: int, title: str, icon_path: Path | str | None) -> bool:
    """Apply this app's title and icon to the visible Remote Desktop windows for ``pid``.

    Remote Desktop can replace its own title while connecting, so the caller repeats this cosmetic
    operation briefly. Every Win32 failure is contained because branding must never affect
    the connection itself.
    """
    try:
        library = _user32()
        if library is None:
            return False
        windows = top_level_windows_for_process(pid)
        if not windows:
            return False
        icons = _load_icon_handles(library, icon_path)

        branded = False
        for hwnd in windows:
            try:
                current_title = _window_text(library, hwnd)
                if current_title == title:
                    title_ok = True
                elif current_title is None:
                    title_ok = False
                else:
                    # WM_SETTEXT is one of the messages USER32 marshals across process boundaries,
                    # so this is the correct cross-process equivalent, and unlike SetWindowTextW it
                    # cannot hang.
                    title_buffer = ctypes.create_unicode_buffer(title)
                    title_result = _send_message_timeout(
                        library,
                        hwnd,
                        WM_SETTEXT,
                        0,
                        ctypes.cast(title_buffer, ctypes.c_void_p).value or 0,
                    )
                    title_ok = title_result is not None and bool(title_result)

                icon_ok = False
                if icons is not None:
                    # Both sizes are queried, not just the big one: Remote Desktop can replace the
                    # small icon on its own, and checking only the big one would report that as
                    # already branded and never restore the small icon the taskbar shows.
                    current_small_icon = _send_message_timeout(
                        library, hwnd, WM_GETICON, ICON_SMALL, 0
                    )
                    current_big_icon = _send_message_timeout(
                        library, hwnd, WM_GETICON, ICON_BIG, 0
                    )
                    if current_small_icon == icons[0] and current_big_icon == icons[1]:
                        icon_ok = True
                    else:
                        # Querying the current icons avoids stale handle values and reasserts them
                        # if Remote Desktop replaces its own icon while connecting.
                        small_result = _send_message_timeout(
                            library, hwnd, WM_SETICON, ICON_SMALL, icons[0]
                        )
                        big_result = _send_message_timeout(
                            library, hwnd, WM_SETICON, ICON_BIG, icons[1]
                        )
                        icon_ok = small_result is not None and big_result is not None
                branded = branded or title_ok or icon_ok
            except Exception:
                continue
        return branded
    except Exception:
        return False


def run_branding_loop(
    pid: int,
    title: str,
    icon_path: Path | str | None,
    cancel: threading.Event,
    *,
    attempts: int = 30,
    interval: float = 0.5,
    sleep: Callable[[float], object] = time.sleep,
    keep_alive: object = None,
) -> None:
    """Retry branding briefly while Remote Desktop replaces its connecting window title.

    ``attempts`` and ``sleep`` are injected so tests can cover the retry lifecycle without waiting.
    This function deliberately has no Qt dependency, so it is safe to run on a plain thread.

    ``keep_alive`` is never read. It exists so the launched client's Popen, and therefore its open
    process handle, stays referenced on THIS frame for exactly as long as the loop can still act on
    ``pid``. Windows does not recycle a process id while a handle to it is open, so holding it here
    rather than only on the caller closes the last gap: cancellation drops the caller's reference
    immediately, but a pass already in flight would otherwise still be targeting an id that had
    become free to reuse.
    """
    try:
        if cancel.is_set():
            return
        for attempt in range(attempts):
            if cancel.is_set():
                return
            apply_branding(pid, title, icon_path)
            if attempt == attempts - 1 or cancel.is_set():
                return
            sleep(interval)
            if cancel.is_set():
                return
    except Exception:
        return
