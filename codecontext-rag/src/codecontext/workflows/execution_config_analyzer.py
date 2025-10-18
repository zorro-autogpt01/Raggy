"""
Product Analysis: Execution Configuration Recommendations
Checks repositories for execution configs and recommends setup
"""
from typing import List, Dict, Optional
from pathlib import Path
import json

from ..api.schemas.execution_models import (
    RepositoryExecutionProfile,
    ExecutionConfig,
    ExecutionStrategy,
    EXAMPLE_CONFIGS
)


class ExecutionConfigAnalyzer:
    """Analyzes repositories and recommends execution configurations"""
    
    def __init__(self, repo_store, vector_store, llm_gateway_url: str):
        self.repo_store = repo_store
        self.vector_store = vector_store
        self.llm_gateway_url = llm_gateway_url
    
    async def analyze_repository_execution_needs(self, repo_id: str) -> Dict:
        """
        Analyze repository and determine if execution config is needed
        
        Returns:
            {
                "has_config": bool,
                "needs_config": bool,
                "confidence": float,
                "detected_type": str,
                "recommendations": [...]
            }
        """
        
        repo = self.repo_store.get(repo_id)
        if not repo:
            return {"error": "Repository not found"}
        
        # Check if already has execution config
        has_config = "execution_profile" in repo and repo["execution_profile"] is not None
        
        if has_config:
            return {
                "has_config": True,
                "needs_config": False,
                "message": "Repository already has execution configuration"
            }
        
        # Analyze repository structure
        repo_path = Path(repo.get("local_path", ""))
        if not repo_path.exists():
            return {
                "has_config": False,
                "needs_config": False,
                "confidence": 0.0,
                "message": "Repository path not found"
            }
        
        # Detect project characteristics
        analysis = self._analyze_structure(repo_path)
        
        # Determine if config is beneficial
        needs_config = analysis["is_executable_project"]
        confidence = analysis["confidence"]
        
        # Generate recommendations
        recommendations = self._generate_recommendations(analysis)
        
        return {
            "has_config": False,
            "needs_config": needs_config,
            "confidence": confidence,
            "detected_type": analysis["project_type"],
            "framework": analysis.get("framework"),
            "has_tests": analysis["has_tests"],
            "test_framework": analysis.get("test_framework"),
            "recommendations": recommendations,
            "suggested_configs": self._suggest_configs(analysis)
        }
    
    def _analyze_structure(self, repo_path: Path) -> Dict:
        """Analyze repository file structure"""
        
        analysis = {
            "project_type": "unknown",
            "framework": None,
            "is_executable_project": False,
            "has_tests": False,
            "test_framework": None,
            "has_entry_point": False,
            "entry_points": [],
            "confidence": 0.0,
            "indicators": []
        }
        
        # Python detection
        if (repo_path / "requirements.txt").exists():
            analysis["project_type"] = "python"
            analysis["confidence"] += 0.3
            analysis["indicators"].append("requirements.txt found")
        
        if (repo_path / "setup.py").exists():
            analysis["project_type"] = "python_package"
            analysis["confidence"] += 0.2
            analysis["indicators"].append("setup.py found")
        
        # Check for web frameworks
        for entry_file in ["app.py", "main.py", "server.py", "application.py"]:
            file_path = repo_path / entry_file
            if file_path.exists():
                analysis["has_entry_point"] = True
                analysis["entry_points"].append(entry_file)
                analysis["confidence"] += 0.3
                
                try:
                    content = file_path.read_text(errors='ignore')
                    
                    if "flask" in content.lower():
                        analysis["framework"] = "flask"
                        analysis["is_executable_project"] = True
                        analysis["confidence"] += 0.4
                        analysis["indicators"].append("Flask framework detected")
                    
                    elif "fastapi" in content.lower():
                        analysis["framework"] = "fastapi"
                        analysis["is_executable_project"] = True
                        analysis["confidence"] += 0.4
                        analysis["indicators"].append("FastAPI framework detected")
                    
                    elif "django" in content.lower():
                        analysis["framework"] = "django"
                        analysis["is_executable_project"] = True
                        analysis["confidence"] += 0.4
                        analysis["indicators"].append("Django framework detected")
                    
                    # Check for CLI tools
                    if "argparse" in content or "click" in content:
                        analysis["is_executable_project"] = True
                        analysis["confidence"] += 0.3
                        analysis["indicators"].append("CLI tool detected")
                
                except:
                    pass
        
        # Node.js detection
        if (repo_path / "package.json").exists():
            analysis["project_type"] = "nodejs"
            analysis["confidence"] += 0.3
            analysis["indicators"].append("package.json found")
            
            try:
                package_data = json.loads((repo_path / "package.json").read_text())
                
                if "scripts" in package_data:
                    if "start" in package_data["scripts"]:
                        analysis["has_entry_point"] = True
                        analysis["entry_points"].append("npm start")
                        analysis["is_executable_project"] = True
                        analysis["confidence"] += 0.4
                        analysis["indicators"].append("npm start script found")
                    
                    if "test" in package_data["scripts"]:
                        analysis["has_tests"] = True
                        analysis["confidence"] += 0.2
                
                # Check for frameworks
                deps = package_data.get("dependencies", {})
                if "express" in deps:
                    analysis["framework"] = "express"
                    analysis["is_executable_project"] = True
                    analysis["indicators"].append("Express framework detected")
                elif "next" in deps:
                    analysis["framework"] = "nextjs"
                    analysis["is_executable_project"] = True
                    analysis["indicators"].append("Next.js framework detected")
            
            except:
                pass
        
        # Test detection
        test_dirs = ["tests", "test", "__tests__"]
        for test_dir in test_dirs:
            test_path = repo_path / test_dir
            if test_path.exists() and test_path.is_dir():
                analysis["has_tests"] = True
                analysis["confidence"] += 0.2
                analysis["indicators"].append(f"{test_dir}/ directory found")
                
                # Detect test framework
                for test_file in test_path.glob("**/*.py"):
                    try:
                        content = test_file.read_text(errors='ignore')
                        if "pytest" in content or "@pytest" in content:
                            analysis["test_framework"] = "pytest"
                            analysis["indicators"].append("pytest detected")
                            break
                        elif "unittest" in content:
                            analysis["test_framework"] = "unittest"
                            analysis["indicators"].append("unittest detected")
                            break
                    except:
                        pass
                
                # Node.js tests
                for test_file in test_path.glob("**/*.test.js"):
                    analysis["test_framework"] = "jest"
                    analysis["indicators"].append("Jest tests detected")
                    break
        
        # Docker detection
        if (repo_path / "Dockerfile").exists():
            analysis["confidence"] += 0.2
            analysis["indicators"].append("Dockerfile found")
        
        # Cap confidence at 1.0
        analysis["confidence"] = min(1.0, analysis["confidence"])
        
        return analysis
    
    def _generate_recommendations(self, analysis: Dict) -> List[Dict]:
        """Generate specific recommendations based on analysis"""
        
        recommendations = []
        
        # Recommendation 1: Set up execution config
        if analysis["is_executable_project"] and analysis["confidence"] > 0.6:
            rec = {
                "priority": "high",
                "category": "execution",
                "title": "Configure Execution Validation",
                "description": f"This appears to be a {analysis['project_type']} project",
                "reasoning": " ".join(analysis["indicators"]),
                "action": "Set up execution configuration to automatically validate code changes",
                "implementation": "recommended_config_below"
            }
            
            if analysis.get("framework"):
                rec["description"] += f" using {analysis['framework']}"
                rec["reasoning"] += f". Framework: {analysis['framework']}"
            
            recommendations.append(rec)
        
        # Recommendation 2: Set up test execution
        if analysis["has_tests"]:
            recommendations.append({
                "priority": "high",
                "category": "testing",
                "title": "Enable Automated Test Execution",
                "description": f"Tests detected using {analysis.get('test_framework', 'unknown framework')}",
                "reasoning": "Running tests automatically ensures code quality",
                "action": "Configure test execution strategy",
                "implementation": "test_config_below"
            })
        
        # Recommendation 3: Consider adding tests
        if analysis["is_executable_project"] and not analysis["has_tests"]:
            recommendations.append({
                "priority": "medium",
                "category": "quality",
                "title": "Add Automated Tests",
                "description": "No tests detected in this executable project",
                "reasoning": "Tests improve code reliability and catch regressions",
                "action": f"Add {analysis.get('test_framework', 'pytest')} tests",
                "implementation": "manual"
            })
        
        # Recommendation 4: Health checks for services
        if analysis.get("framework") in ["flask", "fastapi", "express", "nextjs"]:
            recommendations.append({
                "priority": "medium",
                "category": "monitoring",
                "title": "Add Health Check Endpoint",
                "description": f"{analysis['framework']} service detected",
                "reasoning": "Health checks ensure service starts correctly",
                "action": "Add /health endpoint to your application",
                "implementation": "code_snippet"
            })
        
        return recommendations
    
    def _suggest_configs(self, analysis: Dict) -> List[Dict]:
        """Suggest concrete execution configurations"""
        
        suggestions = []
        
        # Suggest service config for web frameworks
        if analysis.get("framework") in ["flask", "fastapi"]:
            entry_point = analysis["entry_points"][0] if analysis["entry_points"] else "app.py"
            
            config = ExecutionConfig(
                enabled=True,
                strategy=ExecutionStrategy.SERVICE,
                command="python",
                args=[entry_point],
                startup_wait=5,
                health_check={
                    "type": "http",
                    "url": "http://localhost:5000/health",
                    "expected_status": 200
                },
                description=f"{analysis['framework']} service validation"
            )
            
            suggestions.append({
                "name": "service_validation",
                "description": f"Validate {analysis['framework']} service starts and responds",
                "config": config.dict()
            })
        
        # Suggest test config
        if analysis["has_tests"]:
            test_fw = analysis.get("test_framework", "pytest")
            
            config = ExecutionConfig(
                enabled=True,
                strategy=ExecutionStrategy.TEST,
                test_command=test_fw,
                test_framework=test_fw,
                test_timeout=300,
                success_if={
                    "exit_code": 0,
                    "test_pass_rate": 1.0
                },
                description=f"Run {test_fw} test suite"
            )
            
            suggestions.append({
                "name": "test_execution",
                "description": f"Run {test_fw} tests automatically",
                "config": config.dict()
            })
        
        # Suggest script execution for CLI tools
        if analysis["has_entry_point"] and not analysis.get("framework"):
            entry_point = analysis["entry_points"][0] if analysis["entry_points"] else "main.py"
            
            config = ExecutionConfig(
                enabled=True,
                strategy=ExecutionStrategy.SCRIPT,
                command="python" if entry_point.endswith(".py") else "node",
                args=[entry_point, "--help"],  # Safe default
                timeout=30,
                success_if={"exit_code": 0},
                description="Basic script execution validation"
            )
            
            suggestions.append({
                "name": "script_validation",
                "description": "Validate script runs without errors",
                "config": config.dict()
            })
        
        return suggestions
    
    async def apply_recommended_config(
        self,
        repo_id: str,
        config_name: str
    ) -> Dict:
        """Apply a recommended execution configuration to repository"""
        
        # Get analysis
        analysis_result = await self.analyze_repository_execution_needs(repo_id)
        
        if not analysis_result.get("suggested_configs"):
            return {"success": False, "error": "No configurations available"}
        
        # Find the requested config
        selected_config = None
        for suggestion in analysis_result["suggested_configs"]:
            if suggestion["name"] == config_name:
                selected_config = suggestion["config"]
                break
        
        if not selected_config:
            return {"success": False, "error": f"Configuration '{config_name}' not found"}
        
        # Create execution profile
        profile = RepositoryExecutionProfile(
            repo_id=repo_id,
            default_config=ExecutionConfig(**selected_config),
            project_type=analysis_result.get("detected_type"),
            framework=analysis_result.get("framework"),
            has_tests=analysis_result.get("has_tests", False),
            test_framework=analysis_result.get("test_framework"),
            created_at=self._now_iso(),
            updated_at=self._now_iso()
        )
        
        # Store in repository
        self.repo_store.update(repo_id, {
            "execution_profile": profile.dict()
        })
        
        return {
            "success": True,
            "message": f"Applied {config_name} configuration",
            "profile": profile.dict()
        }
    
    def _now_iso(self) -> str:
        """Get current time as ISO string"""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"


# Integration point for Product Analysis
def add_execution_config_analysis_to_product_analysis(product_analysis_results: Dict, analyzer: ExecutionConfigAnalyzer, repo_id: str) -> Dict:
    """
    Add execution configuration recommendations to Product Analysis
    
    Call this from your Product Analysis route/function
    """
    import asyncio
    
    # Run async analysis
    loop = asyncio.get_event_loop()
    execution_analysis = loop.run_until_complete(
        analyzer.analyze_repository_execution_needs(repo_id)
    )
    
    # Add to product analysis results
    if execution_analysis.get("needs_config"):
        product_analysis_results.setdefault("recommendations", []).extend(
            execution_analysis.get("recommendations", [])
        )
        
        product_analysis_results["execution_config"] = {
            "status": "missing",
            "confidence": execution_analysis.get("confidence"),
            "detected_type": execution_analysis.get("detected_type"),
            "suggested_configs": execution_analysis.get("suggested_configs", [])
        }
    else:
        product_analysis_results["execution_config"] = {
            "status": "configured" if execution_analysis.get("has_config") else "not_needed",
            "message": execution_analysis.get("message", "")
        }
    
    return product_analysis_results