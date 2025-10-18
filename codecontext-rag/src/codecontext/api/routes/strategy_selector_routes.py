"""
Strategy Selector API Routes
Endpoints for strategy selection decisions
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Optional
import os

from ..schemas.strategy_selector_models import (
    StrategySelectionRequest,
    StrategySelectionResponse,
    StrategyType,
    DECISION_RULES
)
from ..schemas.task_analyzer_models import TaskAnalysisRequest
from ...workflows.strategy_selector_impl import StrategySelector
from ...workflows.task_analyzer_impl import TaskAnalyzer


# Create router
router = APIRouter(prefix="/api/strategy", tags=["Strategy Selection"])

# Configuration
LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:3010")
RAG_API_URL = os.getenv("RAG_API_URL", "http://localhost:8000")


def get_strategy_selector(request: Request) -> StrategySelector:
    """Get or create StrategySelector instance"""
    if not hasattr(request.app.state, 'strategy_selector'):
        request.app.state.strategy_selector = StrategySelector()
    return request.app.state.strategy_selector


def get_task_analyzer(request: Request) -> TaskAnalyzer:
    """Get or create TaskAnalyzer instance from app state"""
    if not hasattr(request.app.state, 'task_analyzer'):
        # Create and cache it
        request.app.state.task_analyzer = TaskAnalyzer(
            llm_gateway_url=LLM_GATEWAY_URL,
            rag_api_url=RAG_API_URL,
            model="gpt-4o-mini"
        )
    return request.app.state.task_analyzer


@router.post("/select", response_model=StrategySelectionResponse)
async def select_strategy(
    request: StrategySelectionRequest,
    selector: StrategySelector = Depends(get_strategy_selector)
):
    """
    Select execution strategy based on task analysis
    
    Takes the output from task analysis and decides whether to use
    direct commit or branch-based workflow.
    
    Example request:
    ```json
    {
      "task_type": "feature",
      "complexity": "low",
      "impact": "isolated",
      "estimated_file_count": 2,
      "is_breaking_change": false,
      "needs_database_migration": false,
      "confidence_score": 0.9,
      "repo_id": "myrepo",
      "task_description": "Add hello world endpoint"
    }
    ```
    
    Example response:
    ```json
    {
      "success": true,
      "decision": {
        "strategy": "direct",
        "confidence": 0.85,
        "primary_reason": "simple_change",
        "rules_applied": ["direct_low_impact"],
        "estimated_risk_level": "low",
        "explanation": "...",
        "recommendation": "✅ Safe for direct commit..."
      }
    }
    ```
    """
    result = selector.select_strategy(request)
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    return result


@router.post("/analyze-and-select")
async def analyze_and_select(
    request: TaskAnalysisRequest,
    task_analyzer: TaskAnalyzer = Depends(get_task_analyzer),
    selector: StrategySelector = Depends(get_strategy_selector)
):
    """
    Combined endpoint: Analyze task AND select strategy in one call
    
    This is a convenience endpoint that combines task analysis
    and strategy selection into a single API call.
    
    Example request:
    ```json
    {
      "repo_id": "myrepo",
      "task_description": "Add OAuth2 authentication with Google"
    }
    ```
    
    Example response:
    ```json
    {
      "analysis": {
        "task_type": "feature",
        "complexity": "high",
        ...
      },
      "strategy_decision": {
        "strategy": "branch",
        "confidence": 0.9,
        ...
      }
    }
    ```
    """
    # Step 1: Analyze the task
    analysis_result = await task_analyzer.analyze(request, use_rag_context=True)
    
    if not analysis_result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Task analysis failed: {analysis_result.error}"
        )
    
    analysis = analysis_result.analysis
    
    # Step 2: Select strategy based on analysis
    selection_request = StrategySelectionRequest(
        task_type=analysis.task_type.value,
        complexity=analysis.complexity.value,
        impact=analysis.impact.value,
        estimated_file_count=analysis.estimated_file_count,
        is_breaking_change=analysis.is_breaking_change,
        needs_database_migration=analysis.needs_database_migration,
        confidence_score=analysis.confidence_score,
        repo_id=request.repo_id,
        task_description=request.task_description
    )
    
    strategy_result = selector.select_strategy(selection_request)
    
    if not strategy_result.success:
        raise HTTPException(
            status_code=500,
            detail=f"Strategy selection failed: {strategy_result.error}"
        )
    
    return {
        "success": True,
        "analysis": analysis.dict(),
        "strategy_decision": strategy_result.decision.dict(),
        "recommended_approach": _get_approach_description(strategy_result.decision.strategy)
    }


@router.get("/rules")
async def list_decision_rules():
    """
    List all decision rules used by the strategy selector
    
    Useful for understanding how decisions are made and debugging.
    
    Example response:
    ```json
    {
      "total_rules": 10,
      "rules": [
        {
          "name": "force_branch_breaking",
          "condition": "is_breaking_change == True",
          "suggested_strategy": "branch",
          "priority": 10,
          "reasoning": "Breaking changes must go through branch workflow..."
        },
        ...
      ]
    }
    ```
    """
    return {
        "total_rules": len(DECISION_RULES),
        "rules": [rule.dict() for rule in DECISION_RULES],
        "priority_scale": "1 (lowest) to 10 (highest)"
    }


@router.post("/explain")
async def explain_decision(
    request: StrategySelectionRequest,
    selector: StrategySelector = Depends(get_strategy_selector)
):
    """
    Get detailed explanation of why a particular strategy was chosen
    
    Same as /select but with more verbose explanation and debugging info.
    
    Example response includes:
    - All rules that were evaluated
    - Which rules matched
    - Score breakdown (direct vs branch)
    - Alternative strategies considered
    - Risk assessment details
    """
    result = selector.select_strategy(request)
    
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error)
    
    decision = result.decision
    
    return {
        "decision": decision.dict(),
        "debug_info": {
            "rules_evaluated": len(DECISION_RULES),
            "rules_matched": decision.rules_considered,
            "rules_applied": decision.rules_applied,
            "confidence_breakdown": {
                "strategy_confidence": decision.confidence,
                "task_analysis_confidence": request.confidence_score
            },
            "risk_assessment": {
                "level": decision.estimated_risk_level,
                "factors": decision.risk_factors
            },
            "alternative_considered": {
                "strategy": decision.alternative_strategy,
                "reasoning": decision.alternative_reasoning
            } if decision.alternative_strategy else None
        }
    }


@router.get("/health")
async def strategy_selector_health():
    """
    Check if strategy selector is working
    
    Returns health status and configuration info
    """
    return {
        "status": "healthy",
        "total_rules": len(DECISION_RULES),
        "strategies_available": ["direct", "branch"],
        "version": "1.0.0"
    }


def _get_approach_description(strategy: StrategyType) -> str:
    """Get human-readable description of the approach"""
    
    if strategy == StrategyType.DIRECT:
        return """
**Direct Commit Approach (Strategy A)**

1. Generate patch with LLM
2. Validate in sandbox (syntax + build + execution)
3. If validation fails, use LLM to fix and retry
4. Commit directly to main branch
5. Push to remote

Best for: Simple, isolated changes with low risk
        """.strip()
    else:
        return """
**Branch-Based Approach (Strategy C)**

1. Create feature branch
2. Generate multiple patches sequentially
3. Validate each patch in sandbox
4. Commit each validated patch to branch
5. Run comprehensive tests
6. Merge to main with squash (after review)

Best for: Complex changes, multiple files, or high-risk modifications
        """.strip()