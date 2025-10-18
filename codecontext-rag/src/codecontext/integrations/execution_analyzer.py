"""
RAG Execution Strategy Analyzer
Uses LLM to determine the best execution strategy for code validation
"""
import httpx
import json
import re
from typing import Optional, Dict, List
from pathlib import Path

from ..api.schemas.execution_models import (
    ExecutionConfig,
    ExecutionStrategy,
    HealthCheckConfig,
    SuccessCriteria,
    RepositoryExecutionProfile
)


class ExecutionStrategyAnalyzer:
    """Analyzes code changes and determines execution strategy"""
    
    def __init__(self, llm_gateway_url: str, repo_store, vector_store):
        self.llm_gateway_url = llm_gateway_url
        self.repo_store = repo_store
        self.vector_store = vector_store
    
    async def analyze_and_generate_config(
        self,
        repo_id: str,
        patch: str,
        files_changed: list[str],
        commit_message: str
    ) -> ExecutionConfig:
        """
        Analyze code change and generate execution configuration
        
        Args:
            repo_id: Repository identifier
            patch: The code patch being applied
            files_changed: List of files being modified
            commit_message: Description of the change
        
        Returns:
            ExecutionConfig with appropriate strategy
        """
        
        # 1. Check if repo has stored execution profile
        profile = self._get_repo_profile(repo_id)
        
        # 2. Gather context about the repository
        repo_context = await self._gather_repo_context(repo_id, files_changed)
        
        # 3. Extract detailed file information from patch
        file_analysis = self._analyze_patch_files(patch, files_changed)
        repo_context.update(file_analysis)
        
        # 4. Use LLM to analyze and recommend strategy
        config = await self._llm_analyze(
            repo_id=repo_id,
            patch=patch,
            files_changed=files_changed,
            commit_message=commit_message,
            repo_context=repo_context,
            existing_profile=profile
        )
        
        return config
    
    def _analyze_patch_files(self, patch: str, files_changed: list[str]) -> Dict:
        """Extract detailed information about files from the patch"""
        
        analysis = {
            "new_files": [],
            "modified_files": [],
            "deleted_files": [],
            "primary_file": None,  # The main file being worked on
            "file_extensions": set()
        }
        
        # Parse patch to determine file operations
        for line in patch.split('\n'):
            if line.startswith('---'):
                # Extract old file
                match = re.search(r'--- a/(.+?)(?:\s|$)', line)
                if match:
                    old_file = match.group(1)
                    if old_file != '/dev/null':
                        analysis["modified_files"].append(old_file)
            
            elif line.startswith('+++'):
                # Extract new file
                match = re.search(r'\+\+\+ b/(.+?)(?:\s|$)', line)
                if match:
                    new_file = match.group(1)
                    if new_file != '/dev/null':
                        ext = Path(new_file).suffix
                        if ext:
                            analysis["file_extensions"].add(ext)
                        
                        # Check if this is a new file (previous line was /dev/null)
                        if '/dev/null' in patch.split('\n')[patch.split('\n').index(line) - 1]:
                            analysis["new_files"].append(new_file)
                        else:
                            if new_file not in analysis["modified_files"]:
                                analysis["modified_files"].append(new_file)
        
        # Determine primary file (prefer new files, then modified)
        if analysis["new_files"]:
            # If creating a single new file, that's probably the primary one
            analysis["primary_file"] = analysis["new_files"][0]
        elif analysis["modified_files"]:
            analysis["primary_file"] = analysis["modified_files"][0]
        elif files_changed:
            analysis["primary_file"] = files_changed[0]
        
        return analysis
    
    def _get_repo_profile(self, repo_id: str) -> Optional[RepositoryExecutionProfile]:
        """Get stored execution profile for repository"""
        repo = self.repo_store.get(repo_id)
        if not repo:
            return None
        
        execution_profile = repo.get("execution_profile")
        if execution_profile:
            return RepositoryExecutionProfile(**execution_profile)
        
        return None
    
    async def _gather_repo_context(
        self, 
        repo_id: str, 
        files_changed: list[str]
    ) -> Dict:
        """Gather context about repository structure"""
        
        repo = self.repo_store.get(repo_id)
        if not repo:
            return {}
        
        repo_path = Path(repo.get("local_path", ""))
        
        context = {
            "project_type": None,
            "framework": None,
            "has_tests": False,
            "test_framework": None,
            "has_requirements": False,
            "main_files": [],
            "entry_points": []
        }
        
        if not repo_path.exists():
            return context
        
        # Detect Python project
        if (repo_path / "requirements.txt").exists():
            context["has_requirements"] = True
            context["project_type"] = "python"
        
        if (repo_path / "setup.py").exists():
            context["project_type"] = "python_package"
        
        # Detect web frameworks
        for file in ["app.py", "application.py", "main.py"]:
            file_path = repo_path / file
            if file_path.exists():
                try:
                    content = file_path.read_text(errors='ignore')
                    if "flask" in content.lower():
                        context["framework"] = "flask"
                        context["entry_points"].append(file)
                    elif "fastapi" in content.lower():
                        context["framework"] = "fastapi"
                        context["entry_points"].append(file)
                except:
                    pass
        
        # Detect tests
        test_dirs = ["tests", "test"]
        for test_dir in test_dirs:
            test_path = repo_path / test_dir
            if test_path.exists() and test_path.is_dir():
                context["has_tests"] = True
                
                # Check test framework
                try:
                    for test_file in test_path.glob("*.py"):
                        content = test_file.read_text(errors='ignore')
                        if "pytest" in content or "@pytest" in content:
                            context["test_framework"] = "pytest"
                            break
                        elif "unittest" in content:
                            context["test_framework"] = "unittest"
                            break
                except:
                    pass
        
        # Detect Node.js
        if (repo_path / "package.json").exists():
            context["project_type"] = "nodejs"
            try:
                package = json.loads((repo_path / "package.json").read_text())
                if "scripts" in package:
                    if "start" in package["scripts"]:
                        context["entry_points"].append("npm start")
                    if "test" in package["scripts"]:
                        context["has_tests"] = True
                        context["test_framework"] = "jest"
            except:
                pass
        
        # Identify main files
        for main_file in ["main.py", "app.py", "server.py", "index.js", "server.js"]:
            if (repo_path / main_file).exists():
                context["main_files"].append(main_file)
        
        return context
    
    async def _llm_analyze(
        self,
        repo_id: str,
        patch: str,
        files_changed: list[str],
        commit_message: str,
        repo_context: Dict,
        existing_profile: Optional[RepositoryExecutionProfile]
    ) -> ExecutionConfig:
        """Use LLM to analyze and recommend execution strategy"""
        
        # Build analysis prompt
        prompt = self._build_analysis_prompt(
            patch=patch,
            files_changed=files_changed,
            commit_message=commit_message,
            repo_context=repo_context,
            existing_profile=existing_profile
        )
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.llm_gateway_url}/api/v1/chat",
                    json={
                        "model": "gpt-4o",  # Use stronger model for analysis
                        "messages": [
                            {
                                "role": "system",
                                "content": self._get_system_prompt()
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"}
                    }
                )
                
                response.raise_for_status()
                result = response.json()
                
                # Parse LLM response into ExecutionConfig
                config_dict = json.loads(result.get("content", "{}"))
                
                return self._parse_llm_response(config_dict, repo_context)
        
        except Exception as e:
            # Fallback: use heuristics
            return self._fallback_strategy(repo_context, files_changed)
    
    def _get_system_prompt(self) -> str:
        """System prompt for LLM analysis"""
        return """You are an expert code execution strategist. Analyze code changes and determine the best validation strategy.

Your goal: Recommend how to execute and validate code changes safely and effectively.

Available strategies:
1. SCRIPT - Run code and expect it to exit (for CLI tools, scripts)
2. SERVICE - Start service and perform health checks (for web servers, APIs)
3. TEST - Run test suite (when tests exist and are relevant)
4. DAEMON - Start long-running process (for background workers)
5. NONE - No execution needed (documentation, config files only)

CRITICAL RULES:
- When creating a NEW file, ALWAYS use that exact filename in the command
- For script strategy, the "args" array must contain the ACTUAL filename being created/modified
- Example: If creating "calculator.py", use: {"command": "python", "args": ["calculator.py"]}
- NEVER use generic filenames like "main.py" unless that's the actual file being modified

Consider:
- What type of code is being changed?
- Which specific file should be executed?
- Is this a service that needs to stay running?
- Are there tests that should be run?
- What indicates success?

Return JSON with execution configuration following the ExecutionConfig schema."""
    
    def _build_analysis_prompt(
        self,
        patch: str,
        files_changed: list[str],
        commit_message: str,
        repo_context: Dict,
        existing_profile: Optional[RepositoryExecutionProfile]
    ) -> str:
        """Build detailed analysis prompt"""
        
        # Extract file details
        new_files = repo_context.get("new_files", [])
        modified_files = repo_context.get("modified_files", [])
        primary_file = repo_context.get("primary_file")
        
        prompt = f"""Analyze this code change and recommend execution strategy.

## Code Change
**Commit message:** {commit_message}

**Files changed:** {', '.join(files_changed)}
**New files created:** {', '.join(new_files) if new_files else 'None'}
**Existing files modified:** {', '.join(modified_files) if modified_files else 'None'}
**Primary file:** {primary_file if primary_file else 'Unknown'}

**Patch:**
```diff
{patch[:2000]}
```

## Repository Context
**Project type:** {repo_context.get('project_type', 'unknown')}
**Framework:** {repo_context.get('framework', 'none')}
**Has tests:** {repo_context.get('has_tests', False)}
**Test framework:** {repo_context.get('test_framework', 'none')}
**Entry points:** {', '.join(repo_context.get('entry_points', []))}
**Main files:** {', '.join(repo_context.get('main_files', []))}
"""
        
        if existing_profile:
            prompt += f"""
## Existing Configuration
This repository already has an execution profile:
**Default strategy:** {existing_profile.default_config.strategy}
**Project type:** {existing_profile.project_type}
"""
        
        prompt += f"""
## Task
Provide execution configuration as JSON.

**CRITICAL:** Use the ACTUAL filename from the patch!
- Primary file to execute: **{primary_file}**
- If creating a new Python file, use that exact filename in args
- Example: {{"command": "python", "args": ["{primary_file}"]}}

{{
  "enabled": true/false,
  "strategy": "script" | "service" | "test" | "daemon" | "none",
  "command": "python",
  "args": ["{primary_file if primary_file else 'ACTUAL_FILENAME.py'}"],
  "timeout": 30,
  
  // For services
  "startup_wait": 5,
  "health_check": {{
    "type": "http",
    "url": "http://localhost:5000/health",
    "expected_status": 200
  }},
  
  // For tests
  "test_command": "pytest",
  "test_framework": "pytest",
  
  // Success criteria
  "success_if": {{
    "exit_code": 0,
    "stdout_contains": ["SUCCESS"],
    "health_check_passes": true
  }},
  
  "description": "Brief explanation of strategy"
}}

If execution is not needed (docs/config only), set enabled to false.
If this is a simple script, use strategy="script" with the actual filename.
"""
        
        return prompt
    
    def _parse_llm_response(self, config_dict: Dict, repo_context: Dict) -> ExecutionConfig:
        """Parse LLM JSON response into ExecutionConfig"""
        
        try:
            # Handle nested objects
            if "health_check" in config_dict and config_dict["health_check"]:
                config_dict["health_check"] = HealthCheckConfig(**config_dict["health_check"])
            
            if "success_if" in config_dict and config_dict["success_if"]:
                config_dict["success_if"] = SuccessCriteria(**config_dict["success_if"])
            
            # Validate that if it's a script strategy, it has a command
            config = ExecutionConfig(**config_dict)
            
            # Post-validation: ensure filename is correct
            if config.strategy == ExecutionStrategy.SCRIPT and config.enabled:
                primary_file = repo_context.get("primary_file")
                if primary_file and config.args:
                    # If LLM didn't use the right filename, fix it
                    if config.args[0] not in ["main.py", primary_file]:
                        # LLM might have used wrong file, correct it
                        if primary_file.endswith('.py') and config.command == "python":
                            config.args = [primary_file]
            
            return config
        
        except Exception as e:
            # Fallback if parsing fails
            return self._fallback_strategy(repo_context, [])
    
    def _fallback_strategy(self, repo_context: Dict, files_changed: list[str]) -> ExecutionConfig:
        """Fallback heuristic-based strategy"""
        
        # Try to use primary file from patch analysis
        primary_file = repo_context.get("primary_file")
        
        # If tests exist and test files were changed, run tests
        if repo_context.get("has_tests") and any("test" in f for f in files_changed):
            test_fw = repo_context.get("test_framework", "pytest")
            return ExecutionConfig(
                enabled=True,
                strategy=ExecutionStrategy.TEST,
                test_command=test_fw,
                test_framework=test_fw,
                description="Running tests (fallback strategy)"
            )
        
        # If it's a web framework, use service strategy
        if repo_context.get("framework") in ["flask", "fastapi", "express"]:
            entry_point = repo_context.get("entry_points", ["app.py"])[0]
            return ExecutionConfig(
                enabled=True,
                strategy=ExecutionStrategy.SERVICE,
                command="python" if entry_point.endswith(".py") else "node",
                args=[entry_point],
                startup_wait=5,
                health_check=HealthCheckConfig(
                    type="http",
                    url="http://localhost:5000/health"
                ),
                description=f"Service health check (fallback for {repo_context.get('framework')})"
            )
        
        # Default: simple script execution with primary file
        if primary_file and primary_file.endswith('.py'):
            return ExecutionConfig(
                enabled=True,
                strategy=ExecutionStrategy.SCRIPT,
                command="python",
                args=[primary_file],
                timeout=30,
                success_if=SuccessCriteria(exit_code=0),
                description=f"Execute {primary_file} (fallback)"
            )
        
        # Last resort fallback
        main_file = repo_context.get("main_files", ["main.py"])[0] if repo_context.get("main_files") else "main.py"
        return ExecutionConfig(
            enabled=True,
            strategy=ExecutionStrategy.SCRIPT,
            command="python" if main_file.endswith(".py") else "node",
            args=[main_file],
            timeout=30,
            success_if=SuccessCriteria(exit_code=0),
            description="Basic script execution (fallback)"
        )


# Helper function for RAG routes
async def analyze_execution_strategy(
    repo_id: str,
    patch: str,
    files_changed: list[str],
    commit_message: str,
    analyzer: ExecutionStrategyAnalyzer
) -> ExecutionConfig:
    """
    Convenience function to analyze and get execution config
    Can be called from RAG routes before sending to runner
    """
    return await analyzer.analyze_and_generate_config(
        repo_id=repo_id,
        patch=patch,
        files_changed=files_changed,
        commit_message=commit_message
    )