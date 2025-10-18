# src/codecontext/api/routes/test_discovery.py
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Dict, Optional
from ...api.dependencies import authorize
from ...utils.responses import success_response

router = APIRouter(prefix="/repositories", tags=["Test Discovery"], dependencies=[Depends(authorize)])


@router.get("/{repo_id}/tests/coverage")
def get_test_coverage(
    request: Request,
    repo_id: str,
    file_path: Optional[str] = None,
    function_name: Optional[str] = None
):
    """
    Get test coverage information for files/functions
    
    Returns tests that cover the specified code
    """
    vector_store = request.app.state.vector_store
    indexer = request.app.state.indexer
    
    # Get all test files
    test_entities = vector_store.search(
        embedding=[0.0] * 1536,  # Dummy embedding
        k=1000,
        filters={
            'repo_id': repo_id,
            'entity_type': 'file'
        }
    )
    
    test_files = [
        e for e in test_entities 
        if 'test' in e.get('file_path', '').lower()
    ]
    
    # If specific file requested, find related tests
    if file_path:
        # Use dependency graph to find tests that import this file
        dep_graph = indexer.graphs.get(repo_id)
        
        related_tests = []
        if dep_graph:
            try:
                deps = dep_graph.dependencies_of(file_path, depth=2, direction="imported_by")
                imported_by = deps.get("imported_by", [])
                
                for test_file in test_files:
                    if test_file.get('file_path') in imported_by:
                        related_tests.append({
                            "test_file": test_file['file_path'],
                            "coverage_type": "direct",
                            "test_framework": _detect_test_framework(test_file['file_path']),
                            "run_command": _generate_test_command(test_file['file_path'])
                        })
            except Exception:
                pass
        
        data = {
            "file_path": file_path,
            "tests": related_tests,
            "coverage_summary": {
                "has_tests": len(related_tests) > 0,
                "test_count": len(related_tests),
                "coverage_type": "dependency_based"
            }
        }
    else:
        # Return all test files
        data = {
            "test_files": [
                {
                    "file_path": t.get('file_path'),
                    "test_framework": _detect_test_framework(t.get('file_path', '')),
                    "run_command": _generate_test_command(t.get('file_path', ''))
                }
                for t in test_files
            ],
            "total_test_files": len(test_files)
        }
    
    return success_response(request, data)


@router.post("/{repo_id}/tests/select")
def select_impacted_tests(
    request: Request,
    repo_id: str,
    body: Dict
):
    """
    Select tests impacted by changed files
    
    Body: {"modified_files": ["file1.py", "file2.py"]}
    """
    modified_files = body.get("modified_files", [])
    
    indexer = request.app.state.indexer
    dep_graph = indexer.graphs.get(repo_id)
    
    impacted_tests = []
    
    if dep_graph:
        for modified_file in modified_files:
            try:
                deps = dep_graph.dependencies_of(modified_file, depth=3, direction="imported_by")
                imported_by = set(deps.get("imported_by", []))
                
                # Find test files in dependents
                for dependent in imported_by:
                    if 'test' in dependent.lower():
                        impacted_tests.append({
                            "test_file": dependent,
                            "reason": f"Depends on {modified_file}",
                            "priority": "high",
                            "run_command": _generate_test_command(dependent)
                        })
            except Exception:
                continue
    
    data = {
        "modified_files": modified_files,
        "impacted_tests": impacted_tests,
        "total_tests": len(impacted_tests)
    }
    
    return success_response(request, data)


def _detect_test_framework(file_path: str) -> str:
    """Detect test framework from file path"""
    if 'pytest' in file_path or file_path.startswith('test_'):
        return "pytest"
    elif 'unittest' in file_path:
        return "unittest"
    elif 'jest' in file_path or file_path.endswith('.test.js'):
        return "jest"
    elif 'mocha' in file_path:
        return "mocha"
    else:
        return "unknown"


def _generate_test_command(file_path: str) -> str:
    """Generate command to run specific test file"""
    framework = _detect_test_framework(file_path)
    
    if framework == "pytest":
        return f"pytest {file_path}"
    elif framework == "unittest":
        return f"python -m unittest {file_path}"
    elif framework == "jest":
        return f"npm test {file_path}"
    else:
        return f"# Run {file_path}"