"""
Enhanced Runner Service with Git Branch Operations
Adds branch management endpoints for Strategy C implementation
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import subprocess
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Create a separate router for branch operations
branch_router = APIRouter(prefix="/repositories/{repo_id}/branch", tags=["branches"])


class BranchCreateRequest(BaseModel):
    branch_name: str
    from_branch: str = "main"


class BranchMergeRequest(BaseModel):
    source_branch: str
    target_branch: str = "main"
    squash: bool = True
    commit_message: Optional[str] = None


class BranchResponse(BaseModel):
    success: bool
    branch: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None


def run_git_command(repo_path: Path, command: list[str], error_msg: str) -> tuple[bool, str]:
    """
    Execute a git command and return success status and output
    
    Args:
        repo_path: Path to the repository
        command: Git command as list
        error_msg: Error message prefix for logging
    
    Returns:
        Tuple of (success, output/error)
    """
    try:
        result = subprocess.run(
            command,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        logger.error(f"{error_msg}: {e.stderr}")
        return False, e.stderr
    except Exception as e:
        logger.error(f"{error_msg}: {str(e)}")
        return False, str(e)


@branch_router.post("/create", response_model=BranchResponse)
async def create_branch(
    repo_id: str,
    request: BranchCreateRequest
):
    """
    Create a new branch from an existing branch
    
    Example:
        POST /repositories/{repo_id}/branch/create
        {
            "branch_name": "feature/new-feature",
            "from_branch": "main"
        }
    """
    logger.info(f"Creating branch '{request.branch_name}' from '{request.from_branch}' in repo {repo_id}")
    
    # Get repository
    repo_store = get_repo_store()
    repo = repo_store.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")
    
    repo_path = Path(repo["local_path"])
    
    # Step 1: Fetch latest changes
    success, output = run_git_command(
        repo_path,
        ["git", "fetch", "origin"],
        "Failed to fetch from origin"
    )
    if not success:
        return BranchResponse(
            success=False,
            message="Failed to fetch latest changes",
            details={"error": output}
        )
    
    # Step 2: Checkout base branch
    success, output = run_git_command(
        repo_path,
        ["git", "checkout", request.from_branch],
        f"Failed to checkout base branch '{request.from_branch}'"
    )
    if not success:
        return BranchResponse(
            success=False,
            message=f"Base branch '{request.from_branch}' does not exist",
            details={"error": output}
        )
    
    # Step 3: Pull latest changes
    success, output = run_git_command(
        repo_path,
        ["git", "pull", "origin", request.from_branch],
        "Failed to pull latest changes"
    )
    if not success:
        logger.warning(f"Pull failed, continuing anyway: {output}")
    
    # Step 4: Check if branch already exists
    result = subprocess.run(
        ["git", "branch", "--list", request.branch_name],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    
    if result.stdout.strip():
        # Branch exists - checkout and update
        success, output = run_git_command(
            repo_path,
            ["git", "checkout", request.branch_name],
            "Failed to checkout existing branch"
        )
        if success:
            return BranchResponse(
                success=True,
                branch=request.branch_name,
                message=f"Branch '{request.branch_name}' already exists and was checked out"
            )
    
    # Step 5: Create new branch
    success, output = run_git_command(
        repo_path,
        ["git", "checkout", "-b", request.branch_name],
        "Failed to create branch"
    )
    
    if not success:
        return BranchResponse(
            success=False,
            message=f"Failed to create branch '{request.branch_name}'",
            details={"error": output}
        )
    
    # Step 6: Push branch to remote (optional, creates remote tracking)
    success, output = run_git_command(
        repo_path,
        ["git", "push", "-u", "origin", request.branch_name],
        "Failed to push branch to origin"
    )
    
    logger.info(f"Successfully created branch '{request.branch_name}' in repo {repo_id}")
    
    return BranchResponse(
        success=True,
        branch=request.branch_name,
        message=f"Branch '{request.branch_name}' created successfully from '{request.from_branch}'",
        details={"pushed_to_remote": success}
    )


@branch_router.post("/merge", response_model=BranchResponse)
async def merge_branch(
    repo_id: str,
    request: BranchMergeRequest
):
    """
    Merge source branch into target branch
    
    Example:
        POST /repositories/{repo_id}/branch/merge
        {
            "source_branch": "feature/new-feature",
            "target_branch": "main",
            "squash": true,
            "commit_message": "Add new feature"
        }
    """
    logger.info(f"Merging '{request.source_branch}' into '{request.target_branch}' in repo {repo_id}")
    
    # Get repository
    repo_store = get_repo_store()
    repo = repo_store.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")
    
    repo_path = Path(repo["local_path"])
    
    # Step 1: Fetch latest
    success, output = run_git_command(
        repo_path,
        ["git", "fetch", "origin"],
        "Failed to fetch from origin"
    )
    if not success:
        return BranchResponse(
            success=False,
            message="Failed to fetch latest changes",
            details={"error": output}
        )
    
    # Step 2: Checkout target branch
    success, output = run_git_command(
        repo_path,
        ["git", "checkout", request.target_branch],
        f"Failed to checkout target branch '{request.target_branch}'"
    )
    if not success:
        return BranchResponse(
            success=False,
            message=f"Target branch '{request.target_branch}' does not exist",
            details={"error": output}
        )
    
    # Step 3: Pull target branch
    success, output = run_git_command(
        repo_path,
        ["git", "pull", "origin", request.target_branch],
        "Failed to pull target branch"
    )
    
    # Step 4: Merge source into target
    merge_cmd = ["git", "merge"]
    if request.squash:
        merge_cmd.append("--squash")
    merge_cmd.append(request.source_branch)
    
    success, output = run_git_command(
        repo_path,
        merge_cmd,
        f"Failed to merge '{request.source_branch}' into '{request.target_branch}'"
    )
    
    if not success:
        # Check for merge conflicts
        if "CONFLICT" in output:
            return BranchResponse(
                success=False,
                message="Merge conflicts detected",
                details={
                    "error": output,
                    "action": "Manual conflict resolution required"
                }
            )
        return BranchResponse(
            success=False,
            message="Merge failed",
            details={"error": output}
        )
    
    # Step 5: Commit if squash merge
    if request.squash:
        # Configure git user before committing
        git_author_name = os.getenv("GIT_AUTHOR_NAME", "Test Runner Bot")
        git_author_email = os.getenv("GIT_AUTHOR_EMAIL", "runner@codecontext.local")
        
        run_git_command(
            repo_path,
            ["git", "config", "user.name", git_author_name],
            "Failed to set git user.name"
        )
        run_git_command(
            repo_path,
            ["git", "config", "user.email", git_author_email],
            "Failed to set git user.email"
        )
        
        commit_msg = request.commit_message or f"Merge {request.source_branch} into {request.target_branch}"
        
        success, output = run_git_command(
            repo_path,
            ["git", "commit", "-m", commit_msg],
            "Failed to commit squash merge"
        )
        
        if not success:
            return BranchResponse(
                success=False,
                message="Failed to commit merge",
                details={"error": output}
            )
    
    # Step 6: Push to remote
    success, output = run_git_command(
        repo_path,
        ["git", "push", "origin", request.target_branch],
        "Failed to push merge to origin"
    )
    
    if not success:
        return BranchResponse(
            success=False,
            message="Merge succeeded locally but failed to push",
            details={"error": output}
        )
    
    logger.info(f"Successfully merged '{request.source_branch}' into '{request.target_branch}'")
    
    return BranchResponse(
        success=True,
        message=f"Successfully merged '{request.source_branch}' into '{request.target_branch}'",
        details={
            "squashed": request.squash,
            "pushed": True
        }
    )


@branch_router.delete("/delete", response_model=BranchResponse)
async def delete_branch(
    repo_id: str,
    branch_name: str,
    delete_remote: bool = True
):
    """
    Delete a branch locally and optionally on remote
    
    Example:
        DELETE /repositories/{repo_id}/branch/delete?branch_name=feature/test&delete_remote=true
    """
    logger.info(f"Deleting branch '{branch_name}' from repo {repo_id}")
    
    # Get repository
    repo_store = get_repo_store()
    repo = repo_store.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")
    
    repo_path = Path(repo["local_path"])
    
    # Step 1: Checkout main/master to avoid deleting current branch
    success, output = run_git_command(
        repo_path,
        ["git", "checkout", "main"],
        "Failed to checkout main"
    )
    if not success:
        # Try master instead
        success, output = run_git_command(
            repo_path,
            ["git", "checkout", "master"],
            "Failed to checkout master"
        )
    
    # Step 2: Delete local branch
    success, output = run_git_command(
        repo_path,
        ["git", "branch", "-D", branch_name],
        f"Failed to delete local branch '{branch_name}'"
    )
    
    if not success:
        return BranchResponse(
            success=False,
            message=f"Failed to delete branch '{branch_name}'",
            details={"error": output}
        )
    
    # Step 3: Delete remote branch if requested
    remote_deleted = False
    if delete_remote:
        success, output = run_git_command(
            repo_path,
            ["git", "push", "origin", "--delete", branch_name],
            "Failed to delete remote branch"
        )
        remote_deleted = success
        
        if not success:
            logger.warning(f"Failed to delete remote branch: {output}")
    
    logger.info(f"Successfully deleted branch '{branch_name}'")
    
    return BranchResponse(
        success=True,
        message=f"Branch '{branch_name}' deleted successfully",
        details={
            "local_deleted": True,
            "remote_deleted": remote_deleted
        }
    )


@branch_router.get("/list", response_model=Dict[str, Any])
async def list_branches(
    repo_id: str,
    include_remote: bool = True
):
    """
    List all branches in the repository
    
    Example:
        GET /repositories/{repo_id}/branch/list?include_remote=true
    """
    # Get repository
    repo_store = get_repo_store()
    repo = repo_store.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail=f"Repository {repo_id} not found")
    
    repo_path = Path(repo["local_path"])
    
    # Get local branches
    result = subprocess.run(
        ["git", "branch"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    
    local_branches = [
        branch.strip().replace("* ", "")
        for branch in result.stdout.split("\n")
        if branch.strip()
    ]
    
    remote_branches = []
    if include_remote:
        result = subprocess.run(
            ["git", "branch", "-r"],
            cwd=repo_path,
            capture_output=True,
            text=True
        )
        
        remote_branches = [
            branch.strip().replace("origin/", "")
            for branch in result.stdout.split("\n")
            if branch.strip() and "HEAD ->" not in branch
        ]
    
    # Get current branch
    result = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    current_branch = result.stdout.strip()
    
    return {
        "success": True,
        "current_branch": current_branch,
        "local_branches": local_branches,
        "remote_branches": remote_branches if include_remote else None,
        "total_branches": len(local_branches)
    }


# This will be set by runner_service.py to avoid circular imports
_repo_store = None

def set_repo_store(store):
    """Called by runner_service.py to inject the repo store"""
    global _repo_store
    _repo_store = store

def get_repo_store():
    """Get the repository store"""
    if _repo_store is None:
        raise RuntimeError("Repository store not initialized. Call set_repo_store() first.")
    return _repo_store