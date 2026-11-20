from flask import Blueprint, render_template, request, flash, redirect, url_for, session, abort
from ghostledger.extensions import db
from ghostledger.models import ReconciliationRun, ReconciliationMatch, DiscrepancyException
from ghostledger.services.reconciliation_engine import ReconciliationEngine

reconciliation_bp = Blueprint('reconciliation', __name__)


@reconciliation_bp.route('/reconciliation', methods=['GET'])
def index():
    runs = db.session.query(ReconciliationRun).order_by(ReconciliationRun.id.desc()).all()
    latest_run = runs[0] if runs else None
    return render_template('reconciliation_runs.html', runs=runs, latest_run=latest_run)


@reconciliation_bp.route('/reconciliation/run', methods=['POST'])
def trigger_run():
    actor = session.get('username', 'analyst')
    engine = ReconciliationEngine()
    try:
        run = engine.run(actor=actor, ip_address=request.remote_addr)
        flash(
            f"Reconciliation Run #{run.id} completed: {run.matched_records} matched ({run.match_rate}%), "
            f"{run.discrepancy_records} exceptions flagged.",
            'success'
        )
    except Exception as e:
        flash(f"Reconciliation failed: {str(e)}", 'error')

    return redirect(url_for('reconciliation.index'))


@reconciliation_bp.route('/reconciliation/runs/<int:run_id>', methods=['GET'])
def run_detail(run_id: int):
    run = db.session.query(ReconciliationRun).filter_by(id=run_id).first()
    if not run:
        abort(404)
    matches = db.session.query(ReconciliationMatch).filter_by(reconciliation_run_id=run.id).limit(100).all()
    exceptions = db.session.query(DiscrepancyException).filter_by(reconciliation_run_id=run.id).all()
    return render_template('reconciliation_detail.html', run=run, matches=matches, exceptions=exceptions)
