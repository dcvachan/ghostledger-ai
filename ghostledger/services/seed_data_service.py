import json
import random
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, Any, List, Tuple
from ghostledger.extensions import db
from ghostledger.models import Transaction, ImportedFile
from ghostledger.services.audit_service import audit_service


class SeedDataService:
    """
    Generates >= 100 synthetic records across Payment, Bank, Settlement, Invoice, and Refund datasets.
    Includes known test scenarios with a separate ground-truth evaluation fixture.
    """

    @classmethod
    def generate_demo_dataset(cls) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
        """
        Synthesizes realistic datasets and generates ground-truth labels.
        Returns (datasets_dict, ground_truth_dict).
        """
        random.seed(42)  # Deterministic seed for reproducible evaluation
        base_time = datetime(2026, 11, 10, 10, 0, 0, tzinfo=timezone.utc)

        payments = []
        bank_statements = []
        settlements = []
        invoices = []
        refunds = []

        ground_truth = {
            'exact_matches': [],
            'duplicate_payments': [],
            'missing_settlements': [],
            'fee_mismatches': [],
            'amount_mismatches': [],
            'delayed_refunds': [],
            'ambiguous_candidates': [],
            'total_synthetic_payments': 0
        }

        pay_counter = 1000
        bank_counter = 2000
        setl_counter = 3000
        inv_counter = 4000
        rf_counter = 5000

        # -------------------------------------------------------------
        # 1. Healthy Exact Matches (70 records)
        # -------------------------------------------------------------
        for i in range(70):
            pay_counter += 1
            bank_counter += 1
            setl_counter += 1
            inv_counter += 1

            amt = Decimal(str(random.randint(250, 15000))) + Decimal('0.00')
            fee = (amt * Decimal('0.02')).quantize(Decimal('0.01'))  # Standard 2% fee
            tax = (fee * Decimal('0.18')).quantize(Decimal('0.01'))  # 18% GST on fee
            net_amt = amt - fee - tax
            tx_time = base_time + timedelta(hours=i * 2, minutes=random.randint(1, 45))
            settle_time = tx_time + timedelta(days=1, hours=4)
            order_id = f"ORD_2026_{pay_counter}"
            pay_id = f"pay_gt_{pay_counter}"
            bank_id = f"bank_tx_{bank_counter}"
            setl_id = f"setl_rec_{setl_counter}"
            inv_id = f"INV-2026-{inv_counter}"
            customer = f"Customer_{random.randint(100, 999)} Corp"

            payments.append({
                'payment_id': pay_id,
                'merchant_order_id': order_id,
                'counterparty': customer,
                'amount': amt,
                'currency': 'INR',
                'fee': fee,
                'tax': tax,
                'net_amount': net_amt,
                'status': 'COMPLETED',
                'transaction_time': tx_time,
                'test_scenario': 'HEALTHY_EXACT_MATCH'
            })

            settlements.append({
                'settlement_id': setl_id,
                'payment_id': pay_id,
                'merchant_order_id': order_id,
                'counterparty': 'Razorpay Acquirer',
                'amount': amt,
                'currency': 'INR',
                'fee': fee,
                'tax': tax,
                'net_amount': net_amt,
                'status': 'SETTLED',
                'transaction_time': settle_time,
                'test_scenario': 'HEALTHY_EXACT_MATCH'
            })

            bank_statements.append({
                'bank_reference_id': bank_id,
                'payment_id': pay_id,
                'merchant_order_id': order_id,
                'counterparty': 'HDFC Nodal Settlement',
                'amount': amt,
                'currency': 'INR',
                'fee': Decimal('0.00'),
                'tax': Decimal('0.00'),
                'net_amount': amt,
                'status': 'COMPLETED',
                'transaction_time': settle_time + timedelta(hours=2),
                'test_scenario': 'HEALTHY_EXACT_MATCH'
            })

            invoices.append({
                'invoice_number': inv_id,
                'merchant_order_id': order_id,
                'counterparty': customer,
                'amount': amt,
                'currency': 'INR',
                'transaction_time': tx_time - timedelta(hours=1),
                'status': 'PAID'
            })

            ground_truth['exact_matches'].append(pay_id)

        # -------------------------------------------------------------
        # 2. Known Duplicate Charges (10 payments across 5 order IDs)
        # -------------------------------------------------------------
        for i in range(5):
            order_id = f"ORD_DUP_{i+1:03d}"
            amt = Decimal(str(random.randint(1200, 8500))) + Decimal('0.00')
            dup_time = base_time + timedelta(days=2, hours=i * 3)

            for d in range(2):
                pay_counter += 1
                pay_id = f"pay_dup_{pay_counter}"
                payments.append({
                    'payment_id': pay_id,
                    'merchant_order_id': order_id,
                    'counterparty': f"Duplicate Buyer {i+1}",
                    'amount': amt,
                    'currency': 'INR',
                    'fee': (amt * Decimal('0.02')).quantize(Decimal('0.01')),
                    'tax': Decimal('0.00'),
                    'net_amount': amt - (amt * Decimal('0.02')).quantize(Decimal('0.01')),
                    'status': 'COMPLETED',
                    'transaction_time': dup_time + timedelta(minutes=d * 3),  # 3 minutes apart!
                    'test_scenario': 'DUPLICATE_PAYMENT'
                })
                ground_truth['duplicate_payments'].append(pay_id)

        # -------------------------------------------------------------
        # 3. Missing Settlements (10 payments overdue with 0 settlement)
        # -------------------------------------------------------------
        for i in range(10):
            pay_counter += 1
            amt = Decimal(str(random.randint(2000, 25000))) + Decimal('0.00')
            overdue_time = base_time - timedelta(days=5, hours=i * 2)  # Completed 5 days ago
            pay_id = f"pay_nosetl_{pay_counter}"
            order_id = f"ORD_NOSETL_{i+1:03d}"

            payments.append({
                'payment_id': pay_id,
                'merchant_order_id': order_id,
                'counterparty': f"Unsettled Client {i+1}",
                'amount': amt,
                'currency': 'INR',
                'fee': Decimal('0.00'),
                'tax': Decimal('0.00'),
                'net_amount': amt,
                'status': 'COMPLETED',
                'transaction_time': overdue_time,
                'test_scenario': 'MISSING_SETTLEMENT'
            })
            ground_truth['missing_settlements'].append(pay_id)

        # -------------------------------------------------------------
        # 4. Fee Mismatches (8 payments with inflated gateway fees)
        # -------------------------------------------------------------
        for i in range(8):
            pay_counter += 1
            setl_counter += 1
            amt = Decimal(str(random.randint(5000, 40000))) + Decimal('0.00')
            benchmark_fee = (amt * Decimal('0.02')).quantize(Decimal('0.01'))
            inflated_fee = (amt * Decimal('0.045')).quantize(Decimal('0.01'))  # 4.5% instead of 2%!
            tax = Decimal('0.00')
            net_amt = amt - inflated_fee
            tx_time = base_time + timedelta(days=1, hours=i * 2)
            pay_id = f"pay_feemismatch_{pay_counter}"
            setl_id = f"setl_inflated_{setl_counter}"
            order_id = f"ORD_FEE_{i+1:03d}"

            payments.append({
                'payment_id': pay_id,
                'merchant_order_id': order_id,
                'counterparty': f"Merchant Partner {i+1}",
                'amount': amt,
                'currency': 'INR',
                'fee': benchmark_fee,
                'tax': tax,
                'net_amount': amt - benchmark_fee,
                'status': 'COMPLETED',
                'transaction_time': tx_time,
                'test_scenario': 'FEE_MISMATCH'
            })

            settlements.append({
                'settlement_id': setl_id,
                'payment_id': pay_id,
                'merchant_order_id': order_id,
                'counterparty': 'Gateway Partner Inc',
                'amount': amt,
                'currency': 'INR',
                'fee': inflated_fee,
                'tax': tax,
                'net_amount': net_amt,
                'status': 'SETTLED',
                'transaction_time': tx_time + timedelta(days=1),
                'test_scenario': 'FEE_MISMATCH'
            })
            ground_truth['fee_mismatches'].append(pay_id)

        # -------------------------------------------------------------
        # 5. Amount Mismatches (6 payments with currency/variance delta)
        # -------------------------------------------------------------
        for i in range(6):
            pay_counter += 1
            setl_counter += 1
            pay_amt = Decimal('10000.00') + Decimal(str(i * 1000))
            settled_amt = pay_amt - Decimal('500.00')  # 500 INR difference
            tx_time = base_time + timedelta(days=2, hours=i)
            pay_id = f"pay_amtmismatch_{pay_counter}"
            setl_id = f"setl_diff_{setl_counter}"
            order_id = f"ORD_DIFF_{i+1:03d}"

            payments.append({
                'payment_id': pay_id,
                'merchant_order_id': order_id,
                'counterparty': f"Variance Customer {i+1}",
                'amount': pay_amt,
                'currency': 'INR',
                'fee': Decimal('50.00'),
                'tax': Decimal('0.00'),
                'net_amount': pay_amt - Decimal('50.00'),
                'status': 'COMPLETED',
                'transaction_time': tx_time,
                'test_scenario': 'AMOUNT_MISMATCH'
            })

            settlements.append({
                'settlement_id': setl_id,
                'payment_id': pay_id,
                'merchant_order_id': order_id,
                'counterparty': 'Gateway Partner Inc',
                'amount': settled_amt,
                'currency': 'INR',
                'fee': Decimal('50.00'),
                'tax': Decimal('0.00'),
                'net_amount': settled_amt - Decimal('50.00'),
                'status': 'SETTLED',
                'transaction_time': tx_time + timedelta(days=1),
                'test_scenario': 'AMOUNT_MISMATCH'
            })
            ground_truth['amount_mismatches'].append(pay_id)

        # -------------------------------------------------------------
        # 6. Delayed Refunds (6 refunds pending > 6 days)
        # -------------------------------------------------------------
        for i in range(6):
            rf_counter += 1
            rf_id = f"rfnd_overdue_{rf_counter}"
            linked_pay = f"pay_gt_{1001 + i}"
            amt = Decimal(str(random.randint(500, 4500))) + Decimal('0.00')
            rf_time = base_time - timedelta(days=7, hours=i)

            refunds.append({
                'refund_id': rf_id,
                'payment_id': linked_pay,
                'amount': amt,
                'currency': 'INR',
                'refund_time': rf_time,
                'status': 'PENDING',
                'test_scenario': 'DELAYED_REFUND'
            })
            ground_truth['delayed_refunds'].append(rf_id)

        # -------------------------------------------------------------
        # 7. Ambiguous Candidate Cases (4 payments; 2 candidate pairs)
        # -------------------------------------------------------------
        for i in range(2):
            pay_counter += 1
            pay_id = f"pay_ambig_{pay_counter}"
            order_id = f"ORD_AMBIG_{i+1:02d}"
            amt = Decimal('3999.00')
            tx_time = base_time + timedelta(days=3, hours=i * 4)

            payments.append({
                'payment_id': pay_id,
                'merchant_order_id': order_id,
                'counterparty': f"Ambiguous Corp {i+1}",
                'amount': amt,
                'currency': 'INR',
                'fee': Decimal('0.00'),
                'tax': Decimal('0.00'),
                'net_amount': amt,
                'status': 'COMPLETED',
                'transaction_time': tx_time,
                'test_scenario': 'AMBIGUOUS_CANDIDATE'
            })
            ground_truth['ambiguous_candidates'].append(pay_id)

            # Create TWO identical candidate bank statements with same order and amount
            for c in range(2):
                bank_counter += 1
                bank_statements.append({
                    'bank_reference_id': f"bank_ambig_{bank_counter}",
                    'merchant_order_id': order_id,
                    'counterparty': 'Bank Payout',
                    'amount': amt,
                    'currency': 'INR',
                    'fee': Decimal('0.00'),
                    'tax': Decimal('0.00'),
                    'net_amount': amt,
                    'status': 'COMPLETED',
                    'transaction_time': tx_time + timedelta(hours=3),
                    'test_scenario': 'AMBIGUOUS_CANDIDATE'
                })

        ground_truth['total_synthetic_payments'] = len(payments)

        datasets = {
            'payments': payments,
            'bank_statements': bank_statements,
            'settlements': settlements,
            'invoices': invoices,
            'refunds': refunds
        }
        return datasets, ground_truth

    @classmethod
    def serialize_metadata(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """Converts Decimal and datetime objects to JSON-serializable types."""
        clean = {}
        for k, v in data.items():
            if isinstance(v, Decimal):
                clean[k] = str(v)
            elif isinstance(v, datetime):
                clean[k] = v.isoformat()
            else:
                clean[k] = v
        return clean

    @classmethod
    def seed_database(cls, actor: str = 'system:seed_runner') -> Dict[str, Any]:
        """
        Clears previous synthetic data, generates fresh 100+ records, and persists into DB.
        """
        datasets, ground_truth = cls.generate_demo_dataset()

        # Delete existing synthetic records
        db.session.query(Transaction).filter_by(is_synthetic=True).delete()
        db.session.commit()

        # Create ImportedFile entries for each dataset
        file_records = {}
        for file_type, rows in datasets.items():
            imp = ImportedFile(
                filename=f"synthetic_{file_type.lower()}.csv",
                file_type=file_type.upper().rstrip('S') if file_type != 'bank_statements' else 'BANK_STATEMENT',
                file_hash=f"synthetic_hash_{file_type}",
                record_count=len(rows),
                valid_count=len(rows),
                error_count=0,
                status='COMPLETED',
                summary_json={'synthetic': True, 'count': len(rows)}
            )
            db.session.add(imp)
            db.session.flush()
            file_records[file_type] = imp.id

        # Insert transactions
        inserted_counts = {}
        for file_type, rows in datasets.items():
            source_type = file_type.upper().rstrip('S')
            if file_type == 'bank_statements':
                source_type = 'BANK_STATEMENT'

            count = 0
            for r in rows:
                ext_id = (
                    r.get('payment_id') or
                    r.get('bank_reference_id') or
                    r.get('settlement_id') or
                    r.get('invoice_number') or
                    r.get('refund_id')
                )
                tx = Transaction(
                    source_file_id=file_records[file_type],
                    source_type=source_type,
                    external_reference_id=ext_id,
                    merchant_order_id=r.get('merchant_order_id'),
                    counterparty=r.get('counterparty'),
                    amount=r['amount'],
                    currency=r.get('currency', 'INR'),
                    fee=r.get('fee', Decimal('0.00')),
                    tax=r.get('tax', Decimal('0.00')),
                    net_amount=r.get('net_amount', r['amount']),
                    status=r.get('status', 'COMPLETED'),
                    transaction_time=r.get('transaction_time') or r.get('refund_time'),
                    is_synthetic=True,
                    is_reconciled=False,
                    raw_metadata=cls.serialize_metadata(r)
                )
                db.session.add(tx)
                count += 1
            inserted_counts[file_type] = count


        # Save separate ground truth fixture file
        gt_path = Path(__file__).resolve().parent.parent.parent / 'evaluation_ground_truth.json'
        with open(gt_path, 'w', encoding='utf-8') as f:
            json.dump(ground_truth, f, indent=2)

        audit_service.log(
            event_type='SYSTEM_SEED',
            actor=actor,
            entity_type='Dataset',
            entity_id='synthetic_demo_v1',
            action_details={
                'inserted_counts': inserted_counts,
                'total_payments': ground_truth['total_synthetic_payments']
            }
        )

        db.session.commit()
        return {
            'status': 'SUCCESS',
            'inserted_counts': inserted_counts,
            'ground_truth_path': str(gt_path),
            'summary': f"Successfully seeded {ground_truth['total_synthetic_payments']} payment transactions and counterparts."
        }

    @classmethod
    def export_sample_csv_files(cls, target_dir: Path) -> Dict[str, str]:
        """
        Exports realistic CSV template files to the sample_data/ directory.
        """
        import csv
        target_dir.mkdir(parents=True, exist_ok=True)
        datasets, _ = cls.generate_demo_dataset()
        exported_files = {}

        # 1. payments.csv
        p_path = target_dir / 'payments.csv'
        with open(p_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['payment_id', 'merchant_order_id', 'counterparty', 'amount', 'currency', 'fee', 'tax', 'net_amount', 'status', 'transaction_time'])
            for r in datasets['payments'][:25]:
                w.writerow([
                    r['payment_id'], r.get('merchant_order_id', ''), r.get('counterparty', ''),
                    str(r['amount']), r['currency'], str(r.get('fee', '0.00')), str(r.get('tax', '0.00')),
                    str(r.get('net_amount', r['amount'])), r['status'], r['transaction_time'].strftime('%Y-%m-%d %H:%M:%S')
                ])
        exported_files['payments'] = str(p_path)

        # 2. bank_statements.csv
        b_path = target_dir / 'bank_statements.csv'
        with open(b_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['bank_reference_id', 'merchant_order_id', 'counterparty', 'amount', 'currency', 'transaction_time', 'status'])
            for r in datasets['bank_statements'][:25]:
                w.writerow([
                    r['bank_reference_id'], r.get('merchant_order_id', ''), r.get('counterparty', ''),
                    str(r['amount']), r['currency'], r['transaction_time'].strftime('%Y-%m-%d %H:%M:%S'), r['status']
                ])
        exported_files['bank_statements'] = str(b_path)

        # 3. settlements.csv
        s_path = target_dir / 'settlements.csv'
        with open(s_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['settlement_id', 'payment_id', 'merchant_order_id', 'counterparty', 'amount', 'currency', 'fee', 'tax', 'net_amount', 'status', 'transaction_time'])
            for r in datasets['settlements'][:25]:
                w.writerow([
                    r['settlement_id'], r.get('payment_id', ''), r.get('merchant_order_id', ''), r.get('counterparty', ''),
                    str(r['amount']), r['currency'], str(r['fee']), str(r['tax']), str(r['net_amount']), r['status'], r['transaction_time'].strftime('%Y-%m-%d %H:%M:%S')
                ])
        exported_files['settlements'] = str(s_path)

        # 4. invoices.csv
        i_path = target_dir / 'invoices.csv'
        with open(i_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['invoice_number', 'merchant_order_id', 'counterparty', 'amount', 'currency', 'issue_date', 'status'])
            for r in datasets['invoices'][:25]:
                w.writerow([
                    r['invoice_number'], r.get('merchant_order_id', ''), r.get('counterparty', ''),
                    str(r['amount']), r['currency'], r['transaction_time'].strftime('%Y-%m-%d %H:%M:%S'), r['status']
                ])
        exported_files['invoices'] = str(i_path)

        # 5. refunds.csv
        r_path = target_dir / 'refunds.csv'
        with open(r_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['refund_id', 'payment_id', 'amount', 'currency', 'refund_time', 'status'])
            for r in datasets['refunds'][:25]:
                w.writerow([
                    r['refund_id'], r['payment_id'], str(r['amount']), r['currency'],
                    r['refund_time'].strftime('%Y-%m-%d %H:%M:%S'), r['status']
                ])
        exported_files['refunds'] = str(r_path)

        return exported_files


seed_data_service = SeedDataService()
