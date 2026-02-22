"""
Permission System for Automation

Features:
- Whitelist/blacklist for actions
- User confirmation prompts
- Scope validation (domains, files, etc.)
- Comprehensive audit logging
- Risk assessment
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4


class ActionType(str, Enum):
    MOUSE_CLICK = "mouse.click"
    MOUSE_MOVE = "mouse.move"
    KEYBOARD_TYPE = "keyboard.type"
    KEYBOARD_PRESS = "keyboard.press"
    WINDOW_FOCUS = "window.focus"
    WINDOW_CLOSE = "window.close"
    BROWSER_NAVIGATE = "browser.navigate"
    BROWSER_FILL_FORM = "browser.fill_form"
    FILE_READ = "file.read"
    FILE_WRITE = "file.write"
    FILE_DELETE = "file.delete"
    CODE_EXECUTE = "code.execute"
    NETWORK_REQUEST = "network.request"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    PROMPT = "prompt"


@dataclass
class PermissionRule:
    """Single permission rule"""
    id: str
    action_type: ActionType
    decision: PermissionDecision
    scope: Optional[Dict[str, Any]] = None
    reason: str = ""
    expires_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class AuditLog:
    """Audit log entry"""
    id: str
    timestamp: datetime
    action_type: ActionType
    action_params: Dict[str, Any]
    decision: PermissionDecision
    user_approved: bool
    risk_level: RiskLevel
    metadata: Dict[str, Any] = field(default_factory=dict)


class PermissionManager:
    """
    Manage permissions for automation actions
    
    Features:
    - Whitelist/blacklist rules
    - User confirmation prompts
    - Scope validation
    - Risk assessment
    - Audit logging
    """
    
    # Default risk levels for actions
    RISK_LEVELS = {
        ActionType.MOUSE_CLICK: RiskLevel.LOW,
        ActionType.MOUSE_MOVE: RiskLevel.LOW,
        ActionType.KEYBOARD_TYPE: RiskLevel.MEDIUM,
        ActionType.KEYBOARD_PRESS: RiskLevel.MEDIUM,
        ActionType.WINDOW_FOCUS: RiskLevel.LOW,
        ActionType.WINDOW_CLOSE: RiskLevel.MEDIUM,
        ActionType.BROWSER_NAVIGATE: RiskLevel.MEDIUM,
        ActionType.BROWSER_FILL_FORM: RiskLevel.HIGH,
        ActionType.FILE_READ: RiskLevel.MEDIUM,
        ActionType.FILE_WRITE: RiskLevel.HIGH,
        ActionType.FILE_DELETE: RiskLevel.CRITICAL,
        ActionType.CODE_EXECUTE: RiskLevel.CRITICAL,
        ActionType.NETWORK_REQUEST: RiskLevel.MEDIUM,
    }
    
    def __init__(
        self,
        audit_log_path: Optional[Path] = None,
        prompt_callback: Optional[Callable] = None,
    ):
        self.audit_log_path = audit_log_path or Path("data/audit_logs/automation.jsonl")
        self.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.prompt_callback = prompt_callback or self._default_prompt
        
        self._rules: List[PermissionRule] = []
        self._audit_logs: List[AuditLog] = []
        self._whitelist_domains: Set[str] = set()
        self._blacklist_domains: Set[str] = set()
        self._whitelist_paths: Set[Path] = set()
        self._blacklist_paths: Set[Path] = set()
    
    def add_rule(
        self,
        action_type: ActionType,
        decision: PermissionDecision,
        scope: Optional[Dict[str, Any]] = None,
        reason: str = "",
        expires_at: Optional[datetime] = None,
    ) -> str:
        """Add permission rule"""
        rule = PermissionRule(
            id=str(uuid4()),
            action_type=action_type,
            decision=decision,
            scope=scope,
            reason=reason,
            expires_at=expires_at,
        )
        self._rules.append(rule)
        return rule.id
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove permission rule"""
        for i, rule in enumerate(self._rules):
            if rule.id == rule_id:
                self._rules.pop(i)
                return True
        return False
    
    def whitelist_domain(self, domain: str):
        """Add domain to whitelist"""
        self._whitelist_domains.add(domain.lower())
    
    def blacklist_domain(self, domain: str):
        """Add domain to blacklist"""
        self._blacklist_domains.add(domain.lower())
    
    def whitelist_path(self, path: Path):
        """Add file path to whitelist"""
        self._whitelist_paths.add(path.resolve())
    
    def blacklist_path(self, path: Path):
        """Add file path to blacklist"""
        self._blacklist_paths.add(path.resolve())
    
    async def check_permission(
        self,
        action_type: ActionType,
        action_params: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Check if action is permitted
        
        Returns:
            True if allowed, False if denied
        """
        metadata = metadata or {}
        
        risk_level = self._assess_risk(action_type, action_params)
        
        matching_rule = self._find_matching_rule(action_type, action_params)
        
        if matching_rule:
            if matching_rule.expires_at and datetime.now() > matching_rule.expires_at:
                self.remove_rule(matching_rule.id)
                matching_rule = None
        
        if matching_rule:
            decision = matching_rule.decision
        else:
            decision = self._default_decision(action_type, risk_level)
        
        user_approved = False
        
        if decision == PermissionDecision.PROMPT:
            user_approved = await self.prompt_callback(
                action_type=action_type,
                action_params=action_params,
                risk_level=risk_level,
            )
            decision = PermissionDecision.ALLOW if user_approved else PermissionDecision.DENY
        
        elif decision == PermissionDecision.ALLOW:
            if not self._validate_scope(action_type, action_params):
                decision = PermissionDecision.DENY
        
        audit_log = AuditLog(
            id=str(uuid4()),
            timestamp=datetime.now(),
            action_type=action_type,
            action_params=action_params.copy(),
            decision=decision,
            user_approved=user_approved,
            risk_level=risk_level,
            metadata=metadata,
        )
        
        self._audit_logs.append(audit_log)
        self._write_audit_log(audit_log)
        
        return decision == PermissionDecision.ALLOW
    
    def _assess_risk(
        self,
        action_type: ActionType,
        action_params: Dict[str, Any],
    ) -> RiskLevel:
        """Assess risk level of action"""
        base_risk = self.RISK_LEVELS.get(action_type, RiskLevel.MEDIUM)
        
        if action_type == ActionType.FILE_WRITE:
            path = action_params.get("path", "")
            if any(critical in str(path).lower() for critical in ["system32", "windows", "program files"]):
                return RiskLevel.CRITICAL
        
        elif action_type == ActionType.BROWSER_NAVIGATE:
            url = action_params.get("url", "")
            if any(danger in url.lower() for danger in ["file://", "javascript:", "data:"]):
                return RiskLevel.HIGH
        
        elif action_type == ActionType.CODE_EXECUTE:
            code = action_params.get("code", "")
            if any(danger in code.lower() for danger in ["rm -rf", "del /f", "format", "mkfs"]):
                return RiskLevel.CRITICAL
        
        return base_risk
    
    def _find_matching_rule(
        self,
        action_type: ActionType,
        action_params: Dict[str, Any],
    ) -> Optional[PermissionRule]:
        """Find matching permission rule"""
        for rule in reversed(self._rules):
            if rule.action_type != action_type:
                continue
            
            if rule.scope:
                if not self._match_scope(rule.scope, action_params):
                    continue
            
            return rule
        
        return None
    
    def _match_scope(
        self,
        scope: Dict[str, Any],
        action_params: Dict[str, Any],
    ) -> bool:
        """Check if action params match rule scope"""
        for key, pattern in scope.items():
            if key not in action_params:
                return False
            
            value = action_params[key]
            
            if isinstance(pattern, str) and isinstance(value, str):
                if not re.match(pattern, value):
                    return False
            elif pattern != value:
                return False
        
        return True
    
    def _default_decision(
        self,
        action_type: ActionType,
        risk_level: RiskLevel,
    ) -> PermissionDecision:
        """Get default decision for action"""
        if risk_level == RiskLevel.CRITICAL:
            return PermissionDecision.PROMPT
        elif risk_level == RiskLevel.HIGH:
            return PermissionDecision.PROMPT
        elif risk_level == RiskLevel.MEDIUM:
            return PermissionDecision.ALLOW
        else:
            return PermissionDecision.ALLOW
    
    def _validate_scope(
        self,
        action_type: ActionType,
        action_params: Dict[str, Any],
    ) -> bool:
        """Validate action is within allowed scope"""
        if action_type == ActionType.BROWSER_NAVIGATE:
            url = action_params.get("url", "")
            domain = self._extract_domain(url)
            
            if domain in self._blacklist_domains:
                return False
            
            if self._whitelist_domains and domain not in self._whitelist_domains:
                return False
        
        elif action_type in [ActionType.FILE_READ, ActionType.FILE_WRITE, ActionType.FILE_DELETE]:
            path_str = action_params.get("path", "")
            path = Path(path_str).resolve()
            
            if any(path.is_relative_to(bp) for bp in self._blacklist_paths):
                return False
            
            if self._whitelist_paths:
                if not any(path.is_relative_to(wp) for wp in self._whitelist_paths):
                    return False
        
        return True
    
    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        return parsed.netloc.lower()
    
    async def _default_prompt(
        self,
        action_type: ActionType,
        action_params: Dict[str, Any],
        risk_level: RiskLevel,
    ) -> bool:
        """Default prompt implementation (always deny)"""
        print(f"[PERMISSION PROMPT] Action: {action_type}, Risk: {risk_level}")
        print(f"Params: {action_params}")
        print("Auto-deny (no prompt callback configured)")
        return False
    
    def _write_audit_log(self, log: AuditLog):
        """Write audit log to file"""
        try:
            log_dict = {
                "id": log.id,
                "timestamp": log.timestamp.isoformat(),
                "action_type": log.action_type.value,
                "action_params": log.action_params,
                "decision": log.decision.value,
                "user_approved": log.user_approved,
                "risk_level": log.risk_level.value,
                "metadata": log.metadata,
            }
            
            with open(self.audit_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_dict) + "\n")
        except Exception as e:
            print(f"Failed to write audit log: {e}")
    
    def get_audit_logs(
        self,
        action_type: Optional[ActionType] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[AuditLog]:
        """Get audit logs with filters"""
        logs = self._audit_logs.copy()
        
        if action_type:
            logs = [log for log in logs if log.action_type == action_type]
        
        if since:
            logs = [log for log in logs if log.timestamp >= since]
        
        logs.sort(key=lambda x: x.timestamp, reverse=True)
        
        return logs[:limit]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get permission statistics"""
        if not self._audit_logs:
            return {}
        
        total = len(self._audit_logs)
        allowed = sum(1 for log in self._audit_logs if log.decision == PermissionDecision.ALLOW)
        denied = sum(1 for log in self._audit_logs if log.decision == PermissionDecision.DENY)
        prompted = sum(1 for log in self._audit_logs if log.user_approved)
        
        by_action = {}
        for log in self._audit_logs:
            action = log.action_type.value
            if action not in by_action:
                by_action[action] = {"total": 0, "allowed": 0, "denied": 0}
            by_action[action]["total"] += 1
            if log.decision == PermissionDecision.ALLOW:
                by_action[action]["allowed"] += 1
            else:
                by_action[action]["denied"] += 1
        
        by_risk = {}
        for log in self._audit_logs:
            risk = log.risk_level.value
            if risk not in by_risk:
                by_risk[risk] = {"total": 0, "allowed": 0}
            by_risk[risk]["total"] += 1
            if log.decision == PermissionDecision.ALLOW:
                by_risk[risk]["allowed"] += 1
        
        return {
            "total_actions": total,
            "allowed": allowed,
            "denied": denied,
            "prompted": prompted,
            "allow_rate": allowed / total if total > 0 else 0,
            "by_action_type": by_action,
            "by_risk_level": by_risk,
        }
