import pytest
from ghostledger.models import User, AuditEvent
from ghostledger.services.audit_service import audit_service
from ghostledger.services.reporting_service import reporting_service


def test_password_hashing(app, db):
    with app.app_context():
        u = User(username='sec_user', email='sec@ghostledger.ai')
        u.set_password('MyStrongPassword@2026')
        db.session.add(u)
        db.session.commit()

        # Password hash must not be plain text
        assert u.password_hash != 'MyStrongPassword@2026'
        assert u.check_password('MyStrongPassword@2026') is True
        assert u.check_password('WrongPassword') is False


def test_append_only_audit_log(app, db):
    with app.app_context():
        ev = audit_service.log(
            event_type='TEST_SECURITY_EVENT',
            actor='security_tester',
            entity_type='TestEntity',
            entity_id='12345',
            action_details={'test': True, 'ip': '127.0.0.1'},
            ip_address='127.0.0.1'
        )
        db.session.commit()

        queried = db.session.query(AuditEvent).filter_by(event_type='TEST_SECURITY_EVENT').first()
        assert queried is not None
        assert queried.actor == 'security_tester'
        assert queried.action_details['test'] is True


def test_safe_csv_export_excludes_secrets(app, db):
    with app.app_context():
        csv_text = reporting_service.export_exceptions_csv()
        # Verify CSV format and absence of secrets
        assert 'Exception ID' in csv_text
        assert 'password' not in csv_text.lower()
        assert 'secret' not in csv_text.lower()
        assert 'token' not in csv_text.lower()
