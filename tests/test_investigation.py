from datetime import datetime, timezone
from decimal import Decimal
import pytest
from ghostledger.models import Transaction, DiscrepancyException, InvestigationReport, ReconciliationRun
from ghostledger.services.agent_tools import agent_tools
from ghostledger.services.investigation_engine import investigation_engine


def test_agent_tools_transaction_details_and_compare(app, db):
    with app.app_context():
        now = datetime.now(timezone.utc)
        pay = Transaction(
            source_type='PAYMENT',
            external_reference_id='pay_tool_test',
            merchant_order_id='ORD_TOOL',
            amount=Decimal('10000.00'),
            currency='INR',
            net_amount=Decimal('9800.00'),
            fee=Decimal('200.00'),
            status='COMPLETED',
            transaction_time=now
        )
        setl = Transaction(
            source_type='SETTLEMENT',
            external_reference_id='setl_tool_test',
            merchant_order_id='ORD_TOOL',
            amount=Decimal('10000.00'),
            currency='INR',
            net_amount=Decimal('9650.00'),
            fee=Decimal('350.00'),  # Inflated fee
            status='SETTLED',
            transaction_time=now
        )
        db.session.add_all([pay, setl])
        db.session.commit()

        # Tool 1: get_transaction_details
        details = agent_tools.get_transaction_details(pay.id)
        assert details['found'] is True
        assert details['amount'] == 10000.0
        assert details['currency'] == 'INR'

        # Tool 2: compare_settlement_amounts
        comp = agent_tools.compare_settlement_amounts(pay.id, setl.id)
        assert comp['gross_amount'] == 10000.0
        assert comp['actual_fee_deducted'] == 350.0
        assert comp['benchmark_standard_fee'] == 200.0
        assert comp['is_fee_inflated'] is True


def test_investigation_deterministic_fallback_no_llm(app, db):
    with app.app_context():
        now = datetime.now(timezone.utc)
        run = ReconciliationRun(run_id='test-run-inv', status='COMPLETED')
        db.session.add(run)
        db.session.flush()

        pay = Transaction(
            source_type='PAYMENT',
            external_reference_id='pay_dup_inv',
            merchant_order_id='ORD_INV_DUP',
            amount=Decimal('2500.00'),
            currency='INR',
            net_amount=Decimal('2500.00'),
            status='COMPLETED',
            transaction_time=now
        )
        db.session.add(pay)
        db.session.flush()

        exc = DiscrepancyException(
            reconciliation_run_id=run.id,
            transaction_id=pay.id,
            exception_type='DUPLICATE_PAYMENT',
            severity='HIGH',
            status='OPEN',
            amount_exposed=Decimal('2500.00'),
            currency='INR',
            evidence_summary='Suspected duplicate charge',
            evidence_details={'order_id': 'ORD_INV_DUP'}
        )
        db.session.add(exc)
        db.session.commit()

        # Execute investigation without LLM API key
        report = investigation_engine.investigate_exception(exc.id, actor='test_analyst')

        assert report is not None
        # Must strictly identify as RULES_ENGINE and never pretend to be LLM
        assert report.engine_used == 'RULES_ENGINE'
        assert report.model_name is None
        assert report.confidence_score >= Decimal('80.00')
        assert report.priority == 'HIGH'
        assert len(report.evidence_items) > 0
        assert len(report.alternative_hypotheses) > 0
        assert report.recommended_action_type in (
            'CREATE_FOLLOW_UP_TASK',
            'DRAFT_REFUND_INQUIRY',
            'PROPOSED_RECONCILIATION_ADJUSTMENT',
            'FLAG_SUSPECTED_DUPLICATE'
        )
