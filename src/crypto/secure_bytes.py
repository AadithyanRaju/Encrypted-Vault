"""Memory-safe container for sensitive cryptographic key material.

Provides:
  - Mutable bytearray backing so the buffer can be zeroed on cleanup.
  - Optional memory locking (mlock on Linux/macOS, VirtualLock on Windows)
    to prevent the key pages from being swapped to disk.
  - Context-manager and __del__ support so keys are wiped automatically
    when the block exits or the object is garbage-collected.
  - A standalone wipe_key() helper for plain bytearray buffers.
"""

import ctypes
import platform


def _get_libc():
    """Return the libc CDLL handle for mlock/munlock (Unix-like only)."""
    system = platform.system()
    if system == "Linux":
        return ctypes.CDLL("libc.so.6", use_errno=True)
    if system == "Darwin":
        return ctypes.CDLL("libc.dylib", use_errno=True)
    return None


def wipe_key(buf: bytearray) -> None:
    """Overwrite a mutable bytearray key buffer with zeros in-place.

    Uses ctypes.memset so the write cannot be optimised away by the
    compiler or interpreter.  Falls back to a pure-Python loop if the
    ctypes path fails.
    """
    if not isinstance(buf, bytearray) or len(buf) == 0:
        return
    n = len(buf)
    try:
        addr = ctypes.addressof((ctypes.c_char * n).from_buffer(buf))
        ctypes.memset(addr, 0, n)
    except Exception:
        for i in range(n):
            buf[i] = 0


class SecureBytes:
    """Immutable-length, mutable-content buffer for cryptographic key material.

    On creation the backing bytearray is optionally locked into RAM via
    mlock(2) (Linux / macOS) or VirtualLock (Windows) so it is never
    paged to swap.  When the object is cleaned up (context-manager exit
    or garbage-collection) the buffer is overwritten with zeros before
    being released.

    Usage as a context manager (preferred)::

        with SecureBytes(derive_raw_key()) as key:
            do_something(bytes(key))
        # key material is wiped here

    Usage with explicit cleanup::

        key = SecureBytes(raw_bytes)
        try:
            do_something(bytes(key))
        finally:
            key.wipe()
    """

    __slots__ = ("_buf", "_locked")

    def __init__(self, data: "bytes | bytearray") -> None:
        self._buf: "bytearray | None" = bytearray(data)
        self._locked: bool = False
        self._mlock()

    # ------------------------------------------------------------------
    # Memory-locking helpers (best-effort; silently ignored on failure)
    # ------------------------------------------------------------------

    def _mlock(self) -> None:
        """Attempt to lock the backing pages so they are never swapped."""
        if self._buf is None:
            return
        n = len(self._buf)
        if n == 0:
            return
        try:
            system = platform.system()
            if system in ("Linux", "Darwin"):
                libc = _get_libc()
                if libc is not None:
                    carray = (ctypes.c_char * n).from_buffer(self._buf)
                    ret = libc.mlock(carray, ctypes.c_size_t(n))
                    self._locked = ret == 0
            elif system == "Windows":
                carray = (ctypes.c_char * n).from_buffer(self._buf)
                ok = ctypes.windll.kernel32.VirtualLock(
                    ctypes.cast(carray, ctypes.c_void_p),
                    ctypes.c_size_t(n),
                )
                self._locked = bool(ok)
        except Exception:
            self._locked = False

    def _munlock(self) -> None:
        """Release any memory lock held on the backing buffer."""
        if not self._locked or self._buf is None:
            return
        n = len(self._buf)
        try:
            system = platform.system()
            if system in ("Linux", "Darwin"):
                libc = _get_libc()
                if libc is not None:
                    carray = (ctypes.c_char * n).from_buffer(self._buf)
                    libc.munlock(carray, ctypes.c_size_t(n))
            elif system == "Windows":
                carray = (ctypes.c_char * n).from_buffer(self._buf)
                ctypes.windll.kernel32.VirtualUnlock(
                    ctypes.cast(carray, ctypes.c_void_p),
                    ctypes.c_size_t(n),
                )
        except Exception:
            pass
        self._locked = False

    # ------------------------------------------------------------------
    # Secure wiping
    # ------------------------------------------------------------------

    def wipe(self) -> None:
        """Overwrite key material with zeros and release the buffer.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if self._buf is None:
            return
        self._munlock()
        wipe_key(self._buf)
        self._buf = None

    # ------------------------------------------------------------------
    # Standard dunder helpers
    # ------------------------------------------------------------------

    def __bytes__(self) -> bytes:
        if self._buf is None:
            raise ValueError("SecureBytes has already been wiped")
        return bytes(self._buf)

    def __len__(self) -> int:
        return len(self._buf) if self._buf is not None else 0

    def __bool__(self) -> bool:
        return self._buf is not None and len(self._buf) > 0

    def __enter__(self) -> "SecureBytes":
        return self

    def __exit__(self, *_) -> None:
        self.wipe()

    def __del__(self) -> None:
        self.wipe()

    def __repr__(self) -> str:
        # Never reveal key material in string representations.
        return f"<SecureBytes len={len(self)} locked={self._locked}>"
