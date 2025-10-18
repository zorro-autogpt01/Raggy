"""
Execution Configuration Models for Test Runner
These define how code should be validated after syntax/build checks
"""
from pydantic import BaseModel, Field
from typing import Optional, Literal, Dict, List
from enum import Enum


class ExecutionStrategy(str, Enum):
    """Types of execution strategies"""
    NONE = "none"              # No execution
    SCRIPT = "script"          # Run and expect exit
    SERVICE = "service"        # Start and health check
    TEST = "test"              # Run test suite
    DAEMON = "daemon"          # Long-running process


class HealthCheckConfig(BaseModel):
    """Health check configuration for services"""
    type: Literal["http", "tcp", "command"] = "http"
    url: Optional[str] = None                          # For HTTP checks
    host: Optional[str] = None                         # For TCP checks
    port: Optional[int] = None                         # For TCP checks
    command: Optional[str] = None                      # For command checks
    expected_status: Optional[int] = 200               # For HTTP
    expected_body_contains: Optional[List[str]] = None # For HTTP
    timeout: int = 10


class SuccessCriteria(BaseModel):
    """Criteria to determine if execution was successful"""
    exit_code: Optional[int] = None                    # Expected exit code
    exit_code_not: Optional[List[int]] = None          # Disallowed exit codes
    stdout_contains: Optional[List[str]] = None        # Must contain these
    stdout_not_contains: Optional[List[str]] = None    # Must NOT contain these
    stderr_empty: Optional[bool] = None                # Stderr must be empty
    stderr_contains: Optional[List[str]] = None        # Stderr must contain
    runs_for_at_least: Optional[int] = None            # Minimum runtime (seconds)
    health_check_passes: Optional[bool] = None         # Health check must pass
    test_pass_rate: Optional[float] = None             # Min % of tests passing


class ExecutionConfig(BaseModel):
    """Complete execution configuration"""
    enabled: bool = False
    strategy: ExecutionStrategy = ExecutionStrategy.NONE
    
    # Command execution
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[Dict[str, str]] = None
    working_dir: Optional[str] = None
    timeout: int = 30
    expect_exit: bool = True
    
    # Service configuration
    startup_wait: Optional[int] = None
    health_check: Optional[HealthCheckConfig] = None
    shutdown_command: Optional[str] = None
    shutdown_timeout: int = 10
    
    # Test configuration
    test_command: Optional[str] = None
    test_framework: Optional[str] = None  # pytest, jest, junit, etc.
    test_timeout: int = 300
    
    # Success criteria
    success_if: Optional[SuccessCriteria] = None
    
    # Metadata
    description: Optional[str] = None
    tags: Optional[List[str]] = None


class ExecutionResult(BaseModel):
    """Result of code execution"""
    strategy: ExecutionStrategy
    success: bool
    
    # Basic execution data
    exit_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    runtime_seconds: Optional[float] = None
    
    # Service data
    service_started: Optional[bool] = None
    health_check_passed: Optional[bool] = None
    health_check_response: Optional[str] = None
    
    # Test data
    tests_run: Optional[int] = None
    tests_passed: Optional[int] = None
    tests_failed: Optional[int] = None
    test_output: Optional[str] = None
    
    # Error information
    error: Optional[str] = None
    error_details: Optional[str] = None
    
    # Criteria evaluation
    criteria_met: Optional[Dict[str, bool]] = None


# Repository execution profiles
class RepositoryExecutionProfile(BaseModel):
    """Execution configuration stored per repository"""
    repo_id: str
    
    # Default execution config for the repo
    default_config: ExecutionConfig
    
    # File-pattern specific configs
    # e.g., "*.py" -> script strategy, "app.py" -> service strategy
    pattern_configs: Optional[Dict[str, ExecutionConfig]] = None
    
    # Project metadata
    project_type: Optional[str] = None  # "web_service", "cli_tool", "library", etc.
    framework: Optional[str] = None     # "flask", "fastapi", "express", etc.
    
    # Auto-detected capabilities
    has_tests: bool = False
    test_framework: Optional[str] = None
    has_requirements: bool = False
    has_dockerfile: bool = False
    
    # Timestamps
    created_at: str
    updated_at: str
    last_analyzed_at: Optional[str] = None


# Example configs for common scenarios
EXAMPLE_CONFIGS = {
    "python_script": ExecutionConfig(
        enabled=True,
        strategy=ExecutionStrategy.SCRIPT,
        command="python",
        args=["main.py"],
        timeout=30,
        expect_exit=True,
        success_if=SuccessCriteria(
            exit_code=0,
            stderr_empty=False  # Warnings OK
        ),
        description="Standard Python script execution"
    ),
    
    "flask_service": ExecutionConfig(
        enabled=True,
        strategy=ExecutionStrategy.SERVICE,
        command="python",
        args=["app.py"],
        startup_wait=5,
        health_check=HealthCheckConfig(
            type="http",
            url="http://localhost:5000/health",
            expected_status=200
        ),
        shutdown_command="pkill -f app.py",
        success_if=SuccessCriteria(
            health_check_passes=True
        ),
        description="Flask web service with health check"
    ),
    
    "pytest_tests": ExecutionConfig(
        enabled=True,
        strategy=ExecutionStrategy.TEST,
        test_command="pytest",
        args=["-v", "tests/"],
        test_framework="pytest",
        test_timeout=300,
        success_if=SuccessCriteria(
            exit_code=0,
            test_pass_rate=1.0  # 100% pass rate
        ),
        description="Run pytest test suite"
    ),
    
    "nodejs_cli": ExecutionConfig(
        enabled=True,
        strategy=ExecutionStrategy.SCRIPT,
        command="node",
        args=["index.js", "--help"],
        timeout=10,
        success_if=SuccessCriteria(
            exit_code=0,
            stdout_contains=["Usage:"]
        ),
        description="Node.js CLI tool execution"
    )
}