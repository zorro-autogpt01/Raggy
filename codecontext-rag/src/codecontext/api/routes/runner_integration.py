# src/codecontext/api/routes/runner_integration.py
"""
API routes for runner integration
"""
from fastapi import APIRouter, Depends, HTTPException, Request
import httpx
from ...utils.logging import get_logger
from pydantic import BaseModel
from typing import Optional
from .dependencies import authorize
from ...utils.responses import success_response
from ...integrations.runner_client import RunnerClient
from ...integrations.execution_analyzer import ExecutionStrategyAnalyzer
from ...api.schemas.execution_models import ExecutionConfig

#router = APIRouter(prefix="/runner", tags=["Runner Integration"], dependencies=[Depends(authorize)])
router = APIRouter(prefix="/runner", tags=["Runner Integration"])
logger = get_logger(__name__)


class TriggerValidationRequest(BaseModel):
    """Request to trigger validation on runner"""
    repo_id: str
    patch: str
    commit_message: str
    branch: Optional[str] = "main"
    wait_for_completion: bool = False
    # NEW: Optional - allow manual execution config override
    execution_config: Optional[ExecutionConfig] = None
    # NEW: Optional - disable automatic execution analysis
    skip_execution_analysis: bool = False


@router.post("/validate")
async def trigger_validation(request: Request, body: TriggerValidationRequest):
    """
    Trigger validation run on test runner
    
    This endpoint now includes intelligent execution strategy analysis:
    - Automatically analyzes the code change
    - Uses LLM to determine best execution strategy
    - Sends appropriate execution config to runner
    
    If wait_for_completion=True, this will block until validation completes
    """
    repo_store = request.app.state.repo_store
    vector_store = request.app.state.vector_store
    runner_client = RunnerClient()
    
    try:
        # Get repository details
        repo = repo_store.get(body.repo_id)
        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")
        
        # Get authenticated clone URL from GitHub Hub
        connection_id = repo.get('connection_id')
        if not connection_id:
            raise HTTPException(
                status_code=400,
                detail="Repository has no connection_id for authentication"
            )
        
        # Fetch authenticated clone URL from GitHub Hub
        from ...config import settings
        async with httpx.AsyncClient(timeout=10.0) as client:
            clone_response = await client.get(
                f"{settings.github_hub_url}/api/connections/{connection_id}/clone_url"
            )
            
            if clone_response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"Could not get authenticated clone URL: {clone_response.text}"
                )
            
            clone_data = clone_response.json()
            authenticated_repo_url = clone_data.get("clone_url")
        
        if not authenticated_repo_url:
            raise HTTPException(
                status_code=400,
                detail="Failed to obtain authenticated clone URL"
            )
        
        # NEW: Determine execution configuration
        execution_config = None
        
        if body.execution_config:
            # User provided explicit config - use it
            execution_config = body.execution_config
        elif not body.skip_execution_analysis:
            # Automatically analyze and generate execution config
            try:
                # Initialize analyzer
                from ...config import settings
                analyzer = ExecutionStrategyAnalyzer(
                    llm_gateway_url=settings.llm_gateway_url,
                    repo_store=repo_store,
                    vector_store=vector_store
                )
                
                # Extract files changed from patch (simple extraction)
                files_changed = extract_files_from_patch(body.patch)
                
                # Analyze and generate execution config
                execution_config = await analyzer.analyze_and_generate_config(
                    repo_id=body.repo_id,
                    patch=body.patch,
                    files_changed=files_changed,
                    commit_message=body.commit_message
                )
                
                # Log what strategy was chosen
                if execution_config and execution_config.enabled:
                    logger.info(
                        f"Execution strategy for {body.repo_id}: {execution_config.strategy} "
                        f"(reason: {execution_config.description})"
                    )
            
            except Exception as e:
                # Don't fail validation if execution analysis fails
                logger.warning(
                    f"Execution analysis failed for {body.repo_id}: {e}. "
                    "Continuing with validation only."
                )
                execution_config = None
        
        # Trigger validation (now with optional execution config)
        trigger_result = await runner_client.trigger_validation(
            repo_id=body.repo_id,
            repo_url=authenticated_repo_url,
            branch=body.branch,
            patch=body.patch,
            commit_message=body.commit_message,
            execution_config=execution_config  # NEW: Pass execution config
        )
        
        run_id = trigger_result['run_id']
        
        # If wait for completion, poll until done
        if body.wait_for_completion:
            final_status = await runner_client.wait_for_validation(run_id)
            
            data = {
                "run_id": run_id,
                "completed": True,
                "status": final_status['status'],
                "result": final_status.get('result'),
                "attempts": final_status.get('attempts'),
                "execution_result": final_status.get('result', {}).get('execution')  # NEW
            }
        else:
            data = {
                "run_id": run_id,
                "completed": False,
                "status": "started",
                "message": "Validation started in background. Poll /runner/validate/{run_id} for status.",
                "execution_enabled": execution_config.enabled if execution_config else False  # NEW
            }
        
        return success_response(request, data)
    
    finally:
        await runner_client.close()


@router.get("/validate/{run_id}")
async def get_validation_status(request: Request, run_id: str):
    """Get status of validation run"""
    
    runner_client = RunnerClient()
    
    try:
        status = await runner_client.get_validation_status(run_id)
        return success_response(request, status)
    
    finally:
        await runner_client.close()


# Helper function
def extract_files_from_patch(patch: str) -> list[str]:
    """Extract file paths from unified diff patch"""
    import re
    
    files = []
    
    # Look for lines like: +++ b/path/to/file.py
    for line in patch.split('\n'):
        if line.startswith('+++') or line.startswith('---'):
            # Extract file path after b/ or a/
            match = re.search(r'[ab]/(.+?)(?:\s|$)', line)
            if match:
                filepath = match.group(1)
                if filepath != '/dev/null':  # Ignore null device
                    files.append(filepath)
    
    return list(set(files))  # Remove duplicates