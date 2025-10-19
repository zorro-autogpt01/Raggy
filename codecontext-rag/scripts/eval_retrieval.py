
#!/usr/bin/env python3
import argparse
import json
import httpx
from typing import List, Dict, Any
import math

def precision_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    topk = retrieved[:k]
    rel = set(relevant)
    hits = sum(1 for f in topk if f in rel)
    return hits / max(1, min(k, len(retrieved)))

def recall_at_k(retrieved: List[str], relevant: List[str], k: int) -> float:
    topk = set(retrieved[:k])
    rel = set(relevant)
    hits = len(topk & rel)
    return hits / max(1, len(rel))

def reciprocal_rank(retrieved: List[str], relevant: List[str]) -> float:
    rel = set(relevant)
    for i, f in enumerate(retrieved, 1):
        if f in rel:
            return 1.0 / i
    return 0.0

async def eval_dataset(api_base: str, dataset: List[Dict[str, Any]], k: int, timeout: float = 20.0):
    p_sum = 0.0; r_sum = 0.0; rr_sum = 0.0; n = 0
    async with httpx.AsyncClient(timeout=timeout) as client:
        for item in dataset:
            repo_id = item["repo_id"]; query = item["query"]; relevant = item["relevant_files"]
            payload = {
                "query": query,
                "max_chunks": k,
                "expand_neighbors": False,
                "retrieval_mode": "vector"
            }
            # call /repositories/{repo_id}/context
            url = f"{api_base}/repositories/{repo_id}/context"
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json().get("data") or {}
            chunks = data.get("chunks") or []
            retrieved_files = [c.get("file_path") for c in chunks if c.get("file_path")]
            p = precision_at_k(retrieved_files, relevant, k)
            r = recall_at_k(retrieved_files, relevant, k)
            rr = reciprocal_rank(retrieved_files, relevant)
            p_sum += p; r_sum += r; rr_sum += rr; n += 1
            print(f"[{repo_id}] '{query[:50]}' P@{k}={p:.3f} R@{k}={r:.3f} RR={rr:.3f}")
    print("----")
    if n > 0:
        print(f"AVG P@{k}: {p_sum/n:.3f}")
        print(f"AVG R@{k}: {r_sum/n:.3f}")
        print(f"MRR: {rr_sum/n:.3f}")
    else:
        print("No samples evaluated")

def main():
    parser = argparse.ArgumentParser(description="Offline retrieval evaluation")
    parser.add_argument("--api-base", default="http://localhost:8000", help="API base URL (e.g., http://localhost:7998)")
    parser.add_argument("--dataset", required=True, help="Path to JSON dataset with [{repo_id,query,relevant_files:[...]}, ...]")
    parser.add_argument("--k", type=int, default=8, help="Top-k")
    args = parser.parse_args()
    with open(args.dataset, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    import asyncio
    asyncio.run(eval_dataset(args.api_base.rstrip("/"), dataset, args.k))

if __name__ == "__main__":
    main()
