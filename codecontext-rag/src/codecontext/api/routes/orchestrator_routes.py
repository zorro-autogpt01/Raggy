"""
Orchestrator Routes - Integrated into existing service
Add to: src/codecontext/api/routes/orchestrator_routes.py
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import httpx
import asyncio
from datetime import datetime
import uuid

router = APIRouter(prefix="/api/orchestrate", tags=["orchestrator"])

# Configuration - all internal to same service
RUNNER_URL = "http://runner:8001"  # External runner service
RUNNER_API_KEY = "dev-runner-key-123"

# Models
class OrchestrateRequest(BaseModel):
    repo_id: str
    task_description: str
    context: Optional[Dict[str, Any]] = None

class ExecutionStep(BaseModel):
    step_id: str
    type: str  # 'branch_create', 'patch_apply', 'validate', 'branch_merge'
    status: str  # 'pending', 'running', 'success', 'failed'
    params: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: datetime

class OrchestrateResponse(BaseModel):
    execution_id: str
    status: str  # 'running', 'completed', 'failed'
    task_analysis: Dict[str, Any]
    strategy: Dict[str, Any]
    steps: List[ExecutionStep]
    final_result: Optional[Dict[str, Any]] = None
    started_at: datetime
    completed_at: Optional[datetime] = None

# In-memory execution store (replace with Redis/DB in production)
executions = {}


def get_task_analyzer():
    """Get task analyzer from app state"""
    from ...workflows.task_analyzer_impl import TaskAnalyzerImpl
    from fastapi import Request
    from ...api import app
    
    if not hasattr(app.state, 'task_analyzer'):
        app.state.task_analyzer = TaskAnalyzerImpl(
            llm_gateway_url="http://192.168.0.10:3010",
            rag_base_url="http://localhost:7998"
        )
    return app.state.task_analyzer


def get_strategy_selector():
    """Get strategy selector from app state"""
    from ...workflows.strategy_selector_impl import StrategySelector
    from ...api import app
    
    if not hasattr(app.state, 'strategy_selector'):
        app.state.strategy_selector = StrategySelector(
            llm_gateway_url="http://192.168.0.10:3010"
        )
    return app.state.strategy_selector


async def execute_step(step: ExecutionStep, repo_id: str) -> ExecutionStep:
    """Execute a single step via Runner service"""
    step.status = "running"
    step.timestamp = datetime.utcnow()
    
    try:
        async with httpx.AsyncClient() as client:
            if step.type == "branch_create":
                response = await client.post(
                    f"{RUNNER_URL}/branch/create",
                    params={
                        "repo_id": repo_id,
                        "branch_name": step.params["branch_name"],
                        "from_branch": step.params.get("from_branch", "main")
                    },
                    headers={"X-API-Key": RUNNER_API_KEY},
                    timeout=60.0
                )
                
            elif step.type == "patch_apply":
                response = await client.post(
                    f"{RUNNER_URL}/validate",
                    json={
                        "repo_id": repo_id,
                        "branch": step.params.get("branch", "main"),
                        "patch": step.params["patch"],
                        "targets": step.params.get("targets", [])
                    },
                    headers={"X-API-Key": RUNNER_API_KEY},
                    timeout=300.0
                )
                
            elif step.type == "validate":
                response = await client.post(
                    f"{RUNNER_URL}/validate",
                    json={
                        "repo_id": repo_id,
                        "branch": step.params.get("branch", "main"),
                        "patch": "",  # Just validate existing code
                        "targets": step.params.get("targets", [])
                    },
                    headers={"X-API-Key": RUNNER_API_KEY},
                    timeout=300.0
                )
                
            elif step.type == "branch_merge":
                response = await client.post(
                    f"{RUNNER_URL}/branch/merge",
                    params={
                        "repo_id": repo_id,
                        "source": step.params["source_branch"],
                        "target": step.params.get("target_branch", "main")
                    },
                    headers={"X-API-Key": RUNNER_API_KEY},
                    timeout=120.0
                )
            
            else:
                raise ValueError(f"Unknown step type: {step.type}")
            
            response.raise_for_status()
            step.result = response.json()
            step.status = "success"
            
    except Exception as e:
        step.status = "failed"
        step.error = str(e)
    
    return step


async def execute_strategy(execution_id: str, repo_id: str, strategy: Dict):
    """Execute the selected strategy steps"""
    execution = executions[execution_id]
    
    try:
        # Generate execution steps based on strategy
        steps = []
        
        strategy_type = strategy.get("strategy", "unknown")
        
        if strategy_type == "direct" or strategy["recommended_strategy"] == "Strategy A: Simple Patch":
            # Single patch application
            steps.append(ExecutionStep(
                step_id=f"{execution_id}-step-1",
                type="patch_apply",
                status="pending",
                params={
                    "branch": "main",
                    "patch": strategy.get("patch", "# TODO: Generate patch"),
                    "targets": strategy.get("affected_files", [])
                },
                timestamp=datetime.utcnow()
            ))
            
        elif "multi" in strategy_type.lower() or strategy["recommended_strategy"] == "Strategy B: Multi-Patch":
            # Multiple patches in sequence on main
            patches = strategy.get("patches", [])
            for i, patch in enumerate(patches, 1):
                steps.append(ExecutionStep(
                    step_id=f"{execution_id}-step-{i}",
                    type="patch_apply",
                    status="pending",
                    params={
                        "branch": "main",
                        "patch": patch,
                        "targets": strategy.get("affected_files", [])
                    },
                    timestamp=datetime.utcnow()
                ))
                
        elif "branch" in strategy_type.lower() or strategy["recommended_strategy"] == "Strategy C: Branch-Based":
            # Create branch
            branch_name = f"fix/{execution_id[:8]}"
            steps.append(ExecutionStep(
                step_id=f"{execution_id}-step-1",
                type="branch_create",
                status="pending",
                params={
                    "branch_name": branch_name,
                    "from_branch": "main"
                },
                timestamp=datetime.utcnow()
            ))
            
            # Apply patches on branch
            patches = strategy.get("patches", [])
            for i, patch in enumerate(patches, 2):
                steps.append(ExecutionStep(
                    step_id=f"{execution_id}-step-{i}",
                    type="patch_apply",
                    status="pending",
                    params={
                        "branch": branch_name,
                        "patch": patch,
                        "targets": strategy.get("affected_files", [])
                    },
                    timestamp=datetime.utcnow()
                ))
            
            # Merge branch back
            steps.append(ExecutionStep(
                step_id=f"{execution_id}-step-merge",
                type="branch_merge",
                status="pending",
                params={
                    "source_branch": branch_name,
                    "target_branch": "main"
                },
                timestamp=datetime.utcnow()
            ))
        
        execution.steps = steps
        
        # Execute steps sequentially
        for step in execution.steps:
            step = await execute_step(step, repo_id)
            
            # Stop on failure unless strategy allows continuation
            if step.status == "failed" and not strategy.get("continue_on_failure", False):
                execution.status = "failed"
                execution.completed_at = datetime.utcnow()
                return
        
        # All steps completed successfully
        execution.status = "completed"
        execution.final_result = {
            "success": True,
            "message": f"Successfully executed {strategy_type}",
            "steps_completed": len([s for s in execution.steps if s.status == "success"]),
            "total_steps": len(execution.steps)
        }
        
    except Exception as e:
        execution.status = "failed"
        execution.final_result = {"success": False, "error": str(e)}
    
    finally:
        execution.completed_at = datetime.utcnow()


@router.post("/execute", response_model=OrchestrateResponse)
async def orchestrate_execution(
    request: OrchestrateRequest,
    task_analyzer=Depends(get_task_analyzer),
    strategy_selector=Depends(get_strategy_selector)
):
    """
    Main orchestration endpoint - coordinates entire workflow
    
    Steps:
    1. Analyze task (internal)
    2. Select strategy (internal)
    3. Execute strategy (via Runner)
    4. Return results
    """
    execution_id = str(uuid.uuid4())
    
    print(f"[{execution_id}] Starting orchestration for: {request.task_description}")
    
    try:
        # Step 1: Analyze the task (internal call)
        print(f"[{execution_id}] Analyzing task...")
        task_analysis_result = await task_analyzer.analyze_task(
            repo_id=request.repo_id,
            task_description=request.task_description,
            context=request.context or {}
        )
        
        if not task_analysis_result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Task analysis failed: {task_analysis_result.get('error')}"
            )
        
        task_analysis = task_analysis_result["analysis"]
        
        # Step 2: Select strategy (internal call)
        print(f"[{execution_id}] Selecting strategy...")
        strategy_result = await strategy_selector.select_strategy(task_analysis)
        
        if not strategy_result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=f"Strategy selection failed: {strategy_result.get('error')}"
            )
        
        strategy = strategy_result["strategy_decision"]
        
        # Create execution record
        execution = OrchestrateResponse(
            execution_id=execution_id,
            status="running",
            task_analysis=task_analysis,
            strategy=strategy,
            steps=[],
            started_at=datetime.utcnow()
        )
        executions[execution_id] = execution
        
        # Step 3: Execute strategy asynchronously
        print(f"[{execution_id}] Executing {strategy.get('strategy', 'unknown')} strategy...")
        asyncio.create_task(execute_strategy(execution_id, request.repo_id, strategy))
        
        return execution
        
    except Exception as e:
        print(f"[{execution_id}] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{execution_id}", response_model=OrchestrateResponse)
async def get_execution_status(execution_id: str):
    """Get execution status"""
    if execution_id not in executions:
        raise HTTPException(status_code=404, detail="Execution not found")
    
    return executions[execution_id]


@router.get("/executions", response_model=List[OrchestrateResponse])
async def list_executions(limit: int = 10):
    """List recent executions"""
    sorted_executions = sorted(
        executions.values(),
        key=lambda x: x.started_at,
        reverse=True
    )
    return sorted_executions[:limit]


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "orchestrator",
        "active_executions": len([e for e in executions.values() if e.status == "running"]),
        "total_executions": len(executions)
    }