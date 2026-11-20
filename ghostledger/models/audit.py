from sqlalchemy import Column, Integer, String, DateTime, JSON
from ghostledger.extensions import Base
from ghostledger.models.base import get_utc_now


class AuditEvent(Base):
    __tablename__ = 'audit_events'

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), default=get_utc_now, nullable=False, index=True)
    event_type = Column(String(64), nullable=False, index=True)
    # IMPORT_FILE, RUN_RECONCILIATION, INVESTIGATION_GENERATED, ACTION_DRAFTED, ACTION_APPROVED, ACTION_REJECTED, RESOLUTION_RECORDED, SYSTEM_SEED
    actor = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(64), nullable=False)
    entity_id = Column(String(128), nullable=False)
    action_details = Column(JSON, default=dict)
    ip_address = Column(String(64), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'event_type': self.event_type,
            'actor': self.actor,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'action_details': self.action_details or {},
            'ip_address': self.ip_address
        }
