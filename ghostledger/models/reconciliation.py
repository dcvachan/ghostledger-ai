from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from ghostledger.extensions import Base
from ghostledger.models.base import TimestampMixin, get_utc_now


class ReconciliationRun(Base, TimestampMixin):
    __tablename__ = 'reconciliation_runs'

    id = Column(Integer, primary_key=True)
    run_id = Column(String(36), unique=True, nullable=False, index=True)
    status = Column(String(30), default='PENDING', nullable=False)  # PENDING, RUNNING, COMPLETED, FAILED
    
    total_records = Column(Integer, default=0, nullable=False)
    matched_records = Column(Integer, default=0, nullable=False)
    unmatched_records = Column(Integer, default=0, nullable=False)
    discrepancy_records = Column(Integer, default=0, nullable=False)
    
    match_rate = Column(Numeric(5, 2), default=Decimal('0.00'), nullable=False)
    amount_at_risk = Column(Numeric(14, 2), default=Decimal('0.00'), nullable=False)
    confirmed_discrepancy_amount = Column(Numeric(14, 2), default=Decimal('0.00'), nullable=False)
    recovered_amount = Column(Numeric(14, 2), default=Decimal('0.00'), nullable=False)
    
    parameters = Column(JSON, default=dict)
    started_at = Column(DateTime(timezone=True), default=get_utc_now)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    matches = relationship('ReconciliationMatch', backref='reconciliation_run', cascade='all, delete-orphan')
    exceptions = relationship('DiscrepancyException', backref='reconciliation_run', cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'run_id': self.run_id,
            'status': self.status,
            'total_records': self.total_records,
            'matched_records': self.matched_records,
            'unmatched_records': self.unmatched_records,
            'discrepancy_records': self.discrepancy_records,
            'match_rate': float(self.match_rate) if self.match_rate is not None else 0.0,
            'amount_at_risk': float(self.amount_at_risk) if self.amount_at_risk is not None else 0.0,
            'confirmed_discrepancy_amount': float(self.confirmed_discrepancy_amount) if self.confirmed_discrepancy_amount is not None else 0.0,
            'recovered_amount': float(self.recovered_amount) if self.recovered_amount is not None else 0.0,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None
        }


class ReconciliationMatch(Base, TimestampMixin):
    __tablename__ = 'reconciliation_matches'

    id = Column(Integer, primary_key=True)
    reconciliation_run_id = Column(Integer, ForeignKey('reconciliation_runs.id', ondelete='CASCADE'), nullable=False)
    match_type = Column(String(50), nullable=False)  # EXACT_ID, EXACT_HEURISTIC, WINDOW_FEE_TOLERANT, BATCH_ONE_TO_MANY
    confidence_score = Column(Numeric(5, 2), nullable=False)  # e.g. 100.00, 95.00
    
    primary_tx_id = Column(Integer, ForeignKey('transactions.id'), nullable=False)
    matched_tx_id = Column(Integer, ForeignKey('transactions.id'), nullable=False)
    
    evidence_json = Column(JSON, default=dict)

    # Relationships
    primary_transaction = relationship('Transaction', foreign_keys=[primary_tx_id])
    matched_transaction = relationship('Transaction', foreign_keys=[matched_tx_id])

    def to_dict(self):
        return {
            'id': self.id,
            'reconciliation_run_id': self.reconciliation_run_id,
            'match_type': self.match_type,
            'confidence_score': float(self.confidence_score) if self.confidence_score is not None else 0.0,
            'primary_tx_id': self.primary_tx_id,
            'matched_tx_id': self.matched_tx_id,
            'evidence_json': self.evidence_json,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
