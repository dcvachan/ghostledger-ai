from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, ForeignKey
from ghostledger.extensions import Base
from ghostledger.models.base import TimestampMixin, get_utc_now


class Resolution(Base, TimestampMixin):
    __tablename__ = 'resolutions'

    id = Column(Integer, primary_key=True)
    exception_id = Column(Integer, ForeignKey('discrepancy_exceptions.id', ondelete='CASCADE'), nullable=False)
    draft_action_id = Column(Integer, ForeignKey('draft_actions.id', ondelete='SET NULL'), nullable=True)
    
    resolution_type = Column(String(64), nullable=False)
    # MANUAL_MATCH, SETTLEMENT_ADJUSTMENT, DUPLICATE_VOIDED, REFUND_CONFIRMED, WRITE_OFF
    
    # Strictly recorded recovered amount
    recovered_amount = Column(Numeric(14, 2), default=Decimal('0.00'), nullable=False)
    currency = Column(String(3), default='INR', nullable=False)
    
    verification_notes = Column(Text, nullable=False)
    resolved_by = Column(String(100), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'exception_id': self.exception_id,
            'draft_action_id': self.draft_action_id,
            'resolution_type': self.resolution_type,
            'recovered_amount': float(self.recovered_amount) if self.recovered_amount is not None else 0.0,
            'currency': self.currency,
            'verification_notes': self.verification_notes,
            'resolved_by': self.resolved_by,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
