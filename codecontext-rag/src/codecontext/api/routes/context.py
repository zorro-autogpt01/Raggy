from fastapi import APIRouter, Depends, HTTPException, Request, Response
from typing import List, Dict, Tuple, Set, Optional
import uuid
import inspect as _inspect

from ...api.dependencies import authorize
from ...utils.responses import success_response
from ...api.schemas.request import ContextRequest
from ...diagramming.serializers import to_mermaid
from ...core.reranker import LocalReranker
from ...integrations.llm_gateway import LLMGatewayClient
from ...config import settings

# Unified retrieval
from ...core.retrieval import retrieve_chunks

router = APIRouter(prefix="/repositories", tags=["Context"], dependencies=[Depends(authorize)])

@router.post("/{repo_id}/context")
async def get_minimal_context(
    request: Request,
    repo_id: str,
    body: ContextRequest,
    response: Response
):
    session_id = str(uuid.uuid4())
    request.state.request_id = session_id

    embedder = request.app.state.embedder
    vector_store = request.app.state.vector_store
    ranker = request.app.state.ranker
    indexer = request.app.state.indexer

    max_chunks = body.max_chunks or 8
    artifacts: List[Dict] = []

    retrieval_mode = (body.retrieval_mode or "vector").lower()

    # Use unified retrieval
    try:
        base_chunks, base_artifacts, _ = await retrieve_chunks(
            request=request,
            repo_id=repo_id,
            query=body.query,
            max_chunks=max_chunks,
            languages=(body.filters.languages if body.filters and body.filters.languages else None),
            retrieval_mode=retrieval_mode,
            call_graph_depth=body.call_graph_depth or 2,
            slice_target=body.slice_target,
            slice_direction=(body.slice_direction or "forward"),
            slice_depth=body.slice_depth or 2,
            hybrid_alpha=0.2,
            agentic=getattr(body, "agentic", settings.agentic_default),
            max_agentic_iters=getattr(body, "max_agentic_iters", settings.agentic_max_iters)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retrieval failed: {str(e)}")

    artifacts.extend(base_artifacts)

    # Format results for response (mimic original shape)
    seen_chunk_ids = set()
    results = []
    for item in base_chunks:
        file_path = item.get('file_path'); chunk_id = item.get('chunk_id') or item.get('id')
        if not file_path or not chunk_id: continue
        if chunk_id in seen_chunk_ids: continue
        seen_chunk_ids.add(chunk_id)
        snippet = (item.get('snippet') or item.get('code') or '')[:1200]
        results.append({
            'file_path': file_path,
            'start_line': int(item.get('start_line') or 0),
            'end_line': int(item.get('end_line') or 0),
            'language': item.get('language') or 'unknown',
            'snippet': snippet,
            'confidence': int(item.get('confidence', 0)),
            'reasons': item.get('reasons', []),
            'distance': float(item.get('_distance', 0.5))
        })
        if len(results) >= max_chunks: break

    # Optional local file neighbor expansion (original behavior)
    if body.expand_neighbors and results:
        expanded = list(results)
        for r in results:
            if len(expanded) >= max_chunks: break
            file_entities = vector_store.get_by_file(repo_id, r['file_path'])
            file_chunks = [e for e in file_entities if e.get('entity_type') == 'chunk']
            def proximity_score(e):
                s = int(e.get('start_line') or 0); center = (r['start_line'] + r['end_line']) // 2
                return abs(s - center)
            file_chunks.sort(key=proximity_score)
            for ch in file_chunks[:2]:
                ch_id = ch.get('chunk_id') or ch.get('id')
                if ch_id in seen_chunk_ids: continue
                seen_chunk_ids.add(ch_id)
                expanded.append({
                    'file_path': ch.get('file_path'),
                    'start_line': int(ch.get('start_line') or 0),
                    'end_line': int(ch.get('end_line') or 0),
                    'language': ch.get('language') or 'unknown',
                    'snippet': (ch.get('code') or '')[:1000],
                    'confidence': int(ch.get('confidence', 0)),
                    'reasons': ch.get('reasons', []),
                    'distance': float(ch.get('_distance', 0.5))
                })
                if len(expanded) >= max_chunks: break
        results = expanded[:max_chunks]

    data = {
        'query': body.query,
        'chunks': results,
        'summary': {
            'total_chunks': len(results),
            'avg_confidence': sum(r['confidence'] for r in results) / max(1, len(results)),
            'retrieval_mode': retrieval_mode
        },
        'artifacts': artifacts
    }
    return success_response(request, data, response)

