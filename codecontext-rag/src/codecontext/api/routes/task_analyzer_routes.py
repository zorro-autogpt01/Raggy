"""
Task Analyzer API Routes
Follows the standard pattern used in other route modules
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional
import os
from pydantic import BaseModel

from ..schemas.task_analyzer_models import (
    TaskAnalysisRequest,
    TaskAnalysisResponse
)
from ...workflows.task_analyzer_impl import TaskAnalyzer


class QuickClassifyRequest(BaseModel):
    """Request for quick classification"""
    task_description: str
    repo_id: Optional[str] = None

# Create router following the standard pattern
router = APIRouter(prefix="/api/analyze", tags=["Task Analysis"])

# Configuration from environment
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:3010")
RAG_API_URL = os.getenv("RAG_API_URL", "http://localhost:8000")




def get_task_analyzer(request: Request) -> TaskAnalyzer:
    """
    Get or create TaskAnalyzer instance using app state
    
    This follows the dependency injection pattern used in other routes
    """
    # Check if we already have one in app state
    if not hasattr(request.app.state, 'task_analyzer'):
        # Create and cache it
        request.app.state.task_analyzer = TaskAnalyzer(
            llm_gateway_url=LLM_GATEWAY_URL,
            rag_api_url=RAG_API_URL,
            model="gpt-4o-mini"
        )
    
    return request.app.state.task_analyzer


@router.post("/task", response_model=TaskAnalysisResponse)
async def analyze_task(
    request: TaskAnalysisRequest,
    task_analyzer: TaskAnalyzer = Depends(get_task_analyzer)
):
    """
    Analyze a task to determine scope, complexity, and strategy
    
    This endpoint:
    1. Takes a task description
    2. Queries RAG for relevant context
    3. Uses LLM to analyze the task
    4. Suggests direct vs branch-based strategy
    
    Example request:
    ```json
    {
      "repo_id": "myrepo",
      "task_description": "Add a new API endpoint for user profile updates",
      "additional_context": "Should support partial updates"
    }
    ```
    
    Example response:
    ```json
    {
      "success": true,
      "analysis": {
        "task_type": "feature",
        "complexity": "low",
        "impact": "isolated",
        "files_to_modify": [
          {
            "path": "src/api/users.py",
            "reason": "Add new endpoint handler",
            "change_type": "modify",
            "estimated_lines_changed": 25
          }
        ],
        "estimated_file_count": 1,
        "summary": "Add PATCH endpoint to users API",
        "confidence_score": 0.9
      },
      "suggested_strategy": "direct"
    }
    ```
    """
    result = await task_analyzer.analyze(request, use_rag_context=True)
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return result


@router.post("/quick-classify")
async def quick_classify_task(
    request: QuickClassifyRequest,  # ← Changed this line
    task_analyzer: TaskAnalyzer = Depends(get_task_analyzer)
):
    """
    Quickly classify a task without full analysis
    
    Useful for fast UI feedback or routing decisions.
    Returns basic classification in under 2 seconds.
    
    Example:
    ```bash
    curl -X POST http://localhost:8000/api/analyze/quick-classify \
      -H "Content-Type: application/json" \
      -d '{"task_description": "Fix the login bug"}'
    ```
    
    Response:
    ```json
    {
      "type": "fix",
      "complexity": "low",
      "strategy": "direct"
    }
    ```
    """
    result = await task_analyzer.quick_classify(request.task_description)  # ← And this line
    return result


@router.get("/health")
async def task_analyzer_health():
    """
    Check if task analyzer is working
    
    Tests connectivity to LLM gateway
    """
    import httpx
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{LLM_GATEWAY_URL}/health",
                timeout=5.0
            )
            llm_healthy = response.status_code == 200
    except:
        llm_healthy = False
    
    return {
        "status": "healthy" if llm_healthy else "degraded",
        "llm_gateway": LLM_GATEWAY_URL,
        "llm_healthy": llm_healthy,
        "rag_available": RAG_API_URL is not None
    }