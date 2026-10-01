"""Helpers for adding audit records to the same transaction as an action."""
from __future__ import annotations

import re

from flask_login import current_user

from app import AuditLog, db


_SECRET_ASSIGNMENT = re.compile(
    r'(?i)\b(password|пароль|secret|секрет|token|токен|api[_ -]?key)\s*[:=]\s*[^,;\s]+'
)


def _safe_text(value, limit: int) -> str | None:
    if value is None:
        return None
    text = _SECRET_ASSIGNMENT.sub(r'\1=[СКРЫТО]', str(value).strip())
    return text[:limit]


def add_audit_entry(action: str, object_type: str, object_label: str,
                    object_id=None, details: str | None = None) -> AuditLog:
    """Stage an audit row; the caller's following commit makes both changes atomic."""
    if not current_user.is_authenticated:
        raise RuntimeError('Audit entries for user actions require an authenticated user')
    entry = AuditLog(
        user_id=current_user.id,
        user_name=_safe_text(current_user.full_name, 200) or '—',
        user_login=_safe_text(current_user.login, 100) or '—',
        action=_safe_text(action, 30) or '—',
        object_type=_safe_text(object_type, 100) or '—',
        object_id=_safe_text(object_id, 100),
        object_label=_safe_text(object_label, 500) or '—',
        details=_safe_text(details, 1000),
    )
    db.session.add(entry)
    return entry


def commit_with_audit(action: str, object_type: str, object_label: str,
                      object_id=None, details: str | None = None) -> AuditLog:
    """Commit a successful application change together with its audit snapshot."""
    entry = add_audit_entry(action, object_type, object_label, object_id, details)
    db.session.commit()
    return entry
