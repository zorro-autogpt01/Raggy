from __future__ import annotations
from typing import Any, Dict
import time
import threading

class TTLCache:
    """
    Simple in-memory TTL cache with prefix invalidation.
    Not process-safe across workers; intended for single-process uvicorn.
    """
    def __init__(self):
        self._store: Dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            exp, val = entry
            if exp and exp < now:
                # expired
                self._store.pop(key, None)
                return None
            return val

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        exp = time.time() + float(ttl_seconds) if ttl_seconds > 0 else 0.0
        with self._lock:
            self._store[key] = (exp, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def invalidate_prefix(self, prefix: str) -> int:
        """
        Delete all keys starting with prefix. Returns number deleted.
        """
        with self._lock:
            keys = [k for k in self._store.keys() if k.startswith(prefix)]
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()