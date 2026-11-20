from decimal import Decimal
from sqlalchemy import Column, Integer, String, Numeric, DateTime, Text, ForeignKey, JSON
from ghostledger.extensions import Base
from ghostledger.models.base import TimestampMixin, get_utc_now


class InvestigationReport(Base, TimestampMixin):
    __tablename__ = 'investigation_reports'

    id = Column(Integer, primary_key=True)
    exception_id = Column(Integer, ForeignKey('discrepancy_exceptions.id', ondelete='CASCADE'), nullable=False)
    
    engine_used = Column(String(20), nullable=False)  # RULES_ENGINE, LLM_AGENT
    model_name = Column(String(64), nullable=True)
    confidence_score = Column(Numeric(5, 2), nullable=False)  # 0.0 - 100.0%
    
    root_cause = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    evidence_items = Column(JSON, default=list)  # list of {field, expected, actual, source_id, note}
    alternative_hypotheses = Column(JSON, default=list)  # list of strings
    
    priority = Column(String(10), nullable=False)  # HIGH, MEDIUM, LOW
    priority_rationale = Column(Text, nullable=False)
    
    recommended_action_type = Column(String(64), nullable=False)
    recommended_action_payload = Column(JSON, default=dict)

    def to_dict(self):
        return {
            'id': self.id,
            'exception_id': self.exception_id,
            'engine_used': self.engine_used,
            'model_name': self.model_name,
            'confidence_score': float(self.confidence_score) if self.confidence_score is not None else 0.0,
            'root_cause': self.root_cause,
            'explanation': self.explanation,
            'evidence_items': self.evidence_items or [],
            'alternative_hypotheses': self.alternative_hypotheses or [],
            'priority': self.priority,
            'priority_rationale': self.priority_rationale,
            'recommended_action_type': self.recommended_action_type,
            'recommended_action_payload': self.recommended_action_payload or {},
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
