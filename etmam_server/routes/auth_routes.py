"""
Authentication routes for user login, registration, and password management.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, current_user
from ..forms import LoginForm, RegistrationForm, RequestResetForm, ResetPasswordForm
from ..models import User, Role
from ..extensions import db
from ..auth import check_role_and_redirect
from ..utils import send_email

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('client.dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        new_user = User(
            username=form.username.data,
            email=form.email.data,
            password=form.password.data,
            full_name=form.full_name.data,
            phone=form.phone.data,
            role=Role.USER,
            subscription_plan=form.subscription_plan.data
        )
        db.session.add(new_user)
        db.session.commit()
        flash('تهانينا، لقد تم تسجيلك بنجاح! يمكنك الآن تسجيل الدخول.', 'success')
        return redirect(url_for('auth.client_login'))
    return render_template('register.html', title='إنشاء حساب جديد', form=form)

@auth_bp.route('/client-login', methods=['GET', 'POST'])
def client_login():
    if current_user.is_authenticated:
        return check_role_and_redirect(current_user)
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            if not user.is_active:
                flash('حسابك غير نشط. يرجى مراجعة الإدارة.', 'danger')
                return redirect(url_for('auth.client_login'))
            login_user(user, remember=form.remember_me.data)
            flash('تم تسجيل الدخول بنجاح!', 'success')
            return check_role_and_redirect(user)
        else:
            flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'danger')
    return render_template('client_login.html', form=form)

@auth_bp.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated and (current_user.is_admin or current_user.is_super_admin):
        return check_role_and_redirect(current_user)
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data) and (user.is_admin or user.is_super_admin):
            if not user.is_active:
                flash('Your account is inactive. Please contact support.', 'danger')
                return redirect(url_for('auth.admin_login'))
            login_user(user, remember=form.remember_me.data)
            flash('Logged in successfully!', 'success')
            return check_role_and_redirect(user)
        else:
            flash('Invalid username, password, or insufficient privileges.', 'danger')
    return render_template('admin_login.html', title='Admin Login', form=form)

@auth_bp.route('/logout')
def logout():
    logout_user()
    flash('تم تسجيل الخروج بنجاح.', 'success')
    return redirect(url_for('public.homepage'))

@auth_bp.route("/reset-password-request", methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('public.homepage'))
    form = RequestResetForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            token = user.get_reset_password_token()
            send_email('Password Reset Request',
                       recipients=[user.email],
                       text_body=f'''To reset your password, visit the following link:
{url_for('auth.reset_token', token=token, _external=True)}

If you did not make this request then simply ignore this email and no changes will be made.
''',
                       html_body=f'''<h3>Password Reset Request</h3>
<p>To reset your password, visit the following link:</p>
<p><a href="{url_for('auth.reset_token', token=token, _external=True)}">Reset Password</a></p>
<p>If you did not make this request then simply ignore this email and no changes will be made.</p>
''')
        flash('An email has been sent with instructions to reset your password.', 'info')
        return redirect(url_for('auth.client_login'))
    return render_template('auth/request_reset_form.html', title='Reset Password', form=form)

@auth_bp.route("/reset-password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('public.homepage'))
    user = User.verify_reset_password_token(token)
    if user is None:
        flash('That is an invalid or expired token', 'warning')
        return redirect(url_for('auth.reset_password_request'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash('Your password has been updated! You are now able to log in', 'success')
        return redirect(url_for('auth.client_login'))
    return render_template('auth/reset_password_form.html', title='Reset Password', form=form)
