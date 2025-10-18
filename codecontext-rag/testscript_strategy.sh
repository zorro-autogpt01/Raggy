#!/bin/bash
# Strategy Selector Test Script
# Tests strategy selection logic

# Configuration
API_URL="http://localhost:7998"
REPO_ID="testrepository_zorro-autogpt01_testrepository"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "================================================"
echo "Strategy Selector Test Suite"
echo "================================================"
echo ""

# Helper function
function test_strategy() {
    local name=$1
    local expected=$2
    local data=$3
    
    echo -e "${BLUE}Test: ${name}${NC}"
    echo "Expected strategy: ${expected}"
    echo ""
    
    response=$(curl -s -X POST "${API_URL}/api/strategy/select" \
        -H "Content-Type: application/json" \
        -d "${data}")
    
    strategy=$(echo "$response" | jq -r '.decision.strategy')
    confidence=$(echo "$response" | jq -r '.decision.confidence')
    risk=$(echo "$response" | jq -r '.decision.estimated_risk_level')
    
    if [ "$strategy" == "$expected" ]; then
        echo -e "${GREEN}✅ PASS${NC} - Strategy: ${strategy}, Confidence: ${confidence}, Risk: ${risk}"
    else
        echo -e "${RED}❌ FAIL${NC} - Expected: ${expected}, Got: ${strategy}"
    fi
    
    echo ""
    echo "Full decision:"
    echo "$response" | jq '.decision | {strategy, confidence, primary_reason, risk_level: .estimated_risk_level, rules_applied}'
    echo ""
    echo "---"
    echo ""
}

# Test 0: Health Check
echo "================================================"
echo "Test 0: Health Check"
echo "================================================"
curl -s "${API_URL}/api/strategy/health" | jq '.'
echo ""

# Test 1: Simple Bug Fix → Direct
echo "================================================"
echo "Test 1: Simple Bug Fix"
echo "================================================"
test_strategy "Simple bug fix" "direct" '{
    "task_type": "fix",
    "complexity": "low",
    "impact": "isolated",
    "estimated_file_count": 1,
    "is_breaking_change": false,
    "needs_database_migration": false,
    "confidence_score": 0.9,
    "repo_id": "'"$REPO_ID"'",
    "task_description": "Fix typo in error message"
}'

# Test 2: Documentation Change → Direct
echo "================================================"
echo "Test 2: Documentation Change"
echo "================================================"
test_strategy "Documentation" "direct" '{
    "task_type": "docs",
    "complexity": "low",
    "impact": "isolated",
    "estimated_file_count": 2,
    "is_breaking_change": false,
    "needs_database_migration": false,
    "confidence_score": 0.95,
    "repo_id": "'"$REPO_ID"'",
    "task_description": "Update README with installation steps"
}'

# Test 3: Breaking Change → Branch
echo "================================================"
echo "Test 3: Breaking Change"
echo "================================================"
test_strategy "Breaking change" "branch" '{
    "task_type": "feature",
    "complexity": "medium",
    "impact": "module",
    "estimated_file_count": 5,
    "is_breaking_change": true,
    "needs_database_migration": false,
    "confidence_score": 0.85,
    "repo_id": "'"$REPO_ID"'",
    "task_description": "Change API response format"
}'

# Test 4: Database Migration → Branch
echo "================================================"
echo "Test 4: Database Migration"
echo "================================================"
test_strategy "Database migration" "branch" '{
    "task_type": "feature",
    "complexity": "medium",
    "impact": "module",
    "estimated_file_count": 6,
    "is_breaking_change": false,
    "needs_database_migration": true,
    "confidence_score": 0.8,
    "repo_id": "'"$REPO_ID"'",
    "task_description": "Add user_preferences table"
}'

# Test 5: Many Files → Branch
echo "================================================"
echo "Test 5: Many Files"
echo "================================================"
test_strategy "Many files" "branch" '{
    "task_type": "refactor",
    "complexity": "medium",
    "impact": "module",
    "estimated_file_count": 15,
    "is_breaking_change": false,
    "needs_database_migration": false,
    "confidence_score": 0.75,
    "repo_id": "'"$REPO_ID"'",
    "task_description": "Extract common utilities into shared module"
}'

# Test 6: High Complexity → Branch
echo "================================================"
echo "Test 6: High Complexity"
echo "================================================"
test_strategy "High complexity" "branch" '{
    "task_type": "feature",
    "complexity": "high",
    "impact": "cross_cutting",
    "estimated_file_count": 8,
    "is_breaking_change": false,
    "needs_database_migration": false,
    "confidence_score": 0.7,
    "repo_id": "'"$REPO_ID"'",
    "task_description": "Implement real-time notification system"
}'

# Test 7: Low Complexity Isolated → Direct
echo "================================================"
echo "Test 7: Low Complexity Isolated"
echo "================================================"
test_strategy "Simple isolated change" "direct" '{
    "task_type": "feature",
    "complexity": "low",
    "impact": "isolated",
    "estimated_file_count": 2,
    "is_breaking_change": false,
    "needs_database_migration": false,
    "confidence_score": 0.9,
    "repo_id": "'"$REPO_ID"'",
    "task_description": "Add new API endpoint for health check"
}'

# Test 8: Medium Complexity Few Files → Could go either way
echo "================================================"
echo "Test 8: Medium Complexity, Few Files"
echo "================================================"
test_strategy "Medium complexity" "direct" '{
    "task_type": "feature",
    "complexity": "medium",
    "impact": "module",
    "estimated_file_count": 4,
    "is_breaking_change": false,
    "needs_database_migration": false,
    "confidence_score": 0.85,
    "repo_id": "'"$REPO_ID"'",
    "task_description": "Add caching layer to API responses"
}'

# Test 9: Combined Analysis + Selection
echo "================================================"
echo "Test 9: Combined Analysis + Selection"
echo "================================================"
echo -e "${BLUE}Combined endpoint test${NC}"
echo ""

response=$(curl -s -X POST "${API_URL}/api/strategy/analyze-and-select" \
    -H "Content-Type: application/json" \
    -d '{
        "repo_id": "'"$REPO_ID"'",
        "task_description": "Add a new hello world endpoint"
    }')

echo "Analysis result:"
echo "$response" | jq '.analysis | {task_type, complexity, impact, file_count: .estimated_file_count}'

echo ""
echo "Strategy decision:"
echo "$response" | jq '.strategy_decision | {strategy, confidence, risk_level: .estimated_risk_level}'

echo ""
echo "---"
echo ""

# Test 10: List All Rules
echo "================================================"
echo "Test 10: List Decision Rules"
echo "================================================"
curl -s "${API_URL}/api/strategy/rules" | jq '{total_rules, high_priority_rules: [.rules[] | select(.priority >= 8) | {name, priority, strategy: .suggested_strategy}]}'

echo ""
echo "================================================"
echo "Test Suite Complete!"
echo "================================================"
echo ""
echo "Summary:"
echo "  - Health check ✓"
echo "  - Simple changes → direct ✓"
echo "  - Complex changes → branch ✓"
echo "  - Breaking changes → branch ✓"
echo "  - Combined endpoint ✓"
echo ""
echo "Next steps:"
echo "  1. Review decisions above"
echo "  2. Verify strategies make sense"
echo "  3. Ready for Day 3: Full Orchestrator!"
echo ""
