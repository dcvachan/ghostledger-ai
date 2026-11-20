from flask import Blueprint, render_template, request, flash, redirect, url_for, session, jsonify, abort
from ghostledger.extensions import db
from ghostledger.models import (
    DiscrepancyException,
    InvestigationReport,
    DraftAction,
    Resolution,
    AuditEvent
)
from ghostledger.services.investigation_engine import investigation_engine
from ghostledger.services.reporting_service import reporting_service

exceptions_bp = Blueprint('exceptions', __name__)


@exceptions_bp.route('/exceptions', methods=['GET'])
def index():
    status = request.args.get('status')
    severity = request.args.get('severity')
    exc_type = request.args.get('type')

    exceptions = reporting_service.filter_exceptions(
        status=status,
        severity=severity,
        exception_type=exc_type,
        limit=200
    )

    return render_template(
        'exceptions.html',
        exceptions=exceptions,
        current_status=status,
        current_severity=severity,
        current_type=exc_type
    )


@exceptions_bp.route('/exceptions/<int:exception_id>', methods=['GET'])
def detail(exception_id: int):
    exc = db.session.query(DiscrepancyException).filter_by(id=exception_id).first()
    if not exc:
        abort(404)
    investigation = db.session.query(InvestigationReport).filter_by(exception_id=exc.id).order_by(
        InvestigationReport.id.desc()
    ).first()

    draft_actions = db.session.query(DraftAction).filter_by(exception_id=exc.id).all()
    resolutions = db.session.query(Resolution).filter_by(exception_id=exc.id).all()

    # Fetch audit events related to this exception
    audit_trail = db.session.query(AuditEvent).filter(
        AuditEvent.entity_id == str(exc.id)
    ).order_by(AuditEvent.timestamp.desc()).all()

    return render_template(
        'exception_detail.html',
        exception=exc,
        investigation=investigation,
        draft_actions=draft_actions,
        resolutions=resolutions,
        audit_trail=audit_trail
    )


@exceptions_bp.route('/exceptions/<int:exception_id>/investigate', methods=['POST'])
def run_investigation(exception_id: int):
    actor = session.get('username', 'analyst')
    force_rules = request.form.get('engine') == 'rules'
    try:
        report = investigation_engine.investigate_exception(
            exception_id=exception_id,
            actor=actor,
            force_rules_engine=force_rules
        )
        engine_label = "Deterministic Rules Engine" if report.engine_used == 'RULES_ENGINE' else f"LLM Agent ({report.model_name})"
        flash(f"Investigation completed using {engine_label} (Confidence: {report.confidence_score}%).", 'success')
    except Exception as e:
        flash(f"Investigation failed: {str(e)}", 'error')

    return redirect(url_for('exceptions.detail', exception_id=exception_id))
