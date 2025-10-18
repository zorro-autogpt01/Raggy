# src/codecontext/api/routes/symbols.py
from fastapi import APIRouter, Depends, Request
from typing import Optional
from ...api.dependencies import authorize
from ...utils.responses import success_response

router = APIRouter(prefix="/repositories", tags=["Symbols"], dependencies=[Depends(authorize)])


@router.get("/{repo_id}/symbols/definition")
def find_symbol_definition(
    request: Request,
    repo_id: str,
    symbol_name: str,
    context_file: Optional[str] = None
):
    """
    Find where a symbol (function/class) is defined
    
    Query params:
    - symbol_name: Name to search for
    - context_file: Optional file context for disambiguation
    """
    vector_store = request.app.state.vector_store
    
    # Search for functions and classes with this name
    all_entities = vector_store.search(
        embedding=[0.0] * 1536,
        k=10000,
        filters={'repo_id': repo_id}
    )
    
    # Filter by name
    matches = [
        e for e in all_entities
        if e.get('entity_type') in ('function', 'class')
        and e.get('name') == symbol_name
    ]
    
    # If context file provided, prioritize matches from same file or nearby
    if context_file and matches:
        # Exact file match first
        same_file = [m for m in matches if m.get('file_path') == context_file]
        if same_file:
            matches = same_file
    
    if not matches:
        definition = None
    else:
        # Take first match
        match = matches[0]
        definition = {
            "entity_id": match.get('id'),
            "name": match.get('name'),
            "entity_type": match.get('entity_type'),
            "file_path": match.get('file_path'),
            "start_line": match.get('start_line'),
            "end_line": match.get('end_line'),
            "code": match.get('code', '')[:500],  # Preview
            "language": match.get('language')
        }
    
    data = {
        "symbol_name": symbol_name,
        "definition": definition,
        "total_matches": len(matches)
    }
    
    return success_response(request, data)


@router.get("/{repo_id}/symbols/usages")
def find_symbol_usages(
    request: Request,
    repo_id: str,
    symbol_name: str
):
    """
    Find all places where a symbol is used
    
    This searches for the symbol in code chunks
    """
    vector_store = request.app.state.vector_store
    embedder = request.app.state.embedder
    
    # Generate embedding for symbol name
    import asyncio
    import inspect
    
    if inspect.iscoroutinefunction(embedder.embed_text):
        loop = asyncio.get_event_loop()
        query_embedding = loop.run_until_complete(embedder.embed_text(symbol_name))
    else:
        query_embedding = embedder.embed_text(symbol_name)
    
    # Search chunks that might contain this symbol
    chunks = vector_store.search(
        embedding=query_embedding,
        k=50,
        filters={
            'repo_id': repo_id,
            'entity_type': 'chunk'
        }
    )
    
    # Filter to those that actually contain the symbol
    usages = []
    for chunk in chunks:
        code = chunk.get('code', '')
        if symbol_name in code:
            # Try to find the line
            lines = code.split('\n')
            line_nums = []
            for i, line in enumerate(lines):
                if symbol_name in line:
                    line_nums.append(chunk.get('start_line', 0) + i)
            
            usages.append({
                "file_path": chunk.get('file_path'),
                "start_line": chunk.get('start_line'),
                "end_line": chunk.get('end_line'),
                "lines_with_symbol": line_nums[:5],  # Limit
                "context": code[:200]  # Preview
            })
    
    data = {
        "symbol_name": symbol_name,
        "usages": usages[:20],  # Limit to 20
        "usage_count": len(usages)
    }
    
    return success_response(request, data)