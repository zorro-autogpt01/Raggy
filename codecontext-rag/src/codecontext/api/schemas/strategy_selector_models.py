"""
Strategy Selector Models
Data structures for strategy selection decisions
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from enum import Enum


class StrategyType(str, Enum):
    """Available execution strategies"""
    DIRECT = "direct"      # Strategy A: Direct commit to main
    BRANCH = "branch"      # Strategy C: Branch-based workflow


class DecisionReason(str, Enum):
    """Reasons for strategy decisions"""
    # Direct reasons
    SIMPLE_CHANGE = "simple_change"
    LOW_RISK = "low_risk"
    SINGLE_FILE = "single_file"
    DOCUMENTATION = "documentation"
    
    # Branch reasons
    COMPLEX_CHANGE = "complex_change"
    BREAKING_CHANGE = "breaking_change"
    MANY_FILES = "many_files"
    DATABASE_MIGRATION = "database_migration"
    CROSS_CUTTING = "cross_cutting"
    HIGH_RISK = "high_risk"
    USER_OVERRIDE = "user_override"


class StrategySelectionRequest(BaseModel):
    """Request for strategy selection"""
    
    # From task analyzer (can pass the whole analysis)
    task_type: str
    complexity: str
    impact: str
    estimated_file_count: int
    is_breaking_change: bool = False
    needs_database_migration: bool = False
    confidence_score: float
    
    # Optional overrides
    preferred_strategy: Optional[StrategyType] = None
    force_strategy: bool = False  # If true, ignore rules and use preferred
    
    # Context
    repo_id: str
    task_description: str


class DecisionRule(BaseModel):
    """A single decision rule"""
    name: str
    condition: str
    suggested_strategy: StrategyType
    priority: int = Field(ge=1, le=10, description="1=lowest, 10=highest")
    reasoning: str


class StrategyDecision(BaseModel):
    """The final strategy decision with reasoning"""
    
    strategy: StrategyType
    confidence: float = Field(ge=0.0, le=1.0)
    
    # Reasoning
    primary_reason: DecisionReason
    contributing_factors: List[str] = Field(default_factory=list)
    
    # Rules that fired
    rules_applied: List[str] = Field(default_factory=list)
    rules_considered: int = 0
    
    # Risk assessment
    estimated_risk_level: Literal["low", "medium", "high"] = "medium"
    risk_factors: List[str] = Field(default_factory=list)
    
    # Alternative suggestion
    alternative_strategy: Optional[StrategyType] = None
    alternative_reasoning: Optional[str] = None
    
    # Human-readable explanation
    explanation: str
    recommendation: str


class StrategySelectionResponse(BaseModel):
    """Response from strategy selector"""
    success: bool
    decision: Optional[StrategyDecision] = None
    error: Optional[str] = None
    
    # Metadata
    decision_timestamp: Optional[str] = None
    selector_version: str = "1.0.0"


# Built-in decision rules
DECISION_RULES = [
    DecisionRule(
        name="force_branch_breaking",
        condition="is_breaking_change == True",
        suggested_strategy=StrategyType.BRANCH,
        priority=10,
        reasoning="Breaking changes must go through branch workflow for review"
    ),
    DecisionRule(
        name="force_branch_migration",
        condition="needs_database_migration == True",
        suggested_strategy=StrategyType.BRANCH,
        priority=10,
        reasoning="Database migrations require careful review and testing"
    ),
    DecisionRule(
        name="direct_single_file",
        condition="estimated_file_count == 1 and complexity == 'low'",
        suggested_strategy=StrategyType.DIRECT,
        priority=8,
        reasoning="Single file with low complexity is safe for direct commit"
    ),
    DecisionRule(
        name="direct_documentation",
        condition="task_type == 'docs'",
        suggested_strategy=StrategyType.DIRECT,
        priority=7,
        reasoning="Documentation changes are typically low risk"
    ),
    DecisionRule(
        name="branch_many_files",
        condition="estimated_file_count > 10",
        suggested_strategy=StrategyType.BRANCH,
        priority=9,
        reasoning="Changes to many files require comprehensive review"
    ),
    DecisionRule(
        name="branch_high_complexity",
        condition="complexity == 'high'",
        suggested_strategy=StrategyType.BRANCH,
        priority=8,
        reasoning="High complexity changes need thorough testing"
    ),
    DecisionRule(
        name="branch_cross_cutting",
        condition="impact == 'cross_cutting' or impact == 'architectural'",
        suggested_strategy=StrategyType.BRANCH,
        priority=9,
        reasoning="Cross-cutting changes affect multiple modules"
    ),
    DecisionRule(
        name="direct_simple_fix",
        condition="task_type == 'fix' and complexity == 'low' and estimated_file_count <= 3",
        suggested_strategy=StrategyType.DIRECT,
        priority=7,
        reasoning="Simple bug fixes can be committed directly"
    ),
    DecisionRule(
        name="direct_low_impact",
        condition="complexity == 'low' and impact == 'isolated' and estimated_file_count <= 3",
        suggested_strategy=StrategyType.DIRECT,
        priority=6,
        reasoning="Low complexity isolated changes are safe"
    ),
    DecisionRule(
        name="branch_medium_complexity",
        condition="complexity == 'medium' and estimated_file_count > 5",
        suggested_strategy=StrategyType.BRANCH,
        priority=6,
        reasoning="Medium complexity with multiple files benefits from review"
    ),
]


def get_rule_by_name(name: str) -> Optional[DecisionRule]:
    """Get a specific rule by name"""
    for rule in DECISION_RULES:
        if rule.name == name:
            return rule
    return None


def get_rules_for_strategy(strategy: StrategyType) -> List[DecisionRule]:
    """Get all rules that suggest a specific strategy"""
    return [rule for rule in DECISION_RULES if rule.suggested_strategy == strategy]


def get_high_priority_rules() -> List[DecisionRule]:
    """Get rules with priority >= 8"""
    return [rule for rule in DECISION_RULES if rule.priority >= 8]