# codecontext-rag/src/codecontext/api/routes/webhooks.py

from fastapi import APIRouter, Request, HTTPException, Header, BackgroundTasks
from typing import Optional
import hmac
import hashlib
import json

from ...utils.logging import get_logger
from ...indexing.incremental import IncrementalIndexer

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])
logger = get_logger(__name__)

def verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub Hub webhook signature"""
    if not signature or not secret:
        return False
    
    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256
    ).hexdigest()
    
    expected_sig = f"sha256={expected}"
    return hmac.compare_digest(expected_sig, signature)

@router.post("/github-hub")
async def github_hub_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_ghh_signature: Optional[str] = Header(None, alias="X-GHH-Signature-256"),
    x_ghh_event: Optional[str] = Header(None, alias="X-GHH-Event"),
):
    """
    Receive webhook notifications from GitHub Hub
    
    Automatically triggers incremental indexing when changes are detected
    """
    
    # Get webhook secret from settings
    from ...config import settings
    webhook_secret = getattr(settings, 'github_hub_webhook_secret', None)
    
    # Read raw body for signature verification
    body = await request.body()
    
    # Verify signature if secret is configured
    if webhook_secret:
        if not verify_signature(body, x_ghh_signature, webhook_secret):
            logger.warning("Invalid webhook signature")
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    # Parse event payload
    try:
        event = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    event_type = event.get("type") or x_ghh_event
    
    if event_type == "ping":
        logger.info("Received ping from GitHub Hub")
        return {"ok": True, "message": "pong"}
    
    if event_type == "repo.push":
        # Extract change information
        repo_info = event.get("repository", {})
        connection = event.get("connection", {})
        branch = event.get("branch")
        files = event.get("files", [])
        
        # Find matching repository
        repo_store = request.app.state.repo_store
        
        # Match by connection_id
        conn_id = connection.get("id")
        matching_repos = [
            r for r in repo_store.list()
            if r.get("connection_id") == conn_id and r.get("branch") == branch
        ]
        
        if not matching_repos:
            logger.warning(f"No matching repository found for connection {conn_id}, branch {branch}")
            return {"ok": True, "message": "No matching repository"}
        
        for repo in matching_repos:
            repo_id = repo["id"]
            
            # Extract changed file paths
            changed_files = [f["filename"] for f in files if f.get("filename")]
            
            if not changed_files:
                logger.info(f"No file changes detected for {repo_id}")
                continue
            
            logger.info(f"Repository {repo_id} changed: {len(changed_files)} files")
            
            # Trigger incremental indexing in background
            background_tasks.add_task(
                trigger_incremental_index,
                request=request,
                repo_id=repo_id,
                changed_files=changed_files
            )
        
        return {"ok": True, "triggered": len(matching_repos)}
    
    return {"ok": True, "message": f"Unhandled event type: {event_type}"}

async def trigger_incremental_index(
    request: Request,
    repo_id: str,
    changed_files: list[str]
):
    """Background task to trigger incremental indexing"""
    try:
        indexer = request.app.state.indexer
        repo_store = request.app.state.repo_store
        
        logger.info(f"Starting incremental index for {repo_id} with {len(changed_files)} files")
        
        result = await indexer.incremental_index(
            repo_id=repo_id,
            changed_files=changed_files
        )
        
        logger.info(f"Incremental index completed: {result}")
        
    except Exception as e:
        logger.error(f"Incremental indexing failed for {repo_id}: {e}", exc_info=True)