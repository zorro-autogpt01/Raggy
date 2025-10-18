# src/codecontext/api/routes/agent_feedback.py
from fastapi import APIRouter, Depends, Request
from typing import List, Dict, Optional
from pydantic import BaseModel
from datetime import datetime
import json
from pathlib import Path
from ...api.dependencies import authorize
from ...utils.responses import success_response

router = APIRouter(prefix="/agent", tags=["Agent Feedback"], dependencies=[Depends(authorize)])


class ExecutionFeedback(BaseModel):
    """Feedback from agent execution"""
    task_id: str
    repo_id: str
    retrieval_query: str
    retrieved_entities: List[str]
    entities_used: List[str]
    entities_missing: Optional[List[Dict]] = None
    execution_result: Dict
    duration_seconds: Optional[float] = None


class ChangeSuccessFeedback(BaseModel):
    """Feedback on code changes"""
    change_id: str
    repo_id: str
    files_modified: List[str]
    dependencies_retrieved: List[str]
    dependencies_actually_affected: List[str]
    blast_radius_predicted: int
    blast_radius_actual: int
    tests_run: Optional[List[str]] = None
    tests_passed: Optional[int] = None
    tests_failed: Optional[int] = None
    success: bool


@router.post("/feedback/execution")
def record_execution_feedback(request: Request, feedback: ExecutionFeedback):
    """
    Record feedback from agent execution
    
    This helps RAG learn which retrieval strategies work
    """
    # Store feedback for analysis
    feedback_store = _get_feedback_store()
    
    feedback_data = {
        "type": "execution",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **feedback.dict()
    }
    
    _append_feedback(feedback_store, feedback_data)
    
    # Calculate retrieval effectiveness
    total_retrieved = len(feedback.retrieved_entities)
    actually_used = len(feedback.entities_used)
    
    effectiveness = {
        "retrieval_precision": actually_used / max(1, total_retrieved),
        "had_missing": len(feedback.entities_missing or []) > 0,
        "success": feedback.execution_result.get("success", False)
    }
    
    data = {
        "recorded": True,
        "task_id": feedback.task_id,
        "effectiveness": effectiveness,
        "message": "Feedback recorded. RAG will learn from this execution."
    }
    
    return success_response(request, data)


@router.post("/feedback/change")
def record_change_feedback(request: Request, feedback: ChangeSuccessFeedback):
    """
    Record feedback on code changes
    
    This helps RAG improve dependency analysis accuracy
    """
    feedback_store = _get_feedback_store()
    
    feedback_data = {
        "type": "change",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        **feedback.dict()
    }
    
    _append_feedback(feedback_store, feedback_data)
    
    # Calculate blast radius accuracy
    predicted = feedback.blast_radius_predicted
    actual = feedback.blast_radius_actual
    accuracy = 1.0 - abs(predicted - actual) / max(1, max(predicted, actual))
    
    data = {
        "recorded": True,
        "change_id": feedback.change_id,
        "blast_radius_accuracy": round(accuracy, 3),
        "test_results": {
            "passed": feedback.tests_passed,
            "failed": feedback.tests_failed,
            "total": (feedback.tests_passed or 0) + (feedback.tests_failed or 0)
        },
        "message": "Change feedback recorded. This will improve dependency predictions."
    }
    
    return success_response(request, data)


@router.get("/feedback/summary")
def get_feedback_summary(
    request: Request,
    repo_id: Optional[str] = None,
    feedback_type: Optional[str] = None
):
    """
    Get summary of feedback received
    
    Useful for monitoring agent effectiveness
    """
    feedback_store = _get_feedback_store()
    
    all_feedback = _load_feedback(feedback_store)
    
    # Filter
    filtered = all_feedback
    if repo_id:
        filtered = [f for f in filtered if f.get('repo_id') == repo_id]
    if feedback_type:
        filtered = [f for f in filtered if f.get('type') == feedback_type]
    
    # Calculate metrics
    if feedback_type == "execution" or not feedback_type:
        execution_feedback = [f for f in filtered if f.get('type') == 'execution']
        
        if execution_feedback:
            avg_precision = sum(
                len(f.get('entities_used', [])) / max(1, len(f.get('retrieved_entities', [])))
                for f in execution_feedback
            ) / len(execution_feedback)
            
            success_rate = sum(
                1 for f in execution_feedback
                if f.get('execution_result', {}).get('success', False)
            ) / len(execution_feedback)
        else:
            avg_precision = 0.0
            success_rate = 0.0
    else:
        avg_precision = None
        success_rate = None
    
    if feedback_type == "change" or not feedback_type:
        change_feedback = [f for f in filtered if f.get('type') == 'change']
        
        if change_feedback:
            avg_blast_accuracy = sum(
                1.0 - abs(f.get('blast_radius_predicted', 0) - f.get('blast_radius_actual', 0)) /
                max(1, max(f.get('blast_radius_predicted', 0), f.get('blast_radius_actual', 0)))
                for f in change_feedback
            ) / len(change_feedback)
            
            change_success_rate = sum(
                1 for f in change_feedback if f.get('success', False)
            ) / len(change_feedback)
        else:
            avg_blast_accuracy = None
            change_success_rate = None
    else:
        avg_blast_accuracy = None
        change_success_rate = None
    
    data = {
        "total_feedback": len(filtered),
        "by_type": {
            "execution": len([f for f in filtered if f.get('type') == 'execution']),
            "change": len([f for f in filtered if f.get('type') == 'change'])
        },
        "metrics": {
            "avg_retrieval_precision": round(avg_precision, 3) if avg_precision is not None else None,
            "execution_success_rate": round(success_rate, 3) if success_rate is not None else None,
            "avg_blast_radius_accuracy": round(avg_blast_accuracy, 3) if avg_blast_accuracy is not None else None,
            "change_success_rate": round(change_success_rate, 3) if change_success_rate is not None else None
        }
    }
    
    return success_response(request, data)


def _get_feedback_store() -> Path:
    """Get path to feedback storage"""
    store_path = Path("./data/agent_feedback.jsonl")
    store_path.parent.mkdir(parents=True, exist_ok=True)
    return store_path


def _append_feedback(store_path: Path, feedback: Dict):
    """Append feedback to JSONL file"""
    with open(store_path, 'a') as f:
        f.write(json.dumps(feedback) + '\n')


def _load_feedback(store_path: Path) -> List[Dict]:
    """Load all feedback from JSONL file"""
    if not store_path.exists():
        return []
    
    feedback = []
    with open(store_path, 'r') as f:
        for line in f:
            try:
                feedback.append(json.loads(line.strip()))
            except:
                continue
    
    return feedback