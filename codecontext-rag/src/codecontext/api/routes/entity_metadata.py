# src/codecontext/api/routes/entity_metadata.py
from fastapi import APIRouter, Depends, HTTPException, Request
from typing import Optional
from ...api.dependencies import authorize
from ...utils.responses import success_response

router = APIRouter(prefix="/repositories", tags=["Entity Metadata"], dependencies=[Depends(authorize)])


@router.get("/{repo_id}/entities/{entity_id}")
def get_entity_metadata(request: Request, repo_id: str, entity_id: str):
    """
    Get detailed metadata for a specific entity
    
    Returns: Entity details including code, metrics, and context
    """
    vector_store = request.app.state.vector_store
    indexer = request.app.state.indexer
    
    # Search for entity by ID
    # Since LanceDB doesn't have direct ID lookup, we filter
    all_entities = vector_store.search(
        embedding=[0.0] * 1536,  # Dummy
        k=10000,
        filters={'repo_id': repo_id}
    )
    
    entity = next((e for e in all_entities if e.get('id') == entity_id), None)
    
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity {entity_id} not found")
    
    # Enrich with git context
    git_recency = indexer.git_recency.get(repo_id, {})
    comod_scores = indexer.comodification_scores.get(repo_id, {})
    centrality = indexer.dependency_centrality.get(repo_id, {})
    
    file_path = entity.get('file_path')
    
    metadata = {
        "id": entity_id,
        "repo_id": repo_id,
        "entity_type": entity.get('entity_type'),
        "name": entity.get('name'),
        "file_path": file_path,
        "language": entity.get('language'),
        "start_line": entity.get('start_line'),
        "end_line": entity.get('end_line'),
        "code": entity.get('code', '')[:2000],  # Truncate
        
        "metrics": {
            "lines_of_code": entity.get('end_line', 0) - entity.get('start_line', 0),
            "complexity": None,  # Could calculate if needed
            "centrality": centrality.get(file_path, 0.0),
            "recency_score": git_recency.get(file_path, 0.5),
            "change_frequency": comod_scores.get(file_path, 0.5)
        },
        
        "git_context": {
            "recency_score": git_recency.get(file_path, 0.5),
            "change_frequency": comod_scores.get(file_path, 0.5),
            "is_hotspot": comod_scores.get(file_path, 0) > 0.7
        }
    }
    
    return success_response(request, metadata)


@router.get("/{repo_id}/files/{file_path:path}/metadata")
def get_file_metadata(request: Request, repo_id: str, file_path: str):
    """
    Get metadata for entire file including all entities
    """
    vector_store = request.app.state.vector_store
    indexer = request.app.state.indexer
    
    # Get all entities in file
    entities = vector_store.get_by_file(repo_id, file_path)
    
    if not entities:
        raise HTTPException(status_code=404, detail=f"File {file_path} not found")
    
    # Organize by type
    functions = [e for e in entities if e.get('entity_type') == 'function']
    classes = [e for e in entities if e.get('entity_type') == 'class']
    chunks = [e for e in entities if e.get('entity_type') == 'chunk']
    
    # Get metrics
    git_recency = indexer.git_recency.get(repo_id, {})
    comod_scores = indexer.comodification_scores.get(repo_id, {})
    centrality = indexer.dependency_centrality.get(repo_id, {})
    
    metadata = {
        "file_path": file_path,
        "repo_id": repo_id,
        "language": entities[0].get('language') if entities else 'unknown',
        
        "entities": {
            "functions": len(functions),
            "classes": len(classes),
            "chunks": len(chunks),
            "total": len(entities)
        },
        
        "functions_list": [
            {
                "name": f.get('name'),
                "start_line": f.get('start_line'),
                "end_line": f.get('end_line')
            }
            for f in functions[:20]  # Limit
        ],
        
        "classes_list": [
            {
                "name": c.get('name'),
                "start_line": c.get('start_line'),
                "end_line": c.get('end_line')
            }
            for c in classes[:20]
        ],
        
        "metrics": {
            "centrality": centrality.get(file_path, 0.0),
            "recency_score": git_recency.get(file_path, 0.5),
            "change_frequency": comod_scores.get(file_path, 0.5)
        }
    }
    
    return success_response(request, metadata)