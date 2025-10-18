"""
Task Analyzer Models
Defines the data structures for task analysis
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from enum import Enum


class TaskType(str, Enum):
    """Types of tasks that can be requested"""
    FEATURE = "feature"
    REFACTOR = "refactor"
    FIX = "fix"
    TEST = "test"
    DOCS = "docs"
    OPTIMIZATION = "optimization"
    DEPENDENCY = "dependency"


class ComplexityLevel(str, Enum):
    """Complexity levels for tasks"""
    LOW = "low"          # 1-3 files, simple changes
    MEDIUM = "medium"    # 4-10 files, moderate complexity
    HIGH = "high"        # 10+ files or architectural changes


class ImpactLevel(str, Enum):
    """Impact level on codebase"""
    ISOLATED = "isolated"        # Single module/component
    MODULE = "module"            # Multiple related files
    CROSS_CUTTING = "cross_cutting"  # Affects multiple modules
    ARCHITECTURAL = "architectural"  # Fundamental changes


class TaskAnalysisRequest(BaseModel):
    """Request to analyze a task"""
    repo_id: str
    task_description: str
    additional_context: Optional[str] = None


class FileChange(BaseModel):
    """Represents a file that will be modified"""
    path: str
    reason: str
    change_type: Literal["modify", "create", "delete"]
    estimated_lines_changed: Optional[int] = None


class TaskAnalysis(BaseModel):
    """Complete analysis of a task"""
    
    # Basic classification
    task_type: TaskType
    complexity: ComplexityLevel
    impact: ImpactLevel
    
    # File analysis
    files_to_modify: List[FileChange] = Field(default_factory=list)
    estimated_file_count: int
    
    # Change characteristics
    requires_new_files: bool = False
    requires_file_deletion: bool = False
    is_breaking_change: bool = False
    
    # Dependencies
    dependencies: List[str] = Field(
        default_factory=list,
        description="Files/modules that depend on changed code"
    )
    
    # Execution considerations
    needs_database_migration: bool = False
    needs_config_changes: bool = False
    needs_external_service: bool = False
    
    # Testing
    test_strategy: Optional[str] = None
    existing_tests_affected: List[str] = Field(default_factory=list)
    
    # Summary
    summary: str = Field(description="Brief summary of what will be done")
    rationale: str = Field(description="Why this approach was chosen")
    risks: List[str] = Field(
        default_factory=list,
        description="Potential risks or concerns"
    )
    
    # Confidence
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in this analysis (0-1)"
    )
    
    # LLM metadata
    llm_model_used: Optional[str] = None
    analysis_timestamp: Optional[str] = None
    
    def is_simple_change(self) -> bool:
        """Determine if this is a simple change suitable for direct commit"""
        return (
            self.complexity == ComplexityLevel.LOW and
            self.impact == ImpactLevel.ISOLATED and
            not self.is_breaking_change and
            not self.needs_database_migration and
            self.estimated_file_count <= 3
        )
    
    def is_complex_change(self) -> bool:
        """Determine if this needs branch-based workflow"""
        return (
            self.complexity in [ComplexityLevel.MEDIUM, ComplexityLevel.HIGH] or
            self.impact in [ImpactLevel.CROSS_CUTTING, ImpactLevel.ARCHITECTURAL] or
            self.is_breaking_change or
            self.estimated_file_count > 10
        )
    
    def get_risk_summary(self) -> str:
        """Get a summary of risks"""
        if not self.risks:
            return "No significant risks identified"
        return f"{len(self.risks)} risk(s): " + "; ".join(self.risks[:3])


class TaskAnalysisResponse(BaseModel):
    """Response from task analyzer"""
    success: bool
    analysis: Optional[TaskAnalysis] = None
    error: Optional[str] = None
    suggested_strategy: Optional[Literal["direct", "branch"]] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "analysis": {
                    "task_type": "feature",
                    "complexity": "low",
                    "impact": "isolated",
                    "files_to_modify": [
                        {
                            "path": "src/api/routes.py",
                            "reason": "Add new endpoint",
                            "change_type": "modify",
                            "estimated_lines_changed": 15
                        }
                    ],
                    "estimated_file_count": 1,
                    "summary": "Add new API endpoint for user profiles",
                    "rationale": "Simple single-file change",
                    "confidence_score": 0.9
                },
                "suggested_strategy": "direct"
            }
        }


# Analysis Prompt Templates
TASK_ANALYSIS_SYSTEM_PROMPT = """You are an expert software architect analyzing code change requests.

Your job is to analyze a task description and determine:
1. What type of change it is (feature, fix, refactor, etc.)
2. How complex the change will be
3. Which files will need to be modified
4. What the impact will be on the codebase
5. Any risks or concerns

Be thorough but concise. Focus on actionable insights.

Always respond with valid JSON matching the TaskAnalysis schema."""


def create_task_analysis_prompt(
    task_description: str,
    repo_context: Optional[str] = None,
    file_list: Optional[List[str]] = None
) -> str:
    """Create a prompt for task analysis"""
    
    prompt = f"""Analyze this task request:

## Task Description
{task_description}
"""
    
    if repo_context:
        prompt += f"""
## Repository Context
{repo_context}
"""
    
    if file_list:
        prompt += f"""
## Available Files
{chr(10).join(f"- {f}" for f in file_list[:50])}
{f"... and {len(file_list) - 50} more files" if len(file_list) > 50 else ""}
"""
    
    prompt += """
## Analysis Required

Provide a detailed analysis including:

1. **Task Classification**
   - Type (feature/fix/refactor/etc.)
   - Complexity (low/medium/high)
   - Impact (isolated/module/cross-cutting/architectural)

2. **File Analysis**
   - Which files need to be modified
   - Why each file needs changes
   - Estimated lines changed per file
   - Any new files needed

3. **Dependencies**
   - Files that depend on the changed code
   - External dependencies affected

4. **Risks**
   - Potential breaking changes
   - Areas of concern
   - Testing requirements

5. **Summary**
   - Brief description of the approach
   - Rationale for the strategy
   - Confidence in this analysis (0-1)

Respond with a JSON object matching this schema:
```json
{
  "task_type": "feature|fix|refactor|test|docs|optimization|dependency",
  "complexity": "low|medium|high",
  "impact": "isolated|module|cross_cutting|architectural",
  "files_to_modify": [
    {
      "path": "path/to/file.py",
      "reason": "Why this file needs changes",
      "change_type": "modify|create|delete",
      "estimated_lines_changed": 10
    }
  ],
  "estimated_file_count": 1,
  "requires_new_files": false,
  "requires_file_deletion": false,
  "is_breaking_change": false,
  "dependencies": ["file1.py", "file2.py"],
  "needs_database_migration": false,
  "needs_config_changes": false,
  "needs_external_service": false,
  "test_strategy": "Unit tests for new endpoint",
  "existing_tests_affected": ["test_api.py"],
  "summary": "Brief summary of changes",
  "rationale": "Why this approach",
  "risks": ["Potential risk 1", "Potential risk 2"],
  "confidence_score": 0.85
}
```

Be realistic and thorough. It's better to overestimate complexity than underestimate."""
    
    return prompt