# src/codecontext/api/routes/repo_structure.py
from fastapi import APIRouter, Depends, HTTPException, Request
from pathlib import Path
import os
from typing import Dict, List
from ...api.dependencies import authorize
from ...utils.responses import success_response

router = APIRouter(prefix="/repositories", tags=["Repository Structure"], dependencies=[Depends(authorize)])


@router.get("/{repo_id}/structure")
def get_repository_structure(request: Request, repo_id: str):
    """
    Get structured information about repository
    
    Returns: Entry points, directory structure, build system info
    """
    repo_store = request.app.state.repo_store
    vector_store = request.app.state.vector_store
    
    repo = repo_store.get(repo_id)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    
    repo_path = repo.get('local_path') or repo.get('source_path')
    if not repo_path or not os.path.exists(repo_path):
        raise HTTPException(status_code=400, detail="Repository path not found")
    
    # Get all files from vector store
    all_entities = vector_store.search(
        embedding=[0.0] * 1536,
        k=10000,
        filters={'repo_id': repo_id, 'entity_type': 'file'}
    )
    
    files = [e.get('file_path') for e in all_entities if e.get('file_path')]
    
    # Detect entry points
    entry_points = _detect_entry_points(files)
    
    # Build directory structure
    directory_structure = _build_directory_structure(files)
    
    # Detect build system
    build_system = _detect_build_system(repo_path)
    
    # Detect configuration files
    config_files = _detect_config_files(repo_path)
    
    data = {
        "repo_id": repo_id,
        "entry_points": entry_points,
        "directory_structure": directory_structure,
        "build_system": build_system,
        "configuration": config_files,
        "statistics": {
            "total_files": len(files),
            "total_directories": len(directory_structure)
        }
    }
    
    return success_response(request, data)


def _detect_entry_points(files: List[str]) -> List[str]:
    """Detect likely entry points"""
    entry_points = []
    
    for file in files:
        # Common entry point patterns
        if any(pattern in file.lower() for pattern in [
            'main.py', '__main__.py', 'app.py', 'server.py',
            'index.js', 'app.js', 'server.js', 'main.js',
            'main.java', 'application.java'
        ]):
            entry_points.append(file)
    
    return entry_points[:5]  # Limit


def _build_directory_structure(files: List[str]) -> Dict:
    """Build directory structure from file list"""
    structure = {}
    
    for file in files:
        parts = file.split('/')
        if len(parts) > 1:
            top_dir = parts[0]
            if top_dir not in structure:
                structure[top_dir] = {
                    "purpose": _infer_directory_purpose(top_dir),
                    "file_count": 0,
                    "subdirectories": set()
                }
            structure[top_dir]["file_count"] += 1
            
            if len(parts) > 2:
                structure[top_dir]["subdirectories"].add(parts[1])
    
    # Convert sets to lists for JSON serialization
    for dir_info in structure.values():
        dir_info["subdirectories"] = list(dir_info["subdirectories"])
    
    return structure


def _infer_directory_purpose(dir_name: str) -> str:
    """Infer purpose from directory name"""
    purposes = {
        'src': 'Source code',
        'lib': 'Libraries',
        'test': 'Tests',
        'tests': 'Tests',
        'docs': 'Documentation',
        'config': 'Configuration',
        'scripts': 'Scripts',
        'bin': 'Binaries',
        'dist': 'Distribution',
        'build': 'Build output',
        'node_modules': 'Dependencies',
        'vendor': 'Dependencies',
        'public': 'Public assets',
        'static': 'Static files'
    }
    return purposes.get(dir_name.lower(), 'Unknown')


def _detect_build_system(repo_path: str) -> Dict:
    """Detect build system and commands"""
    build_info = {
        "type": "unknown",
        "package_manager": None,
        "dependency_file": None,
        "build_commands": [],
        "test_commands": [],
        "run_commands": []
    }
    
    # Python
    if os.path.exists(os.path.join(repo_path, 'setup.py')):
        build_info.update({
            "type": "python",
            "package_manager": "pip",
            "dependency_file": "setup.py",
            "build_commands": ["python setup.py install"],
            "test_commands": ["python -m pytest"],
            "run_commands": ["python -m <module>"]
        })
    elif os.path.exists(os.path.join(repo_path, 'requirements.txt')):
        build_info.update({
            "type": "python",
            "package_manager": "pip",
            "dependency_file": "requirements.txt",
            "build_commands": ["pip install -r requirements.txt"],
            "test_commands": ["pytest"],
            "run_commands": ["python main.py"]
        })
    
    # Node.js
    elif os.path.exists(os.path.join(repo_path, 'package.json')):
        build_info.update({
            "type": "javascript",
            "package_manager": "npm",
            "dependency_file": "package.json",
            "build_commands": ["npm install", "npm run build"],
            "test_commands": ["npm test"],
            "run_commands": ["npm start"]
        })
    
    # Java Maven
    elif os.path.exists(os.path.join(repo_path, 'pom.xml')):
        build_info.update({
            "type": "java",
            "package_manager": "maven",
            "dependency_file": "pom.xml",
            "build_commands": ["mvn clean install"],
            "test_commands": ["mvn test"],
            "run_commands": ["mvn exec:java"]
        })
    
    return build_info


def _detect_config_files(repo_path: str) -> Dict:
    """Detect configuration files"""
    config = {
        "env_files": [],
        "config_files": [],
        "ci_cd_files": []
    }
    
    # Check for common config files
    for root, dirs, files in os.walk(repo_path):
        # Skip hidden and build directories
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', 'venv', '__pycache__']]
        
        for file in files:
            rel_path = os.path.relpath(os.path.join(root, file), repo_path)
            
            if file.startswith('.env'):
                config["env_files"].append(rel_path)
            elif file in ['config.yaml', 'config.json', 'settings.py', 'config.py']:
                config["config_files"].append(rel_path)
            elif file in ['.github/workflows', 'Jenkinsfile', '.gitlab-ci.yml']:
                config["ci_cd_files"].append(rel_path)
    
    return config