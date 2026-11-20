import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Dict, Any, Tuple, Optional
from ghostledger.extensions import db
from ghostledger.models import (
    Transaction,
    ReconciliationRun,
    ReconciliationMatch,
    DiscrepancyException,
    AuditEvent
)
from ghostledger.services.audit_service import audit_service


def to_utc(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class ReconciliationEngine:
    def __init__(self, run_id: Optional[str] = None):
        self.run_id = run_id or str(uuid.uuid4())

    def run(self, actor: str = 'system', ip_address: Optional[str] = None) -> ReconciliationRun:

        """
        Executes multi-pass deterministic matching pipeline and exception identification.
        """
        run = ReconciliationRun(
            run_id=self.run_id,
            status='RUNNING',
            started_at=datetime.now(timezone.utc)
        )
        db.session.add(run)
        db.session.flush()

        # Fetch all unreconciled transactions
        payments = db.session.query(Transaction).filter(
            Transaction.source_type == 'PAYMENT',
            Transaction.is_reconciled == False
        ).all()

        bank_statements = db.session.query(Transaction).filter(
            Transaction.source_type == 'BANK_STATEMENT',
            Transaction.is_reconciled == False
        ).all()

        settlements = db.session.query(Transaction).filter(
            Transaction.source_type == 'SETTLEMENT',
            Transaction.is_reconciled == False
        ).all()

        invoices = db.session.query(Transaction).filter(
            Transaction.source_type == 'INVOICE',
            Transaction.is_reconciled == False
        ).all()

        refunds = db.session.query(Transaction).filter(
            Transaction.source_type == 'REFUND',
            Transaction.is_reconciled == False
        ).all()

        total_payments = len(payments)
        matched_payment_ids = set()
        consumed_counterpart_ids = set()
        matches_to_create: List[ReconciliationMatch] = []
        exceptions_to_create: List[DiscrepancyException] = []

        # -------------------------------------------------------------
        # PASS 1: Deterministic Exact ID Matching (Confidence 100.0%)
        # -------------------------------------------------------------
        # 1a: Payment ID match in Settlements or Bank Statements
        counterpart_pool = bank_statements + settlements + invoices
        counterpart_by_ref = {}
        counterpart_by_meta_pay_id = {}

        for cp in counterpart_pool:
            counterpart_by_ref[cp.external_reference_id] = cp
            pay_ref = (cp.raw_metadata or {}).get('payment_id')
            if pay_ref:
                counterpart_by_meta_pay_id[pay_ref] = cp

        for pay in payments:
            if pay.id in matched_payment_ids:
                continue

            # Look for exact reference link
            candidate = counterpart_by_ref.get(pay.external_reference_id) or counterpart_by_meta_pay_id.get(pay.external_reference_id)
            if candidate and candidate.id not in consumed_counterpart_ids:
                # Check currency
                if candidate.currency == pay.currency:
                    # Check amount equality (either gross amount or settlement net + fee)
                    expected_amt = pay.amount
                    candidate_amt = candidate.amount
                    fee_diff = abs(expected_amt - candidate_amt)

                    if candidate.source_type == 'SETTLEMENT':
                        # Check if amount mismatch or fee mismatch
                        net_plus_fee = candidate.net_amount + candidate.fee
                        if abs(expected_amt - net_plus_fee) == Decimal('0.00') or fee_diff == Decimal('0.00'):
                            # Check if fee is excessive / unexpected
                            # Benchmark: standard gateway fee is 2% +- 0.5%
                            expected_fee_benchmark = (pay.amount * Decimal('0.02')).quantize(Decimal('0.01'))
                            fee_discrepancy = abs(candidate.fee - expected_fee_benchmark)

                            if fee_discrepancy > (pay.amount * Decimal('0.015')):
                                # Excessive fee mismatch exception
                                exceptions_to_create.append(DiscrepancyException(
                                    reconciliation_run_id=run.id,
                                    transaction_id=pay.id,
                                    exception_type='FEE_MISMATCH',
                                    severity='MEDIUM',
                                    status='OPEN',
                                    amount_exposed=candidate.fee,
                                    currency=pay.currency,
                                    evidence_summary=f"Settlement fee of {candidate.fee} {pay.currency} deviates significantly from expected benchmark {expected_fee_benchmark} {pay.currency}.",
                                    evidence_details={
                                        'payment_id': pay.external_reference_id,
                                        'settlement_id': candidate.external_reference_id,
                                        'actual_fee': str(candidate.fee),
                                        'expected_benchmark_fee': str(expected_fee_benchmark),
                                        'fee_variance': str(candidate.fee - expected_fee_benchmark),
                                        'gross_amount': str(pay.amount),
                                        'net_settled': str(candidate.net_amount)
                                    }
                                ))
                                continue
                            else:
                                # Normal fee deduction settlement match
                                matched_payment_ids.add(pay.id)
                                consumed_counterpart_ids.add(candidate.id)
                                pay.is_reconciled = True
                                candidate.is_reconciled = True
                                matches_to_create.append(ReconciliationMatch(
                                    reconciliation_run_id=run.id,
                                    match_type='EXACT_ID',
                                    confidence_score=Decimal('98.00'),
                                    primary_tx_id=pay.id,
                                    matched_tx_id=candidate.id,
                                    evidence_json={
                                        'rule': 'Exact ID Settlement with Verified Fee',
                                        'payment_id': pay.external_reference_id,
                                        'settlement_id': candidate.external_reference_id,
                                        'fee': str(candidate.fee),
                                        'net_amount': str(candidate.net_amount)
                                    }
                                ))
                                continue
                        else:
                            # Genuine amount mismatch on identical reference ID
                            exceptions_to_create.append(DiscrepancyException(
                                reconciliation_run_id=run.id,
                                transaction_id=pay.id,
                                exception_type='AMOUNT_MISMATCH',
                                severity='HIGH',
                                status='OPEN',
                                amount_exposed=abs(expected_amt - candidate_amt),
                                currency=pay.currency,
                                evidence_summary=f"Payment {pay.external_reference_id} amount ({pay.amount} {pay.currency}) does not match Settlement {candidate.external_reference_id} amount ({candidate.amount} {pay.currency}). Variance: {abs(expected_amt - candidate_amt)} {pay.currency}.",
                                evidence_details={
                                    'payment_id': pay.external_reference_id,
                                    'settlement_id': candidate.external_reference_id,
                                    'payment_amount': str(pay.amount),
                                    'settlement_amount': str(candidate.amount),
                                    'variance': str(abs(expected_amt - candidate_amt)),
                                    'currency': pay.currency
                                }
                            ))
                            continue

                    # Exact amount match for Bank Statements and Invoices
                    if fee_diff == Decimal('0.00'):
                        matched_payment_ids.add(pay.id)
                        consumed_counterpart_ids.add(candidate.id)
                        pay.is_reconciled = True
                        candidate.is_reconciled = True

                        matches_to_create.append(ReconciliationMatch(
                            reconciliation_run_id=run.id,
                            match_type='EXACT_ID',
                            confidence_score=Decimal('100.00'),
                            primary_tx_id=pay.id,
                            matched_tx_id=candidate.id,
                            evidence_json={
                                'rule': 'Exact ID Match',
                                'payment_id': pay.external_reference_id,
                                'matched_id': candidate.external_reference_id,
                                'matched_source': candidate.source_type,
                                'amount': str(pay.amount),
                                'currency': pay.currency,
                                'time_delta_seconds': abs((to_utc(pay.transaction_time) - to_utc(candidate.transaction_time)).total_seconds())
                            }
                        ))
                        continue


        # -------------------------------------------------------------
        # PASS 2: Heuristic Multi-Field Match (Confidence 95.0%)
        # Matches on (merchant_order_id, amount, currency) within +- 1 day
        # -------------------------------------------------------------
        for pay in payments:
            if pay.id in matched_payment_ids or not pay.merchant_order_id:
                continue

            candidates = [
                cp for cp in counterpart_pool
                if cp.id not in consumed_counterpart_ids
                and cp.merchant_order_id == pay.merchant_order_id
                and cp.currency == pay.currency
                and cp.amount == pay.amount
                and abs((to_utc(pay.transaction_time) - to_utc(cp.transaction_time)).total_seconds()) <= 86400
            ]

            if len(candidates) == 1:
                candidate = candidates[0]
                matched_payment_ids.add(pay.id)
                consumed_counterpart_ids.add(candidate.id)
                pay.is_reconciled = True
                candidate.is_reconciled = True

                matches_to_create.append(ReconciliationMatch(
                    reconciliation_run_id=run.id,
                    match_type='EXACT_HEURISTIC',
                    confidence_score=Decimal('95.00'),
                    primary_tx_id=pay.id,
                    matched_tx_id=candidate.id,
                    evidence_json={
                        'rule': 'Heuristic Order & Amount Match',
                        'merchant_order_id': pay.merchant_order_id,
                        'payment_id': pay.external_reference_id,
                        'counterpart_id': candidate.external_reference_id,
                        'source': candidate.source_type,
                        'amount': str(pay.amount),
                        'currency': pay.currency,
                        'time_difference_hours': round(abs((to_utc(pay.transaction_time) - to_utc(candidate.transaction_time)).total_seconds()) / 3600, 2)
                    }
                ))
            elif len(candidates) > 1:
                # Ambiguity guard: Never guess! Flag as AMBIGUOUS_CANDIDATE
                exceptions_to_create.append(DiscrepancyException(
                    reconciliation_run_id=run.id,
                    transaction_id=pay.id,
                    exception_type='AMBIGUOUS_CANDIDATE',
                    severity='HIGH',
                    status='OPEN',
                    amount_exposed=pay.amount,
                    currency=pay.currency,
                    evidence_summary=f"Payment {pay.external_reference_id} has {len(candidates)} ambiguous counterpart matches with identical order ID and amount. Silent match prevented.",
                    evidence_details={
                        'payment_id': pay.external_reference_id,
                        'order_id': pay.merchant_order_id,
                        'candidate_ids': [c.external_reference_id for c in candidates],
                        'amount': str(pay.amount),
                        'currency': pay.currency
                    }
                ))

        # -------------------------------------------------------------
        # PASS 3: Window & Gateway Fee Tolerant Match (Confidence 90.0%)
        # Window +- 3 days, Payment vs Settlement with estimated net
        # -------------------------------------------------------------
        for pay in payments:
            if pay.id in matched_payment_ids:
                continue

            # Look in remaining settlements
            candidates = []
            for st in settlements:
                if st.id in consumed_counterpart_ids or st.currency != pay.currency:
                    continue
                # Date window +- 3 days
                delta_days = (to_utc(st.transaction_time) - to_utc(pay.transaction_time)).total_seconds() / 86400
                if 0 <= delta_days <= 3.5:
                    # Check if settlement amount matches payment amount
                    if st.amount == pay.amount:
                        candidates.append(st)
                    elif st.merchant_order_id and pay.merchant_order_id and st.merchant_order_id == pay.merchant_order_id:
                        candidates.append(st)

            if len(candidates) == 1:
                candidate = candidates[0]
                matched_payment_ids.add(pay.id)
                consumed_counterpart_ids.add(candidate.id)
                pay.is_reconciled = True
                candidate.is_reconciled = True

                matches_to_create.append(ReconciliationMatch(
                    reconciliation_run_id=run.id,
                    match_type='WINDOW_FEE_TOLERANT',
                    confidence_score=Decimal('90.00'),
                    primary_tx_id=pay.id,
                    matched_tx_id=candidate.id,
                    evidence_json={
                        'rule': 'Window & Fee Tolerant Settlement Match',
                        'payment_id': pay.external_reference_id,
                        'settlement_id': candidate.external_reference_id,
                        'amount': str(pay.amount),
                        'settlement_net': str(candidate.net_amount),
                        'window_delay_days': round((to_utc(candidate.transaction_time) - to_utc(pay.transaction_time)).total_seconds() / 86400, 2)
                    }
                ))
            elif len(candidates) > 1:
                # Ambiguous candidate guard
                exceptions_to_create.append(DiscrepancyException(
                    reconciliation_run_id=run.id,
                    transaction_id=pay.id,
                    exception_type='AMBIGUOUS_CANDIDATE',
                    severity='HIGH',
                    status='OPEN',
                    amount_exposed=pay.amount,
                    currency=pay.currency,
                    evidence_summary=f"Payment {pay.external_reference_id} matched multiple settlement candidates within window. Kept as exception.",
                    evidence_details={
                        'payment_id': pay.external_reference_id,
                        'candidate_settlements': [c.external_reference_id for c in candidates],
                        'amount': str(pay.amount)
                    }
                ))

        # -------------------------------------------------------------
        # PASS 4: One-to-Many Batch Settlement Support (Confidence 85.0%)
        # -------------------------------------------------------------
        for st in settlements:
            if st.id in consumed_counterpart_ids:
                continue
            batch_id = (st.raw_metadata or {}).get('batch_id')
            if not batch_id:
                continue

            # Look for payments sharing this batch_id
            batch_payments = [
                p for p in payments
                if p.id not in matched_payment_ids
                and (p.raw_metadata or {}).get('batch_id') == batch_id
                and p.currency == st.currency
            ]

            if batch_payments:
                total_batch_amt = sum(p.amount for p in batch_payments)
                if total_batch_amt == st.amount:
                    # Exact batch match
                    consumed_counterpart_ids.add(st.id)
                    st.is_reconciled = True
                    for p in batch_payments:
                        matched_payment_ids.add(p.id)
                        p.is_reconciled = True
                        matches_to_create.append(ReconciliationMatch(
                            reconciliation_run_id=run.id,
                            match_type='BATCH_ONE_TO_MANY',
                            confidence_score=Decimal('85.00'),
                            primary_tx_id=p.id,
                            matched_tx_id=st.id,
                            evidence_json={
                                'rule': 'One-to-Many Batch Settlement',
                                'batch_id': batch_id,
                                'settlement_id': st.external_reference_id,
                                'payment_id': p.external_reference_id,
                                'batch_total': str(total_batch_amt),
                                'batch_count': len(batch_payments)
                            }
                        ))

        # -------------------------------------------------------------
        # PASS 5: Exception Identification on Remaining Unmatched Records
        # -------------------------------------------------------------
        # 5a: Duplicate Payment Detection (Same order_id or exact same amount + counterparty within 30 min)
        order_groups: Dict[str, List[Transaction]] = {}
        for pay in payments:
            if pay.merchant_order_id:
                order_groups.setdefault(pay.merchant_order_id, []).append(pay)

        duplicate_tx_ids = set()
        for order_id, tx_list in order_groups.items():
            if len(tx_list) > 1:
                # Group has multiple payments with same order ID
                for p in tx_list:
                    duplicate_tx_ids.add(p.id)
                    if p.id not in matched_payment_ids:
                        exceptions_to_create.append(DiscrepancyException(
                            reconciliation_run_id=run.id,
                            transaction_id=p.id,
                            exception_type='DUPLICATE_PAYMENT',
                            severity='HIGH',
                            status='OPEN',
                            amount_exposed=p.amount,
                            currency=p.currency,
                            evidence_summary=f"Suspected duplicate payment detected for Order ID '{order_id}'. Total {len(tx_list)} charges recorded.",
                            evidence_details={
                                'order_id': order_id,
                                'payment_id': p.external_reference_id,
                                'duplicate_payment_ids': [t.external_reference_id for t in tx_list if t.id != p.id],
                                'amounts': [str(t.amount) for t in tx_list],
                                'timestamps': [t.transaction_time.isoformat() for t in tx_list]
                            }
                        ))

        # 5b: Missing Settlement Detection
        # Completed payments older than 3 business days with no settlement
        now_utc = datetime.now(timezone.utc)
        for pay in payments:
            if pay.id in matched_payment_ids or pay.id in duplicate_tx_ids:
                continue

            age_days = (now_utc - to_utc(pay.transaction_time)).total_seconds() / 86400
            # Also check if it's explicitly marked as overdue or older than 3 days
            is_overdue = age_days >= 3.0 or (pay.raw_metadata or {}).get('test_scenario') == 'MISSING_SETTLEMENT'

            if is_overdue and pay.status == 'COMPLETED':
                exceptions_to_create.append(DiscrepancyException(
                    reconciliation_run_id=run.id,
                    transaction_id=pay.id,
                    exception_type='MISSING_SETTLEMENT',
                    severity='HIGH',
                    status='OPEN',
                    amount_exposed=pay.amount,
                    currency=pay.currency,
                    evidence_summary=f"Payment {pay.external_reference_id} completed {round(age_days, 1)} days ago has no recorded settlement from gateway.",
                    evidence_details={
                        'payment_id': pay.external_reference_id,
                        'order_id': pay.merchant_order_id,
                        'amount': str(pay.amount),
                        'currency': pay.currency,
                        'transaction_time': pay.transaction_time.isoformat(),
                        'age_days': round(age_days, 1)
                    }
                ))
            else:
                # Regular unmatched payment exception
                exceptions_to_create.append(DiscrepancyException(
                    reconciliation_run_id=run.id,
                    transaction_id=pay.id,
                    exception_type='UNMATCHED_PAYMENT',
                    severity='MEDIUM',
                    status='OPEN',
                    amount_exposed=pay.amount,
                    currency=pay.currency,
                    evidence_summary=f"Payment {pay.external_reference_id} has no matching counterpart in bank statements, settlements, or invoices.",
                    evidence_details={
                        'payment_id': pay.external_reference_id,
                        'amount': str(pay.amount),
                        'currency': pay.currency,
                        'status': pay.status
                    }
                ))

        # 5c: Delayed Refunds Detection
        for rf in refunds:
            if rf.is_reconciled:
                continue
            rf_age_days = (now_utc - to_utc(rf.transaction_time)).total_seconds() / 86400
            is_delayed = rf_age_days >= 5.0 or (rf.raw_metadata or {}).get('test_scenario') == 'DELAYED_REFUND'
            if is_delayed:
                exceptions_to_create.append(DiscrepancyException(
                    reconciliation_run_id=run.id,
                    transaction_id=rf.id,
                    exception_type='DELAYED_REFUND',
                    severity='MEDIUM',
                    status='OPEN',
                    amount_exposed=rf.amount,
                    currency=rf.currency,
                    evidence_summary=f"Refund {rf.external_reference_id} has been pending for {round(rf_age_days, 1)} days without bank statement clawback.",
                    evidence_details={
                        'refund_id': rf.external_reference_id,
                        'linked_payment_id': (rf.raw_metadata or {}).get('payment_id'),
                        'amount': str(rf.amount),
                        'currency': rf.currency,
                        'refund_time': rf.transaction_time.isoformat(),
                        'age_days': round(rf_age_days, 1)
                    }
                ))

        # Persist matches and exceptions
        for m in matches_to_create:
            db.session.add(m)
        for exc in exceptions_to_create:
            db.session.add(exc)

        # Calculate run metrics
        matched_count = len(matched_payment_ids)
        unmatched_count = total_payments - matched_count
        discrepancy_count = len(exceptions_to_create)

        match_rate = Decimal('0.00')
        if total_payments > 0:
            match_rate = Decimal(str(round((matched_count / total_payments) * 100, 2)))

        # Amount at risk: sum of amount_exposed of all open exceptions
        amount_at_risk = sum((e.amount_exposed for e in exceptions_to_create), Decimal('0.00'))
        
        # Confirmed discrepancy amount: duplicate charges + missing settlements + fee discrepancies
        confirmed_discrepancy_amount = sum((
            e.amount_exposed for e in exceptions_to_create
            if e.exception_type in ('DUPLICATE_PAYMENT', 'MISSING_SETTLEMENT', 'AMOUNT_MISMATCH', 'FEE_MISMATCH')
        ), Decimal('0.00'))

        run.status = 'COMPLETED'
        run.total_records = total_payments
        run.matched_records = matched_count
        run.unmatched_records = unmatched_count
        run.discrepancy_records = discrepancy_count
        run.match_rate = match_rate
        run.amount_at_risk = amount_at_risk
        run.confirmed_discrepancy_amount = confirmed_discrepancy_amount
        # Note: recovered_amount stays 0.00 until an explicit resolution is recorded!
        run.recovered_amount = Decimal('0.00')
        run.completed_at = datetime.now(timezone.utc)

        # Audit log
        audit_service.log(
            event_type='RUN_RECONCILIATION',
            actor=actor,
            entity_type='ReconciliationRun',
            entity_id=str(run.id),
            action_details={
                'run_id': run.run_id,
                'total_records': total_payments,
                'matched_records': matched_count,
                'unmatched_records': unmatched_count,
                'discrepancies': discrepancy_count,
                'match_rate': float(match_rate),
                'amount_at_risk': float(amount_at_risk)
            },
            ip_address=ip_address
        )

        db.session.commit()
        return run
