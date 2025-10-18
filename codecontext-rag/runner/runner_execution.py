"""
Runner Execution Engine
Implements different execution strategies based on configuration
"""
import asyncio
import httpx
import socket
import time
from typing import Dict, Optional
from pathlib import Path
import subprocess
import signal

from execution_models import (
    ExecutionConfig, 
    ExecutionResult, 
    ExecutionStrategy,
    HealthCheckConfig,
    SuccessCriteria
)


class ExecutionEngine:
    """Handles code execution based on strategy"""
    
    def __init__(self, container, repo_path: Path, run):
        self.container = container
        self.repo_path = repo_path
        self.run = run
        self.process = None
    
    async def execute(self, config: ExecutionConfig) -> ExecutionResult:
        """Execute code based on strategy"""
        
        if not config.enabled:
            self.run.log("Execution disabled", "INFO")
            return ExecutionResult(
                strategy=ExecutionStrategy.NONE,
                success=True
            )
        
        self.run.log(f"Starting execution with strategy: {config.strategy}", "INFO")
        
        try:
            if config.strategy == ExecutionStrategy.SCRIPT:
                return await self._execute_script(config)
            elif config.strategy == ExecutionStrategy.SERVICE:
                return await self._execute_service(config)
            elif config.strategy == ExecutionStrategy.TEST:
                return await self._execute_tests(config)
            elif config.strategy == ExecutionStrategy.DAEMON:
                return await self._execute_daemon(config)
            else:
                raise ValueError(f"Unknown strategy: {config.strategy}")
        
        except Exception as e:
            self.run.log(f"Execution error: {e}", "ERROR")
            return ExecutionResult(
                strategy=config.strategy,
                success=False,
                error=str(e)
            )
    
    async def _execute_script(self, config: ExecutionConfig) -> ExecutionResult:
        """Execute a script and wait for completion"""
        
        self.run.log("Executing script", "DEBUG")
        
        # Build command
        cmd = self._build_command(config)
        self.run.log(f"Command: {cmd}", "DEBUG")
        
        start_time = time.time()
        
        try:
            # Execute in container
            # Note: Don't override workdir if not specified - use container's default
            exec_kwargs = {
                "environment": config.env or {},
                "demux": True  # Separate stdout/stderr
            }
            
            # Only specify workdir if explicitly provided
            if config.working_dir:
                exec_kwargs["workdir"] = config.working_dir
            
            exit_code, output = self.container.exec_run(cmd, **exec_kwargs)
            
            runtime = time.time() - start_time
            
            stdout = output[0].decode('utf-8', errors='ignore') if output[0] else ""
            stderr = output[1].decode('utf-8', errors='ignore') if output[1] else ""
            
            self.run.log(f"Script completed in {runtime:.2f}s with exit code {exit_code}", "INFO")
            
            # Evaluate success criteria
            success, criteria_met = self._evaluate_criteria(
                config.success_if,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                runtime=runtime
            )
            
            return ExecutionResult(
                strategy=ExecutionStrategy.SCRIPT,
                success=success,
                exit_code=exit_code,
                stdout=stdout[:1000],  # Limit output
                stderr=stderr[:1000],
                runtime_seconds=runtime,
                criteria_met=criteria_met
            )
        
        except Exception as e:
            return ExecutionResult(
                strategy=ExecutionStrategy.SCRIPT,
                success=False,
                error=str(e),
                runtime_seconds=time.time() - start_time
            )
    
    async def _execute_service(self, config: ExecutionConfig) -> ExecutionResult:
        """Start a service and perform health checks"""
        
        self.run.log("Starting service", "DEBUG")
        
        cmd = self._build_command(config)
        self.run.log(f"Service command: {cmd}", "DEBUG")
        
        start_time = time.time()
        
        try:
            # Start service in background
            exec_create_kwargs = {
                "stdout": True,
                "stderr": True
            }
            
            # Only specify workdir if explicitly provided
            if config.working_dir:
                exec_create_kwargs["workdir"] = config.working_dir
            
            if config.env:
                exec_create_kwargs["environment"] = config.env
            
            exec_id = self.container.client.api.exec_create(
                self.container.id,
                cmd,
                **exec_create_kwargs
            )
            
            self.container.client.api.exec_start(exec_id, detach=True)
            service_started = True
            
            self.run.log(f"Service started, waiting {config.startup_wait}s for startup", "INFO")
            await asyncio.sleep(config.startup_wait or 3)
            
            # Perform health check
            health_passed = False
            health_response = None
            
            if config.health_check:
                self.run.log("Performing health check", "DEBUG")
                health_passed, health_response = await self._health_check(config.health_check)
                
                if health_passed:
                    self.run.log("✅ Health check passed", "INFO")
                else:
                    self.run.log(f"❌ Health check failed: {health_response}", "ERROR")
            
            # Shutdown service
            if config.shutdown_command:
                self.run.log("Shutting down service", "DEBUG")
                self.container.exec_run(config.shutdown_command)
                await asyncio.sleep(1)
            
            runtime = time.time() - start_time
            
            # Evaluate success
            success = health_passed if config.health_check else service_started
            
            return ExecutionResult(
                strategy=ExecutionStrategy.SERVICE,
                success=success,
                service_started=service_started,
                health_check_passed=health_passed,
                health_check_response=health_response,
                runtime_seconds=runtime
            )
        
        except Exception as e:
            return ExecutionResult(
                strategy=ExecutionStrategy.SERVICE,
                success=False,
                service_started=False,
                error=str(e),
                runtime_seconds=time.time() - start_time
            )
    
    async def _execute_tests(self, config: ExecutionConfig) -> ExecutionResult:
        """Run test suite"""
        
        self.run.log(f"Running tests with {config.test_framework or 'default'}", "DEBUG")
        
        cmd = config.test_command
        if config.args:
            cmd += " " + " ".join(config.args)
        
        self.run.log(f"Test command: {cmd}", "DEBUG")
        
        start_time = time.time()
        
        try:
            exec_kwargs = {
                "environment": config.env or {},
                "demux": True
            }
            
            # Only specify workdir if explicitly provided
            if config.working_dir:
                exec_kwargs["workdir"] = config.working_dir
            
            exit_code, output = self.container.exec_run(cmd, **exec_kwargs)
            
            runtime = time.time() - start_time
            
            stdout = output[0].decode('utf-8', errors='ignore') if output[0] else ""
            stderr = output[1].decode('utf-8', errors='ignore') if output[1] else ""
            
            # Parse test results (basic parsing)
            tests_run, tests_passed, tests_failed = self._parse_test_results(
                stdout, 
                config.test_framework
            )
            
            self.run.log(
                f"Tests: {tests_passed}/{tests_run} passed, {tests_failed} failed", 
                "INFO"
            )
            
            # Evaluate success
            success = exit_code == 0 and (
                config.success_if is None or 
                tests_failed == 0 or
                (tests_passed / max(tests_run, 1)) >= (config.success_if.test_pass_rate or 1.0)
            )
            
            return ExecutionResult(
                strategy=ExecutionStrategy.TEST,
                success=success,
                exit_code=exit_code,
                tests_run=tests_run,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                test_output=stdout[:2000],
                runtime_seconds=runtime
            )
        
        except Exception as e:
            return ExecutionResult(
                strategy=ExecutionStrategy.TEST,
                success=False,
                error=str(e),
                runtime_seconds=time.time() - start_time
            )
    
    async def _execute_daemon(self, config: ExecutionConfig) -> ExecutionResult:
        """Start daemon and verify it runs"""
        
        self.run.log("Starting daemon process", "DEBUG")
        
        cmd = self._build_command(config)
        
        start_time = time.time()
        
        try:
            # Start daemon
            exec_create_kwargs = {
                "stdout": True,
                "stderr": True
            }
            
            # Only specify workdir if explicitly provided
            if config.working_dir:
                exec_create_kwargs["workdir"] = config.working_dir
            
            if config.env:
                exec_create_kwargs["environment"] = config.env
            
            exec_id = self.container.client.api.exec_create(
                self.container.id,
                cmd,
                **exec_create_kwargs
            )
            
            self.container.client.api.exec_start(exec_id, detach=True)
            
            # Wait minimum runtime
            min_runtime = config.success_if.runs_for_at_least if config.success_if else 5
            self.run.log(f"Daemon started, verifying it runs for {min_runtime}s", "INFO")
            
            await asyncio.sleep(min_runtime)
            
            # Check if still running
            exec_info = self.container.client.api.exec_inspect(exec_id)
            still_running = exec_info['Running']
            
            runtime = time.time() - start_time
            
            self.run.log(
                f"Daemon {'still running' if still_running else 'stopped'} after {runtime:.1f}s",
                "INFO" if still_running else "ERROR"
            )
            
            return ExecutionResult(
                strategy=ExecutionStrategy.DAEMON,
                success=still_running,
                runtime_seconds=runtime
            )
        
        except Exception as e:
            return ExecutionResult(
                strategy=ExecutionStrategy.DAEMON,
                success=False,
                error=str(e),
                runtime_seconds=time.time() - start_time
            )
    
    async def _health_check(self, config: HealthCheckConfig) -> tuple[bool, Optional[str]]:
        """Perform health check"""
        
        if config.type == "http":
            return await self._http_health_check(config)
        elif config.type == "tcp":
            return await self._tcp_health_check(config)
        elif config.type == "command":
            return await self._command_health_check(config)
        else:
            return False, f"Unknown health check type: {config.type}"
    
    async def _http_health_check(self, config: HealthCheckConfig) -> tuple[bool, Optional[str]]:
        """HTTP health check"""
        try:
            async with httpx.AsyncClient(timeout=config.timeout) as client:
                response = await client.get(config.url)
                
                # Check status code
                if config.expected_status and response.status_code != config.expected_status:
                    return False, f"Status {response.status_code}, expected {config.expected_status}"
                
                # Check body contains
                if config.expected_body_contains:
                    body = response.text
                    for expected in config.expected_body_contains:
                        if expected not in body:
                            return False, f"Body missing: {expected}"
                
                return True, f"Status {response.status_code}"
        
        except Exception as e:
            return False, str(e)
    
    async def _tcp_health_check(self, config: HealthCheckConfig) -> tuple[bool, Optional[str]]:
        """TCP port health check"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(config.timeout)
            result = sock.connect_ex((config.host, config.port))
            sock.close()
            
            if result == 0:
                return True, f"Port {config.port} open"
            else:
                return False, f"Port {config.port} closed"
        
        except Exception as e:
            return False, str(e)
    
    async def _command_health_check(self, config: HealthCheckConfig) -> tuple[bool, Optional[str]]:
        """Command-based health check"""
        try:
            # Use container's default working directory
            exit_code, output = self.container.exec_run(config.command)
            success = exit_code == 0
            message = output.decode('utf-8', errors='ignore')[:200]
            return success, message
        
        except Exception as e:
            return False, str(e)
    
    def _build_command(self, config: ExecutionConfig) -> str:
        """Build command string from config"""
        cmd = config.command
        if config.args:
            cmd += " " + " ".join(config.args)
        return cmd
    
    def _evaluate_criteria(
        self,
        criteria: Optional[SuccessCriteria],
        exit_code: int = None,
        stdout: str = None,
        stderr: str = None,
        runtime: float = None
    ) -> tuple[bool, Dict[str, bool]]:
        """Evaluate success criteria"""
        
        if not criteria:
            # Default: exit code 0
            return exit_code == 0, {"exit_code_0": exit_code == 0}
        
        results = {}
        
        # Check exit code
        if criteria.exit_code is not None:
            results["exit_code_match"] = exit_code == criteria.exit_code
        
        if criteria.exit_code_not:
            results["exit_code_allowed"] = exit_code not in criteria.exit_code_not
        
        # Check stdout
        if criteria.stdout_contains:
            for phrase in criteria.stdout_contains:
                results[f"stdout_contains_{phrase[:20]}"] = phrase in stdout
        
        if criteria.stdout_not_contains:
            for phrase in criteria.stdout_not_contains:
                results[f"stdout_not_contains_{phrase[:20]}"] = phrase not in stdout
        
        # Check stderr
        if criteria.stderr_empty is not None:
            results["stderr_empty"] = (not stderr or len(stderr.strip()) == 0)
        
        if criteria.stderr_contains:
            for phrase in criteria.stderr_contains:
                results[f"stderr_contains_{phrase[:20]}"] = phrase in stderr
        
        # Check runtime
        if criteria.runs_for_at_least is not None:
            results["min_runtime"] = runtime >= criteria.runs_for_at_least
        
        # Overall success: all criteria must pass
        success = all(results.values())
        
        return success, results
    
    def _parse_test_results(self, output: str, framework: Optional[str]) -> tuple[int, int, int]:
        """Parse test results from output"""
        
        # Basic parsing - can be enhanced per framework
        tests_run = 0
        tests_passed = 0
        tests_failed = 0
        
        if framework == "pytest":
            # Look for: "5 passed, 2 failed"
            import re
            passed_match = re.search(r'(\d+) passed', output)
            failed_match = re.search(r'(\d+) failed', output)
            
            if passed_match:
                tests_passed = int(passed_match.group(1))
            if failed_match:
                tests_failed = int(failed_match.group(1))
            tests_run = tests_passed + tests_failed
        
        elif framework == "jest":
            # Look for: "Tests: 2 failed, 5 passed, 7 total"
            import re
            match = re.search(r'Tests:.*?(\d+) passed.*?(\d+) total', output)
            if match:
                tests_passed = int(match.group(1))
                tests_run = int(match.group(2))
                tests_failed = tests_run - tests_passed
        
        return tests_run, tests_passed, tests_failed