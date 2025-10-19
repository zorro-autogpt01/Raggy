from __future__ import annotations
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import json
import os
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[A-Za-z_]\w+")

def _tokenize(text: str) -> List[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text)]

@dataclass
class LexicalIndex:
    repo_id: str
    doc_ids: List[str]
    tokens_per_doc: List[List[str]]
    df: Dict[str, int]
    avgdl: float
    k1: float = 1.5
    b: float = 0.75

    def score(self, query: str) -> List[Tuple[str, float]]:
        """
        Compute BM25-like score for all docs, return list of (doc_id, score) sorted desc.
        """
        q_tokens = _tokenize(query)
        if not q_tokens or not self.doc_ids:
            return []
        N = len(self.doc_ids)
        # Precompute idf for query terms only
        idf: Dict[str, float] = {}
        for t in set(q_tokens):
            df_t = self.df.get(t, 0)
            # Okapi BM25 idf with +1 smoothing to avoid negative for unseen
            idf[t] = math.log((N - df_t + 0.5) / (df_t + 0.5) + 1.0)

        scores: List[Tuple[int, float]] = []
        for i, doc_tokens in enumerate(self.tokens_per_doc):
            if not doc_tokens:
                scores.append((i, 0.0)); continue
            dl = len(doc_tokens)
            tf = Counter(doc_tokens)
            s = 0.0
            for t in q_tokens:
                f = tf.get(t, 0)
                if f == 0:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * (dl / (self.avgdl or 1.0)))
                s += idf.get(t, 0.0) * ((f * (self.k1 + 1)) / (denom or 1.0))
            scores.append((i, s))
        # Sort descending by score
        scores.sort(key=lambda x: x[1], reverse=True)
        return [(self.doc_ids[i], sc) for (i, sc) in scores]

# In-memory cache of loaded indexes
_CACHE: Dict[str, LexicalIndex] = {}

def _repo_path(base_path: str, repo_id: str) -> str:
    return os.path.join(base_path, f"{repo_id}.json")

def save_index(base_path: str, index: LexicalIndex) -> None:
    os.makedirs(base_path, exist_ok=True)
    path = _repo_path(base_path, index.repo_id)
    data = {
        "repo_id": index.repo_id,
        "doc_ids": index.doc_ids,
        "tokens_per_doc": index.tokens_per_doc,
        "df": index.df,
        "avgdl": index.avgdl,
    }
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

def load_index(base_path: str, repo_id: str) -> Optional[LexicalIndex]:
    if repo_id in _CACHE:
        return _CACHE[repo_id]
    path = _repo_path(base_path, repo_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        idx = LexicalIndex(
            repo_id=data["repo_id"],
            doc_ids=data["doc_ids"],
            tokens_per_doc=data["tokens_per_doc"],
            df=data["df"],
            avgdl=float(data["avgdl"]),
        )
        _CACHE[repo_id] = idx
        return idx
    except Exception:
        return None

def build_index(repo_id: str, documents: List[Dict[str, str]], base_path: str) -> Optional[LexicalIndex]:
    """
    Build a lexical index for the repo. documents: list of {"id": str, "text": str}
    """
    if not documents:
        return None
    doc_ids: List[str] = []
    tokens_per_doc: List[List[str]] = []
    for d in documents:
        doc_ids.append(d["id"])
        tokens_per_doc.append(_tokenize(d.get("text") or ""))

    # df and avgdl
    df: Dict[str, int] = {}
    for toks in tokens_per_doc:
        seen = set(toks)
        for t in seen:
            df[t] = df.get(t, 0) + 1
    total_len = sum(len(toks) for toks in tokens_per_doc)
    avgdl = float(total_len) / float(len(tokens_per_doc)) if tokens_per_doc else 0.0

    idx = LexicalIndex(
        repo_id=repo_id,
        doc_ids=doc_ids,
        tokens_per_doc=tokens_per_doc,
        df=df,
        avgdl=avgdl
    )
    save_index(base_path, idx)
    _CACHE[repo_id] = idx
    return idx

def query_bm25(repo_id: str, query: str, k: int, base_path: str) -> List[Tuple[str, float]]:
    """
    Return top-k (doc_id, score). If no index exists, returns [].
    """
    idx = load_index(base_path, repo_id)
    if not idx:
        return []
    scored = idx.score(query)
    # Filter zero-score docs
    scored = [(doc_id, sc) for (doc_id, sc) in scored if sc > 0.0]
    return scored[:k]