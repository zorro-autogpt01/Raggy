import os
import ast
from typing import Dict, List, Tuple, Set

def _iter_python_files(root: str) -> List[str]:
    files: List[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # skip hidden dirs and typical build dirs
        dirnames[:] = [d for d in dirnames if not d.startswith('.') and d not in ('__pycache__', 'venv', '.venv', 'build', 'dist')]
        for fn in filenames:
            if fn.endswith('.py'):
                files.append(os.path.join(dirpath, fn))
    return files

class _FuncVisitor(ast.NodeVisitor):
    def __init__(self, module_name: str):
        self.module = module_name
        self.current_func: List[str] = []
        self.edges: Set[Tuple[str, str]] = set()
        self.nodes: Set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        qn = f"{self.module}.{node.name}"
        self.nodes.add(qn)
        self.current_func.append(qn)
        self.generic_visit(node)
        self.current_func.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        qn = f"{self.module}.{node.name}"
        self.nodes.add(qn)
        self.current_func.append(qn)
        self.generic_visit(node)
        self.current_func.pop()

    def visit_Call(self, node: ast.Call):
        if not self.current_func:
            self.generic_visit(node)
            return
        caller = self.current_func[-1]
        callee_name = None
        # Simple resolution: Name() -> 'name', Attribute() -> '.attr' fallback to attribute name
        if isinstance(node.func, ast.Name):
            callee_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            callee_name = node.func.attr
        if callee_name:
            # We don't know target module; keep it as unqualified function name (best-effort).
            target = callee_name
            self.edges.add((caller, target))
        self.generic_visit(node)

def _module_name(repo_root: str, file_path: str) -> str:
    """
    Convert an absolute path to a dotted module name relative to repo_root, strip .py
    """
    rel = os.path.relpath(file_path, repo_root).replace("\\", "/")
    if rel.endswith(".py"):
        rel = rel[:-3]
    # convert path separators to dots
    parts = [p for p in rel.split("/") if p and p != "__init__"]
    return ".".join(parts)

def run_static_callgraph(repo_path: str) -> Dict:
    """
    Build a lightweight static Python call graph using ast.
    Nodes: functions as "<module>.<func>"
    Edges: ("<module>.<caller>", "<callee_name>") -- callee might be unqualified.
    """
    files = _iter_python_files(repo_path)
    nodes: Set[str] = set()
    edges: List[Dict] = []

    for f in files:
        try:
            with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                src = fh.read()
            tree = ast.parse(src)
        except Exception:
            continue
        module = _module_name(repo_path, f)
        vis = _FuncVisitor(module)
        try:
            vis.visit(tree)
        except Exception:
            continue
        for n in vis.nodes:
            nodes.add(n)
        for (src_func, callee) in vis.edges:
            edges.append({"source": src_func, "target": callee, "type": "calls"})

    node_objs = [{"id": n, "label": n, "type": "function"} for n in sorted(nodes)]
    return {"nodes": node_objs, "edges": edges}
