from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from ghostledger.extensions import Base
from ghostledger.models.base import TimestampMixin, get_utc_now


class Transaction(Base, TimestampMixin):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True)
    source_file_id = Column(Integer, ForeignKey('imported_files.id', ondelete='SET NULL'), nullable=True)
    source_type = Column(String(50), nullable=False, index=True)  # PAYMENT, BANK_STATEMENT, SETTLEMENT, INVOICE, REFUND
    external_reference_id = Column(String(100), nullable=False, index=True)
    merchant_order_id = Column(String(100), nullable=True, index=True)
    counterparty = Column(String(150), nullable=True)
    
    # Financial fields - Decimal representation
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default='INR')
    fee = Column(Numeric(14, 2), default=Decimal('0.00'), nullable=False)
    tax = Column(Numeric(14, 2), default=Decimal('0.00'), nullable=False)
    net_amount = Column(Numeric(14, 2), nullable=False)

    status = Column(String(30), default='COMPLETED', nullable=False)  # COMPLETED, SETTLED, PENDING, FAILED, REFUNDED
    transaction_time = Column(DateTime(timezone=True), nullable=False, index=True)
    
    raw_metadata = Column(JSON, default=dict)
    is_synthetic = Column(Boolean, default=False, nullable=False)
    is_reconciled = Column(Boolean, default=False, nullable=False, index=True)

    # Relationships
    source_file = relationship('ImportedFile', backref='transactions')

    def to_dict(self):
        return {
            'id': self.id,
            'source_file_id': self.source_file_id,
            'source_type': self.source_type,
            'external_reference_id': self.external_reference_id,
            'merchant_order_id': self.merchant_order_id,
            'counterparty': self.counterparty,
            'amount': float(self.amount) if self.amount is not None else 0.0,
            'currency': self.currency,
            'fee': float(self.fee) if self.fee is not None else 0.0,
            'tax': float(self.tax) if self.tax is not None else 0.0,
            'net_amount': float(self.net_amount) if self.net_amount is not None else 0.0,
            'status': self.status,
            'transaction_time': self.transaction_time.isoformat() if self.transaction_time else None,
            'is_synthetic': self.is_synthetic,
            'is_reconciled': self.is_reconciled,
            'raw_metadata': self.raw_metadata or {}
        }
