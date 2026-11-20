from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey, JSON
from ghostledger.extensions import Base
from ghostledger.models.base import TimestampMixin, get_utc_now


class DraftAction(Base, TimestampMixin):
    __tablename__ = 'draft_actions'

    id = Column(Integer, primary_key=True)
    exception_id = Column(Integer, ForeignKey('discrepancy_exceptions.id', ondelete='CASCADE'), nullable=False)
    
    action_type = Column(String(64), nullable=False)
    # CREATE_FOLLOW_UP_TASK, DRAFT_REFUND_INQUIRY, PROPOSED_RECONCILIATION_ADJUSTMENT, FLAG_SUSPECTED_DUPLICATE
    
    status = Column(String(20), default='DRAFT', nullable=False, index=True)
    # DRAFT, APPROVED, REJECTED, EXECUTED
    
    target_entity_type = Column(String(64), nullable=False)  # TRANSACTION, SETTLEMENT, REFUND, INVOICE
    target_entity_id = Column(String(128), nullable=False)
    action_payload = Column(JSON, default=dict)
    rationale = Column(Text, nullable=False)
    
    created_by = Column(String(100), default='system:ghostledger_ai', nullable=False)
    reviewed_by = Column(String(100), nullable=True)
    review_comment = Column(Text, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'exception_id': self.exception_id,
            'action_type': self.action_type,
            'status': self.status,
            'target_entity_type': self.target_entity_type,
            'target_entity_id': self.target_entity_id,
            'action_payload': self.action_payload or {},
            'rationale': self.rationale,
            'created_by': self.created_by,
            'reviewed_by': self.reviewed_by,
            'review_comment': self.review_comment,
            'approved_at': self.approved_at.isoformat() if self.approved_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
