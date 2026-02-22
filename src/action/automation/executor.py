"""
Docker Sandbox Executor - Safe code execution in isolated containers

Features:
- Minimal Alpine-based Docker images
- Resource limits (memory, CPU)
- Network isolation
- Timeout enforcement
- Multi-language support
"""

import asyncio
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


class ExecutionLanguage(str, Enum):
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    BASH = "bash"
    GO = "go"
    RUST = "rust"


class ExecutionStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    KILLED = "killed"


@dataclass
class ExecutionResult:
    """Result from code execution"""
    status: ExecutionStatus
    output: str
    error: str
    exit_code: int
    execution_time: float
    memory_used_mb: float
    cpu_percent: float
    metadata: Dict[str, Any]


@dataclass
class ResourceLimits:
    """Resource limits for execution"""
    max_memory_mb: int = 512
    max_cpu_percent: float = 50.0
    max_execution_time: float = 60.0
    max_output_size_bytes: int = 1024 * 1024
    network_enabled: bool = False
    allowed_domains: List[str] = None
    
    def __post_init__(self):
        if self.allowed_domains is None:
            self.allowed_domains = []


class DockerSandboxExecutor:
    """
    Execute code in isolated Docker containers
    
    Security features:
    - Read-only filesystem
    - No network access (default)
    - Resource limits (CPU, memory)
    - Timeout enforcement
    - Minimal attack surface
    """
    
    DOCKER_IMAGES = {
        ExecutionLanguage.PYTHON: "python:3.11-alpine",
        ExecutionLanguage.JAVASCRIPT: "node:18-alpine",
        ExecutionLanguage.BASH: "alpine:3.18",
        ExecutionLanguage.GO: "golang:1.21-alpine",
        ExecutionLanguage.RUST: "rust:1.75-alpine",
    }
    
    def __init__(
        self,
        docker_available: bool = True,
        workspace_dir: Optional[Path] = None,
    ):
        self.docker_available = docker_available
        self.workspace_dir = workspace_dir or Path(tempfile.gettempdir()) / "ironclaw_sandbox"
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        
        self._execution_history: List[ExecutionResult] = []
    
    async def execute(
        self,
        code: str,
        language: ExecutionLanguage,
        limits: Optional[ResourceLimits] = None,
        files: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> ExecutionResult:
        """
        Execute code in sandbox
        
        Args:
            code: Source code to execute
            language: Programming language
            limits: Resource limits
            files: Additional files to mount {filename: content}
            env_vars: Environment variables
        """
        limits = limits or ResourceLimits()
        files = files or {}
        env_vars = env_vars or {}
        
        if self.docker_available:
            result = await self._execute_docker(code, language, limits, files, env_vars)
        else:
            result = await self._execute_subprocess(code, language, limits, files, env_vars)
        
        self._execution_history.append(result)
        return result
    
    async def _execute_docker(
        self,
        code: str,
        language: ExecutionLanguage,
        limits: ResourceLimits,
        files: Dict[str, str],
        env_vars: Dict[str, str],
    ) -> ExecutionResult:
        """Execute using Docker container"""
        exec_id = str(uuid4())
        exec_dir = self.workspace_dir / exec_id
        exec_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            script_file = self._write_script(exec_dir, code, language)
            
            for filename, content in files.items():
                (exec_dir / filename).write_text(content, encoding="utf-8")
            
            image = self.DOCKER_IMAGES[language]
            
            docker_cmd = [
                "docker", "run",
                "--rm",
                "--read-only",
                f"--memory={limits.max_memory_mb}m",
                f"--cpus={limits.max_cpu_percent / 100}",
                "--pids-limit=50",
                f"--network={'bridge' if limits.network_enabled else 'none'}",
                "-v", f"{exec_dir.absolute()}:/workspace:ro",
                "-w", "/workspace",
            ]
            
            for key, value in env_vars.items():
                docker_cmd.extend(["-e", f"{key}={value}"])
            
            docker_cmd.extend([
                image,
                self._get_executor_command(language, script_file.name),
            ])
            
            start_time = datetime.now()
            
            try:
                process = await asyncio.create_subprocess_exec(
                    *docker_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=limits.max_execution_time,
                )
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                output = stdout.decode("utf-8", errors="ignore")[:limits.max_output_size_bytes]
                error = stderr.decode("utf-8", errors="ignore")[:limits.max_output_size_bytes]
                
                status = (
                    ExecutionStatus.COMPLETED if process.returncode == 0
                    else ExecutionStatus.FAILED
                )
                
                return ExecutionResult(
                    status=status,
                    output=output,
                    error=error,
                    exit_code=process.returncode,
                    execution_time=execution_time,
                    memory_used_mb=0.0,
                    cpu_percent=0.0,
                    metadata={"executor": "docker", "image": image},
                )
                
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except:
                    pass
                
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    output="",
                    error=f"Execution timed out after {limits.max_execution_time}s",
                    exit_code=-1,
                    execution_time=limits.max_execution_time,
                    memory_used_mb=0.0,
                    cpu_percent=0.0,
                    metadata={"executor": "docker", "image": image},
                )
            
        finally:
            try:
                import shutil
                shutil.rmtree(exec_dir)
            except:
                pass
    
    async def _execute_subprocess(
        self,
        code: str,
        language: ExecutionLanguage,
        limits: ResourceLimits,
        files: Dict[str, str],
        env_vars: Dict[str, str],
    ) -> ExecutionResult:
        """Fallback: Execute using subprocess (less secure)"""
        exec_id = str(uuid4())
        exec_dir = self.workspace_dir / exec_id
        exec_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            script_file = self._write_script(exec_dir, code, language)
            
            for filename, content in files.items():
                (exec_dir / filename).write_text(content, encoding="utf-8")
            
            cmd = self._get_executor_command(language, str(script_file))
            
            env = os.environ.copy()
            env.update(env_vars)
            
            start_time = datetime.now()
            
            try:
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=exec_dir,
                    env=env,
                )
                
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=limits.max_execution_time,
                )
                
                execution_time = (datetime.now() - start_time).total_seconds()
                
                output = stdout.decode("utf-8", errors="ignore")[:limits.max_output_size_bytes]
                error = stderr.decode("utf-8", errors="ignore")[:limits.max_output_size_bytes]
                
                status = (
                    ExecutionStatus.COMPLETED if process.returncode == 0
                    else ExecutionStatus.FAILED
                )
                
                return ExecutionResult(
                    status=status,
                    output=output,
                    error=error,
                    exit_code=process.returncode,
                    execution_time=execution_time,
                    memory_used_mb=0.0,
                    cpu_percent=0.0,
                    metadata={"executor": "subprocess", "fallback": True},
                )
                
            except asyncio.TimeoutError:
                try:
                    process.kill()
                    await process.wait()
                except:
                    pass
                
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    output="",
                    error=f"Execution timed out after {limits.max_execution_time}s",
                    exit_code=-1,
                    execution_time=limits.max_execution_time,
                    memory_used_mb=0.0,
                    cpu_percent=0.0,
                    metadata={"executor": "subprocess", "fallback": True},
                )
            
        finally:
            try:
                import shutil
                shutil.rmtree(exec_dir)
            except:
                pass
    
    def _write_script(self, directory: Path, code: str, language: ExecutionLanguage) -> Path:
        """Write code to script file"""
        extensions = {
            ExecutionLanguage.PYTHON: ".py",
            ExecutionLanguage.JAVASCRIPT: ".js",
            ExecutionLanguage.BASH: ".sh",
            ExecutionLanguage.GO: ".go",
            ExecutionLanguage.RUST: ".rs",
        }
        
        script_file = directory / f"script{extensions[language]}"
        script_file.write_text(code, encoding="utf-8")
        
        if language == ExecutionLanguage.BASH:
            script_file.chmod(0o755)
        
        return script_file
    
    def _get_executor_command(self, language: ExecutionLanguage, script_path: str) -> str:
        """Get command to execute script"""
        commands = {
            ExecutionLanguage.PYTHON: f"python {script_path}",
            ExecutionLanguage.JAVASCRIPT: f"node {script_path}",
            ExecutionLanguage.BASH: f"sh {script_path}",
            ExecutionLanguage.GO: f"go run {script_path}",
            ExecutionLanguage.RUST: f"rustc {script_path} && ./script",
        }
        return commands[language]
    
    async def check_docker_available(self) -> bool:
        """Check if Docker is installed and running"""
        try:
            process = await asyncio.create_subprocess_exec(
                "docker", "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await process.communicate()
            return process.returncode == 0
        except:
            return False
    
    async def pull_images(self):
        """Pull all required Docker images"""
        for language, image in self.DOCKER_IMAGES.items():
            try:
                process = await asyncio.create_subprocess_exec(
                    "docker", "pull", image,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await process.communicate()
            except Exception as e:
                print(f"Failed to pull {image}: {e}")
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics"""
        if not self._execution_history:
            return {}
        
        total = len(self._execution_history)
        completed = sum(1 for r in self._execution_history if r.status == ExecutionStatus.COMPLETED)
        failed = sum(1 for r in self._execution_history if r.status == ExecutionStatus.FAILED)
        timeout = sum(1 for r in self._execution_history if r.status == ExecutionStatus.TIMEOUT)
        
        avg_time = sum(r.execution_time for r in self._execution_history) / total
        
        return {
            "total_executions": total,
            "completed": completed,
            "failed": failed,
            "timeout": timeout,
            "success_rate": completed / total if total > 0 else 0,
            "average_execution_time": avg_time,
        }
