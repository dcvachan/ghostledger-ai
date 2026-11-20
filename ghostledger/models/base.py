from datetime import datetime, timezone
from sqlalchemy import Column, Integer, DateTime
from ghostledger.extensions import Base


def get_utc_now():
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=get_utc_now, onupdate=get_utc_now, nullable=False)
