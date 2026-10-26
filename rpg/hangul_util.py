"""Hangul 2-set QWERTY assembly and Windows clipboard utility."""

from __future__ import annotations

import sys
from typing import Any

# Korean 2-Set (두벌식) consonants and vowels definitions
CHO = [
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"
]
JUNG = [
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅘ",
    "ㅙ", "ㅚ", "ㅛ", "ㅜ", "ㅝ", "ㅞ", "ㅟ", "ㅠ", "ㅡ", "ㅢ", "ㅣ"
]
JONG = [
    "", "ㄱ", "ㄲ", "ㄳ", "ㄴ", "ㄵ", "ㄶ", "ㄷ", "ㄹ", "ㄺ",
    "ㄻ", "ㄼ", "ㄽ", "ㄾ", "ㄿ", "ㅀ", "ㅁ", "ㅂ", "ㅄ", "ㅅ",
    "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ", "ㅎ"
]

KEY_MAP = {
    "q": "ㅂ", "Q": "ㅃ", "w": "ㅈ", "W": "ㅉ", "e": "ㄷ", "E": "ㄸ",
    "r": "ㄱ", "R": "ㄲ", "t": "ㅅ", "T": "ㅆ", "y": "ㅛ", "Y": "ㅛ",
    "u": "ㅕ", "U": "ㅕ", "i": "ㅑ", "I": "ㅑ", "o": "ㅐ", "O": "ㅒ",
    "p": "ㅔ", "P": "ㅖ", "a": "ㅁ", "A": "ㅁ", "s": "ㄴ", "S": "ㄴ",
    "d": "ㅇ", "D": "ㅇ", "f": "ㄹ", "F": "ㄹ", "g": "ㅎ", "G": "ㅎ",
    "h": "ㅗ", "H": "ㅗ", "j": "ㅓ", "J": "ㅓ", "k": "ㅏ", "K": "ㅏ",
    "l": "ㅣ", "L": "ㅣ", "z": "ㅋ", "Z": "ㅋ", "x": "ㅌ", "X": "ㅌ",
    "c": "ㅊ", "C": "ㅊ", "v": "ㅍ", "V": "ㅍ", "b": "ㅠ", "B": "ㅠ",
    "n": "ㅜ", "N": "ㅜ", "m": "ㅡ", "M": "ㅡ"
}

COMPLEX_JUNG = {
    ("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ",
    ("ㅜ", "ㅓ"): "ㅝ", ("ㅜ", "ㅔ"): "ㅞ", ("ㅜ", "ㅣ"): "ㅟ",
    ("ㅡ", "ㅣ"): "ㅢ"
}

COMPLEX_JONG = {
    ("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ",
    ("ㄹ", "ㄱ"): "ㄺ", ("ㄹ", "ㅁ"): "ㄻ", ("ㄹ", "ㅂ"): "ㄼ", ("ㄹ", "ㅅ"): "ㄽ",
    ("ㄹ", "ㅌ"): "ㄾ", ("ㄹ", "ㅍ"): "ㄿ", ("ㄹ", "ㅎ"): "ㅀ",
    ("ㅂ", "ㅅ"): "ㅄ"
}


def eng_to_hangul(text: str) -> str:
    """Convert 2-set English QWERTY keystrokes into combined Hangul syllables."""
    if not text:
        return ""
    jamos = [KEY_MAP.get(c, c) for c in text]
    result: list[str] = []
    i = 0
    n = len(jamos)
    while i < n:
        c = jamos[i]
        if c in CHO:
            if i + 1 < n and jamos[i + 1] in JUNG:
                cho_idx = CHO.index(c)
                jung = jamos[i + 1]
                i += 2
                if i < n and (jung, jamos[i]) in COMPLEX_JUNG:
                    jung = COMPLEX_JUNG[(jung, jamos[i])]
                    i += 1
                jung_idx = JUNG.index(jung)
                jong_idx = 0
                if i < n and jamos[i] in JONG:
                    if i + 1 < n and jamos[i + 1] in JUNG:
                        pass
                    else:
                        c_jong = jamos[i]
                        if i + 1 < n and (c_jong, jamos[i + 1]) in COMPLEX_JONG:
                            if i + 2 < n and jamos[i + 2] in JUNG:
                                jong_idx = JONG.index(c_jong)
                                i += 1
                            else:
                                jong_idx = JONG.index(COMPLEX_JONG[(c_jong, jamos[i + 1])])
                                i += 2
                        else:
                            jong_idx = JONG.index(c_jong)
                            i += 1
                result.append(chr(0xAC00 + (cho_idx * 21 + jung_idx) * 28 + jong_idx))
            else:
                result.append(c)
                i += 1
        else:
            result.append(c)
            i += 1
    return "".join(result)


def get_clipboard_text() -> str:
    """Retrieve UTF-16/Unicode text from Windows clipboard via ctypes."""
    if sys.platform != "win32":
        return ""
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL
        user32.GetClipboardData.argtypes = [wintypes.UINT]
        user32.GetClipboardData.restype = wintypes.HANDLE
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL

        if not user32.OpenClipboard(None):
            return ""
        try:
            handle = user32.GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            p = kernel32.GlobalLock(handle)
            if not p:
                return ""
            try:
                return ctypes.c_wchar_p(p).value or ""
            finally:
                kernel32.GlobalUnlock(handle)
        finally:
            user32.CloseClipboard()
    except Exception:
        return ""


def set_clipboard_text(text: str) -> bool:
    """Copy Unicode text to Windows clipboard via ctypes."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
        kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalLock.restype = wintypes.LPVOID
        kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        user32.OpenClipboard.argtypes = [wintypes.HWND]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
        user32.SetClipboardData.restype = wintypes.HANDLE
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = wintypes.BOOL

        encoded = (text + "\0").encode("utf-16le")
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not h_mem:
            return False
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            return False
        try:
            ctypes.memmove(ptr, encoded, len(encoded))
        finally:
            kernel32.GlobalUnlock(h_mem)

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        finally:
            user32.CloseClipboard()
        return True
    except Exception:
        return False
