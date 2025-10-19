from fastapi import APIRouter, Depends, Request
from typing import Optional
from ...api.dependencies import authorize
from ...utils.responses import success_response

router = APIRouter(prefix="/repositories", tags=["Symbols"], dependencies=[Depends(authorize)])

def _sanitize_sql_literal(value: str) -> str:
    # Basic single-quote escaping for where clauses
    return value.replace("'", "''") if isinstance(value, str) else value

@router.get("/{repo_id}/symbols/definition")
def find_symbol_definition(
    request: Request,
    repo_id: str,
    symbol_name: str,
    context_file: Optional[str] = None
):
    """
    Find where a symbol (function/class) is defined
    """
    vector_store = request.app.state.vector_store

    name = _sanitize_sql_literal(symbol_name)
    where = (
        f"repo_id = '{_sanitize_sql_literal(repo_id)}' AND "
        f"(entity_type = 'function' OR entity_type = 'class') AND "
        f"name = '{name}'"
    )
    matches = vector_store.query_where(where, limit=100)

    if context_file and matches:
        same_file = [m for m in matches if m.get('file_path') == context_file]
        if same_file:
            matches = same_file

    if not matches:
        definition = None
    else:
        match = matches[0]
        definition = {
            "entity_id": match.get('id'),
            "name": match.get('name'),
            "entity_type": match.get('entity_type'),
            "file_path": match.get('file_path'),
            "start_line": match.get('start_line'),
            "end_line": match.get('end_line'),
            "code": match.get('code', '')[:500],
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
    Find places where a symbol is used (best-effort via vector search + filtering)
    """
    vector_store = request.app.state.vector_store
    embedder = request.app.state.embedder

    import asyncio
    import inspect

    if inspect.iscoroutinefunction(embedder.embed_text):
        loop = asyncio.get_event_loop()
        query_embedding = loop.run_until_complete(embedder.embed_text(symbol_name))
    else:
        query_embedding = embedder.embed_text(symbol_name)

    chunks = vector_store.search(
        embedding=query_embedding,
        k=50,
        filters={
            'repo_id': repo_id,
            'entity_type': 'chunk'
        }
    )

    usages = []
    for chunk in chunks:
        code = chunk.get('code', '') or ''
        if symbol_name in code:
            lines = code.split('\n')
            line_nums = []
            for i, line in enumerate(lines):
                if symbol_name in line:
                    line_nums.append((chunk.get('start_line', 0) + i))
            usages.append({
                "file_path": chunk.get('file_path'),
                "start_line": chunk.get('start_line'),
                "end_line": chunk.get('end_line'),
                "lines_with_symbol": line_nums[:5],
                "context": code[:200]
            })

    data = {
        "symbol_name": symbol_name,
        "usages": usages[:20],
        "usage_count": len(usages)
    }

    return success_response(request, data)
