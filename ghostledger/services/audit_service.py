from typing import Optional, Dict, Any
from ghostledger.extensions import db
from ghostledger.models.audit import AuditEvent


class AuditService:
    @staticmethod
    def log(
        event_type: str,
        actor: str,
        entity_type: str,
        entity_id: str,
        action_details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ) -> AuditEvent:
        """Appends an immutable audit event to the audit_events table."""
        event = AuditEvent(
            event_type=event_type,
            actor=actor or 'system',
            entity_type=entity_type,
            entity_id=str(entity_id),
            action_details=action_details or {},
            ip_address=ip_address
        )
        db.session.add(event)
        return event


audit_service = AuditService()
