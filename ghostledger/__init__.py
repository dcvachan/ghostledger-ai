import os
from decimal import Decimal
from datetime import datetime
from flask import Flask, render_template
from ghostledger.config import Config, DevelopmentConfig, TestingConfig, ProductionConfig
from ghostledger.extensions import db, csrf
from ghostledger.models import User


def create_app(config_class=None):
    app = Flask(__name__)

    # Determine configuration
    if config_class is None:
        env = os.getenv('FLASK_ENV', 'development').lower()
        if env == 'testing':
            config_class = TestingConfig
        elif env == 'production':
            config_class = ProductionConfig
        else:
            config_class = DevelopmentConfig

    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    csrf.init_app(app)

    # Register Jinja custom filters
    @app.template_filter('currency')
    def currency_filter(value, code='INR'):
        if value is None:
            return f"₹ 0.00" if code == 'INR' else f"{code} 0.00"
        try:
            val = float(value)
            symbol = '₹' if code == 'INR' else '$' if code == 'USD' else f"{code} "
            return f"{symbol} {val:,.2f}"
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('datetime_format')
    def datetime_format_filter(value):
        if not value:
            return '—'
        if isinstance(value, str):
            try:
                # ISO format string
                value = datetime.fromisoformat(value.replace('Z', '+00:00'))
            except Exception:
                return value
        return value.strftime('%b %d, %Y • %I:%M %p')

    # Register Blueprints
    from ghostledger.blueprints import (
        dashboard_bp,
        imports_bp,
        reconciliation_bp,
        exceptions_bp,
        actions_bp,
        reports_bp,
        auth_bp,
        api_bp
    )

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(imports_bp)
    app.register_blueprint(reconciliation_bp)
    app.register_blueprint(exceptions_bp)
    app.register_blueprint(actions_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)

    # Global Error Handlers
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('error.html', code=403, message="Access Forbidden: CSRF token verification failed or unauthorized request."), 403

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('error.html', code=404, message="The requested financial record or page could not be located."), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('error.html', code=500, message="An internal ledger reconciliation error occurred. The system safely rolled back."), 500

    # Auto-initialize database tables and demo seed user
    with app.app_context():
        db.create_all()

        # Seed default analyst user if empty
        if not db.session.query(User).filter_by(username='demo_analyst').first():
            analyst = User(
                username='demo_analyst',
                email='analyst@ghostledger.ai',
                role='analyst'
            )
            analyst.set_password('GhostLedger@2026')
            db.session.add(analyst)

            admin = User(
                username='admin',
                email='admin@ghostledger.ai',
                role='admin'
            )
            admin.set_password('AdminLedger@2026')
            db.session.add(admin)
            db.session.commit()

    return app
