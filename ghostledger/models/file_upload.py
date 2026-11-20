from sqlalchemy import Column, Integer, String, JSON, DateTime
from ghostledger.extensions import Base
from ghostledger.models.base import TimestampMixin, get_utc_now


class ImportedFile(Base, TimestampMixin):
    __tablename__ = 'imported_files'

    id = Column(Integer, primary_key=True)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(50), nullable=False)  # PAYMENT, BANK_STATEMENT, SETTLEMENT, INVOICE, REFUND
    file_hash = Column(String(64), nullable=False, index=True)  # SHA-256 for idempotency
    record_count = Column(Integer, default=0, nullable=False)
    valid_count = Column(Integer, default=0, nullable=False)
    error_count = Column(Integer, default=0, nullable=False)
    status = Column(String(30), default='COMPLETED', nullable=False)  # COMPLETED, FAILED, PARTIAL
    summary_json = Column(JSON, default=dict)

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'file_type': self.file_type,
            'file_hash': self.file_hash,
            'record_count': self.record_count,
            'valid_count': self.valid_count,
            'error_count': self.error_count,
            'status': self.status,
            'summary_json': self.summary_json,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
