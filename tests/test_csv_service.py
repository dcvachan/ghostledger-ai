import pytest
from decimal import Decimal
from ghostledger.services.csv_service import csv_service
from ghostledger.models import ImportedFile, Transaction


def test_sanitize_field_formula_injection():
    # Defends against CSV Formula Injection (DDE)
    assert csv_service.sanitize_field('=SUM(A1:A10)') == "'=SUM(A1:A10)"
    assert csv_service.sanitize_field('+1+1') == "'+1+1"
    assert csv_service.sanitize_field('-2+5') == "'-2+5"
    assert csv_service.sanitize_field('@cmd') == "'@cmd"
    assert csv_service.sanitize_field('Normal Value') == "Normal Value"


def test_validate_and_parse_valid_payment_csv(app, db):
    with app.app_context():
        csv_content = (
            "payment_id,merchant_order_id,counterparty,amount,currency,fee,tax,net_amount,status,transaction_time\n"
            "pay_001,ord_001,Customer Corp,1500.00,INR,30.00,5.40,1464.60,COMPLETED,2026-11-10 10:00:00\n"
            "pay_002,ord_002,Buyer Inc,2500.00,INR,50.00,9.00,2441.00,COMPLETED,2026-11-10 11:00:00\n"
        ).encode('utf-8')

        success, report, txs = csv_service.validate_and_parse(
            file_bytes=csv_content,
            filename='valid_payments.csv',
            file_type='PAYMENT',
            actor='test_analyst'
        )

        assert success is True
        assert report['valid_count'] == 2
        assert report['error_count'] == 0
        assert len(txs) == 2
        assert txs[0].amount == Decimal('1500.00')
        assert txs[0].currency == 'INR'
        assert txs[0].source_type == 'PAYMENT'


def test_idempotent_duplicate_file_rejection(app, db):
    with app.app_context():
        csv_content = (
            "payment_id,amount,currency,transaction_time\n"
            "pay_idem_1,1000.00,INR,2026-11-10 10:00:00\n"
        ).encode('utf-8')

        # First upload
        s1, r1, _ = csv_service.validate_and_parse(csv_content, 'file1.csv', 'PAYMENT')
        assert s1 is True

        # Second upload with identical content
        s2, r2, _ = csv_service.validate_and_parse(csv_content, 'file1_duplicate.csv', 'PAYMENT')
        assert s2 is False
        assert r2.get('idempotent_duplicate') is True


def test_rejection_of_invalid_amount_and_currency(app, db):
    with app.app_context():
        csv_content = (
            "payment_id,amount,currency,transaction_time\n"
            "pay_bad_1,-500.00,INR,2026-11-10 10:00:00\n"
            "pay_bad_2,abc,INR,2026-11-10 10:00:00\n"
            "pay_bad_3,100.00,XYZ,2026-11-10 10:00:00\n"
            "pay_good,200.00,INR,2026-11-10 10:00:00\n"
        ).encode('utf-8')

        success, report, txs = csv_service.validate_and_parse(csv_content, 'bad_data.csv', 'PAYMENT')
        assert success is True
        assert report['valid_count'] == 1
        assert report['error_count'] == 3
        assert len(txs) == 1
        assert txs[0].external_reference_id == 'pay_good'
