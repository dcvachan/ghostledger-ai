from flask import Blueprint, render_template, session, redirect, url_for, current_app
from ghostledger.extensions import db
from ghostledger.models import DiscrepancyException, ReconciliationRun, DraftAction
from ghostledger.services.reporting_service import reporting_service

dashboard_bp = Blueprint('dashboard', __name__)


@dashboard_bp.route('/')
def index():
    # If not logged in and not in demo mode, redirect to login
    if 'username' not in session and not current_app.config.get('DEMO_MODE'):
        return redirect(url_for('auth.login'))

    # Default demo session if in demo mode
    if 'username' not in session:
        session['username'] = 'demo_analyst'
        session['role'] = 'analyst'

    metrics = reporting_service.get_dashboard_metrics()

    # Recent exceptions requiring attention
    recent_exceptions = db.session.query(DiscrepancyException).order_by(
        DiscrepancyException.created_at.desc()
    ).limit(6).all()

    # Pending actions
    pending_actions = db.session.query(DraftAction).filter_by(status='DRAFT').limit(5).all()

    # Latest reconciliation runs
    runs = db.session.query(ReconciliationRun).order_by(ReconciliationRun.id.desc()).limit(5).all()

    return render_template(
        'dashboard.html',
        metrics=metrics,
        recent_exceptions=recent_exceptions,
        pending_actions=pending_actions,
        runs=runs
    )
