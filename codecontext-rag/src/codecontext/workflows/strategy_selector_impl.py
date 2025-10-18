"""
Strategy Selector Implementation
Decision engine for choosing execution strategy
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

from ..api.schemas.strategy_selector_models import (
    StrategySelectionRequest,
    StrategySelectionResponse,
    StrategyDecision,
    StrategyType,
    DecisionReason,
    DECISION_RULES,
    DecisionRule
)

logger = logging.getLogger(__name__)


class StrategySelector:
    """
    Decision engine that chooses between direct and branch-based strategies
    
    Uses a rule-based system with priority scoring to make intelligent decisions
    """
    
    def __init__(self, custom_rules: List[DecisionRule] = None):
        """
        Initialize strategy selector
        
        Args:
            custom_rules: Additional rules beyond the built-in ones
        """
        self.rules = DECISION_RULES.copy()
        if custom_rules:
            self.rules.extend(custom_rules)
        
        # Sort by priority (highest first)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        
        logger.info(f"StrategySelector initialized with {len(self.rules)} rules")
    
    def select_strategy(
        self,
        request: StrategySelectionRequest
    ) -> StrategySelectionResponse:
        """
        Select the appropriate strategy based on task analysis
        
        Args:
            request: Strategy selection request with task details
        
        Returns:
            StrategySelectionResponse with decision and reasoning
        """
        try:
            logger.info(f"Selecting strategy for: {request.task_description[:100]}")
            
            # Step 1: Check for forced strategy
            if request.force_strategy and request.preferred_strategy:
                decision = self._create_forced_decision(request)
                logger.info(f"Forced strategy: {decision.strategy}")
                return StrategySelectionResponse(
                    success=True,
                    decision=decision,
                    decision_timestamp=datetime.utcnow().isoformat() + "Z"
                )
            
            # Step 2: Evaluate all rules
            matching_rules = self._evaluate_rules(request)
            
            # Step 3: Make decision based on rules
            decision = self._make_decision(request, matching_rules)
            
            logger.info(
                f"Strategy selected: {decision.strategy} "
                f"(confidence: {decision.confidence:.2f}, "
                f"rules: {len(matching_rules)})"
            )
            
            return StrategySelectionResponse(
                success=True,
                decision=decision,
                decision_timestamp=datetime.utcnow().isoformat() + "Z"
            )
        
        except Exception as e:
            logger.error(f"Strategy selection failed: {e}", exc_info=True)
            return StrategySelectionResponse(
                success=False,
                error=str(e)
            )
    
    def _evaluate_rules(
        self,
        request: StrategySelectionRequest
    ) -> List[Dict[str, Any]]:
        """
        Evaluate which rules match the current request
        
        Returns:
            List of matching rules with scores
        """
        matching_rules = []
        
        for rule in self.rules:
            try:
                # Build evaluation context
                context = {
                    "task_type": request.task_type,
                    "complexity": request.complexity,
                    "impact": request.impact,
                    "estimated_file_count": request.estimated_file_count,
                    "is_breaking_change": request.is_breaking_change,
                    "needs_database_migration": request.needs_database_migration,
                    "confidence_score": request.confidence_score,
                }
                
                # Evaluate condition
                if self._evaluate_condition(rule.condition, context):
                    matching_rules.append({
                        "rule": rule,
                        "priority": rule.priority,
                        "strategy": rule.suggested_strategy
                    })
                    logger.debug(f"Rule matched: {rule.name} (priority {rule.priority})")
            
            except Exception as e:
                logger.warning(f"Failed to evaluate rule {rule.name}: {e}")
                continue
        
        return matching_rules
    
    def _evaluate_condition(self, condition: str, context: Dict) -> bool:
        """
        Safely evaluate a rule condition
        
        Args:
            condition: Python expression as string
            context: Variables available in the expression
        
        Returns:
            True if condition is met
        """
        try:
            # Safe evaluation with limited context
            return eval(condition, {"__builtins__": {}}, context)
        except Exception as e:
            logger.warning(f"Condition evaluation failed: {condition} - {e}")
            return False
    
    def _make_decision(
        self,
        request: StrategySelectionRequest,
        matching_rules: List[Dict[str, Any]]
    ) -> StrategyDecision:
        """
        Make final strategy decision based on matching rules
        
        Args:
            request: Original request
            matching_rules: Rules that matched
        
        Returns:
            StrategyDecision with full reasoning
        """
        # Count votes for each strategy
        direct_score = 0
        branch_score = 0
        
        direct_rules = []
        branch_rules = []
        
        for match in matching_rules:
            rule = match["rule"]
            priority = match["priority"]
            
            if match["strategy"] == StrategyType.DIRECT:
                direct_score += priority
                direct_rules.append(rule.name)
            else:
                branch_score += priority
                branch_rules.append(rule.name)
        
        # Determine winning strategy
        if branch_score > direct_score:
            chosen_strategy = StrategyType.BRANCH
            winning_rules = branch_rules
            primary_reason = self._determine_primary_reason(matching_rules, StrategyType.BRANCH)
        elif direct_score > branch_score:
            chosen_strategy = StrategyType.DIRECT
            winning_rules = direct_rules
            primary_reason = self._determine_primary_reason(matching_rules, StrategyType.DIRECT)
        else:
            # Tie - use conservative default
            if request.preferred_strategy:
                chosen_strategy = request.preferred_strategy
                winning_rules = direct_rules if chosen_strategy == StrategyType.DIRECT else branch_rules
            else:
                # Default to branch for safety
                chosen_strategy = StrategyType.BRANCH
                winning_rules = branch_rules
            primary_reason = DecisionReason.USER_OVERRIDE if request.preferred_strategy else DecisionReason.HIGH_RISK
        
        # Calculate confidence
        total_score = direct_score + branch_score
        confidence = max(direct_score, branch_score) / total_score if total_score > 0 else 0.5
        
        # Determine risk level
        risk_level = self._assess_risk(request)
        risk_factors = self._identify_risk_factors(request)
        
        # Build explanation
        explanation = self._build_explanation(
            chosen_strategy,
            winning_rules,
            request,
            confidence
        )
        
        # Generate recommendation
        recommendation = self._generate_recommendation(
            chosen_strategy,
            risk_level,
            request
        )
        
        # Alternative strategy (if close decision)
        alternative = None
        alternative_reasoning = None
        if abs(direct_score - branch_score) <= 2 and total_score > 0:
            alternative = StrategyType.DIRECT if chosen_strategy == StrategyType.BRANCH else StrategyType.BRANCH
            alternative_reasoning = f"Close decision (scores: direct={direct_score}, branch={branch_score}). Alternative strategy is viable."
        
        return StrategyDecision(
            strategy=chosen_strategy,
            confidence=min(confidence, 1.0),
            primary_reason=primary_reason,
            contributing_factors=self._get_contributing_factors(request),
            rules_applied=winning_rules,
            rules_considered=len(matching_rules),
            estimated_risk_level=risk_level,
            risk_factors=risk_factors,
            alternative_strategy=alternative,
            alternative_reasoning=alternative_reasoning,
            explanation=explanation,
            recommendation=recommendation
        )
    
    def _determine_primary_reason(
        self,
        matching_rules: List[Dict[str, Any]],
        strategy: StrategyType
    ) -> DecisionReason:
        """Determine the primary reason for choosing this strategy"""
        
        # Get highest priority rule for this strategy
        strategy_rules = [m for m in matching_rules if m["strategy"] == strategy]
        if not strategy_rules:
            return DecisionReason.LOW_RISK if strategy == StrategyType.DIRECT else DecisionReason.HIGH_RISK
        
        highest_priority = max(strategy_rules, key=lambda x: x["priority"])
        rule_name = highest_priority["rule"].name
        
        # Map rule names to reasons
        reason_map = {
            "force_branch_breaking": DecisionReason.BREAKING_CHANGE,
            "force_branch_migration": DecisionReason.DATABASE_MIGRATION,
            "direct_single_file": DecisionReason.SINGLE_FILE,
            "direct_documentation": DecisionReason.DOCUMENTATION,
            "branch_many_files": DecisionReason.MANY_FILES,
            "branch_high_complexity": DecisionReason.COMPLEX_CHANGE,
            "branch_cross_cutting": DecisionReason.CROSS_CUTTING,
            "direct_simple_fix": DecisionReason.SIMPLE_CHANGE,
            "direct_low_impact": DecisionReason.LOW_RISK,
        }
        
        return reason_map.get(rule_name, DecisionReason.LOW_RISK if strategy == StrategyType.DIRECT else DecisionReason.HIGH_RISK)
    
    def _assess_risk(self, request: StrategySelectionRequest) -> str:
        """Assess overall risk level"""
        
        if request.is_breaking_change or request.needs_database_migration:
            return "high"
        
        if request.complexity == "high" or request.impact in ["cross_cutting", "architectural"]:
            return "high"
        
        if request.complexity == "medium" or request.estimated_file_count > 5:
            return "medium"
        
        return "low"
    
    def _identify_risk_factors(self, request: StrategySelectionRequest) -> List[str]:
        """Identify specific risk factors"""
        factors = []
        
        if request.is_breaking_change:
            factors.append("Breaking change affects existing functionality")
        
        if request.needs_database_migration:
            factors.append("Database migration requires careful planning")
        
        if request.estimated_file_count > 10:
            factors.append(f"Large number of files affected ({request.estimated_file_count})")
        
        if request.complexity == "high":
            factors.append("High complexity increases risk of bugs")
        
        if request.impact in ["cross_cutting", "architectural"]:
            factors.append("Cross-cutting changes affect multiple modules")
        
        if request.confidence_score < 0.7:
            factors.append(f"Lower confidence in analysis ({request.confidence_score:.2f})")
        
        return factors if factors else ["No significant risk factors identified"]
    
    def _get_contributing_factors(self, request: StrategySelectionRequest) -> List[str]:
        """Get contributing factors to the decision"""
        factors = []
        
        factors.append(f"Task type: {request.task_type}")
        factors.append(f"Complexity: {request.complexity}")
        factors.append(f"Impact: {request.impact}")
        factors.append(f"Files affected: {request.estimated_file_count}")
        
        if request.is_breaking_change:
            factors.append("Breaking change")
        
        if request.needs_database_migration:
            factors.append("Database migration required")
        
        return factors
    
    def _build_explanation(
        self,
        strategy: StrategyType,
        rules: List[str],
        request: StrategySelectionRequest,
        confidence: float
    ) -> str:
        """Build human-readable explanation"""
        
        strategy_name = "direct commit" if strategy == StrategyType.DIRECT else "branch-based workflow"
        
        explanation = f"Selected {strategy_name} strategy based on:\n"
        explanation += f"- Task: {request.task_type} with {request.complexity} complexity\n"
        explanation += f"- Impact: {request.impact} ({request.estimated_file_count} files)\n"
        explanation += f"- Confidence: {confidence:.0%}\n"
        
        if rules:
            explanation += f"\nDecision rules applied:\n"
            for rule_name in rules[:3]:  # Top 3 rules
                explanation += f"- {rule_name}\n"
        
        return explanation
    
    def _generate_recommendation(
        self,
        strategy: StrategyType,
        risk_level: str,
        request: StrategySelectionRequest
    ) -> str:
        """Generate actionable recommendation"""
        
        if strategy == StrategyType.DIRECT:
            if risk_level == "low":
                return "✅ Safe for direct commit. Changes are isolated and low-risk."
            elif risk_level == "medium":
                return "⚠️  Direct commit acceptable, but ensure tests pass before pushing."
            else:
                return "⚠️  High risk - consider using branch workflow despite recommendation."
        else:
            if risk_level == "high":
                return "🛡️  Branch workflow strongly recommended due to high risk."
            elif risk_level == "medium":
                return "📋 Branch workflow recommended for proper review and testing."
            else:
                return "📋 Branch workflow suggested for additional safety, though risk is low."
    
    def _create_forced_decision(
        self,
        request: StrategySelectionRequest
    ) -> StrategyDecision:
        """Create a decision when strategy is forced by user"""
        
        return StrategyDecision(
            strategy=request.preferred_strategy,
            confidence=1.0,
            primary_reason=DecisionReason.USER_OVERRIDE,
            contributing_factors=["User explicitly selected this strategy"],
            rules_applied=["user_override"],
            rules_considered=0,
            estimated_risk_level=self._assess_risk(request),
            risk_factors=self._identify_risk_factors(request),
            explanation=f"Strategy forced by user preference: {request.preferred_strategy}",
            recommendation="User has overridden automatic strategy selection."
        )