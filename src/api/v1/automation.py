"""
Automation API Endpoints

Endpoints for workflow execution, code execution, desktop automation, and browser automation
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

from src.action.automation import (
    BrowserAutomation,
    BrowserType,
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
    WaitCondition,
    WindowManager,
    WorkflowEngine,
    create_workflow_from_dict,
)

router = APIRouter(prefix="/automation", tags=["automation"])

workflow_engine = WorkflowEngine(max_parallel_tasks=10)
desktop_automation = DesktopAutomation(safe_mode=True)
window_manager = WindowManager()
executor = DockerSandboxExecutor()
permission_manager = PermissionManager()
rollback_manager = RollbackManager()


class WorkflowRequest(BaseModel):
    """Request to execute workflow"""
    workflow: Dict[str, Any]
    initial_context: Optional[Dict[str, Any]] = None


class WorkflowResponse(BaseModel):
    """Response from workflow execution"""
    workflow_id: str
    status: str
    context: Dict[str, Any]
    execution_time: float


class CodeExecutionRequest(BaseModel):
    """Request to execute code"""
    code: str
    language: ExecutionLanguage
    max_memory_mb: int = Field(default=512, ge=128, le=2048)
    max_cpu_percent: float = Field(default=50.0, ge=10.0, le=100.0)
    max_execution_time: float = Field(default=60.0, ge=1.0, le=300.0)
    network_enabled: bool = False
    files: Optional[Dict[str, str]] = None
    env_vars: Optional[Dict[str, str]] = None


class CodeExecutionResponse(BaseModel):
    """Response from code execution"""
    status: str
    output: str
    error: str
    exit_code: int
    execution_time: float


class MouseClickRequest(BaseModel):
    """Request to click mouse"""
    x: Optional[int] = None
    y: Optional[int] = None
    button: MouseButton = MouseButton.LEFT
    clicks: int = Field(default=1, ge=1, le=3)


class MouseMoveRequest(BaseModel):
    """Request to move mouse"""
    x: int
    y: int
    duration: float = Field(default=0.5, ge=0.0, le=5.0)
    human_like: bool = True


class TypeTextRequest(BaseModel):
    """Request to type text"""
    text: str
    interval: float = Field(default=0.05, ge=0.01, le=1.0)
    human_like: bool = True


class PressKeyRequest(BaseModel):
    """Request to press key"""
    key: str
    modifiers: Optional[List[KeyModifier]] = None


class WindowFocusRequest(BaseModel):
    """Request to focus window"""
    title: str


class BrowserNavigateRequest(BaseModel):
    """Request to navigate browser"""
    url: str
    wait_until: WaitCondition = WaitCondition.LOAD
    timeout: float = Field(default=30.0, ge=1.0, le=120.0)
    take_screenshot: bool = False


class BrowserFillFormRequest(BaseModel):
    """Request to fill form"""
    fields: List[Dict[str, str]]
    timeout: float = Field(default=10.0, ge=1.0, le=60.0)


class BrowserExtractRequest(BaseModel):
    """Request to extract data"""
    rules: List[Dict[str, Any]]


@router.post("/workflow/execute", response_model=WorkflowResponse)
async def execute_workflow(request: WorkflowRequest):
    """
    Execute workflow from JSON definition
    
    The workflow should contain:
    - name: Workflow name
    - tasks: List of tasks with actions and dependencies
    """
    try:
        import time
        from src.action.automation.workflow import Workflow
        
        workflow = create_workflow_from_dict(request.workflow)
        
        start_time = time.time()
        context = await workflow_engine.execute_workflow(
            workflow,
            initial_context=request.initial_context,
        )
        execution_time = time.time() - start_time
        
        return WorkflowResponse(
            workflow_id=workflow.id,
            status="completed",
            context=context,
            execution_time=execution_time,
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Workflow execution failed: {str(e)}",
        )


@router.post("/execute/code", response_model=CodeExecutionResponse)
async def execute_code(request: CodeExecutionRequest):
    """
    Execute code in sandboxed environment
    
    Supported languages:
    - python
    - javascript
    - bash
    - go
    - rust
    """
    try:
        limits = ResourceLimits(
            max_memory_mb=request.max_memory_mb,
            max_cpu_percent=request.max_cpu_percent,
            max_execution_time=request.max_execution_time,
            network_enabled=request.network_enabled,
        )
        
        result = await executor.execute(
            code=request.code,
            language=request.language,
            limits=limits,
            files=request.files,
            env_vars=request.env_vars,
        )
        
        return CodeExecutionResponse(
            status=result.status.value,
            output=result.output,
            error=result.error,
            exit_code=result.exit_code,
            execution_time=result.execution_time,
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Code execution failed: {str(e)}",
        )


@router.post("/desktop/mouse/click")
async def desktop_mouse_click(request: MouseClickRequest):
    """Click mouse at position"""
    try:
        success = await desktop_automation.click(
            x=request.x,
            y=request.y,
            button=request.button,
            clicks=request.clicks,
        )
        
        return {"success": success}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Mouse click failed: {str(e)}",
        )


@router.post("/desktop/mouse/move")
async def desktop_mouse_move(request: MouseMoveRequest):
    """Move mouse to position"""
    try:
        success = await desktop_automation.move_mouse(
            x=request.x,
            y=request.y,
            duration=request.duration,
            human_like=request.human_like,
        )
        
        return {"success": success}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Mouse move failed: {str(e)}",
        )


@router.post("/desktop/keyboard/type")
async def desktop_keyboard_type(request: TypeTextRequest):
    """Type text"""
    try:
        success = await desktop_automation.type_text(
            text=request.text,
            interval=request.interval,
            human_like=request.human_like,
        )
        
        return {"success": success}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Keyboard type failed: {str(e)}",
        )


@router.post("/desktop/keyboard/press")
async def desktop_keyboard_press(request: PressKeyRequest):
    """Press key with modifiers"""
    try:
        success = await desktop_automation.press_key(
            key=request.key,
            modifiers=request.modifiers,
        )
        
        return {"success": success}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Key press failed: {str(e)}",
        )


@router.get("/desktop/windows/list")
async def desktop_windows_list():
    """List all visible windows"""
    try:
        windows = await window_manager.list_windows()
        
        return {
            "windows": [
                {
                    "id": w.id,
                    "title": w.title,
                    "bounds": {
                        "x": w.bounds.x,
                        "y": w.bounds.y,
                        "width": w.bounds.width,
                        "height": w.bounds.height,
                    },
                    "is_visible": w.is_visible,
                    "is_minimized": w.is_minimized,
                    "is_maximized": w.is_maximized,
                }
                for w in windows
            ]
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Window list failed: {str(e)}",
        )


@router.post("/desktop/windows/focus")
async def desktop_windows_focus(request: WindowFocusRequest):
    """Focus window by title"""
    try:
        window = await window_manager.find_window(request.title)
        if not window:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Window not found: {request.title}",
            )
        
        success = await window_manager.focus_window(window)
        
        return {"success": success}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Window focus failed: {str(e)}",
        )


@router.post("/browser/navigate")
async def browser_navigate(request: BrowserNavigateRequest):
    """Navigate browser to URL"""
    try:
        async with BrowserAutomation(headless=True) as browser:
            result = await browser.navigate(
                url=request.url,
                wait_until=request.wait_until,
                timeout=request.timeout,
                take_screenshot=request.take_screenshot,
            )
            
            return {
                "url": result.url,
                "title": result.title,
                "status_code": result.status_code,
                "load_time": result.load_time,
                "screenshot": result.screenshot.hex() if result.screenshot else None,
            }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Browser navigation failed: {str(e)}",
        )


@router.post("/browser/fill-form")
async def browser_fill_form(request: BrowserFillFormRequest):
    """Fill form in browser"""
    try:
        async with BrowserAutomation(headless=True) as browser:
            fields = [
                FormField(**field)
                for field in request.fields
            ]
            
            success = await browser.fill_form(
                fields=fields,
                timeout=request.timeout,
            )
            
            return {"success": success}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Form fill failed: {str(e)}",
        )


@router.post("/browser/extract")
async def browser_extract(request: BrowserExtractRequest):
    """Extract data from browser page"""
    try:
        async with BrowserAutomation(headless=True) as browser:
            rules = [
                ExtractionRule(**rule)
                for rule in request.rules
            ]
            
            data = await browser.extract_data(rules=rules)
            
            return {"data": data}
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data extraction failed: {str(e)}",
        )


@router.get("/permissions/stats")
async def permissions_stats():
    """Get permission statistics"""
    try:
        stats = permission_manager.get_statistics()
        return stats
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}",
        )


@router.get("/rollback/transactions")
async def rollback_transactions():
    """List rollback transactions"""
    try:
        transactions = rollback_manager.list_transactions()
        
        return {
            "transactions": [
                {
                    "id": t.id,
                    "name": t.name,
                    "created_at": t.created_at.isoformat(),
                    "rollback_points_count": len(t.rollback_points),
                    "committed": t.committed,
                    "rolled_back": t.rolled_back,
                }
                for t in transactions
            ]
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list transactions: {str(e)}",
        )


@router.post("/rollback/{transaction_id}")
async def rollback_transaction(transaction_id: str):
    """Rollback transaction"""
    try:
        success = await rollback_manager.rollback_transaction(transaction_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transaction not found: {transaction_id}",
            )
        
        return {"success": success}
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rollback failed: {str(e)}",
        )


@router.get("/stats")
async def automation_stats():
    """Get automation statistics"""
    try:
        return {
            "executor": executor.get_execution_stats(),
            "permissions": permission_manager.get_statistics(),
            "rollback": rollback_manager.get_statistics(),
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get stats: {str(e)}",
        )
