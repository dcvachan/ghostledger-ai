from flask import Blueprint, render_template, request, redirect, url_for, session, flash, current_app
from ghostledger.extensions import db
from ghostledger.models import User
from ghostledger.services.audit_service import audit_service

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Check if one-click demo login was clicked
        if request.form.get('demo_login') == 'true' or current_app.config.get('DEMO_MODE'):
            session['user_id'] = 1
            session['username'] = 'demo_analyst'
            session['role'] = 'analyst'
            session['email'] = 'analyst@ghostledger.ai'
            flash('Logged in as Demo Financial Analyst.', 'success')
            return redirect(url_for('dashboard.index'))

        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = db.session.query(User).filter(
            (User.username == username) | (User.email == username)
        ).first()

        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['email'] = user.email
            
            audit_service.log(
                event_type='USER_LOGIN',
                actor=user.username,
                entity_type='User',
                entity_id=str(user.id),
                action_details={'ip': request.remote_addr}
            )
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(url_for('dashboard.index'))

        flash('Invalid username or password.', 'error')

    return render_template('login.html', demo_mode=current_app.config.get('DEMO_MODE', True))


@auth_bp.route('/logout')
def logout():
    actor = session.get('username', 'anonymous')
    session.clear()
    flash('You have been logged out safely.', 'info')
    return redirect(url_for('auth.login'))
