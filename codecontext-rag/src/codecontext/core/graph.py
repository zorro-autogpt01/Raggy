import os
import re
import networkx as nx
from typing import Dict, List, Set, Optional

class DependencyGraph:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.repo_root = None
    
    def build_from_parsed_files(self, parsed_files: List[Dict], repo_root: str):
        """Build dependency graph from parsed file data"""
        self.repo_root = repo_root
        
        # Add all files as nodes first
        for file_data in parsed_files:
            self.add_file(file_data['file_path'])
        
        # Add edges based on imports
        for file_data in parsed_files:
            source_file = file_data['file_path']
            imports = file_data.get('imports', [])
            
            for imp in imports:
                target_file = self._resolve_import(imp, source_file, file_data['language'])
                if target_file and self.graph.has_node(target_file):
                    self.graph.add_edge(source_file, target_file)
    
    def add_file(self, file_path: str) -> None:
        """Add a file as a node in the graph"""
        self.graph.add_node(file_path, label=file_path.split('/')[-1])
    
    def dependencies_of(self, file_path: str, depth: int = 2, direction: str = "both") -> Dict:
        """Get dependencies of a file up to specified depth"""
        if not self.graph.has_node(file_path):
            return {"imports": [], "imported_by": []}
        
        result = {"imports": [], "imported_by": []}
        
        if direction in ("imports", "both"):
            # Files that this file imports (outgoing edges)
            imports = self._traverse_dependencies(file_path, depth, "out")
            result["imports"] = list(imports)
        
        if direction in ("imported_by", "both"):
            # Files that import this file (incoming edges)
            imported_by = self._traverse_dependencies(file_path, depth, "in")
            result["imported_by"] = list(imported_by)
        
        return result
    
    def _traverse_dependencies(self, start: str, depth: int, direction: str) -> Set[str]:
        """Traverse graph in specified direction up to depth"""
        visited = set()
        current_level = {start}
        
        for _ in range(depth):
            next_level = set()
            for node in current_level:
                if direction == "out":
                    neighbors = set(self.graph.successors(node))
                else:  # "in"
                    neighbors = set(self.graph.predecessors(node))
                
                new_neighbors = neighbors - visited - {start}
                next_level.update(new_neighbors)
                visited.update(new_neighbors)
            
            current_level = next_level
            if not current_level:
                break
        
        return visited
    
    def get_centrality_scores(self) -> Dict[str, float]:
        """Calculate centrality scores for all files"""
        if len(self.graph) == 0:
            return {}
        
        try:
            # PageRank centrality
            centrality = nx.pagerank(self.graph)
            return centrality
        except:
            # Fallback to degree centrality
            return nx.degree_centrality(self.graph)
    
    def find_circular_dependencies(self) -> List[List[str]]:
        """Find circular dependencies in the graph"""
        try:
            cycles = list(nx.simple_cycles(self.graph))
            return cycles
        except:
            return []
    
    def _resolve_import(self, import_stmt: str, source_file: str, language: str) -> Optional[str]:
        """
        Resolve import statement to actual file path (relative to repo root).
        Improved Python resolution: handles relative imports, packages (__init__.py), and absolute modules.
        JS/TS: better inference of extensions.
        """
        if not self.repo_root:
            return None

        # Helper to check candidate path existence under repo_root and return rel path
        def _exists_rel(rel_path: str) -> Optional[str]:
            abs_path = os.path.join(self.repo_root, rel_path)
            if os.path.isfile(abs_path):
                # normalize to posix-style relative
                return rel_path.replace("\\", "/")
            return None

        # Python resolution
        if language == 'python':
            # Extract module from import statement
            # Handle: "from foo.bar import baz", "import foo", "from . import x", "from ..pkg import y"
            m = re.search(r'from\s+([.\w]+)\s+import|import\s+([.\w]+)', import_stmt)
            if not m:
                return None
            module = m.group(1) or m.group(2) or ""
            module = module.strip()

            # Build candidate paths for absolute module
            def _absolute_candidates(mod: str) -> List[str]:
                rel = mod.replace('.', '/')
                return [
                    f"{rel}.py",
                    f"{rel}/__init__.py",
                ]

            # Build candidate paths for relative module (leading dots)
            def _relative_candidates(mod: str, src: str) -> List[str]:
                # src is like "pkg/sub/file.py"
                src_dir = os.path.dirname(src)
                # Count leading dots
                leading = len(mod) - len(mod.lstrip('.'))
                tail = mod.lstrip('.')
                # Ascend parents: one dot = current package; two dots = parent, etc.
                base = src_dir
                for _ in range(max(0, leading - 1)):
                    base = os.path.dirname(base)
                rel = tail.replace('.', '/') if tail else ""
                if rel:
                    path = os.path.normpath(os.path.join(base, rel)).replace("\\", "/")
                    return [f"{path}.py", f"{path}/__init__.py"]
                else:
                    # from . import x  -> current package __init__.py or package root
                    return [f"{base}/__init__.py"]

            candidates: List[str] = []
            if module.startswith('.'):
                candidates = _relative_candidates(module, source_file)
            else:
                candidates = _absolute_candidates(module)

            # Return first existing candidate
            for cand in candidates:
                rel = _exists_rel(cand)
                if rel:
                    return rel

            return None

        elif language == 'javascript':
            # Handle: import foo from './foo' or '../bar'
            m = re.search(r"from\s+['\"]([^'\"]+)['\"]", import_stmt)
            if not m:
                return None
            path = m.group(1)
            src_dir = os.path.dirname(source_file)
            if path.startswith('.'):
                # Relative import
                base = os.path.normpath(os.path.join(src_dir, path)).replace("\\", "/")
                # Try common extensions
                for ext in (".ts", ".tsx", ".js", ".jsx"):
                    rel = _exists_rel(base + ext)
                    if rel:
                        return rel
                # Try index files
                for ext in (".ts", ".tsx", ".js", ".jsx"):
                    rel = _exists_rel(os.path.join(base, "index" + ext))
                    if rel:
                        return rel
            # Non-relative imports are typically resolved via bundler/node_modules.
            return None
        
        return None
