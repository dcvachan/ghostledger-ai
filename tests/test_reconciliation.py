from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from ghostledger.models import Transaction, ReconciliationRun, ReconciliationMatch, DiscrepancyException
from ghostledger.services.reconciliation_engine import ReconciliationEngine


def test_pass_1_exact_id_matching(app, db):
    with app.app_context():
        now = datetime.now(timezone.utc)
        # 1 Payment
        pay = Transaction(
            source_type='PAYMENT',
            external_reference_id='pay_exact_100',
            merchant_order_id='ord_100',
            amount=Decimal('5000.00'),
            currency='INR',
            net_amount=Decimal('4900.00'),
            fee=Decimal('100.00'),
            status='COMPLETED',
            transaction_time=now
        )
        # 1 Bank Statement referencing exact payment ID
        bank = Transaction(
            source_type='BANK_STATEMENT',
            external_reference_id='bank_exact_100',
            merchant_order_id='ord_100',
            amount=Decimal('5000.00'),
            currency='INR',
            net_amount=Decimal('5000.00'),
            status='COMPLETED',
            transaction_time=now,
            raw_metadata={'payment_id': 'pay_exact_100'}
        )
        db.session.add_all([pay, bank])
        db.session.commit()

        engine = ReconciliationEngine()
        run = engine.run(actor='test_analyst')

        assert run.status == 'COMPLETED'
        assert run.total_records == 1
        assert run.matched_records == 1
        assert run.match_rate == Decimal('100.00')

        match = db.session.query(ReconciliationMatch).filter_by(primary_tx_id=pay.id).first()
        assert match is not None
        assert match.match_type == 'EXACT_ID'
        assert match.confidence_score == Decimal('100.00')
        assert pay.is_reconciled is True
        assert bank.is_reconciled is True


def test_pass_2_heuristic_matching(app, db):
    with app.app_context():
        now = datetime.now(timezone.utc)
        # Different reference IDs, but identical order_id, amount, currency within 2 hours
        pay = Transaction(
            source_type='PAYMENT',
            external_reference_id='pay_heur_200',
            merchant_order_id='ord_heur_200',
            amount=Decimal('3500.00'),
            currency='INR',
            net_amount=Decimal('3500.00'),
            status='COMPLETED',
            transaction_time=now
        )
        settle = Transaction(
            source_type='SETTLEMENT',
            external_reference_id='setl_heur_200',
            merchant_order_id='ord_heur_200',
            amount=Decimal('3500.00'),
            currency='INR',
            net_amount=Decimal('3500.00'),
            status='SETTLED',
            transaction_time=now + timedelta(hours=2)
        )
        db.session.add_all([pay, settle])
        db.session.commit()

        engine = ReconciliationEngine()
        run = engine.run(actor='test_analyst')

        assert run.matched_records == 1
        match = db.session.query(ReconciliationMatch).filter_by(primary_tx_id=pay.id).first()
        assert match is not None
        assert match.match_type == 'EXACT_HEURISTIC'
        assert match.confidence_score == Decimal('95.00')


def test_ambiguity_guard_prevents_silent_match(app, db):
    with app.app_context():
        now = datetime.now(timezone.utc)
        # 1 Payment with Order ORD_AMBIG
        pay = Transaction(
            source_type='PAYMENT',
            external_reference_id='pay_ambig_1',
            merchant_order_id='ORD_AMBIG',
            amount=Decimal('1200.00'),
            currency='INR',
            net_amount=Decimal('1200.00'),
            status='COMPLETED',
            transaction_time=now
        )
        # TWO Candidate bank deposits with identical order ORD_AMBIG and identical amount
        bank1 = Transaction(
            source_type='BANK_STATEMENT',
            external_reference_id='bank_cand_1',
            merchant_order_id='ORD_AMBIG',
            amount=Decimal('1200.00'),
            currency='INR',
            net_amount=Decimal('1200.00'),
            status='COMPLETED',
            transaction_time=now + timedelta(minutes=5)
        )
        bank2 = Transaction(
            source_type='BANK_STATEMENT',
            external_reference_id='bank_cand_2',
            merchant_order_id='ORD_AMBIG',
            amount=Decimal('1200.00'),
            currency='INR',
            net_amount=Decimal('1200.00'),
            status='COMPLETED',
            transaction_time=now + timedelta(minutes=10)
        )
        db.session.add_all([pay, bank1, bank2])
        db.session.commit()

        engine = ReconciliationEngine()
        run = engine.run(actor='test_analyst')

        # Engine must NOT guess! It should keep as exception
        assert run.matched_records == 0
        exc = db.session.query(DiscrepancyException).filter_by(transaction_id=pay.id).first()
        assert exc is not None
        assert exc.exception_type == 'AMBIGUOUS_CANDIDATE'
        assert exc.severity == 'HIGH'
        assert 'ambiguous' in exc.evidence_summary.lower()


def test_duplicate_payment_detection(app, db):
    with app.app_context():
        now = datetime.now(timezone.utc)
        # Duplicate charges on same order ID
        pay1 = Transaction(
            source_type='PAYMENT',
            external_reference_id='pay_dup_a',
            merchant_order_id='ORD_DOUBLE_CHARGE',
            amount=Decimal('4200.00'),
            currency='INR',
            net_amount=Decimal('4200.00'),
            status='COMPLETED',
            transaction_time=now
        )
        pay2 = Transaction(
            source_type='PAYMENT',
            external_reference_id='pay_dup_b',
            merchant_order_id='ORD_DOUBLE_CHARGE',
            amount=Decimal('4200.00'),
            currency='INR',
            net_amount=Decimal('4200.00'),
            status='COMPLETED',
            transaction_time=now + timedelta(minutes=2)
        )
        db.session.add_all([pay1, pay2])
        db.session.commit()

        engine = ReconciliationEngine()
        run = engine.run(actor='test_analyst')

        assert run.discrepancy_records >= 2
        dup_exceptions = db.session.query(DiscrepancyException).filter_by(exception_type='DUPLICATE_PAYMENT').all()
        assert len(dup_exceptions) == 2
        assert dup_exceptions[0].severity == 'HIGH'


def test_missing_settlement_detection(app, db):
    with app.app_context():
        old_time = datetime.now(timezone.utc) - timedelta(days=5)
        # Completed payment older than 3 days with NO settlement record
        pay = Transaction(
            source_type='PAYMENT',
            external_reference_id='pay_old_unsettled',
            merchant_order_id='ORD_OLD_1',
            amount=Decimal('8500.00'),
            currency='INR',
            net_amount=Decimal('8500.00'),
            status='COMPLETED',
            transaction_time=old_time
        )
        db.session.add(pay)
        db.session.commit()

        engine = ReconciliationEngine()
        run = engine.run(actor='test_analyst')

        exc = db.session.query(DiscrepancyException).filter_by(transaction_id=pay.id).first()
        assert exc is not None
        assert exc.exception_type == 'MISSING_SETTLEMENT'
        assert exc.amount_exposed == Decimal('8500.00')
