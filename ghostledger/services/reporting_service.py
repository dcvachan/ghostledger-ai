import io
import csv
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy import func
from ghostledger.extensions import db
from ghostledger.models import (
    Transaction,
    ReconciliationRun,
    ReconciliationMatch,
    DiscrepancyException,
    Resolution,
    AuditEvent
)


class ReportingService:
    @staticmethod
    def get_dashboard_metrics() -> Dict[str, Any]:
        """
        Calculates executive KPIs across all runs with mathematical consistency.
        Distinguishes estimated amount at risk, confirmed discrepancies, and actual recovered money.
        """
        # Latest or aggregate runs
        latest_run = db.session.query(ReconciliationRun).order_by(ReconciliationRun.id.desc()).first()

        total_payments = db.session.query(func.count(Transaction.id)).filter(
            Transaction.source_type == 'PAYMENT'
        ).scalar() or 0

        matched_payments = db.session.query(func.count(Transaction.id)).filter(
            Transaction.source_type == 'PAYMENT',
            Transaction.is_reconciled == True
        ).scalar() or 0

        unmatched_payments = total_payments - matched_payments
        match_rate = round((matched_payments / total_payments * 100), 2) if total_payments > 0 else 0.0

        # Exceptions
        open_exceptions = db.session.query(DiscrepancyException).filter(
            DiscrepancyException.status.in_(['OPEN', 'UNDER_INVESTIGATION', 'DRAFTED_ACTION'])
        ).all()
        
        resolved_exceptions = db.session.query(DiscrepancyException).filter(
            DiscrepancyException.status == 'RESOLVED'
        ).all()

        total_discrepancy_count = len(open_exceptions) + len(resolved_exceptions)

        # Estimated Amount at Risk: sum of exposure for active unresolved exceptions
        amount_at_risk = sum((e.amount_exposed for e in open_exceptions), Decimal('0.00'))

        # Confirmed Discrepancy Exposure
        confirmed_discrepancies_amount = sum((
            e.amount_exposed for e in open_exceptions
            if e.exception_type in ('DUPLICATE_PAYMENT', 'MISSING_SETTLEMENT', 'AMOUNT_MISMATCH', 'FEE_MISMATCH')
        ), Decimal('0.00'))

        # Actual Recovered Money: Strictly from verified resolutions
        verified_resolutions = db.session.query(Resolution).all()
        actual_recovered_amount = sum((r.recovered_amount for r in verified_resolutions), Decimal('0.00'))

        # Discrepancy Breakdown by Category
        breakdown_counts = {}
        for exc in open_exceptions + resolved_exceptions:
            cat = exc.exception_type
            breakdown_counts[cat] = breakdown_counts.get(cat, 0) + 1

        # Match Type Breakdown
        matches = db.session.query(ReconciliationMatch).all()
        match_breakdown = {}
        for m in matches:
            match_breakdown[m.match_type] = match_breakdown.get(m.match_type, 0) + 1

        return {
            'total_records': total_payments,
            'matched_records': matched_payments,
            'unmatched_records': unmatched_payments,
            'discrepancy_count': total_discrepancy_count,
            'open_exceptions_count': len(open_exceptions),
            'resolved_exceptions_count': len(resolved_exceptions),
            'match_rate': match_rate,
            'amount_at_risk': float(amount_at_risk),
            'confirmed_discrepancies_amount': float(confirmed_discrepancies_amount),
            'actual_recovered_amount': float(actual_recovered_amount),
            'currency': 'INR',
            'discrepancy_breakdown': breakdown_counts,
            'match_breakdown': match_breakdown,
            'latest_run_id': latest_run.run_id if latest_run else None,
            'latest_run_time': latest_run.completed_at.isoformat() if latest_run and latest_run.completed_at else None
        }

    @staticmethod
    def filter_exceptions(
        status: Optional[str] = None,
        severity: Optional[str] = None,
        exception_type: Optional[str] = None,
        min_amount: Optional[Decimal] = None,
        max_amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
        limit: int = 100
    ) -> List[DiscrepancyException]:
        """
        Filters discrepancy exceptions by criteria.
        """
        query = db.session.query(DiscrepancyException)
        if status:
            query = query.filter(DiscrepancyException.status == status.upper())
        if severity:
            query = query.filter(DiscrepancyException.severity == severity.upper())
        if exception_type:
            query = query.filter(DiscrepancyException.exception_type == exception_type.upper())
        if currency:
            query = query.filter(DiscrepancyException.currency == currency.upper())
        if min_amount is not None:
            query = query.filter(DiscrepancyException.amount_exposed >= min_amount)
        if max_amount is not None:
            query = query.filter(DiscrepancyException.amount_exposed <= max_amount)

        return query.order_by(DiscrepancyException.created_at.desc()).limit(limit).all()

    @staticmethod
    def export_exceptions_csv(
        status: Optional[str] = None,
        exception_type: Optional[str] = None
    ) -> str:
        """
        Exports exceptions to CSV format.
        Strictly excludes passwords, API tokens, internal secrets, or raw PII.
        """
        records = ReportingService.filter_exceptions(
            status=status,
            exception_type=exception_type,
            limit=5000
        )

        output = io.StringIO()
        writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)

        # Header row
        writer.writerow([
            'Exception ID',
            'Exception Type',
            'Severity',
            'Status',
            'Amount Exposed',
            'Currency',
            'Payment ID',
            'Merchant Order ID',
            'Transaction Time',
            'Evidence Summary',
            'Created At'
        ])

        for exc in records:
            tx = exc.transaction
            writer.writerow([
                f"EXC-{exc.id}",
                exc.exception_type,
                exc.severity,
                exc.status,
                str(exc.amount_exposed),
                exc.currency,
                tx.external_reference_id if tx else 'N/A',
                tx.merchant_order_id if tx else 'N/A',
                tx.transaction_time.isoformat() if tx and tx.transaction_time else 'N/A',
                exc.evidence_summary.replace('\n', ' '),
                exc.created_at.isoformat() if exc.created_at else ''
            ])

        return output.getvalue()


reporting_service = ReportingService()
