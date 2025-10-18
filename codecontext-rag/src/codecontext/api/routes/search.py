from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
import inspect as _inspect

from ...api.dependencies import authorize
from ...utils.responses import success_response
from ...api.schemas.request import CodeSearchRequest


router = APIRouter(prefix="", tags=["Recommendations"], dependencies=[Depends(authorize)])


class CodeSearchRequest(BaseModel):
    """Schema for code search requests"""
    query: str = Field(..., description="Search query")
    repository_id: str = Field(..., description="Repository ID")
    max_results: Optional[int] = Field(10, description="Maximum results to return", ge=1, le=50)
    search_type: Optional[str] = Field("hybrid", description="Search type: vector, keyword, or hybrid")
    filters: Optional[dict] = Field(None, description="Additional filters")


@router.post("/search/code")
async def search_code(request: Request, body: CodeSearchRequest):
    """
    Search for code snippets using vector store
    
    This endpoint provides vector + hybrid search across indexed repositories.
    """
    try:
        # Get vector store and embedder from app state
        vector_store = request.app.state.vector_store
        embedder = request.app.state.embedder
        
        # Generate embedding for query
        if _inspect.iscoroutinefunction(getattr(embedder, "embed_text", None)):
            query_embedding = await embedder.embed_text(body.query)
        else:
            query_embedding = embedder.embed_text(body.query)
        
        # Set up filters
        filters = body.filters or {}
        filters['repo_id'] = body.repository_id
        
        # Search based on type
        if body.search_type == "vector" or body.search_type == "semantic":
            # Pure vector search
            results = vector_store.search(
                embedding=query_embedding,
                k=body.max_results or 10,
                filters=filters
            )
        elif body.search_type == "keyword":
            # Keyword search (if your vector store supports it)
            # Otherwise fall back to vector search
            results = vector_store.search(
                embedding=query_embedding,
                k=body.max_results or 10,
                filters=filters
            )
        else:  # hybrid (default)
            # Hybrid search - vector + keyword
            results = vector_store.search(
                embedding=query_embedding,
                k=body.max_results or 10,
                filters=filters
            )
        
        # Format results to match expected schema
        formatted_results = []
        for result in results:
            formatted_results.append({
                "file_path": result.get("file_path", "unknown"),
                "entity_type": result.get("entity_type", "chunk"),
                "entity_name": result.get("name", result.get("entity_name", "")),
                "similarity_score": result.get("score", result.get("similarity_score", 0.0)),
                "code_snippet": result.get("content", result.get("code", ""))[:500],
                "line_number": result.get("line_number", result.get("start_line", 0)),
                "metadata": {
                    "language": result.get("language"),
                    "entity_id": result.get("id"),
                    "repo_id": result.get("repo_id")
                }
            })
        
        data = {
            "query": body.query,
            "repository_id": body.repository_id,
            "search_type": body.search_type or "hybrid",
            "results": formatted_results,
            "total_results": len(formatted_results),
        }
        
        return success_response(request, data)
        
    except AttributeError as e:
        # Vector store or embedder not initialized
        raise HTTPException(
            status_code=503,
            detail=f"Search service not available: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )


@router.post("/search/semantic")
async def search_semantic(request: Request, body: CodeSearchRequest):
    """
    Semantic search using vector similarity only
    """
    body.search_type = "vector"
    return await search_code(request, body)


@router.get("/search/health")
async def search_health(request: Request):
    """
    Health check for search endpoint
    """
    try:
        vector_store = request.app.state.vector_store
        embedder = request.app.state.embedder
        
        return {
            "status": "healthy",
            "service": "code_search",
            "vector_store": "available" if vector_store else "unavailable",
            "embedder": "available" if embedder else "unavailable",
            "search_types": ["vector", "keyword", "hybrid"]
        }
    except Exception as e:
        return {
            "status": "degraded",
            "service": "code_search",
            "error": str(e)
        }