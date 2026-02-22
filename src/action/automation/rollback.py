"""
Rollback System for Automation

Features:
- Undo file changes
- Restore clipboard
- Revert window positions
- Transaction-like semantics
- Rollback history
"""

import asyncio
import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


class ActionType(str, Enum):
    FILE_CREATE = "file.create"
    FILE_MODIFY = "file.modify"
    FILE_DELETE = "file.delete"
    FILE_MOVE = "file.move"
    CLIPBOARD_CHANGE = "clipboard.change"
    WINDOW_MOVE = "window.move"
    WINDOW_RESIZE = "window.resize"
    WINDOW_MINIMIZE = "window.minimize"
    WINDOW_MAXIMIZE = "window.maximize"
    WINDOW_CLOSE = "window.close"


@dataclass
class RollbackPoint:
    """Single rollback point"""
    id: str
    timestamp: datetime
    action_type: ActionType
    original_state: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    can_rollback: bool = True


@dataclass
class Transaction:
    """Transaction containing multiple rollback points"""
    id: str
    name: str
    created_at: datetime
    rollback_points: List[RollbackPoint] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False


class RollbackManager:
    """
    Manage rollback for automation actions
    
    Features:
    - Transaction-like semantics
    - Automatic state capture
    - Rollback history
    - Partial rollback support
    """
    
    def __init__(
        self,
        backup_dir: Optional[Path] = None,
    ):
        self.backup_dir = backup_dir or Path("data/rollback_backups")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        self._transactions: Dict[str, Transaction] = {}
        self._current_transaction: Optional[str] = None
        self._rollback_history: List[dict] = []
        
        try:
            import pyperclip
            self._clipboard = pyperclip
        except ImportError:
            self._clipboard = None
    
    def begin_transaction(self, name: str = "Unnamed") -> str:
        """Start new transaction"""
        transaction = Transaction(
            id=str(uuid4()),
            name=name,
            created_at=datetime.now(),
        )
        
        self._transactions[transaction.id] = transaction
        self._current_transaction = transaction.id
        
        return transaction.id
    
    def commit_transaction(self, transaction_id: Optional[str] = None) -> bool:
        """Commit transaction (mark as successful)"""
        tid = transaction_id or self._current_transaction
        if not tid:
            return False
        
        transaction = self._transactions.get(tid)
        if not transaction:
            return False
        
        transaction.committed = True
        
        if tid == self._current_transaction:
            self._current_transaction = None
        
        return True
    
    async def rollback_transaction(
        self,
        transaction_id: Optional[str] = None,
    ) -> bool:
        """Rollback entire transaction"""
        tid = transaction_id or self._current_transaction
        if not tid:
            return False
        
        transaction = self._transactions.get(tid)
        if not transaction:
            return False
        
        if transaction.rolled_back:
            return False
        
        for rollback_point in reversed(transaction.rollback_points):
            if rollback_point.can_rollback:
                await self._execute_rollback(rollback_point)
        
        transaction.rolled_back = True
        
        if tid == self._current_transaction:
            self._current_transaction = None
        
        self._rollback_history.append({
            "timestamp": datetime.now().isoformat(),
            "transaction_id": tid,
            "transaction_name": transaction.name,
            "rollback_points_count": len(transaction.rollback_points),
        })
        
        return True
    
    async def capture_file_create(self, path: Path) -> str:
        """Capture state before creating file"""
        if not self._current_transaction:
            raise RuntimeError("No active transaction")
        
        rollback_point = RollbackPoint(
            id=str(uuid4()),
            timestamp=datetime.now(),
            action_type=ActionType.FILE_CREATE,
            original_state={"path": str(path)},
            can_rollback=True,
        )
        
        transaction = self._transactions[self._current_transaction]
        transaction.rollback_points.append(rollback_point)
        
        return rollback_point.id
    
    async def capture_file_modify(self, path: Path) -> str:
        """Capture state before modifying file"""
        if not self._current_transaction:
            raise RuntimeError("No active transaction")
        
        if not path.exists():
            can_rollback = False
            original_content = None
        else:
            can_rollback = True
            
            backup_path = self.backup_dir / f"{uuid4().hex}_{path.name}"
            shutil.copy2(path, backup_path)
            
            original_content = path.read_bytes()
            content_hash = hashlib.sha256(original_content).hexdigest()
        
        rollback_point = RollbackPoint(
            id=str(uuid4()),
            timestamp=datetime.now(),
            action_type=ActionType.FILE_MODIFY,
            original_state={
                "path": str(path),
                "backup_path": str(backup_path) if can_rollback else None,
                "content_hash": content_hash if can_rollback else None,
            },
            can_rollback=can_rollback,
        )
        
        transaction = self._transactions[self._current_transaction]
        transaction.rollback_points.append(rollback_point)
        
        return rollback_point.id
    
    async def capture_file_delete(self, path: Path) -> str:
        """Capture state before deleting file"""
        if not self._current_transaction:
            raise RuntimeError("No active transaction")
        
        if not path.exists():
            can_rollback = False
            backup_path = None
        else:
            can_rollback = True
            backup_path = self.backup_dir / f"{uuid4().hex}_{path.name}"
            shutil.copy2(path, backup_path)
        
        rollback_point = RollbackPoint(
            id=str(uuid4()),
            timestamp=datetime.now(),
            action_type=ActionType.FILE_DELETE,
            original_state={
                "path": str(path),
                "backup_path": str(backup_path) if can_rollback else None,
            },
            can_rollback=can_rollback,
        )
        
        transaction = self._transactions[self._current_transaction]
        transaction.rollback_points.append(rollback_point)
        
        return rollback_point.id
    
    async def capture_file_move(self, src: Path, dst: Path) -> str:
        """Capture state before moving file"""
        if not self._current_transaction:
            raise RuntimeError("No active transaction")
        
        rollback_point = RollbackPoint(
            id=str(uuid4()),
            timestamp=datetime.now(),
            action_type=ActionType.FILE_MOVE,
            original_state={
                "src": str(src),
                "dst": str(dst),
            },
            can_rollback=src.exists(),
        )
        
        transaction = self._transactions[self._current_transaction]
        transaction.rollback_points.append(rollback_point)
        
        return rollback_point.id
    
    async def capture_clipboard(self) -> str:
        """Capture clipboard state"""
        if not self._current_transaction:
            raise RuntimeError("No active transaction")
        
        original_content = None
        can_rollback = False
        
        if self._clipboard:
            try:
                original_content = self._clipboard.paste()
                can_rollback = True
            except:
                pass
        
        rollback_point = RollbackPoint(
            id=str(uuid4()),
            timestamp=datetime.now(),
            action_type=ActionType.CLIPBOARD_CHANGE,
            original_state={"content": original_content},
            can_rollback=can_rollback,
        )
        
        transaction = self._transactions[self._current_transaction]
        transaction.rollback_points.append(rollback_point)
        
        return rollback_point.id
    
    async def capture_window_state(
        self,
        window_title: str,
        action: ActionType,
        state: Dict[str, Any],
    ) -> str:
        """Capture window state"""
        if not self._current_transaction:
            raise RuntimeError("No active transaction")
        
        rollback_point = RollbackPoint(
            id=str(uuid4()),
            timestamp=datetime.now(),
            action_type=action,
            original_state={
                "window_title": window_title,
                **state,
            },
            can_rollback=True,
        )
        
        transaction = self._transactions[self._current_transaction]
        transaction.rollback_points.append(rollback_point)
        
        return rollback_point.id
    
    async def _execute_rollback(self, rollback_point: RollbackPoint):
        """Execute single rollback"""
        try:
            if rollback_point.action_type == ActionType.FILE_CREATE:
                path = Path(rollback_point.original_state["path"])
                if path.exists():
                    path.unlink()
            
            elif rollback_point.action_type == ActionType.FILE_MODIFY:
                backup_path = rollback_point.original_state.get("backup_path")
                if backup_path:
                    backup = Path(backup_path)
                    target = Path(rollback_point.original_state["path"])
                    if backup.exists():
                        shutil.copy2(backup, target)
            
            elif rollback_point.action_type == ActionType.FILE_DELETE:
                backup_path = rollback_point.original_state.get("backup_path")
                if backup_path:
                    backup = Path(backup_path)
                    target = Path(rollback_point.original_state["path"])
                    if backup.exists():
                        shutil.copy2(backup, target)
            
            elif rollback_point.action_type == ActionType.FILE_MOVE:
                src = Path(rollback_point.original_state["src"])
                dst = Path(rollback_point.original_state["dst"])
                if dst.exists():
                    shutil.move(str(dst), str(src))
            
            elif rollback_point.action_type == ActionType.CLIPBOARD_CHANGE:
                if self._clipboard:
                    content = rollback_point.original_state.get("content")
                    if content is not None:
                        self._clipboard.copy(content)
            
            elif rollback_point.action_type in [
                ActionType.WINDOW_MOVE,
                ActionType.WINDOW_RESIZE,
            ]:
                pass
            
        except Exception as e:
            print(f"Rollback failed for {rollback_point.id}: {e}")
    
    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """Get transaction by ID"""
        return self._transactions.get(transaction_id)
    
    def list_transactions(
        self,
        committed: Optional[bool] = None,
    ) -> List[Transaction]:
        """List transactions with optional filter"""
        transactions = list(self._transactions.values())
        
        if committed is not None:
            transactions = [t for t in transactions if t.committed == committed]
        
        transactions.sort(key=lambda t: t.created_at, reverse=True)
        
        return transactions
    
    def cleanup_old_backups(self, days: int = 7):
        """Clean up old backup files"""
        from datetime import timedelta
        
        cutoff = datetime.now() - timedelta(days=days)
        
        for backup_file in self.backup_dir.glob("*"):
            if backup_file.is_file():
                mtime = datetime.fromtimestamp(backup_file.stat().st_mtime)
                if mtime < cutoff:
                    backup_file.unlink()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get rollback statistics"""
        total_transactions = len(self._transactions)
        committed = sum(1 for t in self._transactions.values() if t.committed)
        rolled_back = sum(1 for t in self._transactions.values() if t.rolled_back)
        
        total_rollback_points = sum(
            len(t.rollback_points)
            for t in self._transactions.values()
        )
        
        by_action = {}
        for transaction in self._transactions.values():
            for rp in transaction.rollback_points:
                action = rp.action_type.value
                if action not in by_action:
                    by_action[action] = 0
                by_action[action] += 1
        
        return {
            "total_transactions": total_transactions,
            "committed": committed,
            "rolled_back": rolled_back,
            "active": total_transactions - committed - rolled_back,
            "total_rollback_points": total_rollback_points,
            "by_action_type": by_action,
            "rollback_history_count": len(self._rollback_history),
        }


async def with_rollback(
    manager: RollbackManager,
    operation: callable,
    transaction_name: str = "Operation",
):
    """
    Context manager for automatic rollback on error
    
    Usage:
        async with with_rollback(manager, my_operation, "My Operation"):
            # do stuff
            pass
    """
    transaction_id = manager.begin_transaction(transaction_name)
    
    try:
        result = await operation()
        manager.commit_transaction(transaction_id)
        return result
    except Exception as e:
        await manager.rollback_transaction(transaction_id)
        raise
