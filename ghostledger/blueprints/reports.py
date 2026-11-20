from flask import Blueprint, render_template, request, Response, session
from ghostledger.extensions import db
from ghostledger.models import AuditEvent, DiscrepancyException
from ghostledger.services.reporting_service import reporting_service

reports_bp = Blueprint('reports', __name__)


@reports_bp.route('/reports', methods=['GET'])
def index():
    status = request.args.get('status')
    exc_type = request.args.get('type')
    severity = request.args.get('severity')

    exceptions = reporting_service.filter_exceptions(
        status=status,
        severity=severity,
        exception_type=exc_type,
        limit=500
    )
    metrics = reporting_service.get_dashboard_metrics()

    return render_template(
        'reports.html',
        exceptions=exceptions,
        metrics=metrics,
        current_status=status,
        current_type=exc_type,
        current_severity=severity
    )


@reports_bp.route('/reports/export', methods=['GET'])
def export_csv():
    status = request.args.get('status')
    exc_type = request.args.get('type')

    csv_data = reporting_service.export_exceptions_csv(
        status=status,
        exception_type=exc_type
    )

    return Response(
        csv_data,
        mimetype='text/csv',
        headers={
            'Content-Disposition': 'attachment; filename=ghostledger_exceptions_report.csv',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )


@reports_bp.route('/audit-log', methods=['GET'])
def audit_log():
    event_type = request.args.get('event_type')
    actor = request.args.get('actor')

    query = db.session.query(AuditEvent)
    if event_type:
        query = query.filter_by(event_type=event_type)
    if actor:
        query = query.filter_by(actor=actor)

    events = query.order_by(AuditEvent.timestamp.desc()).limit(200).all()

    return render_template(
        'audit_log.html',
        events=events,
        current_event_type=event_type,
        current_actor=actor
    )
