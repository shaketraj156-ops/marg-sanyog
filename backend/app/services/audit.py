from sqlalchemy.orm import Session

from app.db.models import AuditLog, User


def record(
    db: Session,
    user: User | None,
    action: str,
    entity: str,
    entity_id: int | None,
    details: dict | None = None,
) -> None:
    """Add an audit row to the caller's transaction. The caller commits."""
    db.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=entity_id,
            details=details or {},
        )
    )
