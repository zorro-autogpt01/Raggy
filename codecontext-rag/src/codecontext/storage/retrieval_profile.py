from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import os
import json
import threading
from ..config import settings

@dataclass
class RetrievalProfile:
    repo_id: str
    # Ranking weights override (optional): keys 'semantic','dependency','history','recency'
    weights: Optional[Dict[str, float]] = None
    # Blending
    hybrid_alpha: float = 0.2
    # Agentic config
    agentic_min_semantic: float = 0.55
    agentic_verify_files: bool = True
    agentic_verify_symbols: bool = True
    agentic_min_new_files: int = 1
    agentic_gain_min_ratio: float = 0.15
    agentic_max_iters: int = 0  # default inherited elsewhere if 0
    # Dependency defaults (for future use in routes/options)
    dependency_depth_default: int = 1

class RetrievalProfileStore:
    def __init__(self, base_dir: str = "./data/retrieval_profiles"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, repo_id: str) -> str:
        safe = repo_id.replace("/", "_")
        return os.path.join(self.base_dir, f"{safe}.json")

    def load(self, repo_id: str) -> RetrievalProfile:
        path = self._path(repo_id)
        if not os.path.exists(path):
            return self._default(repo_id)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._from_dict(repo_id, data)
        except Exception:
            return self._default(repo_id)

    def save(self, profile: RetrievalProfile) -> None:
        path = self._path(profile.repo_id)
        tmp = path + ".tmp"
        with self._lock:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(asdict(profile), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)

    def _default(self, repo_id: str) -> RetrievalProfile:
        return RetrievalProfile(
            repo_id=repo_id,
            weights=None,
            hybrid_alpha=0.2,
            agentic_min_semantic=settings.agentic_min_semantic,
            agentic_verify_files=settings.agentic_verify_files,
            agentic_verify_symbols=settings.agentic_verify_symbols,
            agentic_min_new_files=settings.agentic_min_new_files,
            agentic_gain_min_ratio=settings.agentic_gain_min_ratio,
            agentic_max_iters=settings.agentic_max_iters,
            dependency_depth_default=1
        )

    def _from_dict(self, repo_id: str, data: Dict[str, Any]) -> RetrievalProfile:
        return RetrievalProfile(
            repo_id=repo_id,
            weights=data.get("weights"),
            hybrid_alpha=float(data.get("hybrid_alpha", 0.2)),
            agentic_min_semantic=float(data.get("agentic_min_semantic", settings.agentic_min_semantic)),
            agentic_verify_files=bool(data.get("agentic_verify_files", settings.agentic_verify_files)),
            agentic_verify_symbols=bool(data.get("agentic_verify_symbols", settings.agentic_verify_symbols)),
            agentic_min_new_files=int(data.get("agentic_min_new_files", settings.agentic_min_new_files)),
            agentic_gain_min_ratio=float(data.get("agentic_gain_min_ratio", settings.agentic_gain_min_ratio)),
            agentic_max_iters=int(data.get("agentic_max_iters", settings.agentic_max_iters)),
            dependency_depth_default=int(data.get("dependency_depth_default", 1)),
        )

    def update_weights(self, repo_id: str, weights: Dict[str, float]) -> RetrievalProfile:
        prof = self.load(repo_id)
        prof.weights = weights
        self.save(prof)
        return prof

    def update_from_execution(self, repo_id: str, metrics: Dict[str, Any]) -> RetrievalProfile:
        """
        metrics expects:
          retrieval_precision: float 0..1
          had_missing: bool
          success: bool
        """
        p = self.load(repo_id)
        precision = float(metrics.get("retrieval_precision") or 0.0)
        had_missing = bool(metrics.get("had_missing"))
        success = bool(metrics.get("success"))

        # Heuristics:
        # - If precision low or missing entities: increase lexical blend and loosen agentic threshold, allow more agentic iters.
        # - If success with good precision: reduce lexical blend a bit, tighten agentic threshold, reduce iters.
        if precision < 0.4 or had_missing:
            p.hybrid_alpha = min(0.6, p.hybrid_alpha + 0.05)
            p.agentic_min_semantic = max(0.40, p.agentic_min_semantic - 0.03)
            p.agentic_max_iters = min(4, (p.agentic_max_iters or 0) + 1)
        elif success and precision >= 0.7 and not had_missing:
            p.hybrid_alpha = max(0.15, p.hybrid_alpha - 0.03)
            p.agentic_min_semantic = min(0.70, p.agentic_min_semantic + 0.02)
            if p.agentic_max_iters > 0:
                p.agentic_max_iters = max(0, p.agentic_max_iters - 1)

        self.save(p)
        return p

    def update_from_change(self, repo_id: str, blast_accuracy: float, success: bool) -> RetrievalProfile:
        """
        Adjust dependency defaults. If blast accuracy low, increase dependency depth default; else slightly reduce it.
        """
        p = self.load(repo_id)
        if blast_accuracy < 0.6:
            p.dependency_depth_default = min(3, p.dependency_depth_default + 1)
        elif success and blast_accuracy >= 0.8:
            p.dependency_depth_default = max(1, p.dependency_depth_default - 1)
        self.save(p)
        return p
