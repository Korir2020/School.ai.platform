"""Append-only audit log: who did what, in which school. No marks or names are stored."""
from __future__ import annotations
import threading
import time
import uuid
from dataclasses import asdict, dataclass

from .domain import User


class AuditAccessDenied(PermissionError):
    pass


@dataclass(frozen=True)
class AuditEntry:
    id: str
    at: float
    school_id: str
    user_id: str
    role: str
    action: str
    target: str
    detail: dict


class AuditLog:
    def __init__(self):
        self._rows: list = []
        self._lock = threading.Lock()

    def record(self, user: User, action: str, target: str = "", detail=None) -> AuditEntry:
        e = AuditEntry(uuid.uuid4().hex, time.time(), user.school_id, user.id,
                       user.role, action, target, dict(detail or {}))
        with self._lock:
            self._rows.append(e)
        return e

    def entries(self, user: User, action=None, limit: int = 100) -> list:
        """Admin only, own school only, newest first."""
        if user.role != "admin":
            raise AuditAccessDenied("admin only")
        with self._lock:
            rows = [r for r in self._rows
                    if r.school_id == user.school_id and (not action or r.action == action)]
        return [asdict(r) for r in reversed(rows)][:limit]
