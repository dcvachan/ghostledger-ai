from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from ghostledger.extensions import db
from ghostledger.models import DraftAction, DiscrepancyException
from ghostledger.services.action_service import action_service
from ghostledger.services.agent_tools import agent_tools

actions_bp = Blueprint('actions', __name__)


@actions_bp.route('/actions', methods=['GET'])
def index():
    status = request.args.get('status')
    query = db.session.query(DraftAction)
    if status:
        query = query.filter_by(status=status.upper())
    actions = query.order_by(DraftAction.created_at.desc()).all()
    return render_template('actions.html', actions=actions, current_status=status)


@actions_bp.route('/actions/create', methods=['POST'])
def create_draft():
    exception_id = int(request.form.get('exception_id', 0))
    action_type = request.form.get('action_type', '').strip()
    rationale = request.form.get('rationale', '').strip()
    actor = session.get('username', 'analyst')

    res = agent_tools.create_draft_action(
        exception_id=exception_id,
        action_type=action_type,
        payload={'manual_trigger': True, 'rationale': rationale},
        rationale=rationale,
        actor=actor
    )
    if res.get('success'):
        flash('Draft action generated. Awaiting human approval.', 'success')
    else:
        flash(f"Failed to create draft action: {res.get('error')}", 'error')

    return redirect(url_for('exceptions.detail', exception_id=exception_id))


@actions_bp.route('/actions/<int:action_id>/review', methods=['POST'])
def review(action_id: int):
    decision = request.form.get('decision', '').upper()
    comment = request.form.get('comment', '').strip()
    reviewer = session.get('username', 'analyst')
    ip = request.remote_addr

    res = action_service.review_draft_action(
        action_id=action_id,
        decision=decision,
        reviewer=reviewer,
        review_comment=comment,
        ip_address=ip
    )

    if res.get('success'):
        flash(res['message'], 'success')
    else:
        flash(res.get('error', 'Review failed'), 'error')

    # Redirect to referer or actions list
    ref = request.headers.get('Referer')
    if ref:
        return redirect(ref)
    return redirect(url_for('actions.index'))


@actions_bp.route('/exceptions/<int:exception_id>/resolve', methods=['POST'])
def record_resolution(exception_id: int):
    resolution_type = request.form.get('resolution_type', '').upper().strip()
    raw_amount = request.form.get('recovered_amount', '0.00').strip()
    notes = request.form.get('verification_notes', '').strip()
    action_id_raw = request.form.get('action_id')
    action_id = int(action_id_raw) if action_id_raw and action_id_raw.isdigit() else None
    resolved_by = session.get('username', 'analyst')

    try:
        recovered_amount = Decimal(raw_amount)
    except (InvalidOperation, ValueError):
        flash(f"Invalid monetary recovered amount: '{raw_amount}'", 'error')
        return redirect(url_for('exceptions.detail', exception_id=exception_id))

    res = action_service.record_resolution(
        exception_id=exception_id,
        resolution_type=resolution_type,
        recovered_amount=recovered_amount,
        verification_notes=notes,
        resolved_by=resolved_by,
        action_id=action_id,
        ip_address=request.remote_addr
    )

    if res.get('success'):
        flash(res['message'], 'success')
    else:
        flash(res.get('error', 'Failed to record resolution'), 'error')

    return redirect(url_for('exceptions.detail', exception_id=exception_id))
