"""Explicit Windows UAC elevation; no ACL or ownership modifications."""
import os
import subprocess
import sys
from pathlib import Path


def is_admin():
    if os.name != 'nt':
        return False
    import ctypes
    return bool(ctypes.windll.shell32.IsUserAnAdmin())


def main():
    if os.name != 'nt':
        raise SystemExit('Le lancement administrateur nécessite Windows.')
    import ctypes
    from ctypes import wintypes
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    shell.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                   wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
    shell.ShellExecuteW.restype = ctypes.c_void_p
    directory = str(Path(__file__).resolve().parent.parent)
    arguments = subprocess.list2cmdline(['-m', 'clair_storage', *sys.argv[1:]])
    result = shell.ShellExecuteW(None, 'runas', sys.executable, arguments, directory, 1)
    if not result or result <= 32:
        raise SystemExit('Lancement administrateur annulé ou refusé.')


if __name__ == '__main__':
    main()
