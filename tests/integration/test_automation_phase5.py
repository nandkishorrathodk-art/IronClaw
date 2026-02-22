"""
Phase 5 Integration Tests - Execution Engine & Safe Automation

Tests for:
- Workflow DAG engine
- Docker sandbox executor
- Desktop automation
- Browser automation
- Permission system
- Rollback capabilities
"""

import asyncio
import pytest
from pathlib import Path
from typing import Dict, Any

from src.action.automation import (
    BrowserAutomation,
    BrowserType,
    ConditionOperator,
    DesktopAutomation,
    DockerSandboxExecutor,
    ExecutionLanguage,
    ExtractionRule,
    FormField,
    KeyModifier,
    MouseButton,
    PermissionManager,
    ResourceLimits,
    RollbackManager,
    TaskCondition,
    WaitCondition,
    WindowManager,
    WorkflowBuilder,
    WorkflowEngine,
    ActionType as PermissionActionType,
    ActionType as RollbackActionType,
)


class TestWorkflowEngine:
    """Test workflow DAG engine"""
    
    @pytest.mark.asyncio
    async def test_simple_workflow(self):
        """Test simple linear workflow"""
        engine = WorkflowEngine()
        
        results = []
        
        async def task_a():
            results.append("A")
            return "result_a"
        
        async def task_b():
            results.append("B")
            return "result_b"
        
        engine.register_executor("test.task_a", task_a)
        engine.register_executor("test.task_b", task_b)
        
        builder = WorkflowBuilder("Test Workflow")
        task_a_id = builder.add_task("Task A", "test.task_a")
        task_b_id = builder.add_task("Task B", "test.task_b", dependencies=[task_a_id])
        workflow = builder.build()
        
        context = await engine.execute_workflow(workflow)
        
        assert results == ["A", "B"]
        assert context["task_" + task_a_id + "_result"] == "result_a"
        assert context["task_" + task_b_id + "_result"] == "result_b"
    
    @pytest.mark.asyncio
    async def test_parallel_workflow(self):
        """Test parallel task execution"""
        engine = WorkflowEngine()
        
        async def task_slow():
            await asyncio.sleep(0.1)
            return "slow"
        
        async def task_fast():
            await asyncio.sleep(0.01)
            return "fast"
        
        engine.register_executor("test.slow", task_slow)
        engine.register_executor("test.fast", task_fast)
        
        builder = WorkflowBuilder("Parallel Workflow")
        slow_id = builder.add_task("Slow Task", "test.slow")
        fast_id = builder.add_task("Fast Task", "test.fast")
        workflow = builder.build()
        
        import time
        start = time.time()
        context = await engine.execute_workflow(workflow)
        duration = time.time() - start
        
        assert duration < 0.2
        assert context["task_" + slow_id + "_result"] == "slow"
        assert context["task_" + fast_id + "_result"] == "fast"
    
    @pytest.mark.asyncio
    async def test_conditional_workflow(self):
        """Test conditional task execution"""
        engine = WorkflowEngine()
        
        executed = []
        
        async def set_value():
            executed.append("set_value")
            return True
        
        async def conditional_task():
            executed.append("conditional_task")
            return "executed"
        
        engine.register_executor("test.set_value", set_value)
        engine.register_executor("test.conditional", conditional_task)
        
        builder = WorkflowBuilder("Conditional Workflow")
        set_id = builder.add_task("Set Value", "test.set_value")
        
        condition = TaskCondition(
            operator=ConditionOperator.EQUALS,
            left_value=f"$task_{set_id}_result",
            right_value=True,
        )
        
        cond_id = builder.add_task(
            "Conditional Task",
            "test.conditional",
            dependencies=[set_id],
            condition=condition,
        )
        workflow = builder.build()
        
        context = await engine.execute_workflow(workflow)
        
        assert "set_value" in executed
        assert "conditional_task" in executed


class TestDockerSandboxExecutor:
    """Test Docker sandbox executor"""
    
    @pytest.mark.asyncio
    async def test_python_execution(self):
        """Test Python code execution"""
        executor = DockerSandboxExecutor(docker_available=False)
        
        code = "print('Hello, World!')"
        
        result = await executor.execute(
            code=code,
            language=ExecutionLanguage.PYTHON,
        )
        
        assert "Hello, World!" in result.output
        assert result.exit_code == 0
    
    @pytest.mark.asyncio
    async def test_execution_timeout(self):
        """Test execution timeout enforcement"""
        executor = DockerSandboxExecutor(docker_available=False)
        
        code = """
import time
time.sleep(10)
print("Should not reach here")
"""
        
        limits = ResourceLimits(max_execution_time=1.0)
        
        result = await executor.execute(
            code=code,
            language=ExecutionLanguage.PYTHON,
            limits=limits,
        )
        
        assert result.status.value == "timeout"
        assert result.execution_time <= 2.0
    
    @pytest.mark.asyncio
    async def test_multi_language_execution(self):
        """Test execution of multiple languages"""
        executor = DockerSandboxExecutor(docker_available=False)
        
        test_cases = [
            (ExecutionLanguage.PYTHON, "print('Python')"),
            (ExecutionLanguage.JAVASCRIPT, "console.log('JavaScript')"),
            (ExecutionLanguage.BASH, "echo 'Bash'"),
        ]
        
        for language, code in test_cases:
            result = await executor.execute(
                code=code,
                language=language,
            )
            
            assert result.exit_code == 0
            assert result.status.value == "completed"


class TestDesktopAutomation:
    """Test desktop automation"""
    
    @pytest.mark.asyncio
    async def test_mouse_position(self):
        """Test getting mouse position"""
        automation = DesktopAutomation()
        
        position = await automation.get_mouse_position()
        
        assert position.x >= 0
        assert position.y >= 0
    
    @pytest.mark.asyncio
    async def test_screen_size(self):
        """Test getting screen size"""
        automation = DesktopAutomation()
        
        screen_size = automation._screen_size
        
        assert screen_size.width > 0
        assert screen_size.height > 0
        assert screen_size.width >= 800
        assert screen_size.height >= 600


class TestPermissionSystem:
    """Test permission system"""
    
    @pytest.mark.asyncio
    async def test_permission_allow(self):
        """Test allowing action"""
        manager = PermissionManager()
        
        manager.add_rule(
            action_type=PermissionActionType.MOUSE_CLICK,
            decision="allow",
        )
        
        allowed = await manager.check_permission(
            action_type=PermissionActionType.MOUSE_CLICK,
            action_params={"x": 100, "y": 100},
        )
        
        assert allowed is True
    
    @pytest.mark.asyncio
    async def test_permission_deny(self):
        """Test denying action"""
        manager = PermissionManager()
        
        manager.add_rule(
            action_type=PermissionActionType.FILE_DELETE,
            decision="deny",
        )
        
        allowed = await manager.check_permission(
            action_type=PermissionActionType.FILE_DELETE,
            action_params={"path": "/test/file.txt"},
        )
        
        assert allowed is False
    
    @pytest.mark.asyncio
    async def test_domain_whitelist(self):
        """Test domain whitelisting"""
        manager = PermissionManager()
        manager.whitelist_domain("example.com")
        
        allowed = await manager.check_permission(
            action_type=PermissionActionType.BROWSER_NAVIGATE,
            action_params={"url": "https://example.com/page"},
        )
        
        assert allowed is True
        
        denied = await manager.check_permission(
            action_type=PermissionActionType.BROWSER_NAVIGATE,
            action_params={"url": "https://malicious.com/page"},
        )
        
        assert denied is False
    
    def test_audit_logging(self):
        """Test audit log creation"""
        manager = PermissionManager()
        
        initial_count = len(manager._audit_logs)
        
        asyncio.run(manager.check_permission(
            action_type=PermissionActionType.MOUSE_CLICK,
            action_params={"x": 100, "y": 100},
        ))
        
        assert len(manager._audit_logs) == initial_count + 1
    
    def test_statistics(self):
        """Test permission statistics"""
        manager = PermissionManager()
        
        manager.add_rule(
            action_type=PermissionActionType.MOUSE_CLICK,
            decision="allow",
        )
        
        asyncio.run(manager.check_permission(
            action_type=PermissionActionType.MOUSE_CLICK,
            action_params={"x": 100, "y": 100},
        ))
        
        stats = manager.get_statistics()
        
        assert stats["total_actions"] > 0
        assert stats["allowed"] > 0


class TestRollbackSystem:
    """Test rollback capabilities"""
    
    @pytest.mark.asyncio
    async def test_file_rollback(self, tmp_path):
        """Test file modification rollback"""
        manager = RollbackManager(backup_dir=tmp_path / "backups")
        
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")
        
        transaction_id = manager.begin_transaction("File Test")
        
        await manager.capture_file_modify(test_file)
        
        test_file.write_text("modified content")
        
        assert test_file.read_text() == "modified content"
        
        await manager.rollback_transaction(transaction_id)
        
        assert test_file.read_text() == "original content"
    
    @pytest.mark.asyncio
    async def test_file_delete_rollback(self, tmp_path):
        """Test file deletion rollback"""
        manager = RollbackManager(backup_dir=tmp_path / "backups")
        
        test_file = tmp_path / "delete_test.txt"
        test_file.write_text("content to delete")
        
        transaction_id = manager.begin_transaction("Delete Test")
        
        await manager.capture_file_delete(test_file)
        
        test_file.unlink()
        
        assert not test_file.exists()
        
        await manager.rollback_transaction(transaction_id)
        
        assert test_file.exists()
        assert test_file.read_text() == "content to delete"
    
    @pytest.mark.asyncio
    async def test_file_create_rollback(self, tmp_path):
        """Test file creation rollback"""
        manager = RollbackManager(backup_dir=tmp_path / "backups")
        
        test_file = tmp_path / "new_file.txt"
        
        transaction_id = manager.begin_transaction("Create Test")
        
        await manager.capture_file_create(test_file)
        
        test_file.write_text("new content")
        
        assert test_file.exists()
        
        await manager.rollback_transaction(transaction_id)
        
        assert not test_file.exists()
    
    def test_transaction_commit(self):
        """Test transaction commit"""
        manager = RollbackManager()
        
        transaction_id = manager.begin_transaction("Commit Test")
        
        success = manager.commit_transaction(transaction_id)
        
        assert success is True
        
        transaction = manager.get_transaction(transaction_id)
        assert transaction.committed is True
    
    def test_statistics(self):
        """Test rollback statistics"""
        manager = RollbackManager()
        
        manager.begin_transaction("Test 1")
        manager.begin_transaction("Test 2")
        
        stats = manager.get_statistics()
        
        assert stats["total_transactions"] == 2
        assert stats["active"] == 2


class TestComplexWorkflow:
    """Test complex end-to-end workflows"""
    
    @pytest.mark.asyncio
    async def test_100_step_workflow(self):
        """Test workflow with 100+ steps"""
        engine = WorkflowEngine()
        
        results = []
        
        async def counter_task(value: int):
            results.append(value)
            return value
        
        engine.register_executor("test.counter", counter_task)
        
        builder = WorkflowBuilder("100 Step Workflow")
        
        for i in range(100):
            builder.add_task(
                f"Task {i}",
                "test.counter",
                params={"value": i},
            )
        
        workflow = builder.build()
        
        import time
        start = time.time()
        context = await engine.execute_workflow(workflow)
        duration = time.time() - start
        
        assert len(results) == 100
        assert duration < 10.0
    
    @pytest.mark.asyncio
    async def test_workflow_with_failures(self):
        """Test workflow error handling"""
        engine = WorkflowEngine()
        
        async def failing_task():
            raise ValueError("Intentional failure")
        
        async def success_task():
            return "success"
        
        engine.register_executor("test.fail", failing_task)
        engine.register_executor("test.success", success_task)
        
        builder = WorkflowBuilder("Error Handling Workflow")
        fail_id = builder.add_task("Failing Task", "test.fail", max_retries=2)
        success_id = builder.add_task("Success Task", "test.success")
        workflow = builder.build()
        
        context = await engine.execute_workflow(workflow)
        
        fail_task = workflow.get_task(fail_id)
        success_task = workflow.get_task(success_id)
        
        assert fail_task.status.value == "failed"
        assert success_task.status.value == "completed"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
