from datetime import datetime, timezone
from decimal import Decimal
import pytest
from ghostledger.models import (
    Transaction,
    ReconciliationRun,
    DiscrepancyException,
    DraftAction,
    Resolution
)
from ghostledger.services.agent_tools import agent_tools
from ghostledger.services.action_service import action_service
from ghostledger.services.reporting_service import reporting_service


def test_draft_action_and_human_review_workflow(app, db):
    with app.app_context():
        now = datetime.now(timezone.utc)
        run = ReconciliationRun(
            run_id='run-act-1',
            status='COMPLETED',
            amount_at_risk=Decimal('5000.00'),
            recovered_amount=Decimal('0.00')
        )
        db.session.add(run)
        db.session.flush()

        tx = Transaction(
            source_type='PAYMENT',
            external_reference_id='pay_act_1',
            amount=Decimal('5000.00'),
            currency='INR',
            net_amount=Decimal('5000.00'),
            status='COMPLETED',
            transaction_time=now
        )
        db.session.add(tx)
        db.session.flush()

        exc = DiscrepancyException(
            reconciliation_run_id=run.id,
            transaction_id=tx.id,
            exception_type='FEE_MISMATCH',
            severity='MEDIUM',
            status='OPEN',
            amount_exposed=Decimal('350.00'),
            currency='INR',
            evidence_summary='Excess fee deducted'
        )
        db.session.add(exc)
        db.session.commit()

        # Step 1: Agent creates draft action
        draft_res = agent_tools.create_draft_action(
            exception_id=exc.id,
            action_type='CREATE_FOLLOW_UP_TASK',
            payload={'delta': 350.0},
            rationale='Inquire with gateway support'
        )
        assert draft_res['success'] is True
        action_id = draft_res['draft_action_id']

        # Assert status is strictly DRAFT (no real money moved)
        action = db.session.query(DraftAction).filter_by(id=action_id).first()
        assert action.status == 'DRAFT'
        assert exc.status == 'DRAFTED_ACTION'

        # Step 2: Human reviewer approves the action
        rev_res = action_service.review_draft_action(
            action_id=action_id,
            decision='APPROVED',
            reviewer='lead_auditor',
            review_comment='Confirmed fee delta with gateway SLA'
        )
        assert rev_res['success'] is True
        assert action.status == 'APPROVED'
        assert action.reviewed_by == 'lead_auditor'

        # Verified recovered funds must STILL be 0.00 before resolution
        metrics = reporting_service.get_dashboard_metrics()
        assert metrics['actual_recovered_amount'] == 0.0

        # Step 3: Record verified resolution
        res_outcome = action_service.record_resolution(
            exception_id=exc.id,
            resolution_type='SETTLEMENT_ADJUSTMENT',
            recovered_amount=Decimal('350.00'),
            verification_notes='Credit adjustment received from gateway on settlement batch #99',
            resolved_by='lead_auditor',
            action_id=action_id
        )
        assert res_outcome['success'] is True
        assert exc.status == 'RESOLVED'
        assert action.status == 'EXECUTED'

        # Now verified recovered amount must accurately reflect 350.00 INR
        metrics_after = reporting_service.get_dashboard_metrics()
        assert metrics_after['actual_recovered_amount'] == 350.0
        assert metrics_after['resolved_exceptions_count'] == 1
