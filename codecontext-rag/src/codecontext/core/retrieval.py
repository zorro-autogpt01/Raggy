from __future__ import annotations
from typing import List, Dict, Any, Optional, Set, Tuple
import re
import time
import json
from collections import defaultdict, deque

from ..config import settings
from ..core.reranker import LocalReranker
from ..core.lexical import query_bm25
from ..utils.metrics import Metrics
from ..storage.retrieval_profile import RetrievalProfileStore

def _normalize_candidates(candidates: List[Dict]) -> List[Dict]:
    out = []
    for c in candidates:
        if "_distance" in c and isinstance(c["_distance"], (int, float)):
            out.append(c); continue
        score = c.get("score", None); dist = 0.5
        if isinstance(score, (int, float)):
            if 0.0 <= score <= 1.0: dist = 1.0 - float(score)
            else: dist = float(score)
        c["_distance"] = dist; out.append(c)
    return out

def _compute_signature(text: str, name: Optional[str]) -> str:
    import hashlib
    t = re.sub(r"\s+", "", (text or ""))
    if name: t = name + "|" + t
    return hashlib.sha1(t.encode("utf-8", errors="ignore")).hexdigest()

def _dedup_by_signature(items: List[Dict], sig_counts: Dict[str, int]) -> List[Dict]:
    seen = set(); out = []
    for it in items:
        sig = _compute_signature(it.get("code") or it.get("snippet") or "", it.get("name"))
        if sig in seen: continue
        seen.add(sig)
        if sig in sig_counts and sig_counts[sig] > 1:
            rs = list(it.get("reasons") or [])
            rs.append({'type': 'dedup','score': 1.0,'explanation': f"Deduplicated {sig_counts[sig]-1} similar definitions"})
            it['reasons'] = rs
        out.append(it)
    return out

def _keyword_score(query: str, text: str) -> float:
    if not query or not text: return 0.0
    q_terms = [t.lower() for t in query.split() if len(t) > 2]
    if not q_terms: return 0.0
    tl = text.lower()
    hits = sum(1 for t in q_terms if t in tl)
    return min(1.0, hits / max(1, len(q_terms)))

def _hybrid_rerank(candidates: List[Dict], query: str, alpha: float = 0.2, bm25_scores: Optional[Dict[str, float]] = None) -> List[Dict]:
    reranked = []
    for c in candidates:
        sem = 1.0 - float(c.get("_distance", 0.5))
        cid = c.get("chunk_id") or c.get("id")
        if bm25_scores is not None:
            bm = float(bm25_scores.get(cid, 0.0))
        else:
            blob = " ".join([c.get("name") or "", c.get("file_path") or "", (c.get("code") or c.get("snippet") or "")])[:4000]
            bm = _keyword_score(query, blob)
        blended = (sem * (1.0 - alpha)) + (bm * alpha)
        c["_hybrid"] = blended
        reranked.append(c)
    reranked.sort(key=lambda x: x.get("_hybrid", 0.0), reverse=True)
    return reranked

def _jaccard_tokens(a: str, b: str) -> float:
    ta = set(re.findall(r"[A-Za-z_]\w+", a or "")[:])
    tb = set(re.findall(r"[A-Za-z_]\w+", b or "")[:])
    if not ta or not tb: return 0.0
    inter = len(ta & tb); union = len(ta | tb)
    return inter / union if union else 0.0

def apply_mmr(candidates: List[Dict], k: int, lambda_: float = 0.7, pool: Optional[int] = None) -> List[Dict]:
    if not candidates or k <= 0:
        return []
    pool_n = pool or min(len(candidates), k * 3)
    pool_items = candidates[:pool_n]
    selected: List[Dict] = []

    def rel(c):
        if "scores" in c and "semantic" in c["scores"]:
            return float(c["scores"]["semantic"])
        return 1.0 - float(c.get("_distance", 0.5))

    while pool_items and len(selected) < k:
        best = None
        best_score = -1.0
        for cand in pool_items:
            r = rel(cand)
            max_sim = 0.0
            for s in selected:
                sim = _jaccard_tokens(
                    (cand.get("snippet") or cand.get("code") or "")[:1000],
                    (s.get("snippet") or s.get("code") or "")[:1000]
                )
                if sim > max_sim:
                    max_sim = sim
            mmr_score = lambda_ * r - (1 - lambda_) * max_sim
            if mmr_score > best_score:
                best_score = mmr_score
                best = cand
        if best is None:
            break
        selected.append(best)
        pool_items.remove(best)
    return selected

async def function_entity_for_name(request, repo_id: str, func_name: str) -> Optional[Dict]:
    vector_store = request.app.state.vector_store
    safe_name = func_name.replace("'", "''")
    where = (
        f"repo_id = '{repo_id}' AND "
        f"(entity_type = 'function' OR entity_type = 'class') AND "
        f"name = '{safe_name}'"
    )
    exact = vector_store.query_where(where, limit=1)
    if exact:
        return exact[0]
    # fallback
    embedder = request.app.state.embedder
    import inspect as _inspect
    if _inspect.iscoroutinefunction(getattr(embedder, "embed_text", None)):
        emb = await embedder.embed_text(func_name)
    else:
        emb = embedder.embed_text(func_name)
    try:
        hits = vector_store.search(embedding=emb, k=1, filters={'repo_id': repo_id, 'entity_type': 'function'})
    except Exception:
        hits = []
    return hits[0] if hits else None

def build_callgraph_artifact(indexer, repo_id: str, selected_names: List[str], depth: int, direction: str = "forward") -> str:
    call_graph = indexer.call_graphs.get(repo_id) or {}
    if not call_graph: return ""
    nodes = call_graph.get("nodes") or []; edges = call_graph.get("edges") or []
    fwd = defaultdict(list); rev = defaultdict(list)
    for e in edges:
        if e.get("type") == "calls":
            s = e.get("source"); t = e.get("target"); fwd[s].append(t); rev[t].append(s)
    use = fwd if direction == "forward" else rev
    subs = {}; sube = []; q = deque([(n, 0) for n in selected_names]); seen = set(selected_names)
    for n in selected_names: subs[n] = {"id": n, "label": n, "type": "function"}
    while q:
        cur, d = q.popleft()
        if d >= depth: continue
        for nxt in use.get(cur, []):
            if direction == "forward": sube.append({"source": cur, "target": nxt, "type": "calls"})
            else: sube.append({"source": nxt, "target": cur, "type": "calls"})
            if nxt not in seen:
                seen.add(nxt); subs[nxt] = {"id": nxt, "label": nxt, "type": "function"}; q.append((nxt, d + 1))
    from ..diagramming.serializers import to_mermaid
    return to_mermaid({"nodes": list(subs.values()), "edges": sube}, kind="call")

def _retrieval_cache_key(repo_id: str, query: str, params: Dict[str, Any]) -> str:
    # Keep it readable and stable; include repo, query, and important params
    # We intentionally do not include agentic flags since we skip caching when agentic=True
    base = {
        "repo": repo_id,
        "query": query,
        "max_chunks": params.get("max_chunks"),
        "languages": params.get("languages"),
        "retrieval_mode": params.get("retrieval_mode"),
        "call_graph_depth": params.get("call_graph_depth"),
        "slice_target": params.get("slice_target"),
        "slice_direction": params.get("slice_direction"),
        "slice_depth": params.get("slice_depth"),
        "hybrid_alpha": params.get("hybrid_alpha_effective"),
    }
    return "repo:{repo}|ctx:{ctx}".format(
        repo=repo_id.replace("|", "_"),
        ctx=json.dumps(base, sort_keys=True)
    )

async def agentic_expand(
    request,
    repo_id: str,
    query: str,
    current_files: List[str],
    query_embedding: List[float],
    min_semantic: float,
    verify_files: bool,
    verify_symbols: bool
) -> Tuple[List[Dict], List[Dict]]:
    from ..integrations.llm_gateway import LLMGatewayClient
    llm = LLMGatewayClient()
    try:
        preview = "\n".join(f"- {f}" for f in current_files[:12] if f)
        messages = [
            {"role": "system", "content": "You are a code assistant optimizing retrieval. Reply with a short bullet list of file paths or symbols still needed. Only list items."},
            {"role": "user", "content": f"Task:\n{query}\n\nFiles so far:\n{preview}\n\nList additional items:"}
        ]
        resp = await llm.chat(messages=messages, temperature=0.2, max_tokens=120)
        content = (resp.get("content") or "")
    finally:
        await llm.close()

    wanted = []
    for line in content.splitlines():
        s = line.strip("- •\t ").strip()
        if s: wanted.append(s)

    vector_store = request.app.state.vector_store
    embedder = request.app.state.embedder
    import inspect as _inspect

    added: List[Dict] = []
    accepted_count = 0
    rejected_count = 0
    rejected_reasons: Dict[str, int] = defaultdict(int)
    accepted_items: List[str] = []
    rejected_items: List[str] = []

    def sem_ok(cand: Dict) -> bool:
        cand = _normalize_candidates([cand])[0]
        sem = 1.0 - float(cand.get("_distance", 0.5))
        return sem >= min_semantic

    for w in wanted[:10]:
        if "/" in w and "." in w:
            if verify_files:
                safe_fp = w.replace("'", "''")
                where = f"repo_id = '{repo_id}' AND entity_type = 'file' AND file_path = '{safe_fp}'"
                file_rows = vector_store.query_where(where, limit=1)
                if not file_rows:
                    rejected_count += 1
                    rejected_reasons["file_not_found"] += 1
                    rejected_items.append(w)
                    Metrics.inc("agentic_reject", {"reason": "file_not_found"})
                    continue
            try:
                if _inspect.iscoroutinefunction(getattr(embedder, "embed_text", None)):
                    emb = await embedder.embed_text(query)
                else:
                    emb = embedder.embed_text(query)
                local = vector_store.search(embedding=emb, k=3, filters={'repo_id': repo_id, 'entity_type': 'chunk', 'file_path': w})
            except Exception:
                local = []
            local = _normalize_candidates(local)
            accepted_here = 0
            for it in local[:3]:
                if sem_ok(it):
                    it["snippet"] = (it.get("code") or "")[:1200]
                    added.append(it); accepted_count += 1; accepted_here += 1
            if accepted_here == 0:
                rejected_reasons["semantic_below_threshold"] += 1
                rejected_items.append(w)
                Metrics.inc("agentic_reject", {"reason": "semantic_below_threshold"})
            else:
                accepted_items.append(w)
                Metrics.inc("agentic_accept", {"type": "file"})
        else:
            symbol_ok = True
            file_path_for_symbol: Optional[str] = None
            if verify_symbols:
                safe_name = w.replace("'", "''")
                where = f"repo_id = '{repo_id}' AND (entity_type = 'function' OR entity_type = 'class') AND name = '{safe_name}'"
                match = vector_store.query_where(where, limit=1)
                if match and match[0].get("file_path"):
                    file_path_for_symbol = match[0]["file_path"]
                else:
                    symbol_ok = False
            if not symbol_ok:
                if _inspect.iscoroutinefunction(getattr(embedder, "embed_text", None)):
                    embn = await embedder.embed_text(w)
                else:
                    embn = embedder.embed_text(w)
                try:
                    guess = vector_store.search(embedding=embn, k=1, filters={'repo_id': repo_id, 'entity_type': 'function'})
                except Exception:
                    guess = []
                if guess and guess[0].get("file_path"):
                    file_path_for_symbol = guess[0]["file_path"]
                else:
                    rejected_count += 1
                    rejected_reasons["symbol_not_found"] += 1
                    rejected_items.append(w)
                    Metrics.inc("agentic_reject", {"reason": "symbol_not_found"})
                    continue
            try:
                local = vector_store.search(embedding=query_embedding, k=2, filters={'repo_id': repo_id, 'entity_type': 'chunk', 'file_path': file_path_for_symbol})
            except Exception:
                local = []
            local = _normalize_candidates(local)
            accepted_here = 0
            for it in local[:2]:
                if sem_ok(it):
                    it["snippet"] = (it.get("code") or "")[:1200]
                    added.append(it); accepted_count += 1; accepted_here += 1
            if accepted_here == 0:
                rejected_reasons["semantic_below_threshold"] += 1
                rejected_items.append(w)
                Metrics.inc("agentic_reject", {"reason": "semantic_below_threshold"})
            else:
                accepted_items.append(w)
                Metrics.inc("agentic_accept", {"type": "symbol"})

    summary_lines = [
        f"Agentic suggestions: {len(wanted)}",
        f"Accepted chunks: {accepted_count}",
        f"Rejected suggestions: {rejected_count}"
    ]
    if rejected_reasons:
        summary_lines.append("Rejected reasons:")
        for k, v in rejected_reasons.items():
            summary_lines.append(f"- {k}: {v}")
    artifact = {
        "type": "agentic_summary",
        "label": "agentic_summary",
        "content": "\n".join(summary_lines)
    }

    return added, [
        {"type": "agentic", "label": "agentic_suggestions", "content": "\n".join(wanted)},
        artifact
    ]

async def dependency_neighbor_chunks(
    request,
    repo_id: str,
    query_embedding: List[float],
    base_files: List[str],
    depth: int,
    direction: str,
    neighbor_files_limit: int,
    per_file_neighbor_chunks: int,
    languages: Optional[List[str]]
) -> List[Dict[str, Any]]:
    indexer = request.app.state.indexer; vector_store = request.app.state.vector_store
    dep_graph = indexer.graphs.get(repo_id)
    if not dep_graph: return []
    neighbor_files: List[str] = []
    for f in base_files:
        try: deps = dep_graph.dependencies_of(f, depth=depth, direction=direction)
        except Exception: deps = {"imports": [], "imported_by": []}
        files = []
        if direction in ("imports", "both"): files.extend(deps.get("imports") or [])
        if direction in ("imported_by", "both"): files.extend(deps.get("imported_by") or [])
        for nf in files:
            if nf not in neighbor_files and nf not in base_files: neighbor_files.append(nf)
        if len(neighbor_files) >= neighbor_files_limit: break

    Metrics.observe("dep_neighbors_examined", len(neighbor_files), labels={"repo": repo_id})

    results = []
    for nf in neighbor_files[:neighbor_files_limit]:
        filters = {"repo_id": repo_id, "entity_type": "chunk", "file_path": nf}
        if languages and len(languages) > 0: filters["language"] = languages[0]
        try:
            local = vector_store.search(embedding=query_embedding, k=per_file_neighbor_chunks, filters=filters)
        except Exception:
            local = []
        local = _normalize_candidates(local)
        for it in local[:per_file_neighbor_chunks]:
            it["snippet"] = (it.get("code") or "")[:1200]
            results.append(it)

    Metrics.observe("dep_neighbor_chunks", len(results), labels={"repo": repo_id})
    return results

async def retrieve_chunks(
    request,
    repo_id: str,
    query: str,
    max_chunks: int,
    languages: Optional[List[str]] = None,
    retrieval_mode: str = "vector",
    call_graph_depth: int = 2,
    slice_target: Optional[str] = None,
    slice_direction: str = "forward",
    slice_depth: int = 2,
    hybrid_alpha: Optional[float] = None,
    agentic: bool = False,
    max_agentic_iters: int = 0
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, str]]:
    t0 = time.perf_counter()
    embedder = request.app.state.embedder
    vector_store = request.app.state.vector_store
    ranker = request.app.state.ranker
    indexer = request.app.state.indexer
    profile_store = RetrievalProfileStore()
    cache = getattr(request.app.state, "cache", None)

    prof = profile_store.load(repo_id)

    import inspect as _inspect
    if _inspect.iscoroutinefunction(getattr(embedder, "embed_text", None)):
        query_embedding = await embedder.embed_text(query)
    else:
        query_embedding = embedder.embed_text(query)

    filters = {"repo_id": repo_id, "entity_type": "chunk"}
    if languages and len(languages) > 0:
        filters["language"] = languages[0]

    artifacts: List[Dict[str, Any]] = []
    preferred_files: Set[str] = set()

    retrieval_mode = (retrieval_mode or "vector").lower()
    Metrics.inc("retrieval_calls", {"mode": retrieval_mode})

    # Effective hybrid alpha from profile if not provided
    eff_hybrid_alpha = hybrid_alpha if hybrid_alpha is not None else prof.hybrid_alpha
    # Build cache key
    cache_key = None
    if cache and settings.retrieval_cache_enabled and not agentic:
        cache_key = _retrieval_cache_key(repo_id, query, {
            "max_chunks": max_chunks,
            "languages": languages,
            "retrieval_mode": retrieval_mode,
            "call_graph_depth": call_graph_depth,
            "slice_target": slice_target,
            "slice_direction": slice_direction,
            "slice_depth": slice_depth,
            "hybrid_alpha_effective": eff_hybrid_alpha
        })
        cached = cache.get(cache_key)
        if cached:
            Metrics.inc("retrieval_cache_hit", {"repo": repo_id, "mode": retrieval_mode})
            return cached

    if retrieval_mode in ("callgraph", "slice"):
        call_graph = indexer.call_graphs.get(repo_id) or {}
        if retrieval_mode == "callgraph":
            if _inspect.iscoroutinefunction(getattr(embedder, "embed_text", None)):
                qf = await embedder.embed_text(query)
            else:
                qf = embedder.embed_text(query)
            func_candidates = vector_store.search(embedding=qf, k=max_chunks * 6, filters={"repo_id": repo_id, "entity_type": "function"})
            func_candidates = _normalize_candidates(func_candidates)
            sig_counts = (indexer.signature_counts or {}).get(repo_id, {}) if hasattr(indexer, "signature_counts") else {}
            func_candidates = _dedup_by_signature(func_candidates, sig_counts)
            if LocalReranker.available():
                func_candidates = LocalReranker.rerank(query, func_candidates, top_k=min(len(func_candidates), settings.reranker_topk))
            centrality = indexer.dependency_centrality.get(repo_id, {}) or {}
            comod = indexer.comodification_scores.get(repo_id, {}) or {}
            recency = indexer.git_recency.get(repo_id, {}) or {}
            orig_weights = ranker.weights.copy()
            try:
                if prof.weights:
                    ranker.weights = prof.weights
                ranked_funcs = ranker.rank(func_candidates, centrality, comod, recency)
            finally:
                ranker.weights = orig_weights
            for it in ranked_funcs[: max(3, max_chunks // 2)]:
                if it.get("file_path"):
                    preferred_files.add(it["file_path"])
            top_names = [it.get("name") for it in ranked_funcs[:5] if it.get("name")]
            mer = build_callgraph_artifact(indexer, repo_id, top_names, call_graph_depth, "forward")
            if mer:
                artifacts.append({"type": "mermaid", "label": "callgraph", "content": mer})
        else:
            seed = (slice_target or "").strip() or query
            ent = await function_entity_for_name(request, repo_id, seed)
            seed_name = ent.get("name") if ent else seed
            mer = build_callgraph_artifact(indexer, repo_id, [seed_name], slice_depth, slice_direction.lower())
            if mer:
                artifacts.append({"type": "mermaid", "label": f"slice({slice_direction})", "content": mer})
            if ent and ent.get("file_path"):
                preferred_files.add(ent["file_path"])

    k = (max_chunks or 8) * 4
    candidates = vector_store.search(embedding=query_embedding, k=k, filters=filters)
    candidates = _normalize_candidates(candidates)
    if preferred_files:
        for c in candidates:
            if c.get("file_path") in preferred_files:
                c["_distance"] = max(0.0, float(c.get("_distance", 0.5)) - 0.07)
    if LocalReranker.available():
        topk = min(len(candidates), settings.reranker_topk)
        head = LocalReranker.rerank(query, candidates[:topk], top_k=topk)
        candidates = head + candidates[topk:]

    bm25_map: Dict[str, float] = {}
    if settings.bm25_enabled:
        try:
            top_bm25 = query_bm25(repo_id, query, k=(max_chunks or 8) * 6, base_path=settings.lexical_index_path)
            if top_bm25:
                max_score = max(sc for _, sc in top_bm25) or 1.0
                for doc_id, sc in top_bm25:
                    bm25_map[doc_id] = float(sc) / float(max_score)
                present_ids = set((c.get("chunk_id") or c.get("id")) for c in candidates)
                add_count = 0
                for doc_id, _ in top_bm25:
                    if add_count >= (max_chunks or 8) * 2:
                        break
                    if doc_id in present_ids:
                        continue
                    extra = vector_store.get_by_id(doc_id)
                    if not extra:
                        continue
                    if extra.get("entity_type") != "chunk":
                        continue
                    extra["_distance"] = 0.5
                    extra["snippet"] = (extra.get("code") or "")[:1600]
                    candidates.append(extra)
                    present_ids.add(doc_id)
                    add_count += 1
        except Exception:
            pass

    candidates = _hybrid_rerank(candidates, query, alpha=eff_hybrid_alpha, bm25_scores=bm25_map if bm25_map else None)

    centrality = indexer.dependency_centrality.get(repo_id, {}) or {}
    comod = indexer.comodification_scores.get(repo_id, {}) or {}
    recency = indexer.git_recency.get(repo_id, {}) or {}
    orig_weights_main = ranker.weights.copy()
    try:
        if prof.weights:
            ranker.weights = prof.weights
        ranked = ranker.rank(candidates, centrality, comod, recency)
    finally:
        ranker.weights = orig_weights_main

    sig_counts = (indexer.signature_counts or {}).get(repo_id, {}) if hasattr(indexer, "signature_counts") else {}
    ranked = _dedup_by_signature(ranked, sig_counts)

    mmr_lambda = 0.7
    pool_n = min(len(ranked), (max_chunks or 8) * 3)
    mmr_selected = apply_mmr(ranked[:pool_n], k=max_chunks or 8, lambda_=mmr_lambda, pool=pool_n)

    seen_chunk_ids = set()
    top: List[Dict[str, Any]] = []
    conf_sum = 0.0
    snippet_len_sum = 0
    for it in mmr_selected:
        cid = it.get("chunk_id") or it.get("id")
        if not cid or cid in seen_chunk_ids: continue
        seen_chunk_ids.add(cid)
        it["snippet"] = (it.get("code") or "")[:1600]
        top.append(it)
        conf_sum += float(it.get("confidence", 0))
        snippet_len_sum += len(it.get("snippet") or "")
        if len(top) >= (max_chunks or 8): break

    eff_agentic_iters = max_agentic_iters or prof.agentic_max_iters or 0
    if agentic and eff_agentic_iters > 0:
        for iter_idx in range(eff_agentic_iters):
            before_files = set(fp for fp in (c.get("file_path") for c in top) if fp)
            before_chunks = len(top)
            selected_files = sorted(list(before_files))
            added, ag_artifacts = await agentic_expand(
                request,
                repo_id,
                query,
                selected_files,
                query_embedding,
                min_semantic=prof.agentic_min_semantic,
                verify_files=prof.agentic_verify_files,
                verify_symbols=prof.agentic_verify_symbols
            )
            if not added:
                artifacts.extend(ag_artifacts)
                break
            artifacts.extend(ag_artifacts)
            for a in added:
                a["_distance"] = max(0.0, float(a.get("_distance", 0.5)) - 0.03)
            merged = _normalize_candidates(top + added)
            orig_weights_loop = ranker.weights.copy()
            try:
                if prof.weights:
                    ranker.weights = prof.weights
                ranked2 = ranker.rank(merged, centrality, comod, recency)
            finally:
                ranker.weights = orig_weights_loop
            ranked2 = _dedup_by_signature(ranked2, sig_counts)
            mmr_selected2 = apply_mmr(ranked2[:pool_n], k=max_chunks or 8, lambda_=mmr_lambda, pool=pool_n)
            new_top = []
            seen_chunk_ids = set()
            conf_sum = 0.0
            snippet_len_sum = 0
            for it in mmr_selected2:
                cid = it.get("chunk_id") or it.get("id")
                if not cid or cid in seen_chunk_ids: continue
                seen_chunk_ids.add(cid)
                it["snippet"] = (it.get("code") or "")[:1600]
                new_top.append(it)
                conf_sum += float(it.get("confidence", 0))
                snippet_len_sum += len(it.get("snippet") or "")
                if len(new_top) >= (max_chunks or 8): break

            after_files = set(fp for fp in (c.get("file_path") for c in new_top) if fp)
            newly_added_files = len(after_files - before_files)
            gain_chunks = max(0, len(new_top) - before_chunks)
            gain_ratio = (gain_chunks / max(1, len(top))) if top else 1.0

            if newly_added_files < prof.agentic_min_new_files and gain_ratio < prof.agentic_gain_min_ratio:
                Metrics.inc("agentic_stop", {"reason": "low_gain"})
                top = new_top
                break

            top = new_top

    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    Metrics.observe("retrieval_latency_ms", elapsed_ms, labels={"mode": retrieval_mode, "repo": repo_id})
    Metrics.observe("retrieval_chunks", len(top), labels={"mode": retrieval_mode, "repo": repo_id})
    if top:
        avg_conf = conf_sum / max(1.0, len(top))
        Metrics.observe("retrieval_avg_confidence", avg_conf, labels={"mode": retrieval_mode, "repo": repo_id})
        Metrics.observe("retrieval_snippet_len_sum", snippet_len_sum, labels={"mode": retrieval_mode, "repo": repo_id})

    per_file_summaries: Dict[str, str] = {}
    selected_files = sorted(list({c.get("file_path") for c in top if c.get("file_path")}))
    for fp in selected_files:
        try:
            ents = request.app.state.vector_store.get_by_file(repo_id, fp)
        except Exception:
            ents = []
        cls = [e.get('name') for e in ents if e.get('entity_type') == 'class'][:8]
        fns = [e.get('name') for e in ents if e.get('entity_type') == 'function'][:12]
        per_file_summaries[fp] = f"File: {fp}\nClasses: {', '.join(cls) or '-'}\nFunctions: {', '.join(fns) or '-'}"

    # Cache the result if allowed
    if cache and settings.retrieval_cache_enabled and not agentic and cache_key:
        try:
            cache.set(cache_key, (top, artifacts, per_file_summaries), settings.retrieval_cache_ttl_sec)
        except Exception:
            pass

    return top, artifacts, per_file_summaries