from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional
from ghostledger.extensions import db
from ghostledger.models import (
    DiscrepancyException,
    DraftAction,
    Resolution,
    ReconciliationRun,
    AuditEvent
)
from ghostledger.services.audit_service import audit_service


class ActionService:
    @staticmethod
    def review_draft_action(
        action_id: int,
        decision: str,  # 'APPROVED' or 'REJECTED'
        reviewer: str,
        review_comment: str,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Human reviewer approves or rejects a draft-only action.
        Explicitly enforces the safety boundary: no real money movement.
        """
        action = db.session.query(DraftAction).filter_by(id=action_id).first()
        if not action:
            return {'success': False, 'error': f"DraftAction #{action_id} not found."}

        if action.status != 'DRAFT':
            return {'success': False, 'error': f"DraftAction #{action_id} has already been {action.status.lower()}."}

        decision = decision.upper().strip()
        if decision not in ('APPROVED', 'REJECTED'):
            return {'success': False, 'error': "Decision must be either 'APPROVED' or 'REJECTED'."}

        action.status = decision
        action.reviewed_by = reviewer or 'financial_analyst'
        action.review_comment = review_comment
        action.approved_at = datetime.now(timezone.utc)

        # Audit log
        audit_service.log(
            event_type=f"ACTION_{decision}",
            actor=reviewer,
            entity_type='DraftAction',
            entity_id=str(action.id),
            action_details={
                'action_type': action.action_type,
                'decision': decision,
                'comment': review_comment,
                'exception_id': action.exception_id
            },
            ip_address=ip_address
        )

        db.session.commit()
        return {
            'success': True,
            'action_id': action.id,
            'status': action.status,
            'reviewed_by': action.reviewed_by,
            'message': f"Action #{action.id} successfully {decision.lower()}."
        }

    @staticmethod
    def record_resolution(
        exception_id: int,
        resolution_type: str,
        recovered_amount: Decimal,
        verification_notes: str,
        resolved_by: str,
        action_id: Optional[int] = None,
        ip_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Records a verified resolution.
        Core rule: Never count an amount as recovered until a verified resolution is recorded!
        """
        exc = db.session.query(DiscrepancyException).filter_by(id=exception_id).first()
        if not exc:
            return {'success': False, 'error': f"DiscrepancyException #{exception_id} not found."}

        if exc.status == 'RESOLVED':
            return {'success': False, 'error': f"Exception #{exception_id} is already resolved."}

        allowed_resolutions = {
            'MANUAL_MATCH',
            'SETTLEMENT_ADJUSTMENT',
            'DUPLICATE_VOIDED',
            'REFUND_CONFIRMED',
            'WRITE_OFF'
        }
        if resolution_type not in allowed_resolutions:
            return {'success': False, 'error': f"Invalid resolution_type. Allowed: {sorted(list(allowed_resolutions))}"}

        if recovered_amount < Decimal('0.00'):
            return {'success': False, 'error': "Recovered amount cannot be negative."}

        # If a draft action is linked, mark it executed
        if action_id:
            action = db.session.query(DraftAction).filter_by(id=action_id).first()
            if action and action.status == 'APPROVED':
                action.status = 'EXECUTED'

        resolution = Resolution(
            exception_id=exc.id,
            draft_action_id=action_id,
            resolution_type=resolution_type,
            recovered_amount=recovered_amount,
            currency=exc.currency,
            verification_notes=verification_notes or 'Human analyst verified financial ledger adjustment.',
            resolved_by=resolved_by or 'financial_analyst'
        )
        db.session.add(resolution)
        db.session.flush()

        # Mark exception resolved
        exc.status = 'RESOLVED'

        # Update parent reconciliation run recovered amount and amount at risk
        run = db.session.query(ReconciliationRun).filter_by(id=exc.reconciliation_run_id).first()
        if run:
            # Recompute total recovered amount strictly from verified resolutions for this run
            run_resolutions = db.session.query(Resolution).join(
                DiscrepancyException, Resolution.exception_id == DiscrepancyException.id
            ).filter(DiscrepancyException.reconciliation_run_id == run.id).all()

            total_recovered = sum((r.recovered_amount for r in run_resolutions), Decimal('0.00')) + recovered_amount
            run.recovered_amount = total_recovered

            # Decrement amount at risk
            remaining_risk = sum((
                e.amount_exposed for e in run.exceptions if e.id != exc.id and e.status in ('OPEN', 'UNDER_INVESTIGATION', 'DRAFTED_ACTION')
            ), Decimal('0.00'))
            run.amount_at_risk = remaining_risk

        # Audit log
        audit_service.log(
            event_type='RESOLUTION_RECORDED',
            actor=resolved_by,
            entity_type='Resolution',
            entity_id=str(resolution.id),
            action_details={
                'exception_id': exc.id,
                'resolution_type': resolution_type,
                'recovered_amount': str(recovered_amount),
                'currency': exc.currency,
                'notes': verification_notes
            },
            ip_address=ip_address
        )

        db.session.commit()
        return {
            'success': True,
            'resolution_id': resolution.id,
            'recovered_amount': float(recovered_amount),
            'currency': exc.currency,
            'message': f"Resolution recorded successfully. Recovered funds: {recovered_amount} {exc.currency}."
        }


action_service = ActionService()
