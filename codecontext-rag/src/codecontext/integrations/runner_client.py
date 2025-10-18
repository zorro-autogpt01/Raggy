# src/codecontext/integrations/runner_client.py
"""
Client for Test Runner Service
"""
import httpx
from typing import Dict, Optional
from ..config import settings
from ..api.schemas.execution_models import ExecutionConfig  # ADD THIS LINE


class RunnerClient:
    """Client for interacting with Test Runner"""
    

    def __init__(self, base_url: str = None):
        self.base_url = base_url or settings.runner_url
        
        # Add API key header
        headers = {}
        if hasattr(settings, 'runner_api_key') and settings.runner_api_key:
            headers["X-API-Key"] = settings.runner_api_key
        
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=120.0,
            headers=headers
        )
    
    async def trigger_validation(
        self,
        repo_id: str,
        repo_url: str,
        branch: str,
        patch: str,
        commit_message: str,
        execution_config: Optional[ExecutionConfig] = None  # NEW parameter
    ) -> Dict:
        """
        Trigger validation run on runner
        
        Returns: {"run_id": "...", "status": "started"}
        """
        payload = {
            "repo_id": repo_id,
            "repo_url": repo_url,
            "branch": branch,
            "patch": patch,
            "commit_message": commit_message
        }
        
        # Add execution config if provided
        if execution_config:
            payload["execution"] = execution_config.dict()
        
        response = await self.client.post("/validate", json=payload)
        response.raise_for_status()
        return response.json()
    
    async def get_validation_status(self, run_id: str) -> Dict:
        """
        Get status of validation run
        
        Returns: {
            "run_id": "...",
            "status": "running|completed|failed|error",
            "attempts": 2,
            "result": {...}
        }
        """
        response = await self.client.get(f"/validate/{run_id}")
        response.raise_for_status()
        return response.json()
    
    async def validate_patch(
        self,
        repo_id: str,
        repo_url: str,
        patch: str,
        commit_message: str,
        execution_config: Optional[ExecutionConfig] = None
    ) -> dict:
        """Submit validation request to runner"""
        
        payload = {
            "repo_id": repo_id,
            "repo_url": repo_url,
            "patch": patch,
            "commit_message": commit_message
        }
        
        # Add execution config if provided
        if execution_config:
            payload["execution"] = execution_config.dict()
        
        # Send request
        response = await self.client.post("/validate", json=payload)
        response.raise_for_status()
        return response.json()

    async def wait_for_validation(
        self,
        run_id: str,
        timeout: int = 600,
        poll_interval: int = 5
    ) -> Dict:
        """
        Poll validation status until completion or timeout
        """
        import asyncio
        
        elapsed = 0
        while elapsed < timeout:
            status = await self.get_validation_status(run_id)
            
            if status['status'] in ('completed', 'failed', 'error'):
                return status
            
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
        
        raise TimeoutError(f"Validation {run_id} did not complete in {timeout}s")
    
    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()