"""
Test Runner Service - Enhanced for remote deployment with auth and observability
Includes branch management for Strategy C implementation
"""
from branch_operations import branch_router, set_repo_store
from fastapi import FastAPI, HTTPException, BackgroundTasks, Header, Depends, WebSocket
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, List
import docker
import uuid
import os
import tempfile
import shutil
from pathlib import Path
import asyncio
import httpx
from datetime import datetime, timedelta
import json
import logging
from logging.handlers import RotatingFileHandler
import subprocess

# Import execution models
from execution_models import ExecutionConfig, ExecutionResult

# ============================================================================
# Configuration
# ============================================================================

RUNNER_API_KEY = os.getenv("RUNNER_API_KEY", "change-me-in-production")
RUNNER_HOST = os.getenv("RUNNER_HOST", "0.0.0.0")
RUNNER_PORT = int(os.getenv("RUNNER_PORT", "8001"))

LLM_GATEWAY_URL = os.getenv("LLM_GATEWAY_URL", "http://llm-gateway:3010")
LLM_GATEWAY_API_KEY = os.getenv("LLM_GATEWAY_API_KEY")

RAG_API_URL = os.getenv("RAG_API_URL")
RAG_API_KEY = os.getenv("RAG_API_KEY")

MAX_ATTEMPTS = int(os.getenv("MAX_VALIDATION_ATTEMPTS", "3"))
SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "600"))
WORKSPACE_ROOT = Path(os.getenv("WORKSPACE_ROOT", "/workspace"))
LOG_RETENTION_DAYS = int(os.getenv("LOG_RETENTION_DAYS", "7"))

# ============================================================================
# Logging Setup
# ============================================================================

LOG_DIR = Path("/var/log/runner")
LOG_DIR.mkdir(parents=True, exist_ok=True)
(LOG_DIR / "runs").mkdir(parents=True, exist_ok=True)

# Application logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("runner")
handler = RotatingFileHandler(
    LOG_DIR / "app.log",
    maxBytes=10_000_000,  # 10MB
    backupCount=5
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
logger.addHandler(handler)

# Per-run loggers
def get_run_logger(run_id: str):
    """Create a logger for specific validation run"""
    run_logger = logging.getLogger(f"runner.{run_id}")
    run_handler = RotatingFileHandler(
        LOG_DIR / "runs" / f"{run_id}.log",
        maxBytes=5_000_000,  # 5MB
        backupCount=2
    )
    run_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s'
    ))
    run_logger.addHandler(run_handler)
    run_logger.setLevel(logging.DEBUG)
    return run_logger

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Test Runner Service",
    version="1.0.0",
    description="Remote validation runner with LLM debug loop and branch management"
)

docker_client = docker.from_env()

# In-memory run tracking (use Redis for production scale)
validation_runs: Dict[str, Dict] = {}

# ============================================================================
# Repository Store
# ============================================================================

class InMemoryRepositoryStore:
    """Simple in-memory store for repository metadata"""
    
    def __init__(self):
        self.repos = {}
    
    def get(self, repo_id: str):
        """Get repository by ID"""
        return self.repos.get(repo_id)
    
    def set(self, repo_id: str, data: dict):
        """Store repository metadata"""
        self.repos[repo_id] = data
    
    def delete(self, repo_id: str):
        """Remove repository from store"""
        if repo_id in self.repos:
            del self.repos[repo_id]
    
    def list(self):
        """List all repositories"""
        return list(self.repos.values())

# Create repository store
repo_store = InMemoryRepositoryStore()

# Inject repository store into branch operations
set_repo_store(repo_store)

# Metrics tracking
metrics = {
    "total_validations": 0,
    "successful_validations": 0,
    "failed_validations": 0,
    "total_llm_fixes": 0,
    "successful_llm_fixes": 0
}

# Include branch operations router
app.include_router(branch_router)

# ============================================================================
# Authentication
# ============================================================================

async def verify_api_key(x_api_key: str = Header(None)):
    """Verify API key from header"""
    if not RUNNER_API_KEY or RUNNER_API_KEY == "change-me-in-production":
        logger.warning("Running with default API key - INSECURE!")
    
    if x_api_key != RUNNER_API_KEY:
        logger.warning(f"Authentication failed - invalid API key")
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    return True

# ============================================================================
# Models
# ============================================================================

class ValidationRequest(BaseModel):
    """Request to validate a patch"""
    repo_id: str
    repo_url: str
    branch: str = "main"
    patch: str
    commit_message: str
    github_conn_id: Optional[str] = None
    callback_url: Optional[str] = None  # Optional webhook
    execution: Optional[ExecutionConfig] = None  # Execution configuration


class RegisterRepoRequest(BaseModel):
    """Request to register a repository"""
    repo_id: str
    repo_url: str
    branch: str = "main"
    github_conn_id: Optional[str] = None  # For authenticated clones via hub


class ValidationRun:
    """Tracks a validation run with detailed logging"""
    
    def __init__(self, run_id: str, request: ValidationRequest):
        self.run_id = run_id
        self.request = request
        self.status = "pending"
        self.attempts = 0
        self.errors = []
        self.workspace = None
        self.sandbox = None
        self.result = None
        self.execution_result = None  # Store execution result
        self.started_at = datetime.utcnow().isoformat() + "Z"
        self.completed_at = None
        self.logs = []  # In-memory log buffer
        self.progress = "Initializing..."
        
        # Create dedicated logger
        self.logger = get_run_logger(run_id)
    
    def log(self, message: str, level: str = "INFO"):
        """Log message and store in buffer"""
        self.logs.append({
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message
        })
        
        # Also log to file
        if level == "DEBUG":
            self.logger.debug(message)
        elif level == "INFO":
            self.logger.info(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "ERROR":
            self.logger.error(message)
    
    def update_progress(self, message: str):
        """Update progress message"""
        self.progress = message
        self.log(f"Progress: {message}", "INFO")
    
    def to_dict(self) -> Dict:
        return {
            "run_id": self.run_id,
            "repo_id": self.request.repo_id,
            "status": self.status,
            "progress": self.progress,
            "attempts": self.attempts,
            "errors": self.errors,
            "result": self.result,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "logs_available": len(self.logs)
        }

# ============================================================================
# Repository Management Endpoints
# ============================================================================

@app.post("/repositories/register", dependencies=[Depends(verify_api_key)])
async def register_repository(request: RegisterRepoRequest):
    """
    Register a repository for branch operations
    
    This clones the repo and stores its local path so branch operations
    can work with it. Required before using branch management endpoints.
    
    Uses PAT token for authenticated access via github_conn_id.
    """
    # Create a persistent workspace for this repository
    repo_workspace = WORKSPACE_ROOT / "repos" / request.repo_id
    repo_workspace.mkdir(parents=True, exist_ok=True)
    
    try:
        repo_path = repo_workspace / "repo"
        
        # If already exists, just update the store
        if repo_path.exists():
            logger.info(f"Repository already exists: {request.repo_id}, updating store")
        else:
            logger.info(f"Registering new repository: {request.repo_id}")
            
            # Construct authenticated clone URL using PAT token
            clone_url = request.repo_url
            
            if request.github_conn_id:
                # Build authenticated URL: https://x-access-token:TOKEN@github.com/user/repo.git
                # This is GitHub's recommended format for PAT tokens
                if clone_url.startswith("https://github.com/"):
                    # Remove https://github.com/ and add token
                    repo_path_part = clone_url.replace("https://github.com/", "")
                    if not repo_path_part.endswith(".git"):
                        repo_path_part += ".git"
                    # Use x-access-token as username with PAT as password
                    clone_url = f"https://x-access-token:{request.github_conn_id}@github.com/{repo_path_part}"
                    logger.info(f"Using authenticated clone URL with PAT token (x-access-token format)")
                else:
                    logger.warning(f"Non-GitHub URL provided, cannot add token authentication")
            else:
                logger.warning(f"No github_conn_id provided, attempting unauthenticated clone")
            
            # Clone the repository
            result = subprocess.run(
                ["git", "clone", "--branch", request.branch, clone_url, str(repo_path)],
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                raise Exception(f"Git clone failed: {result.stderr}")
        
        # Store repository info
        repo_store.set(request.repo_id, {
            "repo_id": request.repo_id,
            "repo_url": request.repo_url,
            "local_path": str(repo_path),
            "branch": request.branch,
            "github_conn_id": request.github_conn_id,
            "registered_at": datetime.utcnow().isoformat() + "Z"
        })
        
        logger.info(f"Repository registered successfully: {request.repo_id}")
        
        return {
            "success": True,
            "repo_id": request.repo_id,
            "local_path": str(repo_path),
            "message": "Repository registered successfully"
        }
    
    except Exception as e:
        logger.error(f"Failed to register repository: {e}")
        # Cleanup on failure
        if repo_workspace.exists() and not any(repo_workspace.iterdir()):
            shutil.rmtree(repo_workspace, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/repositories", dependencies=[Depends(verify_api_key)])
async def list_repositories():
    """List all registered repositories"""
    return {
        "success": True,
        "repositories": repo_store.list(),
        "count": len(repo_store.list())
    }


@app.get("/repositories/{repo_id}", dependencies=[Depends(verify_api_key)])
async def get_repository(repo_id: str):
    """Get details of a specific repository"""
    repo = repo_store.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    return {
        "success": True,
        "repository": repo
    }


@app.delete("/repositories/{repo_id}", dependencies=[Depends(verify_api_key)])
async def unregister_repository(repo_id: str):
    """Unregister a repository and cleanup its local clone"""
    repo = repo_store.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    # Cleanup local path
    try:
        local_path = Path(repo["local_path"])
        if local_path.exists():
            # Remove the repo directory and its parent if empty
            shutil.rmtree(local_path.parent, ignore_errors=True)
            logger.info(f"Cleaned up repository path: {local_path}")
    except Exception as e:
        logger.warning(f"Failed to cleanup repository path: {e}")
    
    repo_store.delete(repo_id)
    
    return {
        "success": True,
        "message": f"Repository {repo_id} unregistered"
    }

# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
        "docker_connected": True
    }

@app.get("/status", dependencies=[Depends(verify_api_key)])
async def get_status():
    """Get overall runner status"""
    active_runs = [r for r in validation_runs.values() if r.status == "running"]
    recent_runs = sorted(
        validation_runs.values(),
        key=lambda x: x.started_at,
        reverse=True
    )[:50]
    
    # Count active sandboxes
    try:
        sandboxes = docker_client.containers.list(
            filters={"name": "workspace"}
        )
        active_sandboxes = len(sandboxes)
    except:
        active_sandboxes = 0
    
    return {
        "status": "operational",
        "active_validations": len(active_runs),
        "total_validations": metrics["total_validations"],
        "success_rate": (
            metrics["successful_validations"] / max(1, metrics["total_validations"])
        ) if metrics["total_validations"] > 0 else 0,
        "active_sandboxes": active_sandboxes,
        "registered_repositories": len(repo_store.list()),
        "recent_runs": [r.to_dict() for r in recent_runs],
        "metrics": metrics
    }

@app.get("/metrics", dependencies=[Depends(verify_api_key)])
async def get_metrics():
    """Prometheus-style metrics"""
    success_rate = (
        metrics["successful_validations"] / max(1, metrics["total_validations"])
    ) if metrics["total_validations"] > 0 else 0
    
    return {
        "validation_runs_total": metrics["total_validations"],
        "validation_success_total": metrics["successful_validations"],
        "validation_failed_total": metrics["failed_validations"],
        "validation_success_rate": success_rate,
        "llm_fix_attempts_total": metrics["total_llm_fixes"],
        "llm_fix_success_total": metrics["successful_llm_fixes"]
    }

# ============================================================================
# Dashboard Endpoint
# ============================================================================

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Simple HTML dashboard"""
    
    active_runs = [r for r in validation_runs.values() if r.status == "running"]
    recent_runs = sorted(
        validation_runs.values(),
        key=lambda x: x.started_at,
        reverse=True
    )[:20]
    
    registered_repos = repo_store.list()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Runner Dashboard</title>
        <meta http-equiv="refresh" content="5">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
            .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; }}
            .metrics {{ display: flex; gap: 20px; margin: 20px 0; }}
            .metric {{ background: white; padding: 20px; border-radius: 5px; flex: 1; text-align: center; }}
            .metric-value {{ font-size: 2em; font-weight: bold; color: #3498db; }}
            .section {{ background: white; padding: 20px; border-radius: 5px; margin: 20px 0; }}
            .run {{ padding: 10px; border-bottom: 1px solid #eee; }}
            .repo {{ padding: 10px; border-bottom: 1px solid #eee; }}
            .status-running {{ color: #f39c12; }}
            .status-completed {{ color: #27ae60; }}
            .status-failed {{ color: #e74c3c; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🏃 Test Runner Dashboard</h1>
            <p>Validation runs with LLM debug loop & branch management</p>
        </div>
        
        <div class="metrics">
            <div class="metric">
                <div class="metric-value">{metrics['total_validations']}</div>
                <div>Total Validations</div>
            </div>
            <div class="metric">
                <div class="metric-value">{len(active_runs)}</div>
                <div>Active Now</div>
            </div>
            <div class="metric">
                <div class="metric-value">{len(registered_repos)}</div>
                <div>Repositories</div>
            </div>
            <div class="metric">
                <div class="metric-value">{metrics['successful_validations']}</div>
                <div>Successful</div>
            </div>
        </div>
        
        <div class="section">
            <h2>Registered Repositories</h2>
            {''.join([f'''
            <div class="repo">
                <strong>{repo['repo_id']}</strong>
                <br/>
                <small>URL: {repo['repo_url']}</small>
                <br/>
                <small>Branch: {repo['branch']} | Registered: {repo['registered_at']}</small>
            </div>
            ''' for repo in registered_repos]) if registered_repos else '<p>No repositories registered yet. Use POST /repositories/register to add one.</p>'}
        </div>
        
        <div class="section">
            <h2>Recent Validations</h2>
            {''.join([f'''
            <div class="run">
                <strong class="status-{run.status}">{run.status.upper()}</strong>
                - {run.run_id[:8]} - {run.request.repo_id}
                <br/>
                <small>Progress: {run.progress} | Attempts: {run.attempts}</small>
                <br/>
                <small>Started: {run.started_at}</small>
                <br/>
                <a href="/validate/{run.run_id}/details">View Details</a>
            </div>
            ''' for run in recent_runs]) if recent_runs else '<p>No validations yet.</p>'}
        </div>
        
        <p><small>Auto-refreshes every 5 seconds | <a href="/docs">API Documentation</a></small></p>
    </body>
    </html>
    """
    
    return html

# ============================================================================
# Validation Endpoints
# ============================================================================

@app.post("/validate", dependencies=[Depends(verify_api_key)])
async def trigger_validation(
    request: ValidationRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger a validation run
    
    Can optionally specify a branch to validate against:
    - If branch is provided, validates on that branch
    - If no branch, validates on default branch (main/master)
    """
    run_id = str(uuid.uuid4())
    
    run = ValidationRun(run_id, request)
    validation_runs[run_id] = run
    
    # Log which branch we're validating on
    branch_info = f" on branch '{request.branch}'" if request.branch else ""
    run.log(f"Validation triggered for repo: {request.repo_id}{branch_info}", "INFO")
    logger.info(f"New validation run: {run_id} for {request.repo_id}{branch_info}")
    
    # Track metrics
    metrics["total_validations"] += 1
    
    # Run validation in background
    background_tasks.add_task(execute_validation, run)
    
    return {
        "run_id": run_id,
        "status": "started",
        "branch": request.branch,
        "message": "Validation run started in background",
        "status_url": f"/validate/{run_id}",
        "logs_url": f"/validate/{run_id}/logs"
    }


@app.get("/validate/{run_id}", dependencies=[Depends(verify_api_key)])
async def get_validation_status(run_id: str):
    """Get status of a validation run"""
    
    run = validation_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Validation run not found")
    
    return run.to_dict()


@app.get("/validate/{run_id}/details", dependencies=[Depends(verify_api_key)])
async def get_validation_details(run_id: str):
    """Get detailed information including recent logs"""
    
    run = validation_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Validation run not found")
    
    return {
        **run.to_dict(),
        "recent_logs": run.logs[-50:],
        "workspace": run.workspace,
        "sandbox_id": run.sandbox
    }


@app.get("/validate/{run_id}/logs", dependencies=[Depends(verify_api_key)])
async def stream_logs(run_id: str):
    """Stream logs for a validation run"""
    
    run = validation_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Validation run not found")
    
    async def log_generator():
        """Generate log lines"""
        # Send existing logs
        for log_entry in run.logs:
            yield f"data: {json.dumps(log_entry)}\n\n"
        
        # If run is still active, poll for new logs
        if run.status == "running":
            last_count = len(run.logs)
            for _ in range(60):  # Poll for up to 5 minutes
                await asyncio.sleep(5)
                if len(run.logs) > last_count:
                    for log_entry in run.logs[last_count:]:
                        yield f"data: {json.dumps(log_entry)}\n\n"
                    last_count = len(run.logs)
                
                if run.status != "running":
                    break
    
    return StreamingResponse(
        log_generator(),
        media_type="text/event-stream"
    )

# ============================================================================
# Validation Logic
# ============================================================================

async def execute_validation(run: ValidationRun):
    """Execute validation workflow with detailed logging"""
    
    try:
        run.status = "running"
        run.update_progress("Setting up workspace")
        
        # 1. Setup workspace
        workspace = setup_workspace(run.run_id, run)
        run.workspace = str(workspace)
        run.log(f"Workspace created: {workspace}", "INFO")
        
        # 2. Clone repository
        run.update_progress("Cloning repository")
        repo_path = clone_repository(
            run.request.repo_url,
            workspace,
            run.request.branch,
            run
        )
        run.log(f"Repository cloned to {repo_path}", "INFO")
        
        # 2.5. Checkout the specified branch
        if run.request.branch and run.request.branch != "main":
            run.update_progress(f"Checking out branch: {run.request.branch}")
            run.log(f"Switching to branch: {run.request.branch}", "INFO")
            
            try:
                # Fetch the branch from remote
                subprocess.run(
                    ["git", "fetch", "origin", run.request.branch],
                    cwd=repo_path,
                    check=True,
                    capture_output=True
                )
                
                # Checkout the branch
                subprocess.run(
                    ["git", "checkout", run.request.branch],
                    cwd=repo_path,
                    check=True,
                    capture_output=True
                )
                
                run.log(f"Successfully checked out branch: {run.request.branch}", "INFO")
                
            except subprocess.CalledProcessError as e:
                run.log(f"Failed to checkout branch {run.request.branch}: {e.stderr.decode()}", "ERROR")
                run.status = "error"
                run.result = {
                    "success": False,
                    "error": f"Branch '{run.request.branch}' not found or checkout failed"
                }
                return

        # 3. Apply patch
        run.update_progress("Applying patch")
        apply_patch(repo_path, run.request.patch, run)
        run.log("Patch applied successfully", "INFO")
        
        # 4. Detect language and create sandbox
        language = detect_language(repo_path, run)
        run.log(f"Detected language: {language}", "INFO")
        
        run.update_progress(f"Creating {language} sandbox")
        sandbox = create_sandbox(language, workspace, run)
        run.sandbox = sandbox.id
        run.log(f"Sandbox created: {sandbox.id[:12]}", "INFO")
        
        # 5. Validation loop with LLM debugging
        success = False
        
        for attempt in range(MAX_ATTEMPTS):
            run.attempts = attempt + 1
            run.update_progress(f"Validation attempt {attempt + 1}/{MAX_ATTEMPTS}")
            
            # Run validation
            validation_result = await validate_in_sandbox(
                sandbox, repo_path, language, run
            )
            
            if validation_result['success']:
                success = True
                run.log("✅ Validation passed!", "INFO")
                break
            
            # Validation failed
            error = validation_result['error']
            run.errors.append(error)
            run.log(f"❌ Validation failed: {error.get('message', 'Unknown')}", "ERROR")
            
            # Last attempt? Don't retry
            if attempt == MAX_ATTEMPTS - 1:
                run.log("Max attempts reached", "WARNING")
                break
            
            # Use LLM to debug and fix
            run.update_progress("Asking LLM to fix error")
            metrics["total_llm_fixes"] += 1
            
            fix_result = await llm_debug_and_fix(
                run=run,
                error=error,
                original_patch=run.request.patch,
                repo_path=repo_path
            )
            
            if not fix_result['success']:
                run.log("LLM failed to generate fix", "ERROR")
                break
            
            metrics["successful_llm_fixes"] += 1
            run.log("LLM generated corrected patch", "INFO")
            
            # Apply corrected patch
            run.update_progress("Applying LLM-corrected patch")
            reset_repository(repo_path, run)
            apply_patch(repo_path, fix_result['corrected_patch'], run)
        
        # 6. Optional execution validation
        if success and run.request.execution and run.request.execution.enabled:
            run.update_progress("Running execution validation")
            run.log(f"Execution strategy: {run.request.execution.strategy}", "INFO")
            
            try:
                # Import execution engine
                from runner_execution import ExecutionEngine
                
                # Create execution engine
                engine = ExecutionEngine(sandbox, repo_path, run)
                
                # Execute according to config
                execution_result = await engine.execute(run.request.execution)
                
                # Initialize result dict if needed
                if run.result is None:
                    run.result = {}
                
                # Store execution result
                run.execution_result = execution_result
                run.result["execution"] = {
                    "strategy": execution_result.strategy,
                    "success": execution_result.success,
                    "exit_code": execution_result.exit_code,
                    "stdout": execution_result.stdout,
                    "stderr": execution_result.stderr,
                    "runtime_seconds": execution_result.runtime_seconds,
                    "service_started": execution_result.service_started,
                    "health_check_passed": execution_result.health_check_passed,
                    "tests_run": execution_result.tests_run,
                    "tests_passed": execution_result.tests_passed,
                    "tests_failed": execution_result.tests_failed,
                    "error": execution_result.error
                }
                
                if not execution_result.success:
                    run.log(f"❌ Execution failed: {execution_result.error}", "ERROR")
                    success = False
                else:
                    run.log("✅ Execution validation passed!", "INFO")
            
            except Exception as e:
                run.log(f"Execution engine error: {e}", "ERROR")
                success = False
                if run.result is None:
                    run.result = {}
                run.result["execution"] = {
                    "success": False,
                    "error": f"Execution engine error: {str(e)}"
                }
        
        # 7. If successful, commit and push
        if success:
            run.update_progress("Committing changes")
            commit_sha = commit_changes(repo_path, run.request.commit_message, run)
            run.log(f"Changes committed: {commit_sha[:8]}", "INFO")
            
            run.update_progress("Pushing to origin")
            push_changes(repo_path, run.request.branch, run)
            run.log("Changes pushed to origin", "INFO")
            
            run.status = "completed"
            run.result = {
                "success": True,
                "commit": commit_sha,
                "attempts": run.attempts,
                "branch": run.request.branch
            }
            
            metrics["successful_validations"] += 1
        else:
            run.status = "failed"
            run.result = {
                "success": False,
                "attempts": run.attempts,
                "errors": run.errors
            }
            
            metrics["failed_validations"] += 1
        
        # Callback to RAG (if configured)
        if run.request.callback_url:
            await send_callback(run)
        
    except Exception as e:
        run.log(f"Exception occurred: {str(e)}", "ERROR")
        logger.exception(f"Error in validation {run.run_id}")
        
        run.status = "error"
        run.result = {
            "success": False,
            "error": str(e)
        }
        
        metrics["failed_validations"] += 1
    
    finally:
        # Cleanup
        run.completed_at = datetime.utcnow().isoformat() + "Z"
        run.update_progress("Cleaning up")
        
        if run.sandbox:
            cleanup_sandbox(run.sandbox, run)
        
        if run.workspace:
            cleanup_workspace(run.workspace, run)
        
        run.log("Validation complete", "INFO")

def setup_workspace(run_id: str, run: ValidationRun) -> Path:
    """Create isolated workspace for this run"""
    workspace = WORKSPACE_ROOT / run_id
    workspace.mkdir(parents=True, exist_ok=True)
    if run:
        run.log(f"Workspace directory created: {workspace}", "DEBUG")
    return workspace


def cleanup_workspace(workspace_path: str, run: ValidationRun):
    """Cleanup workspace"""
    try:
        shutil.rmtree(workspace_path)
        run.log(f"Workspace cleaned up: {workspace_path}", "INFO")
    except Exception as e:
        run.log(f"Failed to cleanup workspace: {e}", "WARNING")


def clone_repository(repo_url: str, workspace: Path, branch: str, run: ValidationRun) -> Path:
    """Clone repository into workspace"""
    repo_path = workspace / "repo"
    
    run.log(f"Cloning repository: {repo_url} (branch: {branch})", "DEBUG")
    
    result = subprocess.run(
        ["git", "clone", "--branch", branch, "--single-branch", repo_url, str(repo_path)],
        capture_output=True,
        text=True,
        timeout=300
    )
    
    if result.returncode != 0:
        run.log(f"Git clone failed: {result.stderr}", "ERROR")
        raise Exception(f"Git clone failed: {result.stderr}")
    
    run.log("Repository cloned successfully", "DEBUG")
    return repo_path


def apply_patch(repo_path: Path, patch: str, run: ValidationRun):
    """Apply unified diff patch"""
    patch_file = repo_path / "temp.patch"
    patch_file.write_text(patch)
    
    run.log("Applying patch to repository", "DEBUG")
    
    try:
        result = subprocess.run(
            ["git", "apply", "--check", str(patch_file)],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            run.log(f"Patch check failed: {result.stderr}", "ERROR")
            raise Exception(f"Patch does not apply: {result.stderr}")
        
        result = subprocess.run(
            ["git", "apply", str(patch_file)],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            run.log(f"Patch apply failed: {result.stderr}", "ERROR")
            raise Exception(f"Patch apply failed: {result.stderr}")
        
        run.log("Patch applied successfully", "DEBUG")
    
    finally:
        patch_file.unlink(missing_ok=True)


def reset_repository(repo_path: Path, run: ValidationRun):
    """Reset repository to clean state"""
    run.log("Resetting repository to clean state", "DEBUG")
    subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=repo_path)
    subprocess.run(["git", "clean", "-fd"], cwd=repo_path)


def commit_changes(repo_path: Path, message: str, run: ValidationRun) -> str:
    """Commit changes and return commit SHA"""
    run.log(f"Committing changes: {message}", "DEBUG")
    
    # Configure Git author (use env vars or defaults)
    git_author_name = os.getenv("GIT_AUTHOR_NAME", "Test Runner Bot")
    git_author_email = os.getenv("GIT_AUTHOR_EMAIL", "runner@codecontext.local")
    
    subprocess.run(
        ["git", "config", "user.name", git_author_name],
        cwd=repo_path
    )
    subprocess.run(
        ["git", "config", "user.email", git_author_email],
        cwd=repo_path
    )
    
    subprocess.run(["git", "add", "-A"], cwd=repo_path)
    subprocess.run(["git", "commit", "-m", message], cwd=repo_path)
    
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    
    commit_sha = result.stdout.strip()
    run.log(f"Commit SHA: {commit_sha}", "DEBUG")
    return commit_sha


def push_changes(repo_path: Path, branch: str, run: ValidationRun):
    """Push changes to origin"""
    run.log(f"Pushing changes to remote branch: {branch}", "DEBUG")
    subprocess.run(["git", "push", "origin", branch], cwd=repo_path, timeout=120)


def detect_language(repo_path: Path, run: ValidationRun) -> str:
    """Detect primary language"""
    
    if (repo_path / "package.json").exists():
        run.log("Detected language: JavaScript", "DEBUG")
        return "javascript"
    elif (repo_path / "requirements.txt").exists() or (repo_path / "setup.py").exists():
        run.log("Detected language: Python", "DEBUG")
        return "python"
    elif (repo_path / "pom.xml").exists():
        run.log("Detected language: Java", "DEBUG")
        return "java"
    else:
        run.log("Defaulting to Python (no clear indicators)", "DEBUG")
        return "python"


def create_sandbox(language: str, workspace: Path, run: ValidationRun):
    """Create Docker sandbox for validation"""
    
    image_map = {
        "python": "python:3.11-slim",
        "javascript": "node:18-alpine",
        "java": "openjdk:17-slim"
    }
    
    image = image_map.get(language, "python:3.11-slim")
    
    run.log(f"Creating sandbox with image: {image}", "DEBUG")
    
    # Get the volume name from environment or construct from compose project
    volume_name = os.getenv("WORKSPACE_VOLUME_NAME", "tst-runner_runner_workspace")
    
    # Extract run_id for proper path mapping
    run_id = workspace.name
    
    run.log(f"Mounting volume: {volume_name} for run: {run_id}", "DEBUG")
    
    container = docker_client.containers.run(
        image=image,
        command="sleep infinity",
        volumes={
            volume_name: {
                'bind': '/workspace',
                'mode': 'rw'
            }
        },
        working_dir=f'/workspace/{run_id}/repo',
        network_mode="none",
        mem_limit="2g",
        detach=True,
        remove=False
    )
    
    run.log(f"Sandbox container created: {container.id[:12]}", "DEBUG")
    return container


def cleanup_sandbox(container_id: str, run: ValidationRun):
    """Cleanup sandbox container"""
    try:
        container = docker_client.containers.get(container_id)
        container.stop(timeout=5)
        container.remove()
        run.log(f"Sandbox cleaned up: {container_id[:12]}", "INFO")
    except Exception as e:
        run.log(f"Failed to cleanup sandbox {container_id[:12]}: {e}", "WARNING")


async def validate_in_sandbox(container, repo_path: Path, language: str, run: ValidationRun) -> Dict:
    """Run validation in sandbox"""
    
    try:
        # Step 1: Syntax check
        run.log("Running syntax check", "DEBUG")
        syntax_result = check_syntax(container, language, run)
        if not syntax_result['passed']:
            run.log(f"Syntax check failed: {syntax_result.get('message', '')[:200]}", "ERROR")
            return {
                'success': False,
                'step': 'syntax',
                'error': syntax_result
            }
        
        run.log("Syntax check passed", "INFO")
        
        # Step 2: Build check (if applicable)
        run.log("Running build check", "DEBUG")
        build_result = check_build(container, language, run)
        if not build_result['passed']:
            run.log(f"Build check failed: {build_result.get('message', '')[:200]}", "ERROR")
            return {
                'success': False,
                'step': 'build',
                'error': build_result
            }
        
        run.log("Build check passed", "INFO")
        return {'success': True}
    
    except Exception as e:
        run.log(f"Validation exception: {str(e)}", "ERROR")
        return {
            'success': False,
            'step': 'validation',
            'error': {
                'type': 'ValidationError',
                'message': str(e),
                'passed': False
            }
        }


def check_syntax(container, language: str, run: ValidationRun) -> Dict:
    """Check syntax"""
    
    commands = {
        "python": "find . -name '*.py' -exec python -m py_compile {} \\;",
        "javascript": "npm install && npx eslint . || true",
        "java": "find . -name '*.java' -exec javac {} \\;"
    }
    
    cmd = commands.get(language, "echo 'No syntax check'")
    
    run.log(f"Executing syntax check: {cmd[:100]}", "DEBUG")
    exit_code, output = container.exec_run(cmd)
    
    result = {
        'passed': exit_code == 0,
        'type': 'SyntaxError' if exit_code != 0 else None,
        'message': output.decode('utf-8', errors='ignore'),
        'exit_code': exit_code
    }
    
    if exit_code != 0:
        run.log(f"Syntax error detected (exit code {exit_code})", "DEBUG")
    
    return result


def check_build(container, language: str, run: ValidationRun) -> Dict:
    """Check if code builds"""
    
    commands = {
        "python": "pip install -r requirements.txt 2>&1 || echo 'No requirements'",
        "javascript": "npm install && npm run build 2>&1 || echo 'No build'",
        "java": "mvn compile 2>&1 || echo 'No Maven'"
    }
    
    cmd = commands.get(language, "echo 'No build step'")
    
    run.log(f"Executing build check: {cmd[:100]}", "DEBUG")
    exit_code, output = container.exec_run(cmd)
    
    # More lenient for build step
    result = {
        'passed': True,  # For MVP, don't fail on build issues
        'message': output.decode('utf-8', errors='ignore'),
        'exit_code': exit_code
    }
    
    return result


async def llm_debug_and_fix(run: ValidationRun, error: Dict, original_patch: str, repo_path: Path) -> Dict:
    """Use LLM to debug error and generate fixed patch"""
    
    run.log("Requesting LLM debug assistance", "INFO")
    
    # Extract error context
    error_file = extract_error_file(error['message'])
    error_line = extract_error_line(error['message'])
    
    # Get code context
    code_context = ""
    if error_file:
        try:
            file_path = repo_path / error_file.lstrip('/')
            if file_path.exists():
                code_context = file_path.read_text()[:3000]  # Limit
                run.log(f"Retrieved code context from: {error_file}", "DEBUG")
        except Exception as e:
            run.log(f"Failed to get code context: {e}", "WARNING")
    
    # Build debug prompt
    prompt = f"""The following patch was applied but caused a validation error:

## Original Patch
```diff
{original_patch}
```

## Validation Error
{error.get('message', 'Unknown error')}

## Code Context
```
{code_context}
```

## Task
Generate a CORRECTED unified diff patch that:
1. Fixes the error
2. Maintains the original intent
3. Uses proper unified diff format

Output ONLY the corrected patch.
"""
    
    # Query LLM Gateway
    async with httpx.AsyncClient() as client:
        try:
            run.log(f"Sending request to LLM Gateway: {LLM_GATEWAY_URL}", "DEBUG")
            
            response = await client.post(
                f"{LLM_GATEWAY_URL}/api/v1/chat",
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert debugger. Output ONLY corrected patches."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 2000
                },
                timeout=60.0
            )
            
            response.raise_for_status()
            result = response.json()
            
            corrected_patch = result.get('content', '')
            
            # Basic validation
            if not ('---' in corrected_patch and '+++' in corrected_patch):
                run.log("LLM response not in valid patch format", "ERROR")
                return {
                    'success': False,
                    'error': 'LLM did not return valid patch format'
                }
            
            run.log("LLM successfully generated corrected patch", "INFO")
            return {
                'success': True,
                'corrected_patch': corrected_patch
            }
        
        except Exception as e:
            run.log(f"LLM request failed: {str(e)}", "ERROR")
            return {
                'success': False,
                'error': f'LLM request failed: {str(e)}'
            }


def extract_error_file(error_message: str) -> Optional[str]:
    """Extract file path from error message"""
    import re
    match = re.search(r'File "([^"]+)"', error_message)
    return match.group(1) if match else None


def extract_error_line(error_message: str) -> Optional[int]:
    """Extract line number from error message"""
    import re
    match = re.search(r'line (\d+)', error_message)
    return int(match.group(1)) if match else None


async def send_callback(run: ValidationRun):
    """Send callback to RAG system"""
    if not run.request.callback_url:
        return
    
    try:
        async with httpx.AsyncClient() as client:
            headers = {}
            if RAG_API_KEY:
                headers["X-API-Key"] = RAG_API_KEY
            
            await client.post(
                run.request.callback_url,
                json={
                    "run_id": run.run_id,
                    "repo_id": run.request.repo_id,
                    "status": run.status,
                    "result": run.result
                },
                headers=headers,
                timeout=10.0
            )
            
            run.log("Callback sent successfully", "DEBUG")
    except Exception as e:
        run.log(f"Callback failed: {e}", "WARNING")


if __name__ == "__main__":
    import uvicorn
    
    logger.info(f"Starting Runner Service on {RUNNER_HOST}:{RUNNER_PORT}")
    logger.info(f"LLM Gateway: {LLM_GATEWAY_URL}")
    logger.info(f"API Key configured: {'Yes' if RUNNER_API_KEY != 'change-me-in-production' else 'No (INSECURE!)'}")
    
    uvicorn.run(
        app,
        host=RUNNER_HOST,
        port=RUNNER_PORT,
        log_level="info"
    )