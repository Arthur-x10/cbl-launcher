"""敏感字段的本地加密存储。

- Windows：DPAPI（CryptProtectData），绑定当前用户 + 当前机器，落盘 `dpapi:...`。
- Linux/macOS：优先系统密钥环 keyring，落盘 `keyring:<slot>`；没有 keyring 时退化为明文，
  并在 stderr 打印一次警告（不静默）。
- 解密失败（换了机器/用户/密钥环条目被删）一律返回空串，绝不把密文当令牌用。
"""

import base64
import ctypes
import sys
from ctypes import wintypes

_PREFIX_DPAPI = "dpapi:"
_PREFIX_KEYRING = "keyring:"
_KEYRING_SERVICE = "CBL-Cube-Launcher"

_warned = False


class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_char)),
    ]


def available() -> bool:
    """是否有可用的加密后端。"""
    return is_windows() or _keyring() is not None


def is_windows() -> bool:
    return sys.platform == "win32"


def _keyring():
    try:
        import keyring  # type: ignore
        return keyring
    except Exception:
        return None


def _to_blob(data: bytes) -> _DATA_BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _from_blob(blob: _DATA_BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _warn_once(msg: str):
    global _warned
    if not _warned:
        _warned = True
        print(f"[secret] {msg}", file=sys.stderr)


# ── 加密 ──

def encrypt(plain: str, slot: str = "") -> str:
    """加密敏感字符串。失败或没有后端时原样返回（调用方无感）。"""
    if not plain or plain.startswith((_PREFIX_DPAPI, _PREFIX_KEYRING)):
        return plain

    if is_windows():
        try:
            out = _DATA_BLOB()
            ok = ctypes.windll.crypt32.CryptProtectData(
                ctypes.byref(_to_blob(plain.encode("utf-8"))),
                None, None, None, None, 0, ctypes.byref(out),
            )
            if ok:
                try:
                    return _PREFIX_DPAPI + base64.b64encode(_from_blob(out)).decode("ascii")
                finally:
                    ctypes.windll.kernel32.LocalFree(out.pbData)
        except Exception:
            pass

    kr = _keyring()
    if kr is not None and slot:
        try:
            kr.set_password(_KEYRING_SERVICE, slot, plain)
            return _PREFIX_KEYRING + slot
        except Exception:
            pass

    _warn_once("没有可用的加密后端，凭证将以明文保存在 config.json 中")
    return plain


def decrypt(stored: str, slot: str = "") -> str:
    """解密。解不开时返回空串。"""
    if not stored or not isinstance(stored, str):
        return ""

    if stored.startswith(_PREFIX_DPAPI):
        if not is_windows():
            return ""
        try:
            raw = base64.b64decode(stored[len(_PREFIX_DPAPI):])
            out = _DATA_BLOB()
            ok = ctypes.windll.crypt32.CryptUnprotectData(
                ctypes.byref(_to_blob(raw)), None, None, None, None, 0, ctypes.byref(out),
            )
            if not ok:
                return ""
            try:
                return _from_blob(out).decode("utf-8", "replace")
            finally:
                ctypes.windll.kernel32.LocalFree(out.pbData)
        except Exception:
            return ""

    if stored.startswith(_PREFIX_KEYRING):
        key = stored[len(_PREFIX_KEYRING):] or slot
        kr = _keyring()
        if kr is None or not key:
            return ""
        try:
            return kr.get_password(_KEYRING_SERVICE, key) or ""
        except Exception:
            return ""

    return stored


def is_encrypted(value) -> bool:
    return isinstance(value, str) and value.startswith((_PREFIX_DPAPI, _PREFIX_KEYRING))
