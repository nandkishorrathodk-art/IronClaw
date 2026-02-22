"""
Workflow DAG Engine - Directed Acyclic Graph-based workflow orchestration

Features:
- DAG-based workflow execution with topological sort
- Parallel execution of independent tasks
- Conditional branching based on task results
- Error handling and retry logic
- Progress tracking and callbacks
"""

import asyncio
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class ConditionOperator(str, Enum):
    EQUALS = "eq"
    NOT_EQUALS = "ne"
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    CONTAINS = "contains"
    ALWAYS = "always"


@dataclass
class TaskCondition:
    """Condition for conditional task execution"""
    operator: ConditionOperator
    left_value: Any
    right_value: Any = None
    
    def evaluate(self, context: Dict[str, Any]) -> bool:
        """Evaluate condition with runtime context"""
        if self.operator == ConditionOperator.ALWAYS:
            return True
            
        left = self._resolve_value(self.left_value, context)
        right = self._resolve_value(self.right_value, context)
        
        if self.operator == ConditionOperator.EQUALS:
            return left == right
        elif self.operator == ConditionOperator.NOT_EQUALS:
            return left != right
        elif self.operator == ConditionOperator.GREATER_THAN:
            return left > right
        elif self.operator == ConditionOperator.LESS_THAN:
            return left < right
        elif self.operator == ConditionOperator.CONTAINS:
            return right in left
        
        return False
    
    def _resolve_value(self, value: Any, context: Dict[str, Any]) -> Any:
        """Resolve value from context if it's a reference"""
        if isinstance(value, str) and value.startswith("$"):
            return context.get(value[1:], value)
        return value


@dataclass
class WorkflowTask:
    """Single task in workflow"""
    id: str
    name: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    condition: Optional[TaskCondition] = None
    retry_count: int = 0
    max_retries: int = 3
    timeout: float = 60.0
    status: TaskStatus = TaskStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@dataclass
class Workflow:
    """Complete workflow definition"""
    id: str
    name: str
    tasks: List[WorkflowTask]
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def get_task(self, task_id: str) -> Optional[WorkflowTask]:
        """Get task by ID"""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None


class WorkflowEngine:
    """
    DAG-based workflow engine with parallel execution
    
    Features:
    - Topological sort for correct execution order
    - Parallel execution of independent tasks
    - Conditional branching
    - Error handling and retries
    - Progress callbacks
    """
    
    def __init__(
        self,
        max_parallel_tasks: int = 10,
        on_task_start: Optional[Callable] = None,
        on_task_complete: Optional[Callable] = None,
        on_task_failed: Optional[Callable] = None,
        on_workflow_complete: Optional[Callable] = None,
    ):
        self.max_parallel_tasks = max_parallel_tasks
        self.on_task_start = on_task_start
        self.on_task_complete = on_task_complete
        self.on_task_failed = on_task_failed
        self.on_workflow_complete = on_workflow_complete
        
        self._active_workflows: Dict[str, Workflow] = {}
        self._task_executors: Dict[str, Callable] = {}
        self._execution_context: Dict[str, Dict[str, Any]] = {}
    
    def register_executor(self, action: str, executor: Callable):
        """Register task executor function"""
        self._task_executors[action] = executor
    
    def _build_dependency_graph(self, tasks: List[WorkflowTask]) -> Dict[str, Set[str]]:
        """Build adjacency list for task dependencies"""
        graph = defaultdict(set)
        for task in tasks:
            for dep in task.dependencies:
                graph[dep].add(task.id)
        return graph
    
    def _topological_sort(self, tasks: List[WorkflowTask]) -> List[List[str]]:
        """
        Return tasks in execution order (layers for parallel execution)
        
        Each layer contains tasks that can run in parallel
        """
        task_map = {task.id: task for task in tasks}
        graph = self._build_dependency_graph(tasks)
        
        in_degree = {task.id: len(task.dependencies) for task in tasks}
        
        layers = []
        current_layer = [tid for tid in in_degree if in_degree[tid] == 0]
        
        while current_layer:
            layers.append(current_layer)
            next_layer = []
            
            for task_id in current_layer:
                for neighbor in graph[task_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_layer.append(neighbor)
            
            current_layer = next_layer
        
        if sum(in_degree.values()) > 0:
            raise ValueError("Workflow contains cycles - not a valid DAG")
        
        return layers
    
    async def execute_workflow(
        self,
        workflow: Workflow,
        initial_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute entire workflow
        
        Returns:
            Execution context with all task results
        """
        self._active_workflows[workflow.id] = workflow
        context = initial_context or {}
        self._execution_context[workflow.id] = context
        
        try:
            layers = self._topological_sort(workflow.tasks)
            
            for layer_idx, layer in enumerate(layers):
                tasks_to_run = []
                
                for task_id in layer:
                    task = workflow.get_task(task_id)
                    if task is None:
                        continue
                    
                    if task.condition and not task.condition.evaluate(context):
                        task.status = TaskStatus.SKIPPED
                        continue
                    
                    tasks_to_run.append(task)
                
                if tasks_to_run:
                    await self._execute_layer(workflow, tasks_to_run, context)
            
            if self.on_workflow_complete:
                await self._safe_callback(self.on_workflow_complete, workflow, context)
            
            return context
            
        finally:
            if workflow.id in self._active_workflows:
                del self._active_workflows[workflow.id]
            if workflow.id in self._execution_context:
                del self._execution_context[workflow.id]
    
    async def _execute_layer(
        self,
        workflow: Workflow,
        tasks: List[WorkflowTask],
        context: Dict[str, Any],
    ):
        """Execute all tasks in a layer (parallel execution)"""
        semaphore = asyncio.Semaphore(self.max_parallel_tasks)
        
        async def execute_with_semaphore(task: WorkflowTask):
            async with semaphore:
                await self._execute_task(workflow, task, context)
        
        await asyncio.gather(*[execute_with_semaphore(task) for task in tasks])
    
    async def _execute_task(
        self,
        workflow: Workflow,
        task: WorkflowTask,
        context: Dict[str, Any],
    ):
        """Execute single task with retry logic"""
        task.status = TaskStatus.RUNNING
        task.start_time = datetime.now()
        
        if self.on_task_start:
            await self._safe_callback(self.on_task_start, workflow, task)
        
        while task.retry_count <= task.max_retries:
            try:
                executor = self._task_executors.get(task.action)
                if executor is None:
                    raise ValueError(f"No executor registered for action: {task.action}")
                
                params = self._resolve_params(task.params, context)
                
                result = await asyncio.wait_for(
                    executor(**params),
                    timeout=task.timeout,
                )
                
                task.result = result
                task.status = TaskStatus.COMPLETED
                task.end_time = datetime.now()
                
                context[f"task_{task.id}_result"] = result
                
                if self.on_task_complete:
                    await self._safe_callback(self.on_task_complete, workflow, task, result)
                
                return
                
            except asyncio.TimeoutError:
                task.error = f"Task timed out after {task.timeout}s"
                task.retry_count += 1
                
            except Exception as e:
                task.error = str(e)
                task.retry_count += 1
                
                if task.retry_count > task.max_retries:
                    break
                
                await asyncio.sleep(min(2 ** task.retry_count, 10))
        
        task.status = TaskStatus.FAILED
        task.end_time = datetime.now()
        
        if self.on_task_failed:
            await self._safe_callback(self.on_task_failed, workflow, task, task.error)
    
    def _resolve_params(
        self,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Resolve parameter values from context"""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$"):
                resolved[key] = context.get(value[1:], value)
            else:
                resolved[key] = value
        return resolved
    
    async def _safe_callback(self, callback: Callable, *args, **kwargs):
        """Execute callback safely without crashing workflow"""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(*args, **kwargs)
            else:
                callback(*args, **kwargs)
        except Exception as e:
            print(f"Callback error: {e}")
    
    def cancel_workflow(self, workflow_id: str):
        """Cancel running workflow"""
        workflow = self._active_workflows.get(workflow_id)
        if workflow:
            for task in workflow.tasks:
                if task.status == TaskStatus.RUNNING:
                    task.status = TaskStatus.CANCELLED


class WorkflowBuilder:
    """Fluent API for building workflows"""
    
    def __init__(self, name: str, description: str = ""):
        self.workflow = Workflow(
            id=str(uuid4()),
            name=name,
            description=description,
            tasks=[],
        )
    
    def add_task(
        self,
        name: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
        condition: Optional[TaskCondition] = None,
        max_retries: int = 3,
        timeout: float = 60.0,
    ) -> str:
        """Add task and return task ID"""
        task_id = str(uuid4())
        task = WorkflowTask(
            id=task_id,
            name=name,
            action=action,
            params=params or {},
            dependencies=dependencies or [],
            condition=condition,
            max_retries=max_retries,
            timeout=timeout,
        )
        self.workflow.tasks.append(task)
        return task_id
    
    def build(self) -> Workflow:
        """Build and return workflow"""
        return self.workflow


def create_workflow_from_dict(workflow_dict: Dict[str, Any]) -> Workflow:
    """Create workflow from dictionary/JSON definition"""
    builder = WorkflowBuilder(
        name=workflow_dict["name"],
        description=workflow_dict.get("description", ""),
    )
    
    task_id_map = {}
    
    for task_def in workflow_dict.get("tasks", []):
        condition = None
        if "condition" in task_def:
            cond = task_def["condition"]
            condition = TaskCondition(
                operator=ConditionOperator(cond["operator"]),
                left_value=cond["left"],
                right_value=cond.get("right"),
            )
        
        task_id = builder.add_task(
            name=task_def["name"],
            action=task_def["action"],
            params=task_def.get("params", {}),
            dependencies=[task_id_map.get(dep, dep) for dep in task_def.get("dependencies", [])],
            condition=condition,
            max_retries=task_def.get("max_retries", 3),
            timeout=task_def.get("timeout", 60.0),
        )
        
        if "id" in task_def:
            task_id_map[task_def["id"]] = task_id
    
    return builder.build()
