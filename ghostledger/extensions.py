from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool
import secrets
from flask import session, request, abort

Base = declarative_base()


class DatabaseManager:
    """SQLAlchemy database manager with Flask request-context scoped sessions."""
    def __init__(self):
        self.engine = None
        self.session_factory = None
        self._scoped_session = None
        self.Model = Base

    def init_app(self, app):
        uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///ghostledger.db')
        engine_options = app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {})

        if uri.startswith('sqlite:///:memory:'):
            # For testing with in-memory SQLite, use StaticPool to preserve tables across threads/sessions
            self.engine = create_engine(
                uri,
                connect_args={'check_same_thread': False},
                poolclass=StaticPool
            )
        elif uri.startswith('sqlite'):
            self.engine = create_engine(
                uri,
                connect_args={'check_same_thread': False}
            )
        else:
            self.engine = create_engine(uri, **engine_options)

        self.session_factory = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        self._scoped_session = scoped_session(self.session_factory)

        # Attach session teardown
        @app.teardown_appcontext
        def remove_session(exception=None):
            if self._scoped_session:
                self._scoped_session.remove()

    @property
    def session(self):
        if self._scoped_session is None:
            raise RuntimeError("DatabaseManager has not been initialized with an application context.")
        return self._scoped_session

    def create_all(self):
        self.Model.metadata.create_all(bind=self.engine)

    def drop_all(self):
        self.Model.metadata.drop_all(bind=self.engine)


db = DatabaseManager()


class SimpleCSRF:
    """Lightweight CSRF protection for state-changing HTTP methods without extra dependencies."""
    def __init__(self, app=None):
        if app:
            self.init_app(app)

    def init_app(self, app):
        @app.before_request
        def check_csrf():
            # Generate session CSRF token if missing
            if 'csrf_token' not in session:
                session['csrf_token'] = secrets.token_hex(32)

            # Skip safe methods and API endpoints if flagged
            if request.method in ('GET', 'HEAD', 'OPTIONS'):
                return

            if app.config.get('TESTING') and not app.config.get('WTF_CSRF_ENABLED', False):
                return

            # Check header or form data
            token = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
            expected = session.get('csrf_token')
            if not token or not expected or token != expected:
                # If content-type is json, return 403 json, else abort(403)
                if request.is_json:
                    abort(403, description="CSRF token missing or invalid")
                abort(403)

        @app.context_processor
        def inject_csrf_token():
            return dict(csrf_token=lambda: session.get('csrf_token', ''))


csrf = SimpleCSRF()
