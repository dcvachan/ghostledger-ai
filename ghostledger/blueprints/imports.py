from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from ghostledger.extensions import db
from ghostledger.models import ImportedFile
from ghostledger.services.csv_service import csv_service

imports_bp = Blueprint('imports', __name__)


@imports_bp.route('/imports', methods=['GET'])
def index():
    files = db.session.query(ImportedFile).order_by(ImportedFile.created_at.desc()).all()
    return render_template('import.html', files=files, report=None)


@imports_bp.route('/imports/upload', methods=['POST'])
def upload():
    file = request.files.get('file')
    file_type = request.form.get('file_type', '').upper()

    if not file or file.filename == '':
        flash('No file selected for upload.', 'error')
        return redirect(url_for('imports.index'))

    if not file.filename.lower().endswith('.csv'):
        flash('Only CSV files are supported.', 'error')
        return redirect(url_for('imports.index'))

    file_bytes = file.read()
    if len(file_bytes) > 10 * 1024 * 1024:
        flash('File exceeds maximum upload size limit (10MB).', 'error')
        return redirect(url_for('imports.index'))

    actor = session.get('username', 'analyst')
    ip_address = request.remote_addr

    success, report, _ = csv_service.validate_and_parse(
        file_bytes=file_bytes,
        filename=file.filename,
        file_type=file_type,
        actor=actor,
        ip_address=ip_address
    )

    if success:
        flash(f"Successfully imported {report['valid_count']} records from '{file.filename}'.", 'success')
    else:
        flash(f"Import failed: {report.get('error', 'Unknown validation failure')}", 'error')

    files = db.session.query(ImportedFile).order_by(ImportedFile.created_at.desc()).all()
    return render_template('import.html', files=files, report=report)
