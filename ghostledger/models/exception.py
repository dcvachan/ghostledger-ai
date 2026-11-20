from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from ghostledger.extensions import Base
from ghostledger.models.base import TimestampMixin, get_utc_now


class DiscrepancyException(Base, TimestampMixin):
    __tablename__ = 'discrepancy_exceptions'

    id = Column(Integer, primary_key=True)
    reconciliation_run_id = Column(Integer, ForeignKey('reconciliation_runs.id', ondelete='CASCADE'), nullable=False)
    transaction_id = Column(Integer, ForeignKey('transactions.id'), nullable=False)
    
    exception_type = Column(String(50), nullable=False, index=True)
    # UNMATCHED_PAYMENT, MISSING_SETTLEMENT, FEE_MISMATCH, DUPLICATE_PAYMENT, AMOUNT_MISMATCH, DELAYED_REFUND, AMBIGUOUS_CANDIDATE
    
    severity = Column(String(10), default='MEDIUM', nullable=False)  # HIGH, MEDIUM, LOW
    status = Column(String(30), default='OPEN', nullable=False, index=True)
    # OPEN, UNDER_INVESTIGATION, DRAFTED_ACTION, RESOLVED, DISMISSED
    
    amount_exposed = Column(Numeric(14, 2), default=Decimal('0.00'), nullable=False)
    currency = Column(String(3), default='INR', nullable=False)
    
    evidence_summary = Column(Text, nullable=False)
    evidence_details = Column(JSON, default=dict)

    # Relationships
    transaction = relationship('Transaction', backref='exceptions')
    investigations = relationship('InvestigationReport', backref='exception', cascade='all, delete-orphan')
    draft_actions = relationship('DraftAction', backref='exception', cascade='all, delete-orphan')
    resolutions = relationship('Resolution', backref='exception', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'reconciliation_run_id': self.reconciliation_run_id,
            'transaction_id': self.transaction_id,
            'exception_type': self.exception_type,
            'severity': self.severity,
            'status': self.status,
            'amount_exposed': float(self.amount_exposed) if self.amount_exposed is not None else 0.0,
            'currency': self.currency,
            'evidence_summary': self.evidence_summary,
            'evidence_details': self.evidence_details,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }
