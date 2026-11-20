import os
import pytest
from ghostledger import create_app
from ghostledger.config import TestingConfig
from ghostledger.extensions import db as _db
from ghostledger.models import User


@pytest.fixture(scope='session')
def app():
    os.environ['FLASK_ENV'] = 'testing'
    app = create_app(TestingConfig)
    return app


@pytest.fixture(scope='function')
def client(app):
    return app.test_client()


@pytest.fixture(scope='function', autouse=True)
def db(app):
    with app.app_context():
        _db.drop_all()
        _db.create_all()

        # Seed test user
        user = User(username='test_analyst', email='analyst@test.local', role='analyst')
        user.set_password('TestPass123!')
        _db.session.add(user)
        _db.session.commit()

        yield _db

        _db.session.rollback()
        _db.drop_all()



@pytest.fixture(scope='function')
def auth_client(client, db):
    """Client with authenticated demo analyst session."""
    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['username'] = 'test_analyst'
        sess['role'] = 'analyst'
        sess['email'] = 'analyst@test.local'
        sess['csrf_token'] = 'test-valid-csrf-token-123'
    return client
