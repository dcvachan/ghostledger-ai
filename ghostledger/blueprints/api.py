from flask import Blueprint, jsonify, request, session
from ghostledger.services.reporting_service import reporting_service
from ghostledger.services.seed_data_service import seed_data_service
from ghostledger.services.investigation_engine import investigation_engine

api_bp = Blueprint('api', __name__, url_prefix='/api')


@api_bp.route('/metrics', methods=['GET'])
def get_metrics():
    metrics = reporting_service.get_dashboard_metrics()
    return jsonify(metrics)


@api_bp.route('/seed-demo', methods=['POST'])
def seed_demo():
    actor = session.get('username', 'demo_runner')
    res = seed_data_service.seed_database(actor=actor)
    return jsonify(res)


@api_bp.route('/investigate/<int:exception_id>', methods=['POST'])
def investigate(exception_id: int):
    actor = session.get('username', 'analyst')
    force_rules = request.json.get('force_rules', False) if request.is_json else False
    try:
        report = investigation_engine.investigate_exception(
            exception_id=exception_id,
            actor=actor,
            force_rules_engine=force_rules
        )
        return jsonify({
            'success': True,
            'report': report.to_dict()
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 400
