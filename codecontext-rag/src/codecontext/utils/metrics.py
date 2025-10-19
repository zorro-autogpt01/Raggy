from __future__ import annotations
from typing import Dict, Tuple, Optional
import threading
from ..config import settings

class Metrics:
    _lock = threading.Lock()
    _counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], int] = {}
    _summaries: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Dict[str, float]] = {}

    @classmethod
    def inc(cls, name: str, labels: Dict[str, str] | None = None, value: int = 1) -> None:
        if not settings.metrics_enabled:
            return
        key = (name, tuple(sorted((labels or {}).items())))
        with cls._lock:
            cls._counters[key] = cls._counters.get(key, 0) + value

    @classmethod
    def observe(cls, name: str, value: float, labels: Dict[str, str] | None = None) -> None:
        """
        Observe numeric value into a summary (count, sum, min, max).
        """
        if not settings.metrics_enabled:
            return
        key = (name, tuple(sorted((labels or {}).items())))
        with cls._lock:
            s = cls._summaries.get(key)
            if not s:
                s = {"count": 0.0, "sum": 0.0, "min": value, "max": value}
                cls._summaries[key] = s
            s["count"] += 1.0
            s["sum"] += float(value)
            if value < s["min"]:
                s["min"] = float(value)
            if value > s["max"]:
                s["max"] = float(value)

    @classmethod
    def snapshot(cls) -> Dict[str, int]:
        """
        Flat counters for quick inspection.
        """
        out: Dict[str, int] = {}
        if not settings.metrics_enabled:
            return out
        with cls._lock:
            for (name, labels), v in cls._counters.items():
                if labels:
                    label_str = ",".join(f"{k}={val}" for k, val in labels)
                    out[f"{name}{{{label_str}}}"] = v
                else:
                    out[name] = v
        return out

    @classmethod
    def snapshot_summaries(cls) -> Dict[str, Dict[str, float]]:
        """
        Flat summaries with count/sum/min/max/avg.
        """
        out: Dict[str, Dict[str, float]] = {}
        if not settings.metrics_enabled:
            return out
        with cls._lock:
            for (name, labels), s in cls._summaries.items():
                avg = (s["sum"] / s["count"]) if s["count"] > 0 else 0.0
                key: str
                if labels:
                    label_str = ",".join(f"{k}={val}" for k, val in labels)
                    key = f"{name}{{{label_str}}}"
                else:
                    key = name
                out[key] = {
                    "count": s["count"],
                    "sum": s["sum"],
                    "min": s["min"],
                    "max": s["max"],
                    "avg": avg
                }
        return out

    @classmethod
    def snapshot_all(cls) -> Dict[str, object]:
        """
        Combined counters and summaries.
        """
        return {
            "counters": cls.snapshot(),
            "summaries": cls.snapshot_summaries()
        }