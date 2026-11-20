import hashlib
import io
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List, Tuple
import pandas as pd
from ghostledger.extensions import db
from ghostledger.models import ImportedFile, Transaction
from ghostledger.services.audit_service import audit_service


REQUIRED_COLUMNS = {
    'PAYMENT': ['payment_id', 'amount', 'currency', 'transaction_time'],
    'BANK_STATEMENT': ['bank_reference_id', 'amount', 'currency', 'transaction_time'],
    'SETTLEMENT': ['settlement_id', 'amount', 'currency', 'net_amount', 'fee', 'transaction_time'],
    'INVOICE': ['invoice_number', 'amount', 'currency', 'issue_date'],
    'REFUND': ['refund_id', 'payment_id', 'amount', 'currency', 'refund_time']
}

VALID_CURRENCIES = {'INR', 'USD', 'EUR', 'GBP', 'SGD', 'AED'}


class CSVService:
    @staticmethod
    def sanitize_field(value: Any) -> Any:
        """
        Defends against CSV Formula Injection (DDE).
        Never execute formulas or code from uploaded files.
        Prepend single quote if field starts with dangerous characters.
        """
        if isinstance(value, str):
            clean = value.strip()
            if clean and clean[0] in ('=', '+', '-', '@', '\t', '\r'):
                return "'" + clean
            return clean
        return value

    @staticmethod
    def compute_hash(file_bytes: bytes) -> str:
        return hashlib.sha256(file_bytes).hexdigest()

    @classmethod
    def validate_and_parse(
        cls,
        file_bytes: bytes,
        filename: str,
        file_type: str,
        actor: str = 'system',
        ip_address: str = None
    ) -> Tuple[bool, Dict[str, Any], List[Transaction]]:
        """
        Validates CSV content and parses into Transaction model instances.
        Returns (success, report_dict, transaction_instances).
        """
        file_type = file_type.upper().strip()
        if file_type not in REQUIRED_COLUMNS:
            return False, {
                'error': f"Invalid file_type '{file_type}'. Supported: {list(REQUIRED_COLUMNS.keys())}",
                'valid_count': 0,
                'error_count': 0,
                'total_rows': 0
            }, []

        file_hash = cls.compute_hash(file_bytes)
        # Check idempotency
        existing_file = db.session.query(ImportedFile).filter_by(file_hash=file_hash).first()
        if existing_file:
            return False, {
                'error': f"File '{filename}' has already been imported previously (Import ID #{existing_file.id}).",
                'idempotent_duplicate': True,
                'existing_id': existing_file.id,
                'valid_count': existing_file.valid_count,
                'error_count': existing_file.error_count,
                'total_rows': existing_file.record_count
            }, []

        # Read CSV with pandas
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), dtype=str, keep_default_na=False)
        except Exception as e:
            return False, {
                'error': f"Failed to parse CSV file: {str(e)}",
                'valid_count': 0,
                'error_count': 0,
                'total_rows': 0
            }, []

        # Sanitize column headers
        df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]

        # Verify required columns
        req_cols = REQUIRED_COLUMNS[file_type]
        missing_cols = [c for c in req_cols if c not in df.columns]
        if missing_cols:
            return False, {
                'error': f"Missing required columns for {file_type}: {missing_cols}. Found: {list(df.columns)}",
                'valid_count': 0,
                'error_count': len(df),
                'total_rows': len(df)
            }, []

        # Process rows
        transactions: List[Transaction] = []
        validation_errors: List[Dict[str, Any]] = []
        preview_rows: List[Dict[str, Any]] = []
        seen_refs = set()

        for idx, row in df.iterrows():
            row_num = idx + 2  # Account for 1-based indexing + header row
            row_dict = {k: cls.sanitize_field(v) for k, v in row.items()}
            
            # Map external_reference_id
            if file_type == 'PAYMENT':
                ext_id = str(row_dict.get('payment_id', '')).strip()
            elif file_type == 'BANK_STATEMENT':
                ext_id = str(row_dict.get('bank_reference_id', '')).strip()
            elif file_type == 'SETTLEMENT':
                ext_id = str(row_dict.get('settlement_id', '')).strip()
            elif file_type == 'INVOICE':
                ext_id = str(row_dict.get('invoice_number', '')).strip()
            elif file_type == 'REFUND':
                ext_id = str(row_dict.get('refund_id', '')).strip()
            else:
                ext_id = ''

            if not ext_id:
                validation_errors.append({'row': row_num, 'reason': 'Missing reference ID'})
                continue

            # Deduplication within current file
            if ext_id in seen_refs:
                validation_errors.append({'row': row_num, 'reference': ext_id, 'reason': 'Duplicate reference ID within file'})
                continue
            seen_refs.add(ext_id)

            # Amount validation
            raw_amount = str(row_dict.get('amount', '')).replace(',', '').strip()
            try:
                amount_dec = Decimal(raw_amount)
                if amount_dec <= Decimal('0.00'):
                    validation_errors.append({'row': row_num, 'reference': ext_id, 'reason': 'Amount must be greater than 0.00'})
                    continue
            except (InvalidOperation, ValueError):
                validation_errors.append({'row': row_num, 'reference': ext_id, 'reason': f"Invalid numeric amount '{raw_amount}'"})
                continue

            # Currency validation
            currency = str(row_dict.get('currency', 'INR')).strip().upper()
            if currency not in VALID_CURRENCIES:
                validation_errors.append({'row': row_num, 'reference': ext_id, 'reason': f"Unsupported currency '{currency}'"})
                continue

            # Fee and Tax parsing
            raw_fee = str(row_dict.get('fee', '0.00')).replace(',', '').strip() or '0.00'
            raw_tax = str(row_dict.get('tax', '0.00')).replace(',', '').strip() or '0.00'
            try:
                fee_dec = Decimal(raw_fee)
                tax_dec = Decimal(raw_tax)
            except (InvalidOperation, ValueError):
                fee_dec = Decimal('0.00')
                tax_dec = Decimal('0.00')

            # Net amount
            raw_net = str(row_dict.get('net_amount', '')).replace(',', '').strip()
            if raw_net:
                try:
                    net_dec = Decimal(raw_net)
                except (InvalidOperation, ValueError):
                    net_dec = amount_dec - fee_dec - tax_dec
            else:
                net_dec = amount_dec - fee_dec - tax_dec

            # Date / Timestamp validation
            raw_time = (
                row_dict.get('transaction_time') or
                row_dict.get('issue_date') or
                row_dict.get('refund_time') or
                ''
            ).strip()

            parsed_time = None
            date_formats = [
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%d',
                '%d-%m-%Y',
                '%d/%m/%Y',
                '%m/%d/%Y'
            ]
            for fmt in date_formats:
                try:
                    dt = datetime.strptime(raw_time, fmt)
                    parsed_time = dt.replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue

            if not parsed_time:
                validation_errors.append({'row': row_num, 'reference': ext_id, 'reason': f"Invalid date format '{raw_time}'"})
                continue

            # Extract order ID and counterparty
            order_id = str(row_dict.get('merchant_order_id') or row_dict.get('order_id') or '').strip() or None
            counterparty = str(row_dict.get('counterparty') or row_dict.get('customer_name') or row_dict.get('merchant_name') or '').strip() or None
            status = str(row_dict.get('status', 'COMPLETED')).strip().upper()

            # Create Transaction model
            tx = Transaction(
                source_type=file_type,
                external_reference_id=ext_id,
                merchant_order_id=order_id,
                counterparty=counterparty,
                amount=amount_dec,
                currency=currency,
                fee=fee_dec,
                tax=tax_dec,
                net_amount=net_dec,
                status=status,
                transaction_time=parsed_time,
                is_synthetic=False,
                raw_metadata=row_dict
            )
            transactions.append(tx)

            if len(preview_rows) < 5:
                preview_rows.append({
                    'reference_id': ext_id,
                    'order_id': order_id,
                    'amount': str(amount_dec),
                    'currency': currency,
                    'time': parsed_time.isoformat(),
                    'counterparty': counterparty
                })

        # Save ImportedFile record
        imported_file = ImportedFile(
            filename=filename,
            file_type=file_type,
            file_hash=file_hash,
            record_count=len(df),
            valid_count=len(transactions),
            error_count=len(validation_errors),
            status='COMPLETED' if len(transactions) > 0 else 'FAILED',
            summary_json={
                'validation_errors': validation_errors[:50],
                'preview_rows': preview_rows,
                'total_rows': len(df)
            }
        )
        db.session.add(imported_file)
        db.session.flush()

        # Link transactions to source file and persist
        for tx in transactions:
            tx.source_file_id = imported_file.id
            db.session.add(tx)

        # Audit log
        audit_service.log(
            event_type='IMPORT_FILE',
            actor=actor,
            entity_type='ImportedFile',
            entity_id=str(imported_file.id),
            action_details={
                'filename': filename,
                'file_type': file_type,
                'total_rows': len(df),
                'valid_count': len(transactions),
                'error_count': len(validation_errors)
            },
            ip_address=ip_address
        )

        db.session.commit()

        report = {
            'file_id': imported_file.id,
            'filename': filename,
            'file_type': file_type,
            'total_rows': len(df),
            'valid_count': len(transactions),
            'error_count': len(validation_errors),
            'errors': validation_errors[:20],
            'preview': preview_rows
        }
        return True, report, transactions


csv_service = CSVService()

