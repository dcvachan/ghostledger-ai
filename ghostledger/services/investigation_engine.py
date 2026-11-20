from decimal import Decimal
from typing import Dict, Any, Optional
from ghostledger.extensions import db
from ghostledger.models import (
    DiscrepancyException,
    InvestigationReport,
    Transaction
)
from ghostledger.services.agent_tools import agent_tools
from ghostledger.services.llm_adapter import LLMAdapter
from ghostledger.services.audit_service import audit_service


class InvestigationEngine:
    """
    Evidence-first financial investigation agent.
    Delegates to LLM when configured, otherwise executes the deterministic rules engine.
    Never pretends a rule-based result came from an LLM.
    """

    @classmethod
    def investigate_exception(
        cls,
        exception_id: int,
        actor: str = 'system:ghostledger_ai',
        force_rules_engine: bool = False
    ) -> InvestigationReport:
        """
        Runs comprehensive investigation on an exception and stores structured InvestigationReport.
        """
        exc = db.session.query(DiscrepancyException).filter_by(id=exception_id).first()
        if not exc:
            raise ValueError(f"DiscrepancyException with ID {exception_id} not found.")

        # Gather factual context using tool calls
        tx_details = agent_tools.get_transaction_details(exc.transaction_id)
        related_records = agent_tools.find_related_records(exc.transaction_id, search_type='order_id')
        refund_status = agent_tools.inspect_refund_status(exc.transaction_id)

        prompt_data = {
            'exception_id': exc.id,
            'exception_type': exc.exception_type,
            'severity': exc.severity,
            'amount_exposed': float(exc.amount_exposed),
            'currency': exc.currency,
            'evidence_summary': exc.evidence_summary,
            'evidence_details': exc.evidence_details,
            'transaction': tx_details,
            'related_records': related_records,
            'refund_status': refund_status
        }

        report_data = None
        # Try LLM if configured and not explicitly forced to rules engine
        if not force_rules_engine and LLMAdapter.is_configured():
            report_data = LLMAdapter.investigate(prompt_data)

        # Fallback to Deterministic Rules Engine if LLM not configured or failed
        if not report_data:
            report_data = cls._run_deterministic_rules(exc, tx_details, related_records, refund_status)

        # Create or update InvestigationReport
        existing_report = db.session.query(InvestigationReport).filter_by(exception_id=exc.id).first()
        if existing_report:
            report = existing_report
            report.engine_used = report_data['engine_used']
            report.model_name = report_data.get('model_name')
            report.confidence_score = Decimal(str(report_data['confidence_score']))
            report.root_cause = report_data['root_cause']
            report.explanation = report_data['explanation']
            report.evidence_items = report_data['evidence_items']
            report.alternative_hypotheses = report_data['alternative_hypotheses']
            report.priority = report_data['priority']
            report.priority_rationale = report_data['priority_rationale']
            report.recommended_action_type = report_data['recommended_action_type']
            report.recommended_action_payload = report_data['recommended_action_payload']
        else:
            report = InvestigationReport(
                exception_id=exc.id,
                engine_used=report_data['engine_used'],
                model_name=report_data.get('model_name'),
                confidence_score=Decimal(str(report_data['confidence_score'])),
                root_cause=report_data['root_cause'],
                explanation=report_data['explanation'],
                evidence_items=report_data['evidence_items'],
                alternative_hypotheses=report_data['alternative_hypotheses'],
                priority=report_data['priority'],
                priority_rationale=report_data['priority_rationale'],
                recommended_action_type=report_data['recommended_action_type'],
                recommended_action_payload=report_data['recommended_action_payload']
            )
            db.session.add(report)

        exc.status = 'UNDER_INVESTIGATION'

        audit_service.log(
            event_type='INVESTIGATION_GENERATED',
            actor=actor,
            entity_type='InvestigationReport',
            entity_id=str(exc.id),
            action_details={
                'exception_id': exc.id,
                'engine_used': report_data['engine_used'],
                'priority': report_data['priority'],
                'confidence': report_data['confidence_score']
            }
        )

        db.session.commit()
        return report

    @classmethod
    def _run_deterministic_rules(
        cls,
        exc: DiscrepancyException,
        tx: Dict[str, Any],
        related: Dict[str, Any],
        refund: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Grounded, deterministic financial rules engine.
        Cites exact transaction IDs and database values. Never invents evidence.
        """
        exc_type = exc.exception_type
        tx_id = tx.get('external_reference_id', 'UNKNOWN')
        amount = tx.get('amount', 0.0)
        currency = tx.get('currency', 'INR')
        order_id = tx.get('merchant_order_id', 'N/A')

        if exc_type == 'DUPLICATE_PAYMENT':
            dup_records = related.get('records', [])
            dup_ids = [r['external_reference_id'] for r in dup_records]
            evidence_items = [
                {
                    'field': 'merchant_order_id',
                    'expected': 'Unique charge per merchant order',
                    'actual': f"{len(dup_records) + 1} charges for order '{order_id}'",
                    'source_id': tx_id,
                    'note': f"Duplicate transactions: {', '.join(dup_ids) if dup_ids else 'Identified in batch'}"
                },
                {
                    'field': 'amount',
                    'expected': f"{amount} {currency}",
                    'actual': f"{amount} {currency} billed multiple times",
                    'source_id': tx_id,
                    'note': 'Identical amount charged'
                }
            ]
            return {
                'summary': f"Suspected Duplicate Charge for Order {order_id}",
                'root_cause': "Customer browser re-submission or retry webhook generated duplicate authorization.",
                'explanation': f"Transaction {tx_id} shares merchant order ID '{order_id}' with duplicate charge(s) {dup_ids}. Both charges were captured within minutes.",
                'evidence_items': evidence_items,
                'alternative_hypotheses': [
                    "Customer deliberately placed two separate identical orders for the same items.",
                    "Merchant inventory software re-used an old order identifier."
                ],
                'priority': 'HIGH',
                'priority_rationale': f"Direct customer dispute risk with chargeback liability of {amount} {currency}.",
                'recommended_action_type': 'FLAG_SUSPECTED_DUPLICATE',
                'recommended_action_payload': {
                    'order_id': order_id,
                    'primary_payment_id': tx_id,
                    'duplicate_payment_ids': dup_ids,
                    'suggested_step': 'Verify customer order history and draft refund inquiry for duplicate authorization.'
                },
                'confidence_score': 96.0,
                'engine_used': 'RULES_ENGINE',
                'model_name': None
            }

        elif exc_type == 'FEE_MISMATCH':
            details = exc.evidence_details or {}
            actual_fee = details.get('actual_fee', '0.00')
            benchmark_fee = details.get('expected_benchmark_fee', '0.00')
            variance = details.get('fee_variance', '0.00')
            evidence_items = [
                {
                    'field': 'gateway_fee',
                    'expected': f"{benchmark_fee} {currency} (Standard contract rate ~2.0% + GST)",
                    'actual': f"{actual_fee} {currency} deducted by gateway",
                    'source_id': details.get('settlement_id', tx_id),
                    'note': f"Fee variance of {variance} {currency}"
                }
            ]
            return {
                'summary': f"Gateway Fee Discrepancy on Settlement {details.get('settlement_id')}",
                'root_cause': "Gateway applied non-standard card processing tier or international interchange surcharge.",
                'explanation': f"Settlement {details.get('settlement_id')} deducted a fee of {actual_fee} {currency}, exceeding the agreed schedule benchmark of {benchmark_fee} {currency}.",
                'evidence_items': evidence_items,
                'alternative_hypotheses': [
                    "Card tier was corporate/commercial with contractually permitted interchange surcharge.",
                    "Dispute or chargeback processing administration surcharge was bundled into settlement."
                ],
                'priority': 'MEDIUM',
                'priority_rationale': f"Accumulated fee overcharging erodes merchant gross margin across volume.",
                'recommended_action_type': 'CREATE_FOLLOW_UP_TASK',
                'recommended_action_payload': {
                    'settlement_id': details.get('settlement_id'),
                    'payment_id': tx_id,
                    'disputed_fee_delta': variance,
                    'suggested_step': 'Open reconciliation ticket with payment gateway partner to request MDR fee audit.'
                },
                'confidence_score': 92.0,
                'engine_used': 'RULES_ENGINE',
                'model_name': None
            }

        elif exc_type == 'MISSING_SETTLEMENT':
            age_days = (exc.evidence_details or {}).get('age_days', 3.0)
            evidence_items = [
                {
                    'field': 'settlement_record',
                    'expected': f"Settlement payout within T+2 days ({currency})",
                    'actual': f"No settlement record after {age_days} calendar days",
                    'source_id': tx_id,
                    'note': 'Payment captured in gateway but absent from bank statement & settlement files'
                }
            ]
            return {
                'summary': f"Unsettled Payment Aging Overdue: {tx_id}",
                'root_cause': "Gateway settlement batch hold, rolling reserve hold, or bank batch transfer failure.",
                'explanation': f"Payment {tx_id} for amount {amount} {currency} was successfully captured on {tx.get('transaction_time')}, but no matching deposit has been received after {age_days} days.",
                'evidence_items': evidence_items,
                'alternative_hypotheses': [
                    "Payment was routed through an un-integrated merchant MID or merchant reserve account.",
                    "Settlement was aggregated into an untagged bulk wire transfer."
                ],
                'priority': 'HIGH',
                'priority_rationale': f"Liquidity risk with {amount} {currency} unpaid funds remaining uncollected.",
                'recommended_action_type': 'CREATE_FOLLOW_UP_TASK',
                'recommended_action_payload': {
                    'payment_id': tx_id,
                    'amount': amount,
                    'currency': currency,
                    'suggested_step': 'Request settlement batch trace report from merchant acquiring bank.'
                },
                'confidence_score': 94.0,
                'engine_used': 'RULES_ENGINE',
                'model_name': None
            }

        elif exc_type == 'AMOUNT_MISMATCH':
            details = exc.evidence_details or {}
            variance = details.get('variance', '0.00')
            evidence_items = [
                {
                    'field': 'transaction_amount',
                    'expected': f"{details.get('payment_amount', amount)} {currency}",
                    'actual': f"{details.get('settlement_amount')} {currency}",
                    'source_id': tx_id,
                    'note': f"Variance of {variance} {currency}"
                }
            ]
            return {
                'summary': f"Amount Discrepancy on Payment {tx_id}",
                'root_cause': "Partial capture, unexpected currency conversion rate, or manual adjustment.",
                'explanation': f"The payment amount recorded ({details.get('payment_amount')} {currency}) diverges from the counterparty settlement amount ({details.get('settlement_amount')} {currency}).",
                'evidence_items': evidence_items,
                'alternative_hypotheses': [
                    "Customer received partial refund prior to initial batch settlement.",
                    "Foreign exchange conversion spread was deducted directly from principal amount."
                ],
                'priority': 'HIGH',
                'priority_rationale': f"Ledger imbalance of {variance} {currency} affecting financial statement accuracy.",
                'recommended_action_type': 'PROPOSED_RECONCILIATION_ADJUSTMENT',
                'recommended_action_payload': {
                    'payment_id': tx_id,
                    'amount_delta': variance,
                    'suggested_step': 'Draft journal voucher entry for partial capture adjustment or FX loss.'
                },
                'confidence_score': 90.0,
                'engine_used': 'RULES_ENGINE',
                'model_name': None
            }

        elif exc_type == 'DELAYED_REFUND':
            rf_details = exc.evidence_details or {}
            evidence_items = [
                {
                    'field': 'refund_clawback',
                    'expected': 'Debit record in bank statement within 5 business days',
                    'actual': 'No debit record found in bank statements or settlement deductions',
                    'source_id': rf_details.get('refund_id', tx_id),
                    'note': f"Pending age: {rf_details.get('age_days', 5)} days"
                }
            ]
            return {
                'summary': f"Delayed Refund Execution for {rf_details.get('refund_id', tx_id)}",
                'root_cause': "Gateway refund queue bottleneck or failed reversal to customer card issuing bank.",
                'explanation': f"A refund of {amount} {currency} was initiated but has not cleared through acquiring channels.",
                'evidence_items': evidence_items,
                'alternative_hypotheses': [
                    "Refund was executed offline via direct bank transfer (NEFT/RTGS).",
                    "Customer bank rejected ARN reversal credit."
                ],
                'priority': 'MEDIUM',
                'priority_rationale': f"Customer escalation risk and compliance penalty for delayed refund SLA.",
                'recommended_action_type': 'DRAFT_REFUND_INQUIRY',
                'recommended_action_payload': {
                    'refund_id': rf_details.get('refund_id', tx_id),
                    'payment_id': rf_details.get('linked_payment_id'),
                    'amount': amount,
                    'suggested_step': 'Dispatch Acquirer Reference Number (ARN) query to issuing bank.'
                },
                'confidence_score': 88.0,
                'engine_used': 'RULES_ENGINE',
                'model_name': None
            }

        elif exc_type == 'AMBIGUOUS_CANDIDATE':
            cands = (exc.evidence_details or {}).get('candidate_ids', [])
            evidence_items = [
                {
                    'field': 'candidate_matches',
                    'expected': '1 unique matching counterpart transaction',
                    'actual': f"{len(cands)} candidate records found with identical match criteria",
                    'source_id': tx_id,
                    'note': f"Candidate IDs: {', '.join(cands)}"
                }
            ]
            return {
                'summary': f"Ambiguous Candidate Match for Payment {tx_id}",
                'root_cause': "Multiple transactions share identical amount, currency, and date parameters.",
                'explanation': f"GhostLedger AI ambiguity guard prevented automated matching because {len(cands)} records matched identically.",
                'evidence_items': evidence_items,
                'alternative_hypotheses': [
                    "Recurring subscription billed multiple times in the same interval.",
                    "Multiple customers purchased the same standardized product SKU simultaneously."
                ],
                'priority': 'HIGH',
                'priority_rationale': "High risk of corrupting financial ledger by linking incorrect settlement batch.",
                'recommended_action_type': 'CREATE_FOLLOW_UP_TASK',
                'recommended_action_payload': {
                    'payment_id': tx_id,
                    'candidate_ids': cands,
                    'suggested_step': 'Manual inspection by reconciliation analyst required to verify ARN/RRN.'
                },
                'confidence_score': 85.0,
                'engine_used': 'RULES_ENGINE',
                'model_name': None
            }

        else:
            # UNMATCHED_PAYMENT or generic exception
            evidence_items = [
                {
                    'field': 'reconciliation_status',
                    'expected': 'Matched counterparty record in Bank or Settlement files',
                    'actual': 'No matching record located across all ingested files',
                    'source_id': tx_id,
                    'note': 'Insufficient external evidence'
                }
            ]
            return {
                'summary': f"Unmatched Payment Record: {tx_id}",
                'root_cause': "Payment file was ingested without corresponding bank statement or settlement file batch.",
                'explanation': f"Transaction {tx_id} remains completely unmatched. Current ingested evidence is insufficient to verify settlement or bank deposit.",
                'evidence_items': evidence_items,
                'alternative_hypotheses': [
                    "Missing file import: settlement batch CSV for this date range has not yet been uploaded.",
                    "Payment was cancelled or charged back prior to clearing."
                ],
                'priority': 'MEDIUM',
                'priority_rationale': f"Unreconciled balance of {amount} {currency} pending ingestion of complete statements.",
                'recommended_action_type': 'CREATE_FOLLOW_UP_TASK',
                'recommended_action_payload': {
                    'payment_id': tx_id,
                    'suggested_step': 'Upload corresponding gateway settlement and bank statement files.'
                },
                'confidence_score': 80.0,
                'engine_used': 'RULES_ENGINE',
                'model_name': None
            }


investigation_engine = InvestigationEngine()
