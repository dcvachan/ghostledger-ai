from decimal import Decimal
from typing import Dict, Any, List, Optional
from ghostledger.extensions import db
from ghostledger.models import (
    Transaction,
    DiscrepancyException,
    DraftAction
)


class AgentTools:
    """
    Narrowly scoped, deterministic tools exposed to investigation workflows.
    Every input is validated in Python; every factual claim is grounded in database state.
    """

    @staticmethod
    def get_transaction_details(tx_id: int) -> Dict[str, Any]:
        """
        Retrieves full verified attributes of a transaction from the database.
        """
        if not isinstance(tx_id, int) or tx_id <= 0:
            return {'error': f"Invalid tx_id '{tx_id}'. Must be a positive integer."}

        tx = db.session.query(Transaction).filter_by(id=tx_id).first()
        if not tx:
            return {'error': f"Transaction with ID {tx_id} not found."}

        return {
            'found': True,
            'id': tx.id,
            'source_type': tx.source_type,
            'external_reference_id': tx.external_reference_id,
            'merchant_order_id': tx.merchant_order_id,
            'counterparty': tx.counterparty,
            'amount': float(tx.amount),
            'currency': tx.currency,
            'fee': float(tx.fee),
            'tax': float(tx.tax),
            'net_amount': float(tx.net_amount),
            'status': tx.status,
            'transaction_time': tx.transaction_time.isoformat() if tx.transaction_time else None,
            'is_reconciled': tx.is_reconciled,
            'raw_metadata': tx.raw_metadata or {}
        }

    @staticmethod
    def find_related_records(tx_id: int, search_type: str = 'order_id') -> Dict[str, Any]:
        """
        Finds companion records across payments, settlements, bank statements, invoices, and refunds.
        """
        tx = db.session.query(Transaction).filter_by(id=tx_id).first()
        if not tx:
            return {'error': f"Transaction with ID {tx_id} not found.", 'records': []}

        results = []
        if search_type == 'order_id' and tx.merchant_order_id:
            related = db.session.query(Transaction).filter(
                Transaction.merchant_order_id == tx.merchant_order_id,
                Transaction.id != tx.id
            ).all()
            results.extend([r.to_dict() for r in related])

        elif search_type == 'reference_id':
            # Search if any record mentions this reference id in raw_metadata or external_reference_id
            related = db.session.query(Transaction).filter(
                (Transaction.external_reference_id == tx.external_reference_id) & (Transaction.id != tx.id)
            ).all()
            results.extend([r.to_dict() for r in related])

        # Also search settlements / refunds referencing this payment_id
        if tx.source_type == 'PAYMENT':
            all_records = db.session.query(Transaction).filter(
                Transaction.source_type.in_(['SETTLEMENT', 'REFUND'])
            ).all()
            for r in all_records:
                meta_pay_id = (r.raw_metadata or {}).get('payment_id')
                if meta_pay_id and meta_pay_id == tx.external_reference_id and r.id != tx.id:
                    results.append(r.to_dict())

        return {
            'query_tx_id': tx_id,
            'search_type': search_type,
            'count': len(results),
            'records': results
        }

    @staticmethod
    def compare_settlement_amounts(payment_id: int, settlement_id: int) -> Dict[str, Any]:
        """
        Compares payment gross amount against settlement net, fees, and standard fee benchmarks.
        """
        pay = db.session.query(Transaction).filter_by(id=payment_id).first()
        st = db.session.query(Transaction).filter_by(id=settlement_id).first()

        if not pay:
            return {'error': f"Payment transaction ID {payment_id} not found."}
        if not st:
            return {'error': f"Settlement transaction ID {settlement_id} not found."}

        gross = pay.amount
        settlement_net = st.net_amount
        actual_fee = st.fee
        actual_tax = st.tax
        net_reconstructed = gross - actual_fee - actual_tax
        discrepancy = settlement_net - net_reconstructed

        # Standard benchmark: 2.0% fee + 18% GST on fee
        benchmark_fee_rate = Decimal('0.02')
        benchmark_fee = (gross * benchmark_fee_rate).quantize(Decimal('0.01'))
        benchmark_tax = (benchmark_fee * Decimal('0.18')).quantize(Decimal('0.01'))
        fee_variance = actual_fee - benchmark_fee

        return {
            'payment_reference': pay.external_reference_id,
            'settlement_reference': st.external_reference_id,
            'gross_amount': float(gross),
            'settlement_net_amount': float(settlement_net),
            'actual_fee_deducted': float(actual_fee),
            'actual_tax_deducted': float(actual_tax),
            'net_reconstructed': float(net_reconstructed),
            'accounting_discrepancy': float(discrepancy),
            'benchmark_standard_fee': float(benchmark_fee),
            'fee_variance_from_benchmark': float(fee_variance),
            'currency': pay.currency,
            'is_fee_inflated': fee_variance > (gross * Decimal('0.01'))
        }

    @staticmethod
    def inspect_refund_status(payment_id: int) -> Dict[str, Any]:
        """
        Inspects refund transactions linked to a payment, examining clawback status and timeline.
        """
        pay = db.session.query(Transaction).filter_by(id=payment_id).first()
        if not pay:
            return {'error': f"Payment ID {payment_id} not found."}

        refunds = db.session.query(Transaction).filter(
            Transaction.source_type == 'REFUND'
        ).all()

        linked_refunds = []
        for rf in refunds:
            ref_pay_id = (rf.raw_metadata or {}).get('payment_id')
            if ref_pay_id == pay.external_reference_id or rf.merchant_order_id == pay.merchant_order_id:
                linked_refunds.append(rf.to_dict())

        return {
            'payment_id': pay.id,
            'payment_reference': pay.external_reference_id,
            'payment_amount': float(pay.amount),
            'payment_status': pay.status,
            'linked_refunds_count': len(linked_refunds),
            'refunds': linked_refunds
        }

    @staticmethod
    def create_draft_action(
        exception_id: int,
        action_type: str,
        payload: Dict[str, Any],
        rationale: str,
        actor: str = 'system:ghostledger_ai'
    ) -> Dict[str, Any]:
        """
        Creates a draft-only action awaiting explicit human approval.
        Enforces safety: no real banking/payout/charge operation is performed.
        """
        allowed_actions = {
            'CREATE_FOLLOW_UP_TASK',
            'DRAFT_REFUND_INQUIRY',
            'PROPOSED_RECONCILIATION_ADJUSTMENT',
            'FLAG_SUSPECTED_DUPLICATE'
        }
        if action_type not in allowed_actions:
            return {'error': f"Disallowed action_type '{action_type}'. Allowed: {sorted(list(allowed_actions))}"}

        exc = db.session.query(DiscrepancyException).filter_by(id=exception_id).first()
        if not exc:
            return {'error': f"DiscrepancyException with ID {exception_id} not found."}

        draft = DraftAction(
            exception_id=exc.id,
            action_type=action_type,
            status='DRAFT',
            target_entity_type='TRANSACTION',
            target_entity_id=str(exc.transaction_id),
            action_payload=payload or {},
            rationale=rationale or 'Automated investigation draft recommendation',
            created_by=actor
        )
        db.session.add(draft)
        exc.status = 'DRAFTED_ACTION'
        db.session.commit()

        return {
            'success': True,
            'draft_action_id': draft.id,
            'status': draft.status,
            'action_type': draft.action_type,
            'message': "Draft action created successfully. Awaiting human approval."
        }


agent_tools = AgentTools()
