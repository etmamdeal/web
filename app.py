"""
تطبيق Flask الرئيسي
---------------
"""

from flask import Blueprint, Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, get_flashed_messages, abort, current_app
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
import werkzeug.routing.exceptions # Added for specific exception handling
from datetime import datetime, timedelta, date # Added date
from dotenv import load_dotenv
from collections import OrderedDict # For ordered columns in deal pipeline
import io
# Removed duplicate dotenv and io imports
import contextlib
import json # json is already imported, ensure it's here
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.utils import secure_filename
from functools import wraps
import subprocess # For execute_python_script
import sys # For execute_python_script
import os # For execute_python_script, path operations

from .models import User, Property, Deal, Script, UserScript, RunLog, Role, Permission, Product, ProductType, Subscription, SubscriptionPeriod, Ebook, Database, Ticket, TicketMessage, TicketAttachment
from .forms import ResetPasswordForm, ProfileForm, ChangePasswordForm, EditProductForm, PropertyForm, DealForm, DEAL_STAGES, AddScriptForm # Imported AddScriptForm
from .extensions import db, login_manager
from .auth import super_admin_required, admin_required, client_required, check_permission, check_role_and_redirect

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

# Helper function for script execution
# SCRIPTS_BASE_DIR will be defined inside the function using current_app.config

def execute_python_script(script_relative_path, input_params_list=None, timeout_seconds=30):
    """
    Executes a Python script securely using subprocess.
    Args:
        script_relative_path (str): The relative path to the .py file from the configured UPLOAD_FOLDER/scripts.
                                    Example: 'some_script_dir/my_script.py'
        input_params_list (list, optional): A list of strings to be passed as command-line arguments.
        timeout_seconds (int, optional): Maximum execution time.
    Returns:
        dict: {'status': 'success'|'error'|'timeout', 'output': str, 'error': str, 'exit_code': int|None}
    """
    if input_params_list is None:
        input_params_list = []

    scripts_upload_subfolder = 'scripts'  # As used in add_script_route

    # Construct absolute path to the main scripts directory
    configured_upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
    if not os.path.isabs(configured_upload_folder):
        # If UPLOAD_FOLDER is relative, it's typically relative to app.instance_path or app.root_path.
        # Flask's default instance_path is app.root_path/instance.
        # Let's assume for consistency with file uploads, it's relative to app.root_path if not absolute.
        abs_upload_folder = os.path.join(current_app.root_path, configured_upload_folder)
    else:
        abs_upload_folder = configured_upload_folder

    scripts_base_dir = os.path.abspath(os.path.join(abs_upload_folder, scripts_upload_subfolder))

    # Ensure scripts_base_dir exists (it should if scripts are being added)
    if not os.path.isdir(scripts_base_dir):
        current_app.logger.error(f"Scripts base directory does not exist: {scripts_base_dir}")
        return {'status': 'error', 'output': '', 'error': 'Scripts directory configuration error.', 'exit_code': None}

    full_script_path = os.path.abspath(os.path.join(scripts_base_dir, script_relative_path))
    script_directory = os.path.dirname(full_script_path)

    if not os.path.isfile(full_script_path):
        return {'status': 'error', 'output': '', 'error': f'Script file not found at {full_script_path}. Relative path: {script_relative_path}', 'exit_code': None}
    if not full_script_path.endswith('.py'):
        return {'status': 'error', 'output': '', 'error': 'Invalid script file type (must be .py).', 'exit_code': None}

    # Security Check: Ensure the resolved full_script_path is truly within the intended scripts_base_dir
    if not os.path.abspath(full_script_path).startswith(scripts_base_dir):
         current_app.logger.warning(f"Attempt to access script outside base directory: {full_script_path} vs {scripts_base_dir}")
         return {'status': 'error', 'output': '', 'error': 'Script path is outside allowed directory.', 'exit_code': None}

    command = [sys.executable, full_script_path] + [str(p) for p in input_params_list]

    try:
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=script_directory,
            check=False  # Do not raise exception for non-zero exit codes
        )

        output_str = process.stdout.strip() if process.stdout else ""
        error_str = process.stderr.strip() if process.stderr else ""

        MAX_STDOUT_SIZE = 1 * 1024 * 1024
        MAX_STDERR_SIZE = 512 * 1024

        if len(output_str) > MAX_STDOUT_SIZE:
            output_str = output_str[:MAX_STDOUT_SIZE] + "\n[... Output truncated ...]"
        if len(error_str) > MAX_STDERR_SIZE:
            error_str = error_str[:MAX_STDERR_SIZE] + "\n[... Error output truncated ...]"

        if process.returncode == 0:
            return {'status': 'success', 'output': output_str, 'error': error_str, 'exit_code': process.returncode}
        else:
            main_error_msg = error_str if error_str else f"Script exited with error code {process.returncode}."
            if not error_str and output_str:
                main_error_msg += f" Output: {output_str[:200]}" # Append some stdout if no stderr
            return {'status': 'error', 'output': output_str,
                    'error': main_error_msg,
                    'exit_code': process.returncode}

    except subprocess.TimeoutExpired:
        return {'status': 'timeout', 'output': '', 'error': f'Script execution timed out after {timeout_seconds} seconds.', 'exit_code': None}
    except Exception as e:
        current_app.logger.error(f"Subprocess execution system error for {script_relative_path}: {str(e)}")
        return {'status': 'error', 'output': '', 'error': f'An internal system error occurred during script execution.', 'exit_code': None}


# إنشاء Blueprint
bp = Blueprint('main', __name__)

# Context processor to inject 'now' for templates
@bp.app_context_processor
def inject_now():
    return {'now': datetime.utcnow()}

# تمرير csrf_token لجميع القوالب (حل مشكلة النقص في بعض النماذج)
@bp.app_context_processor
def inject_csrf_token():
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf)

# تهيئة نظام تسجيل الدخول
# login_manager = LoginManager()
# login_manager.login_view = 'main.client_login'

def create_super_admin():
    """إنشاء حساب السوبر أدمن إذا لم يكن موجوداً"""
    try:
        # التحقق من وجود حساب سوبر أدمن
        super_admin = User.query.filter_by(role=Role.SUPER_ADMIN).first()
        if not super_admin:
            # إنشاء حساب السوبر أدمن
            super_admin = User(
                username='super_admin',
                password=generate_password_hash('super_admin123'),
                email='super_admin@etmamdeal.com',
                full_name='السوبر أدمن',
                phone='0500000000',
                role=Role.SUPER_ADMIN,
                is_active=True,
                permissions=json.dumps(Permission.get_all_permissions())
            )
            db.session.add(super_admin)
            db.session.commit()
            print("✅ تم إنشاء حساب السوبر أدمن بنجاح!")
            print("Username: super_admin")
            print("Password: super_admin123")
        else:
            print("✅ حساب السوبر أدمن موجود مسبقاً")
    except Exception as e:
        print(f"❌ خطأ في إنشاء حساب السوبر أدمن: {str(e)}")
        db.session.rollback()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# إعدادات البريد الإلكتروني من متغيرات البيئة
SMTP_SERVER = 'smtppro.zoho.sa'
SMTP_PORT = 465
SMTP_USERNAME = 'ai_agents@etmamdeal.com'
SMTP_PASSWORD = 'TKxLhzQ2zRtp'
ADMIN_EMAIL = 'ai_agents@etmamdeal.com'

# تحسين التحقق من الصلاحيات
def check_admin_permission(permission):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("يجب تسجيل الدخول أولاً.", "danger")
                return redirect(url_for('main.admin_login'))
                
            if current_user.is_super_admin:
                if request.endpoint.startswith('admin_'):
                    return redirect(url_for('main.super_admin_dashboard'))
            elif current_user.is_admin:
                if not current_user.has_permission(permission):
                    flash("ليس لديك الصلاحية الكافية.", "danger")
                    return redirect(url_for('main.admin_dashboard'))
            else:
                flash("غير مصرح لك بالدخول هنا.", "danger")
                return redirect(url_for('main.homepage'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def send_email(subject, body, to_email):
    try:
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = SMTP_USERNAME
        msg['To'] = to_email

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
            print("✅ تم الإرسال بنجاح")
            return True
    except Exception as e:
        error_msg = f"❌ فشل الإرسال: {str(e)}"
        print(error_msg)
        current_app.logger.error(error_msg)
        return False

# المسارات
@bp.route('/')
def homepage():
    try:
        return render_template('index.html', now=datetime.now())
    except Exception as e:
        current_app.logger.error(f'خطأ في الصفحة الرئيسية: {str(e)}')
        return f'<h1>خطأ في عرض الصفحة</h1><pre>{str(e)}</pre>', 500

@bp.route('/service-description')
def service_description():
    return render_template('service_description.html')

@bp.route('/scripts')
def scripts():
    try:
        # Renamed 'scripts' to 'script_products' for clarity as items are Product objects
        script_products = Product.query.filter_by(type=ProductType.SCRIPT, is_active=True).all()
        return render_template('scripts.html', scripts=script_products, ProductType=ProductType)
    except Exception as e:
        current_app.logger.error(f"Error in /scripts route: {str(e)}")
        flash("حدث خطأ أثناء تحميل السكربتات", "danger")
        return redirect(url_for('main.products'))

@bp.route('/products')
def products():
    try:
        all_products = Product.query.filter_by(is_active=True).all()
        return render_template('products.html', products=all_products, ProductType=ProductType)
    except Exception as e:
        current_app.logger.error(f"Error in /products route: {str(e)}")
        flash("حدث خطأ أثناء تحميل المنتجات", "danger")
        return redirect(url_for('main.homepage'))

@bp.route('/request-script/<int:script_id>')
@bp.route('/request-script/<int:script_id>/<int:period>')
@login_required
def request_script(script_id, period=None):
    script = Product.query.get_or_404(script_id)
    if script.type != 'script':
        abort(404)
    
    # حساب السعر بناءً على فترة الاشتراك
    price = script.price
    if period:
        if period == 3:
            price = script.price * 2.5
        elif period == 6:
            price = script.price * 4.5
        elif period == 12:
            price = script.price * 8

    # إرسال طلب السكربت عبر البريد الإلكتروني
    send_script_request_email(current_user, script, period, price)
    
    flash('تم إرسال طلبك بنجاح. سيتم التواصل معك قريباً.', 'success')
    return redirect(url_for('main.scripts'))

@bp.route('/contact-us', methods=['GET', 'POST'])
def contact_us():
    if request.method == 'POST':
        # ... existing code ...
        return redirect(url_for('main.contact_us'))
    
    return render_template('contact_us.html', now=datetime.now())

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            confirm_password = request.form['confirm_password']
            full_name = request.form['full_name']
            phone = request.form['phone']

            if password != confirm_password:
                flash("كلمتا المرور غير متطابقتين", "danger")
                return redirect(url_for('main.register'))

            if len(password) < 6:
                flash("كلمة المرور يجب أن تكون 6 أحرف على الأقل", "danger")
                return redirect(url_for('main.register'))

            if User.query.filter_by(username=username).first():
                flash("اسم المستخدم مسجل مسبقًا", "danger")
                return redirect(url_for('main.register'))

            if User.query.filter_by(email=email).first():
                flash("البريد الإلكتروني مسجل مسبقًا", "danger")
                return redirect(url_for('main.register'))

            # إنشاء حساب جديد
            user = User(
                username=username,
                email=email,
                password=generate_password_hash(password),
                full_name=full_name,
                phone=phone,
                is_active=True
            )
            
            db.session.add(user)
            db.session.commit()
            
            login_user(user)
            flash("تم تسجيل حسابك بنجاح! مرحباً بك في منصة إتمام", "success")
            return redirect(url_for('main.client_dashboard'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"خطأ في عملية التسجيل: {str(e)}")
            flash("حدث خطأ أثناء التسجيل. الرجاء المحاولة مرة أخرى.", "danger")
            return redirect(url_for('main.register'))

    return render_template('client_register.html', now=datetime.now())

@bp.route('/client-login', methods=['GET', 'POST'])
def client_login():
    if current_user.is_authenticated:
        if current_user.is_super_admin:
            return redirect(url_for('main.super_admin_dashboard'))
        elif current_user.is_admin:
            return redirect(url_for('main.admin_dashboard'))
        else:
            return redirect(url_for('main.client_dashboard'))

    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            
            user = User.query.filter_by(username=username).first()
            
            if not user or not check_password_hash(user.password, password):
                flash("خطأ في اسم المستخدم أو كلمة المرور.", "danger")
                return redirect(url_for('main.client_login'))
            
            if user.is_admin or user.is_super_admin:
                flash("هذا الحساب مخصص للإدارة فقط.", "danger")
                return redirect(url_for('main.client_login'))
            
            if not user.is_active:
                flash("حسابك غير مفعل. الرجاء التواصل مع الإدارة.", "warning")
                return redirect(url_for('main.client_login'))
                
            login_user(user)
            flash("تم تسجيل دخولك بنجاح!", "success")
            return redirect(url_for('main.client_dashboard'))
            
        except Exception as e:
            current_app.logger.error(f"خطأ في تسجيل دخول العميل: {str(e)}")
            flash("حدث خطأ أثناء تسجيل الدخول. الرجاء المحاولة مرة أخرى.", "danger")
            return redirect(url_for('main.client_login'))
            
    return render_template('client_login.html', now=datetime.now())

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash("تم تسجيل خروجك بنجاح.", "success")
    return redirect(url_for('main.homepage'))

@bp.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        if current_user.is_super_admin:
            return redirect(url_for('main.super_admin_dashboard'))
        elif current_user.is_admin:
            return redirect(url_for('main.admin_dashboard'))
        else:
            flash("غير مصرح لك بالدخول هنا أو أنك بالفعل مسجل دخول كمستخدم عادي.", "info")
            return redirect(url_for('main.client_dashboard'))

    if request.method == 'POST':
        try:
            username = request.form['username']
            password = request.form['password']
            
            user = User.query.filter_by(username=username).first()
            
            if not user:
                flash("اسم المستخدم غير موجود.", "danger")
                return redirect(url_for('main.admin_login'))
            
            if not check_password_hash(user.password, password):
                flash("كلمة المرور غير صحيحة.", "danger")
                return redirect(url_for('main.admin_login'))
            
            if not (user.is_admin or user.is_super_admin):
                flash("هذا الحساب ليس لديه صلاحيات إدارية.", "danger")
                return redirect(url_for('main.admin_login'))
            
            if not user.is_active:
                flash("الحساب غير مفعل.", "danger")
                return redirect(url_for('main.admin_login'))
            
            login_user(user)
            user.update_last_login()
            flash("تم تسجيل دخولك بنجاح!", "success")
            
            if user.is_super_admin:
                return redirect(url_for('main.super_admin_dashboard'))
            else:
                return redirect(url_for('main.admin_dashboard'))
            
        except Exception as e:
            current_app.logger.error(f"خطأ في تسجيل دخول المشرف: {str(e)}")
            flash("حدث خطأ أثناء تسجيل الدخول. الرجاء المحاولة مرة أخرى.", "danger")
            return redirect(url_for('main.admin_login'))
            
    return render_template('admin_login.html', now=datetime.now())

@bp.route('/reset-password-request', methods=['POST'])
def reset_password_request():
    try:
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        
        if not user:
            flash("البريد الإلكتروني غير مسجل في النظام.", "danger")
            return redirect(url_for('main.admin_login'))
            
        # إنشاء رابط إعادة تعيين كلمة المرور
        reset_token = user.get_reset_password_token()
        reset_url = url_for('main.reset_password', token=reset_token, _external=True)
        
        # إرسال البريد الإلكتروني
        subject = "طلب إعادة تعيين كلمة المرور"
        body = f"""
        مرحباً {user.username},
        
        لقد تلقينا طلباً لإعادة تعيين كلمة المرور الخاصة بك.
        لإعادة تعيين كلمة المرور، يرجى النقر على الرابط التالي:
        
        {reset_url}
        
        إذا لم تقم بطلب إعادة تعيين كلمة المرور، يرجى تجاهل هذا البريد.
        
        مع تحيات،
        فريق إتمام
        """
        
        if send_email(subject, body, user.email):
            flash("تم إرسال رابط إعادة تعيين كلمة المرور إلى بريدك الإلكتروني.", "success")
        else:
            flash("حدث خطأ أثناء إرسال البريد الإلكتروني. الرجاء المحاولة مرة أخرى.", "danger")
            
    except Exception as e:
        current_app.logger.error(f"خطأ في طلب إعادة تعيين كلمة المرور: {str(e)}")
        flash("حدث خطأ أثناء معالجة الطلب. الرجاء المحاولة مرة أخرى.", "danger")
        
    return redirect(url_for('main.admin_login')) # Keep this, as it's for the modal on admin_login page. The new usage will also redirect.

@bp.route('/reset-password/<token>', methods=['GET', 'POST'], endpoint='reset_password')
def reset_password(token):
    user = User.verify_reset_password_token(token)
    if not user:
        flash('الرابط الخاص بإعادة تعيين كلمة المرور غير صالح أو انتهت صلاحيته.', 'danger')
        return redirect(url_for('main.client_login')) # Or admin_login, depending on typical user

    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = generate_password_hash(form.password.data)
        db.session.commit()
        flash('تم تحديث كلمة المرور بنجاح! يمكنك الآن تسجيل الدخول بكلمة المرور الجديدة.', 'success')
        # Determine redirect based on user role if possible, otherwise default to client_login
        if user.role == Role.ADMIN or user.role == Role.SUPER_ADMIN:
            return redirect(url_for('main.admin_login'))
        return redirect(url_for('main.client_login'))

    return render_template('reset_password.html', form=form, token=token, now=datetime.utcnow())

# This existing route is used by a modal on the admin_login page.
# We will now also use it from the super_admin_dashboard.
# Adding @super_admin_required would break its use for non-logged-in users trying to register an admin account (if that's a flow).
# However, the task implies this route should *now* be for super_admin use.
# This means the modal on admin_login.html for admin_register will become super_admin only.
# Or, we need a new route for super_admin adding admins.
# Given the instruction "Refactor admin_register for Super Admin Use", I will add the decorator and change redirect.
# This implies the previous usage from admin_login.html's modal might become non-functional or also require super_admin.
# For now, I will follow the refactoring instruction strictly.

@bp.route('/admin-register', methods=['POST'])
@login_required # Required for current_user context
@super_admin_required # Add super_admin_required decorator
def admin_register():
    try:
        # التحقق من البيانات
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        full_name = request.form['full_name']
        phone = request.form['phone']
        
        if password != confirm_password:
            flash("كلمتا المرور غير متطابقتين", "danger")
            return redirect(url_for('main.admin_login'))
            
        if User.query.filter_by(username=username).first():
            flash("اسم المستخدم مسجل مسبقاً", "danger")
            return redirect(url_for('main.admin_login'))
            
        if User.query.filter_by(email=email).first():
            flash("البريد الإلكتروني مسجل مسبقاً", "danger")
            return redirect(url_for('main.admin_login'))
            
        # إنشاء حساب المشرف
        admin = User(
            username=username,
            email=email,
            password=generate_password_hash(password),
            full_name=full_name,
            phone=phone,
            role=Role.ADMIN, # Changed from is_admin=True
            is_active=False  # يحتاج لتفعيل من السوبر أدمن
        )
        
        db.session.add(admin)
        db.session.commit()
        
        # Adjusted flash message for super_admin context
        flash(f"تم إنشاء حساب المشرف {admin.username} بنجاح. يحتاج الحساب إلى تفعيل.", "success")
        
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"خطأ في تسجيل المشرف: {str(e)}")
        flash("حدث خطأ أثناء إنشاء الحساب. الرجاء المحاولة مرة أخرى.", "danger")
        
    return redirect(url_for('main.super_admin_dashboard')) # Change redirect to super_admin_dashboard

@bp.route('/super-admin')
@login_required
@super_admin_required
def super_admin_dashboard():
    try:
        admins = User.query.filter_by(role=Role.ADMIN).all()
        users = User.query.filter_by(role=Role.USER).all()

        # Fetch all products, details will be accessed via relationships in the template
        all_products = Product.query.all()

        # For stats, we still need to query by type
        active_scripts_count = Product.query.filter_by(type=ProductType.SCRIPT, is_active=True).count()
        total_scripts_count = Product.query.filter_by(type=ProductType.SCRIPT).count()

        # The template will iterate all_products and use product.type
        # to differentiate and access product.script_definition,
        # product.ebook_details, or product.database_details

        all_scripts = Script.query.all() # Fetch all actual scripts for assignment

        permissions = Permission.get_all_permissions()
        stats = {
            'admins_count': len(admins),
            'users_count': len(users),
            'active_scripts': active_scripts_count,
            'total_scripts': total_scripts_count,
            # Add counts for other product types if needed for stats
            'total_ebooks': Product.query.filter_by(type=ProductType.EBOOK).count(),
            'total_databases': Product.query.filter_by(type=ProductType.DATABASE).count(),
        }
        return render_template(
            'super_admin_dashboard.html',
            admins=admins,
            users=users,
            all_products=all_products, # Pass all products
            scripts=all_scripts, # Pass all scripts for assignment modal
            permissions=permissions,
            stats=stats,
            ProductType=ProductType # Pass ProductType class for template usage
        )
    except Exception as e:
        current_app.logger.error(f"Error in super_admin_dashboard: {str(e)}")
        flash("حدث خطأ أثناء تحميل لوحة التحكم", "danger")
        return redirect(url_for('main.homepage'))

@bp.route('/admin')
@admin_required
def admin_dashboard():
    try:
        # The @admin_required decorator (now updated) handles:
        # 1. Authentication check (redirects to admin_login if not authenticated)
        # 2. Role check (allows admin or super_admin)
        #    - If a super_admin accesses this, they are allowed by the decorator.
        #      It's conventional for super_admins to see admin dashboards.
        #      If specific redirection for super_admins away from this page is still desired,
        #      an explicit check can be maintained:
        if current_user.is_super_admin:
            return redirect(url_for('main.super_admin_dashboard'))
            
        # Fetch data for admin dashboard
        users = User.query.filter_by(role=Role.USER).all()
        all_products = Product.query.all() # Fetch all products

        # The template will iterate all_products and use product.type
        # to differentiate and access product.script_definition,
        # product.ebook_details, or product.database_details

        try:
            return render_template(
                'admin_dashboard.html',
                users=users,
                all_products=all_products, # Pass all products
                ProductType=ProductType, # Pass ProductType class for template usage
                Permission=Permission # Pass Permission class for template usage
            )
        except werkzeug.routing.exceptions.BuildError as e:
            if 'toggle_user_status' in str(e):
                current_app.logger.error(f"BuildError for 'toggle_user_status' in admin_dashboard: {str(e)} - Rendering minimal or redirecting.")
                flash("لوحة التحكم للمشرف واجهت خطأ في عرض جزء من الصفحة، ولكن الوظيفة الرئيسية تمت.", "warning")
                # Option 1: Redirect to a safe page
                return redirect(url_for('main.homepage'))
                # Option 2: Render a minimal template (if one exists or create simple one)
                # return render_template('admin/admin_dashboard_minimal_error.html', users=users, ProductType=ProductType)
            else:
                raise e # Re-raise other BuildErrors
        
    except Exception as e:
        current_app.logger.error(f"Error in admin_dashboard: {str(e)}")
        flash("حدث خطأ أثناء تحميل لوحة التحكم", "danger")
        return redirect(url_for('main.homepage'))

@bp.route('/client', endpoint='client_dashboard') # Assuming this is being repurposed
@login_required
@client_required # Ensure this decorator is appropriate for brokers, or a new one is needed.
def client_dashboard():
    # Stats for Real Estate Broker
    total_properties = Property.query.filter_by(user_id=current_user.id).count()

    # Placeholder stats for deals until deal management is implemented
    # Corrected querying for deals (assuming Deal model is available and user_id links to the broker)
    deals_in_progress_count = Deal.query.filter(Deal.user_id == current_user.id, Deal.stage.notin_(['Closed - Won', 'Closed - Lost'])).count()
    completed_deals_count = Deal.query.filter(Deal.user_id == current_user.id, Deal.stage == 'Closed - Won').count()

    # Placeholder for revenue estimation - this requires a field like 'deal_value' or 'commission_amount' on the Deal model
    # For now, let's assume it's based on property price of 'Closed - Won' deals if no specific value field.
    # This is highly speculative and needs a proper field in Deal model.
    revenue_estimation = db.session.query(db.func.sum(Property.price)).join(Deal, Deal.property_id == Property.id).filter(Deal.user_id == current_user.id, Deal.stage == 'Closed - Won').scalar() or 0.0


    # Placeholder for recent activity - for now, just fetch last 5 properties added by user
    recent_activities = Property.query.filter_by(user_id=current_user.id)\
                                  .order_by(Property.created_at.desc())\
                                  .limit(5).all()

    return render_template('client/dashboard.html', # Changed template path
                                   total_properties=total_properties,
                                   deals_in_progress_count=deals_in_progress_count,
                                   completed_deals_count=completed_deals_count,
                                   revenue_estimation=revenue_estimation,
                                   recent_activities=recent_activities,
                                   now=datetime.utcnow() # Added now
                                  )

@bp.route('/client/my-scripts', endpoint='client_my_scripts')
@login_required
@client_required
def client_my_scripts():
    user_scripts_data = db.session.query(UserScript, Script, Product)\
        .join(Script, UserScript.script_id == Script.id)\
        .join(Product, Script.id == Product.script_id)\
        .filter(UserScript.user_id == current_user.id)\
        .filter(Product.type == ProductType.SCRIPT)\
        .all()

    # user_scripts_data will be a list of tuples (user_script_obj, script_obj, product_obj)
    # It's better to pass it as is, or structure it into a list of dicts if preferred by template complexity.

    return render_template('client/my_scripts.html', user_scripts_data=user_scripts_data, now=datetime.utcnow())

@bp.route('/client/my-logs', endpoint='client_my_logs')
@login_required
@client_required
def client_my_logs():
    page = request.args.get('page', 1, type=int)
    userscript_id_filter = request.args.get('userscript_id_filter', None, type=int)

    query = db.session.query(RunLog, Script.name.label('script_name'))\
        .join(Script, RunLog.script_id == Script.id)\
        .filter(RunLog.user_id == current_user.id)

    filter_active_script_name = None

    if userscript_id_filter is not None:
        user_script_to_filter = UserScript.query.filter_by(id=userscript_id_filter, user_id=current_user.id).first()
        if user_script_to_filter:
            query = query.filter(RunLog.user_script_id == userscript_id_filter)
            script_for_filter = Script.query.get(user_script_to_filter.script_id)
            if script_for_filter:
                product_for_filter = Product.query.filter_by(script_id=script_for_filter.id, type=ProductType.SCRIPT).first()
                if product_for_filter:
                    filter_active_script_name = product_for_filter.name
                else:
                    filter_active_script_name = script_for_filter.name # Fallback to script's internal name
        else:
            flash("Invalid or unauthorized script filter. Showing all logs instead.", "warning")
            userscript_id_filter = None # Reset to show all logs

    logs_pagination = query.order_by(RunLog.executed_at.desc())\
        .paginate(page=page, per_page=10, error_out=False)

    return render_template('client/my_logs.html',
                           logs_pagination=logs_pagination,
                           userscript_id_filter=userscript_id_filter,
                           filter_active_script_name=filter_active_script_name,
                           now=datetime.utcnow())

@bp.route('/client/profile', methods=['GET', 'POST'], endpoint='client_profile')
@login_required
@client_required
def client_profile():
    profile_form = ProfileForm(obj=current_user) # Pre-populate with current_user data
    password_form = ChangePasswordForm()

    # Check which form was submitted using the submit button's name
    if 'submit_profile' in request.form and profile_form.validate_on_submit():
        current_user.full_name = profile_form.full_name.data
        current_user.email = profile_form.email.data
        current_user.phone = profile_form.phone.data
        try:
            db.session.commit()
            flash('تم تحديث بيانات ملفك الشخصي بنجاح!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating profile for {current_user.username}: {str(e)}")
            flash('حدث خطأ أثناء تحديث الملف الشخصي. قد يكون البريد الإلكتروني مستخدماً.', 'danger')
        return redirect(url_for('main.client_profile'))

    if 'submit_password' in request.form and password_form.validate_on_submit():
        # The form already validates current_password and that new_password matches confirm_new_password
        current_user.password = generate_password_hash(password_form.new_password.data)
        try:
            db.session.commit()
            flash('تم تغيير كلمة المرور بنجاح!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error changing password for {current_user.username}: {str(e)}")
            flash('حدث خطأ أثناء تغيير كلمة المرور.', 'danger')
        return redirect(url_for('main.client_profile'))

    return render_template('client/profile.html', profile_form=profile_form, password_form=password_form, now=datetime.utcnow())

@bp.route('/client/properties/map', methods=['GET'], endpoint='client_add_property_map')
@login_required
@client_required
def client_add_property_map():
    user_properties = Property.query.filter_by(user_id=current_user.id).all()
    # Convert properties to a JSON string to be easily embedded in the template for JavaScript
    properties_data = []
    for prop in user_properties:
        properties_data.append({
            "title": prop.title,
            "lat": prop.latitude,
            "lng": prop.longitude,
            "type": prop.type,
            "price": prop.price,
            "url": "#" # Placeholder for url_for('main.client_edit_property', property_id=prop.id)
        })
    properties_json = json.dumps(properties_data)
    form = PropertyForm() # Instantiate the form for the modal
    return render_template('client/property_map.html', properties_json=properties_json, form=form, now=datetime.utcnow())

@bp.route('/client/properties/add', methods=['POST'], endpoint='client_add_property')
@login_required
@client_required
def client_add_property():
    form = PropertyForm()
    latitude = request.form.get('latitude', type=float)
    longitude = request.form.get('longitude', type=float)

    if not latitude or not longitude:
        flash('الموقع (خط العرض وخط الطول) مطلوب. يرجى تحديد نقطة على الخريطة.', 'danger')
        return redirect(url_for('main.client_add_property_map'))

    if form.validate_on_submit():
        try:
            # معالجة الصور
            images = form.images.data if hasattr(form, 'images') else []
            image_filenames = []
            upload_folder = os.path.join(current_app.root_path, 'static', 'property_images')
            os.makedirs(upload_folder, exist_ok=True)
            for image in images:
                if image and image.filename:
                    filename = secure_filename(image.filename)
                    save_path = os.path.join(upload_folder, filename)
                    # تجنب تكرار الاسم
                    if os.path.exists(save_path):
                        base, ext = os.path.splitext(filename)
                        filename = f"{base}_{int(datetime.utcnow().timestamp())}{ext}"
                        save_path = os.path.join(upload_folder, filename)
                    image.save(save_path)
                    image_filenames.append(filename)

            new_property = Property(
                user_id=current_user.id,
                title=form.title.data,
                type=form.type.data,
                price=form.price.data,
                area=form.area.data,
                rooms=form.rooms.data,
                description=form.description.data,
                latitude=latitude,
                longitude=longitude
                # images=json.dumps(image_filenames)  # إذا كان لديك حقل images نصي أو JSON في الجدول
            )
            db.session.add(new_property)
            db.session.commit()
            flash(f'تمت إضافة العقار "{new_property.title}" بنجاح!', 'success')
            return redirect(url_for('main.client_add_property_map'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding property: {str(e)}")
            flash('حدث خطأ أثناء إضافة العقار. يرجى المحاولة مرة أخرى.', 'danger')
    else:
        # Collect WTForm errors and flash them
        error_messages = []
        for field, errors in form.errors.items():
            for error in errors:
                error_messages.append(f"{getattr(form, field).label.text}: {error}")
        if error_messages:
            flash("فشل التحقق من النموذج: " + "؛ ".join(error_messages), 'danger')

    return redirect(url_for('main.client_add_property_map'))

@bp.route('/client/properties', methods=['GET'], endpoint='client_manage_properties')
@login_required
@client_required
def client_manage_properties():
    page = request.args.get('page', 1, type=int)
    property_type_filter = request.args.get('type_filter', None)

    query = Property.query.filter_by(user_id=current_user.id)
    if property_type_filter and property_type_filter != 'all' and property_type_filter != '':
        query = query.filter(Property.type == property_type_filter)

    properties_pagination = query.order_by(Property.created_at.desc()).paginate(page=page, per_page=10, error_out=False)

    # Get distinct property types for filter dropdown, ensuring they are not None or empty
    distinct_types_query = db.session.query(Property.type)\
        .filter(Property.user_id == current_user.id, Property.type.isnot(None), Property.type != '')\
        .distinct().all()
    available_types = [ptype[0] for ptype in distinct_types_query]

    return render_template('client/property_list.html',
                           properties_pagination=properties_pagination,
                           available_types=available_types,
                           current_type_filter=property_type_filter if property_type_filter else 'all', # ensure 'all' is default if None
                           now=datetime.utcnow())

@bp.route('/client/properties/<int:property_id>/edit', methods=['GET', 'POST'], endpoint='client_edit_property')
@login_required
@client_required
def client_edit_property(property_id):
    property_to_edit = Property.query.filter_by(id=property_id, user_id=current_user.id).first_or_404()
    form = PropertyForm(obj=property_to_edit) # Pre-populate form with existing data

    original_lat = property_to_edit.latitude
    original_lng = property_to_edit.longitude

    if form.validate_on_submit(): # This will be true for POST requests if form data is valid
        try:
            property_to_edit.title = form.title.data
            property_to_edit.type = form.type.data
            property_to_edit.price = form.price.data
            property_to_edit.area = form.area.data
            property_to_edit.rooms = form.rooms.data
            property_to_edit.description = form.description.data

            # Get lat/lng from hidden fields in the form for potential re-positioning
            new_latitude = request.form.get('latitude', type=float)
            new_longitude = request.form.get('longitude', type=float)

            if new_latitude and new_longitude:
                property_to_edit.latitude = new_latitude
                property_to_edit.longitude = new_longitude

            property_to_edit.updated_at = datetime.utcnow() # Manually set updated_at
            db.session.commit()
            flash(f'تم تحديث العقار "{property_to_edit.title}" بنجاح!', 'success')
            return redirect(url_for('main.client_manage_properties'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error editing property {property_id}: {str(e)}")
            flash('حدث خطأ أثناء تحديث العقار. يرجى المحاولة مرة أخرى.', 'danger')

    # For GET requests, or if form validation failed on POST:
    # Pass original coordinates for map centering.
    # The form object (form) will contain submitted values and errors if validation failed.
    # Ensure hidden fields in template are populated with these values for JS to pick up on load.
    if request.method == 'POST' and not form.validate(): # If POST failed validation
        # Keep submitted values for hidden fields if they exist, else use original
        current_lat_for_map = request.form.get('latitude', original_lat, type=float)
        current_lng_for_map = request.form.get('longitude', original_lng, type=float)
        flash('الرجاء تصحيح الأخطاء في النموذج.', 'danger')
    else: # For GET requests
        current_lat_for_map = original_lat
        current_lng_for_map = original_lng


    return render_template('client/edit_property.html',
                           form=form,
                           property_id=property_id,
                           property_title=property_to_edit.title,
                           current_lat=current_lat_for_map,
                           current_lng=current_lng_for_map,
                           now=datetime.utcnow())

@bp.route('/client/properties/<int:property_id>/delete', methods=['POST'], endpoint='client_delete_property')
@login_required
@client_required
def client_delete_property(property_id):
    property_to_delete = Property.query.filter_by(id=property_id, user_id=current_user.id).first_or_404()

    try:
        # Note: If Deal model has property_id as ForeignKey without ondelete='CASCADE',
        # and related deals exist, this will fail.
        # For now, proceeding with direct delete as per subtask instructions.
        # Example: Deal.query.filter_by(property_id=property_to_delete.id, user_id=current_user.id).delete()

        # Check for related deals and prevent deletion if they exist, or handle them.
        # This check assumes Deal model is imported and has a 'property_id' field.
        if hasattr(Deal, 'query') and Deal.query.filter_by(property_id=property_to_delete.id).first():
            flash(f'لا يمكن حذف العقار "{property_to_delete.title}" لأنه مرتبط بصفقات حالية. يرجى التعامل مع الصفقات أولاً.', 'danger')
            return redirect(url_for('main.client_manage_properties'))

        db.session.delete(property_to_delete)
        db.session.commit()
        flash(f'تم حذف العقار "{property_to_delete.title}" بنجاح.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting property {property_id}: {str(e)}")
        flash('حدث خطأ أثناء حذف العقار. يرجى المحاولة مرة أخرى.', 'danger')

    return redirect(url_for('main.client_manage_properties'))

@bp.route('/client/marketing-tools', methods=['GET'], endpoint='client_marketing_tools')
@login_required
@client_required
def client_marketing_tools():
    # This page might have dynamic elements in the future, but for now, it's static content.
    return render_template('client/marketing_tools.html', now=datetime.utcnow())

@bp.route('/client/deals', methods=['GET'], endpoint='client_deal_tracker') # Name matches dashboard link
@login_required
@client_required
def client_deal_tracker():
    page = request.args.get('page', 1, type=int)

    # Fetch deals associated with the current user (broker)
    # Joining with Property to display property title
    deals_query = db.session.query(Deal, Property.title.label('property_title'))\
        .join(Property, Deal.property_id == Property.id)\
        .filter(Deal.user_id == current_user.id) # Assuming Deal.user_id is the broker

    # Example filtering by stage (can be expanded)
    deal_stage_filter = request.args.get('stage_filter', 'all')
    if deal_stage_filter and deal_stage_filter != 'all' and deal_stage_filter != '':
        deals_query = deals_query.filter(Deal.stage == deal_stage_filter)

    deals_pagination = deals_query.order_by(Deal.updated_at.desc()).paginate(page=page, per_page=10, error_out=False)

    # Get distinct deal stages for filter dropdown
    distinct_stages_query = db.session.query(Deal.stage)\
        .filter(Deal.user_id == current_user.id, Deal.stage.isnot(None), Deal.stage != '')\
        .distinct()
    available_stages = [d_stage[0] for d_stage in distinct_stages_query.all()]

    return render_template('client/deal_list.html',
                           deals_pagination=deals_pagination,
                           available_stages=available_stages,
                           current_stage_filter=deal_stage_filter if deal_stage_filter else 'all',
                           deal_stages_config=DEAL_STAGES, # Pass DEAL_STAGES for the dropdown
                           now=datetime.utcnow())

@bp.route('/client/deals/<int:deal_id>/change-stage', methods=['POST'], endpoint='client_change_deal_stage')
@login_required
@client_required
def client_change_deal_stage(deal_id):
    deal_to_update = Deal.query.filter_by(id=deal_id, user_id=current_user.id).first_or_404()

    new_stage = request.form.get('new_stage')

    # DEAL_STAGES is imported from .forms
    valid_stages = [stage_tuple[0] for stage_tuple in DEAL_STAGES]
    if not new_stage or new_stage not in valid_stages:
        flash('مرحلة غير صالحة.', 'danger') # Invalid stage selected.
        return redirect(url_for('main.client_deal_tracker'))

    if deal_to_update.stage == new_stage:
        flash(f'الصفقة بالفعل في مرحلة "{new_stage}".', 'info') # Deal is already in the "{new_stage}" stage.
    else:
        deal_to_update.stage = new_stage
        deal_to_update.updated_at = datetime.utcnow()
        try:
            db.session.commit()
            flash(f'تم تحديث مرحلة الصفقة إلى "{new_stage}" بنجاح!', 'success') # Deal stage updated to "{new_stage}" successfully!
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error changing deal stage for deal {deal_id}: {str(e)}")
            flash('حدث خطأ أثناء تحديث مرحلة الصفقة.', 'danger') # An error occurred while updating the deal stage.

    # Preserve pagination and filter context on redirect
    page = request.form.get('page', 1, type=int)
    stage_filter = request.form.get('stage_filter', 'all')
    return redirect(url_for('main.client_deal_tracker',
                            page=page,
                            stage_filter=stage_filter if stage_filter != 'all' else None)) # Pass None if 'all' for cleaner URL

@bp.route('/client/deals/pipeline', methods=['GET'], endpoint='client_deal_pipeline')
@login_required
@client_required
def client_deal_pipeline():
    deals_by_stage = OrderedDict() # Use OrderedDict to maintain stage order
    # DEAL_STAGES is imported from .forms
    for stage_value, stage_display in DEAL_STAGES:
        deals_by_stage[stage_value] = {
            'display_name': stage_display, # Store display name for easier access in template
            'deals': []
        }

    # Fetch all deals for the user, joining with Property for property_title
    user_deals = db.session.query(Deal, Property.title.label('property_title'))\
        .join(Property, Deal.property_id == Property.id)\
        .filter(Deal.user_id == current_user.id)\
        .order_by(Deal.updated_at.desc()).all() # Order by update time within stages

    for deal_tuple in user_deals:
        deal_object = deal_tuple[0]
        # Dynamically adding property_title to the deal_object for easier template access
        deal_object.property_title = deal_tuple[1]

        if deal_object.stage in deals_by_stage:
            deals_by_stage[deal_object.stage]['deals'].append(deal_object)
        else:
            # Handle deals with stages not in DEAL_STAGES (e.g. old/invalid stage)
            # Optionally, create an 'Other' category or log this occurrence
            if '_OTHER_' not in deals_by_stage: # Use a distinct key for uncategorized
                 deals_by_stage['_OTHER_'] = {'display_name': 'Other / Uncategorized', 'deals': []}
            deals_by_stage['_OTHER_']['deals'].append(deal_object)
            current_app.logger.warning(f"Deal ID {deal_object.id} has an unknown stage: {deal_object.stage}")


    return render_template('client/deal_pipeline.html',
                           deals_by_stage=deals_by_stage,
                           # deal_stages_config is not strictly needed if deals_by_stage has display names
                           # But can be passed if template iterates it for columns independently
                           deal_stages_config=DEAL_STAGES,
                           now=datetime.utcnow())

@bp.route('/client/deals/<int:deal_id>/edit', methods=['GET', 'POST'], endpoint='client_edit_deal')
@login_required
@client_required
def client_edit_deal(deal_id):
    pass

@bp.route('/client/resources', methods=['GET'], endpoint='client_resources')
@login_required
@client_required
def client_resources():
    # Similar to marketing tools, this page is initially static.
    return render_template('client/resources.html', now=datetime.utcnow())

@bp.route('/manage_users')
@admin_required # Changed from @login_required
def manage_users():
    # The @admin_required decorator handles auth and base role check.
    # The previous "if not current_user.is_admin:" check is now redundant.
        
    users = User.query.all() # This might need pagination for many users
    return render_template('manage_users.html', users=users)

@bp.route('/manage_users/<int:user_id>/<action>', methods=['GET', 'POST']) # Added methods to include POST
@admin_required # Changed from @login_required
def manage_user_action(user_id, action):
    # The @admin_required decorator handles base auth and role check.
    # The initial broad "if not current_user.is_admin:" check is redundant.
    
    try:
        target_user = User.query.get_or_404(user_id)

        # Specific permission check for the action being performed
        # This existing detailed permission logic for 'toggle_status' is good and should be preserved.
        if action == 'toggle_status': # This specific permission check is more granular than just @admin_required
            if not current_user.is_super_admin and not current_user.has_permission(Permission.MANAGE_USERS):
                flash("ليس لديك الصلاحية الكافية لتغيير حالة المستخدم.", "danger")
                return redirect(url_for('main.admin_dashboard'))

            # Ensure POST for state changes
            if request.method == 'POST':
                if not current_user.is_super_admin and target_user.role != Role.USER:
                    flash("لا يمكنك تعديل حالة هذا المستخدم.", "warning")
                    return redirect(url_for('main.admin_dashboard'))

                if target_user.role == Role.SUPER_ADMIN: # Super admins cannot be toggled here
                    flash("لا يمكن تعديل حالة حساب سوبر أدمن آخر من هنا.", "danger")
                    return redirect(url_for('main.admin_dashboard'))

                if target_user.id == current_user.id: # Prevent self-deactivation
                    flash("لا يمكنك تغيير حالتك الخاصة.", "warning")
                    return redirect(url_for('main.admin_dashboard'))

                target_user.is_active = not target_user.is_active
                db.session.commit()
                flash(f"تم {'تفعيل' if target_user.is_active else 'تعطيل'} حساب المستخدم {target_user.username} بنجاح.", "success")
            else: # GET request for toggle_status (if still linked this way from some old template)
                 flash("الإجراء غير صالح. يجب أن يتم عبر POST لتغيير الحالة.", "warning")

            # Redirect after action
            if current_user.is_super_admin:
                return redirect(url_for('main.super_admin_dashboard'))
            return redirect(url_for('main.admin_dashboard'))

        # Placeholder for other potential actions like 'delete_user', 'edit_user_permissions_by_admin' etc.
        # Each would have its own specific permission checks if necessary.
        flash(f"Action '{action}' on user {target_user.username} is not fully implemented or recognized.", "info")
        if current_user.is_super_admin:
            return redirect(url_for('main.super_admin_dashboard'))
        return redirect(url_for('main.admin_dashboard'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"خطأ في إدارة المستخدم: {str(e)}") # Generic error message
        flash("حدث خطأ أثناء إدارة المستخدم.", "danger")
        # Redirect to a sensible page
        if 'manage_users' in request.referrer:
            return redirect(url_for('main.manage_users'))
        if current_user.is_super_admin:
            return redirect(url_for('main.super_admin_dashboard'))
        return redirect(url_for('main.admin_dashboard'))

        if action == 'toggle_status':
            if request.method == 'POST':
                # Regular admins can only manage regular users. Super admins can manage anyone not themselves (super_admin).
                if not current_user.is_super_admin and target_user.role != Role.USER:
                    flash("لا يمكنك تعديل حالة هذا المستخدم.", "warning")
                    return redirect(url_for('main.admin_dashboard'))

                # Super admins cannot deactivate other super admins through this route (should use specific super_admin tools if any)
                # and cannot deactivate themselves. Regular admins cannot deactivate admins/super_admins.
                if target_user.role == Role.SUPER_ADMIN:
                    flash("لا يمكن تعديل حالة حساب سوبر أدمن آخر من هنا.", "danger")
                    return redirect(url_for('main.admin_dashboard'))

                if target_user.id == current_user.id:
                    flash("لا يمكنك تغيير حالتك الخاصة.", "warning")
                    return redirect(url_for('main.admin_dashboard'))

                target_user.is_active = not target_user.is_active
                db.session.commit()
                flash(f"تم {'تفعيل' if target_user.is_active else 'تعطيل'} حساب المستخدم {target_user.username} بنجاح.", "success")
            else: # GET request for toggle_status
                flash("الإجراء غير صالح. يجب أن يتم عبر POST.", "warning")

            # Determine redirect based on who is performing action
            if current_user.is_super_admin:
                # Super admin might be managing users from their main dashboard or a dedicated user list
                # For now, assume they go back to their main dashboard.
                # If there's a specific user list page they use, redirect there.
                return redirect(url_for('main.super_admin_dashboard'))
            else: # Regular admin
                 # Regular admins manage users from their admin_dashboard (which lists users)
                return redirect(url_for('main.admin_dashboard'))

        # Fallback for other actions or if action is not 'toggle_status'
        # flash(f"Action '{action}' not fully implemented for user {target_user.username}.", "info")
        if current_user.is_super_admin:
            return redirect(url_for('main.super_admin_dashboard'))
        return redirect(url_for('main.admin_dashboard'))

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"خطأ في تحديث حالة المستخدم: {str(e)}")
        flash("حدث خطأ أثناء تحديث حالة المستخدم", "danger")
        return redirect(url_for('main.manage_users'))

# --- Script Execution Route ---
@bp.route('/client/script/<int:userscript_id>/execute', methods=['POST'], endpoint='client_execute_script')
@login_required
@client_required
def client_execute_script(userscript_id):
    userscript = UserScript.query.filter_by(id=userscript_id, user_id=current_user.id).first_or_404()
    script_model = userscript.script

    if not script_model:
        current_app.logger.error(f"No script model found for UserScript ID: {userscript_id}")
        return jsonify({'status': 'error', 'error_message': 'Associated script details not found.'}), 404

    if not script_model.file_path:
        current_app.logger.error(f"Script model ID {script_model.id} has no file_path defined.")
        return jsonify({'status': 'error', 'error_message': 'Script file path not configured.'}), 500

    # --- Subscription Check ---
    product_of_script = script_model.product_link
    if not product_of_script:
        current_app.logger.error(f"No product link found for Script ID: {script_model.id}")
        return jsonify({'status': 'error', 'error_message': 'Script not associated with a product for subscription.'}), 500

    active_subscription = Subscription.query.filter(
        Subscription.user_id == current_user.id,
        Subscription.product_id == product_of_script.id,
        Subscription.is_active == True,
        Subscription.start_date <= datetime.utcnow(),
        Subscription.end_date >= datetime.utcnow()
    ).first()

    if not active_subscription:
        current_app.logger.warning(f"User {current_user.id} attempted to execute script {script_model.id} (Product ID: {product_of_script.id}) without active subscription.")
        return jsonify({'status': 'error', 'error_message': 'You do not have an active subscription for this script or your subscription has expired.'}), 403

    # --- Parameter Validation (Revised) ---
    submitted_params = request.json
    if not isinstance(submitted_params, dict):
        return jsonify({'status': 'error', 'error_message': 'Invalid parameters format. Expected JSON object.'}), 400

    # script_model.parameters is expected to be a dict like {"param_name1": "Description1", ...}
    # or an empty dict if no parameters are defined.
    script_param_definitions = script_model.parameters if isinstance(script_model.parameters, dict) else {}

    validated_params_for_script = []
    validation_errors = []

    # Iterate based on the order of keys in script_param_definitions (Python 3.7+ dicts preserve insertion order)
    # This means the script should expect parameters in the order they were defined by the admin.
    for param_name in script_param_definitions.keys():
        if param_name not in submitted_params:
            # Assuming all defined parameters are required.
            # The description (value in script_param_definitions) can be used in the error message.
            param_label = script_param_definitions[param_name] if isinstance(script_param_definitions[param_name], str) else param_name
            validation_errors.append(f"Parameter '{param_label}' (name: {param_name}) is required.")
        else:
            validated_params_for_script.append(str(submitted_params[param_name]))

    # If script_param_definitions is empty, and submitted_params is not, this is okay;
    # script might not need params, or might use a generic **kwargs.
    # If script_param_definitions is NOT empty, but submitted_params IS empty (and params were required by above loop):
    # validation_errors will be populated.

    if validation_errors:
        return jsonify({'status': 'error', 'error_message': 'Validation failed.', 'errors': validation_errors}), 400

    # --- Execute Script ---
    execution_result = execute_python_script(
        script_relative_path=script_model.file_path,
        input_params_list=validated_params_for_script,
        timeout_seconds=current_app.config.get('SCRIPT_EXECUTION_TIMEOUT', 60)
    )

    # --- Log Execution ---
    run_log_entry = None
    try:
        run_log_entry = RunLog(
            user_script_id=userscript.id,
            user_id=current_user.id,
            script_id=script_model.id,
            input_parameters=json.dumps(submitted_params),
            status=execution_result['status'],
            output=execution_result['output'],
            error=execution_result['error'],
            executed_at=datetime.utcnow()
        )
        db.session.add(run_log_entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback() # Rollback logging failure
        current_app.logger.error(f"Error logging script execution for userscript {userscript_id}: {str(e)}")
        # The script execution already happened. We should still return its result.
        # Optionally, add a specific warning to the response if logging fails.
        if execution_result['status'] == 'success': # If script was fine, but logging failed
            # Add a non-critical error to the response about logging
            execution_result['warning_message'] = 'Script executed successfully, but there was an issue logging the execution details.'
        # If script already failed, its error is more important.
        pass

    return jsonify({
        'status': execution_result['status'],
        'output': execution_result['output'],
        'error_message': execution_result.get('error'), # Use .get() for safety
        'warning_message': execution_result.get('warning_message'), # Include warning if set
        'run_log_id': run_log_entry.id if run_log_entry and hasattr(run_log_entry, 'id') else None
    })

@bp.route('/client/scripts', methods=['GET'], endpoint='client_my_assigned_scripts')
@login_required
@client_required
def client_my_assigned_scripts():
    # Fetch UserScript entries, joining with Script and Product for details
    assigned_scripts_data = db.session.query(
        UserScript.id.label('userscript_id'),
        Product.name.label('product_name'),
        Product.description.label('product_description'),
        Script.id.label('script_id'),
        Script.parameters.label('script_parameters_definition'), # For building the execution form later
        Subscription.end_date.label('subscription_end_date') # To display subscription validity
    ).join(Script, UserScript.script_id == Script.id)\
     .join(Product, Script.id == Product.script_id)\
     .join(Subscription, (Subscription.product_id == Product.id) & (Subscription.user_id == current_user.id))\
     .filter(UserScript.user_id == current_user.id)\
     .filter(Product.type == ProductType.SCRIPT)\
     .filter(Product.is_active == True)\
     .filter(Subscription.is_active == True)\
     .filter(Subscription.start_date <= datetime.utcnow())\
     .filter(Subscription.end_date >= datetime.utcnow())\
     .order_by(Product.name).all()

    scripts_with_logs = []
    for item in assigned_scripts_data:
        last_logs = RunLog.query.filter_by(user_script_id=item.userscript_id, user_id=current_user.id)\
                              .order_by(RunLog.executed_at.desc())\
                              .limit(3).all()

        # Ensure script_parameters_definition is a dict before json.dumps
        # If it's None or not a dict, default to an empty dict for json.dumps
        params_def = item.script_parameters_definition
        if not isinstance(params_def, dict):
            params_def = {}

        scripts_with_logs.append({
            'userscript_id': item.userscript_id,
            'product_name': item.product_name,
            'product_description': item.product_description,
            'script_id': item.script_id,
            'script_parameters_definition_json': json.dumps(params_def), # Ensure it's valid JSON
            'last_logs': last_logs,
            'subscription_end_date': item.subscription_end_date.strftime('%Y-%m-%d') if item.subscription_end_date else "N/A"
        })

    return render_template('client/assigned_scripts_list.html',
                           assigned_scripts=scripts_with_logs,
                           now=datetime.utcnow())

# --- End of Admin User Management (for regular admins, if any) ---


# Admin route to add a new script
@bp.route('/admin/add-script', methods=['GET', 'POST'])
@admin_required
def add_script_route():
    form = AddScriptForm()
    if form.validate_on_submit():
        try:
            script_name = form.name.data
            description = form.description.data
            parameters_str = form.parameters.data # Validator ensures JSON or empty
            price = form.price.data
            is_active = form.is_active.data
            file = form.script_file.data # FileStorage object

            # parameters_str will be an empty string if not provided, or valid JSON string
            parameters_json = json.loads(parameters_str) if parameters_str and parameters_str.strip() else {}

            # Securely save the file
            filename = secure_filename(file.filename)
            scripts_upload_folder = os.path.join(current_app.config['UPLOAD_FOLDER'], 'scripts')

            if not os.path.isabs(scripts_upload_folder):
                 scripts_upload_path = os.path.join(current_app.root_path, scripts_upload_folder)
            else:
                 scripts_upload_path = scripts_upload_folder

            os.makedirs(scripts_upload_path, exist_ok=True)

            file_path_for_db = os.path.join(scripts_upload_folder, filename) # Path to store in DB (relative)
            absolute_file_path = os.path.join(scripts_upload_path, filename) # Absolute path to save file

            if os.path.exists(absolute_file_path):
                base, ext = os.path.splitext(filename)
                new_filename = f"{base}_{int(datetime.now().timestamp())}{ext}"
                absolute_file_path = os.path.join(scripts_upload_path, new_filename)
                file_path_for_db = os.path.join(scripts_upload_folder, new_filename)

            file.save(absolute_file_path)

            new_script_obj = Script(
                name=script_name,
                description=description, # Consider if Script model needs its own description or uses Product's
                file_path=file_path_for_db,
                parameters=parameters_json,
                created_by=current_user.id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.session.add(new_script_obj)
            db.session.flush()

            new_product = Product(
                name=script_name,
                description=description,
                type=ProductType.SCRIPT,
                price=float(price),
                is_active=is_active,
                created_by=current_user.id,
                script_id=new_script_obj.id,
                created_at=datetime.utcnow(),
                last_modified=datetime.utcnow()
            )
            db.session.add(new_product)
            db.session.commit()

            flash(f'تمت إضافة السكربت "{script_name}" بنجاح!', 'success')
            # Redirect to admin dashboard or a page showing all scripts/products
            if current_user.is_super_admin:
                 return redirect(url_for('main.super_admin_dashboard'))
            return redirect(url_for('main.admin_dashboard'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding new script: {str(e)}")
            flash('حدث خطأ أثناء إضافة السكربت. الرجاء المحاولة مرة أخرى.', 'danger')
            # No redirect(request.url) here, will fall through to render_template with form errors

    # For GET requests or if form validation fails
    return render_template('admin/add_script.html', form=form)

# Client Ticket System Routes
@bp.route('/client/tickets/new', methods=['GET', 'POST'], endpoint='client_new_ticket')
@login_required
@client_required
def client_new_ticket():
    if request.method == 'POST':
        ticket_type = request.form.get('ticket_type')
        subject = request.form.get('subject')
        description = request.form.get('description')

        if not all([ticket_type, subject, description]):
            flash('جميع الحقول مطلوبة لإنشاء التذكرة.', 'danger')
            return redirect(url_for('main.client_new_ticket'))

        new_ticket = Ticket(
            user_id=current_user.id,
            ticket_type=ticket_type,
            subject=subject,
            description=description,
            status='open', # Default status
            priority='medium' # Default priority
            # created_at and updated_at have defaults in model
        )
        db.session.add(new_ticket)
        db.session.commit() # Commit to get new_ticket.id

        # Notify admin about the new ticket
        email_subject = f"تذكرة دعم جديدة #{new_ticket.id}: {new_ticket.subject}"
        email_body = f"""
        مرحباً أيها المشرف,

        تم فتح تذكرة دعم جديدة بواسطة المستخدم {current_user.username} (Email: {current_user.email}).

        بيانات التذكرة:
        - المعرف: {new_ticket.id}
        - النوع: {new_ticket.ticket_type}
        - الموضوع: {new_ticket.subject}
        - الوصف: {new_ticket.description}
        - الأولوية: {new_ticket.priority}

        يمكنك عرض التذكرة والرد عليها عبر الرابط التالي:
        {url_for('main.admin_view_ticket', ticket_id=new_ticket.id, _external=True)}
        """
        send_email(email_subject, email_body, ADMIN_EMAIL)

        flash('تم إنشاء تذكرة الدعم بنجاح!', 'success')
        return redirect(url_for('main.client_list_tickets'))

    return render_template('client/new_ticket.html')

@bp.route('/client/tickets', methods=['GET'], endpoint='client_list_tickets')
@login_required
@client_required
def client_list_tickets():
    tickets = Ticket.query.filter_by(user_id=current_user.id).order_by(Ticket.updated_at.desc()).all()
    return render_template('client/list_tickets.html', tickets=tickets)

# Admin Ticket System Routes
@bp.route('/admin/tickets', methods=['GET'], endpoint='admin_list_tickets')
@login_required
@admin_required
def admin_list_tickets():
    tickets = Ticket.query.order_by(Ticket.updated_at.desc()).all()
    # For displaying user email/name, the Ticket model has ticket.user relationship
    return render_template('admin/list_tickets.html', tickets=tickets)

@bp.route('/client/tickets/<int:ticket_id>', methods=['GET', 'POST'], endpoint='client_view_ticket')
@login_required
@client_required
def client_view_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if ticket.user_id != current_user.id:
        abort(403) # Not authorized to view this ticket

    if request.method == 'POST':
        message_body = request.form.get('message_body')
        if not message_body:
            flash('لا يمكن إرسال رسالة فارغة.', 'warning')
        else:
            new_message = TicketMessage(
                ticket_id=ticket.id,
                user_id=current_user.id,
                message_body=message_body
                # created_at has default
            )
            ticket.updated_at = datetime.utcnow() # Update ticket's last update time
            db.session.add(new_message)
            db.session.add(ticket) # Add ticket to session due to updated_at change
            db.session.commit()

            # Notify admin about the client's new message
            email_subject = f"رد من العميل على تذكرة الدعم #{ticket.id}: {ticket.subject}"
            email_body = f"""
            مرحباً أيها المشرف,

            قام العميل {current_user.username} (Email: {current_user.email}) بالرد على التذكرة "{ticket.subject}" (ID: {ticket.id}).

            الرسالة:
            {message_body}

            يمكنك عرض التذكرة والرد عليها عبر الرابط التالي:
            {url_for('main.admin_view_ticket', ticket_id=ticket.id, _external=True)}
            """
            send_email(email_subject, email_body, ADMIN_EMAIL)

            flash('تم إرسال رسالتك بنجاح.', 'success')
            return redirect(url_for('main.client_view_ticket', ticket_id=ticket.id))

    messages = TicketMessage.query.filter_by(ticket_id=ticket.id).order_by(TicketMessage.created_at.asc()).all()
    return render_template('client/view_ticket.html', ticket=ticket, messages=messages)

@bp.route('/admin/tickets/<int:ticket_id>', methods=['GET', 'POST'], endpoint='admin_view_ticket')
@login_required
@admin_required
def admin_view_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    # No user_id check here, as admin should be able to see all tickets

    if request.method == 'POST':
        message_body = request.form.get('message_body')
        new_status = request.form.get('new_status')
        new_priority = request.form.get('new_priority')

        action_taken = False # Flag to check if any action was performed

        if message_body:
            # Admin posts a message
            admin_message = TicketMessage(
                ticket_id=ticket.id,
                user_id=current_user.id, # Admin is the sender
                message_body=message_body
            )
            db.session.add(admin_message)
            action_taken = True

            # Notify client of admin's reply
            email_subject = f"تحديث على تذكرة الدعم #{ticket.id}: {ticket.subject}"
            email_body = f"""
            مرحباً {ticket.user.username},

            قام أحد المشرفين بالرد على تذكرتك "{ticket.subject}" (ID: {ticket.id}).

            الرسالة:
            {message_body}

            يمكنك عرض التذكرة والرد عليها عبر الرابط التالي:
            {url_for('main.client_view_ticket', ticket_id=ticket.id, _external=True)}

            مع تحيات فريق دعم إتمام,
            """
            send_email(email_subject, email_body, ticket.user.email)

        if new_status and new_status != ticket.status:
            ticket.status = new_status
            action_taken = True
            # TODO: Potentially send email notification about status change

        if new_priority and new_priority != ticket.priority:
            ticket.priority = new_priority
            action_taken = True
            # TODO: Potentially send email notification about priority change

        if action_taken:
            ticket.updated_at = datetime.utcnow()
            db.session.add(ticket) # Add ticket to session due to updated_at or status/priority change
            db.session.commit()
            flash('تم تحديث التذكرة بنجاح!', 'success')
        else:
            flash('لم يتم إجراء أي تغييرات على التذكرة.', 'info')

        return redirect(url_for('main.admin_view_ticket', ticket_id=ticket.id))

    messages = TicketMessage.query.filter_by(ticket_id=ticket.id).order_by(TicketMessage.created_at.asc()).all()
    available_statuses = ['open', 'in_progress', 'closed', 'resolved']
    available_priorities = ['low', 'medium', 'high', 'urgent']

    return render_template('admin/view_ticket.html',
                           ticket=ticket,
                           messages=messages,
                           available_statuses=available_statuses,
                           available_priorities=available_priorities)

@bp.route('/super-admin/user/<int:user_id>/toggle-status', methods=['POST'], endpoint='toggle_user_status')
@login_required
@super_admin_required
def toggle_user_status(user_id):
    user_to_toggle = User.query.get_or_404(user_id)

    if user_to_toggle.is_super_admin: # Cannot deactivate a super_admin
        flash('لا يمكن تغيير حالة حساب السوبر أدمن.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    if user_to_toggle.role == Role.ADMIN: # Admins should be handled by toggle_admin_status
        flash('لتغيير حالة حساب المشرف، يرجى استخدام المسار المخصص للمشرفين.', 'warning')
        return redirect(url_for('main.super_admin_dashboard'))

    user_to_toggle.is_active = not user_to_toggle.is_active
    db.session.commit()

    status_message = "مفعل" if user_to_toggle.is_active else "معطل"
    flash(f'تم تغيير حالة المستخدم {user_to_toggle.username} إلى {status_message} بنجاح.', 'success')
    return redirect(url_for('main.super_admin_dashboard'))

@bp.route('/super-admin/admin/<int:admin_id>/toggle-status', methods=['POST'], endpoint='toggle_admin_status')
@login_required
@super_admin_required
def toggle_admin_status(admin_id):
    admin_to_toggle = User.query.get_or_404(admin_id)

    if admin_to_toggle.role != Role.ADMIN:
        flash('هذا المستخدم ليس مشرفاً.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    if admin_to_toggle.id == current_user.id:
        flash('لا يمكن للسوبر أدمن تعطيل حسابه الخاص بهذه الطريقة.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    admin_to_toggle.is_active = not admin_to_toggle.is_active
    db.session.commit()

    status_message = "مفعل" if admin_to_toggle.is_active else "معطل"
    flash(f'تم تغيير حالة المشرف {admin_to_toggle.username} إلى {status_message} بنجاح.', 'success')
    return redirect(url_for('main.super_admin_dashboard'))

@bp.route('/admin/product/<int:product_id>/edit', methods=['GET', 'POST'], endpoint='edit_product')
@login_required
@admin_required # Using general admin_required, specific permission check inside
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)

    # Permission check: Super_admin can edit any. Admin needs MANAGE_SCRIPTS for script products.
    if not current_user.is_super_admin:
        if product.type == ProductType.SCRIPT and not current_user.has_permission(Permission.MANAGE_SCRIPTS):
            flash("ليس لديك الصلاحية لتعديل هذا المنتج (السكربت).", "danger")
            return redirect(url_for('main.admin_dashboard'))
        # Add elif for other product types and their specific permissions if needed
        # elif product.type == ProductType.EBOOK and not current_user.has_permission(Permission.MANAGE_EBOOKS):
        #     flash("You do not have permission to edit this ebook product.", "danger")
        #     return redirect(url_for('main.admin_dashboard'))
        elif product.type != ProductType.SCRIPT: # For now, only allow script editing by non-super-admins if they have MANAGE_SCRIPTS
             flash(f"ليس لديك صلاحية تعديل هذا النوع من المنتجات ('{product.type}').", "warning")
             return redirect(url_for('main.admin_dashboard'))


    form = EditProductForm(obj=product)
    # Populate script_parameters for script products on GET request
    if request.method == 'GET' and product.type == ProductType.SCRIPT:
        if product.script_definition and product.script_definition.parameters:
            try:
                form.script_parameters.data = json.dumps(product.script_definition.parameters, indent=2, ensure_ascii=False)
            except TypeError: # handle cases where parameters might not be serializable directly
                 form.script_parameters.data = "{}" # Default to empty JSON string
                 flash("لم يتمكن من تحميل معلمات السكربت بشكل صحيح، قد تكون غير مهيأة.", "warning")


    if form.validate_on_submit():
        product.name = form.name.data
        product.description = form.description.data
        product.price = form.price.data
        product.is_active = form.is_active.data
        product.last_modified_by = current_user.id
        product.last_modified = datetime.utcnow()

        if product.type == ProductType.SCRIPT and product.script_definition:
            if form.script_parameters.data and form.script_parameters.data.strip():
                try:
                    product.script_definition.parameters = json.loads(form.script_parameters.data)
                except json.JSONDecodeError:
                    # Error is handled by form validator, but we can flash again or log
                    flash("صيغة JSON لمعلمات السكربت غير صحيحة. لم يتم تحديث المعلمات.", "danger")
            else:
                product.script_definition.parameters = {} # Store empty JSON object

        try:
            db.session.commit()
            flash(f'تم تحديث المنتج "{product.name}" بنجاح!', 'success')
            if current_user.is_super_admin:
                return redirect(url_for('main.super_admin_dashboard'))
            return redirect(url_for('main.admin_dashboard'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating product {product.name}: {str(e)}")
            flash(f'خطأ أثناء تحديث المنتج: {str(e)}', 'danger')

    # If form validation failed, errors will be in form.errors and displayed in template
    return render_template('admin/edit_product.html', form=form, product=product, ProductType=ProductType, now=datetime.utcnow())

@bp.route('/admin/product/<int:product_id>/delete', methods=['POST'], endpoint='delete_product')
@login_required
@admin_required # Base protection, more specific checks inside
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)

    # Permission check: Super_admin can "delete" any.
    # Admin needs MANAGE_SCRIPTS for script products.
    can_delete = False
    if current_user.is_super_admin:
        can_delete = True
    elif product.type == ProductType.SCRIPT and current_user.has_permission(Permission.MANAGE_SCRIPTS):
        can_delete = True
    # Add elif for other product types and their specific "manage" permissions if they exist/are added
    # Example:
    # elif product.type == ProductType.EBOOK and current_user.has_permission(Permission.MANAGE_EBOOKS):
    #    can_delete = True

    if not can_delete:
        flash("ليس لديك الصلاحية لحذف هذا المنتج.", "danger")
        if current_user.is_super_admin:
             return redirect(url_for('main.super_admin_dashboard'))
        return redirect(url_for('main.admin_dashboard'))

    if not product.is_active:
        flash(f'المنتج "{product.name}" هو بالفعل غير نشط.', 'info')
    else:
        product.is_active = False
        product.last_modified_by = current_user.id
        product.last_modified = datetime.utcnow()
        try:
            db.session.commit()
            flash(f'تم تحديد المنتج "{product.name}" كـغير نشط وتم إخفاؤه من القوائم العامة.', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deactivating product {product.name}: {str(e)}")
            flash(f'خطأ في إلغاء تنشيط المنتج: {str(e)}', 'danger')

    if current_user.is_super_admin:
        return redirect(url_for('main.super_admin_dashboard'))
    return redirect(url_for('main.admin_dashboard'))

# User Management by Super Admin

@bp.route('/super-admin/user/add', methods=['POST'], endpoint='add_user_by_superadmin')
@login_required
@super_admin_required
def add_user_by_superadmin():
    full_name = request.form.get('full_name')
    username = request.form.get('username')
    email = request.form.get('email')
    phone = request.form.get('phone')
    password = request.form.get('password')
    confirm_password = request.form.get('confirm_password')

    if not all([full_name, username, email, password, confirm_password]):
        flash('جميع الحقول (الاسم الكامل، اسم المستخدم، البريد، كلمة المرور، تأكيد كلمة المرور) مطلوبة.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    if password != confirm_password:
        flash('كلمتا المرور غير متطابقتين.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    if len(password) < 6:
        flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    if User.query.filter_by(username=username).first():
        flash(f'اسم المستخدم "{username}" مسجل مسبقاً.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    if User.query.filter_by(email=email).first():
        flash(f'البريد الإلكتروني "{email}" مسجل مسبقاً.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    new_user = User(
        full_name=full_name,
        username=username,
        email=email,
        phone=phone,
        password=generate_password_hash(password),
        role=Role.USER,
        is_active=True # Or False, if manual activation is preferred
    )
    db.session.add(new_user)
    try:
        db.session.commit()
        flash(f'تم إضافة المستخدم {new_user.username} بنجاح.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error adding user by superadmin: {str(e)}")
        flash('حدث خطأ أثناء إضافة المستخدم.', 'danger')

    return redirect(url_for('main.super_admin_dashboard'))

@bp.route('/super-admin/admin/<int:admin_id>/edit-details', methods=['POST'], endpoint='superadmin_edit_admin_details')
@login_required
@super_admin_required
def superadmin_edit_admin_details(admin_id):
    admin_user = User.query.get_or_404(admin_id)
    if admin_user.role != Role.ADMIN:
        flash("This action can only be performed on Admin accounts.", "warning")
        return redirect(url_for('main.super_admin_dashboard'))

    new_full_name = request.form.get('full_name')
    new_email = request.form.get('email')
    new_phone = request.form.get('phone')
    original_email = admin_user.email

    if not new_full_name or len(new_full_name) < 3:
        flash("Full name is required and must be at least 3 characters.", "danger")
    elif not new_email: # Basic email presence check
        flash("Email is required.", "danger")
    else:
        admin_user.full_name = new_full_name
        admin_user.phone = new_phone # Assuming phone is optional or validated client-side

        email_changed = (new_email != original_email)
        email_valid_for_update = True # Assume true unless a problem is found
        if email_changed:
            existing_user_with_new_email = User.query.filter(User.email == new_email, User.id != admin_id).first()
            if existing_user_with_new_email:
                flash(f"Email '{new_email}' is already taken by another user.", "danger")
                email_valid_for_update = False
            else:
                admin_user.email = new_email

        if email_valid_for_update: # Only proceed if email (if changed) is valid
            if hasattr(admin_user, 'updated_at'): # Check if model has this attribute
                 admin_user.updated_at = datetime.utcnow()
            try:
                db.session.commit()
                flash(f"Admin '{admin_user.username}' details updated successfully.", "success")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error updating admin {admin_id} details: {str(e)}")
                flash("Error updating admin details. Please check logs.", "danger")
        # If email_valid_for_update is false, a flash message about email is already set.

    return redirect(url_for('main.super_admin_dashboard'))

@bp.route('/super-admin/admin/<int:admin_id>/edit-permissions', methods=['POST'], endpoint='superadmin_edit_admin_permissions')
@login_required
@super_admin_required
def superadmin_edit_admin_permissions(admin_id):
    admin_user = User.query.get_or_404(admin_id)
    if admin_user.role != Role.ADMIN:
        flash("Permissions can only be set for Admin accounts.", "warning")
        return redirect(url_for('main.super_admin_dashboard'))

    permissions_list = request.form.getlist('permissions[]')

    admin_user.set_permissions(permissions_list) # Assumes User model has set_permissions method
    if hasattr(admin_user, 'updated_at'): # Check if model has this attribute
        admin_user.updated_at = datetime.utcnow()

    try:
        db.session.commit()
        flash(f"Permissions for admin '{admin_user.username}' updated successfully.", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error updating admin {admin_id} permissions: {str(e)}")
        flash("Error updating admin permissions. Please check logs.", "danger")

    return redirect(url_for('main.super_admin_dashboard'))

@bp.route('/super-admin/admin/<int:admin_id>/reset-password', methods=['POST'], endpoint='superadmin_reset_admin_password')
@login_required
@super_admin_required
def superadmin_reset_admin_password(admin_id):
    admin_user = User.query.get_or_404(admin_id)
    if admin_user.role != Role.ADMIN:
        flash("Password can only be reset for Admin accounts.", "warning")
        return redirect(url_for('main.super_admin_dashboard'))

    new_password = request.form.get('password')

    if not new_password or len(new_password) < 6: # Basic validation
        flash("New password must be at least 6 characters long.", "danger")
    else:
        admin_user.password = generate_password_hash(new_password) # Ensure generate_password_hash is imported
        if hasattr(admin_user, 'updated_at'): # Check if model has this attribute
            admin_user.updated_at = datetime.utcnow()
        try:
            db.session.commit()
            flash(f"Password for admin '{admin_user.username}' has been reset successfully.", "success")
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error resetting admin {admin_id} password: {str(e)}")
            flash("Error resetting admin password. Please check logs.", "danger")

    return redirect(url_for('main.super_admin_dashboard'))


@bp.route('/super-admin/user/<int:user_id>/edit', methods=['POST'], endpoint='edit_user_by_superadmin')
@login_required
@super_admin_required
def edit_user_by_superadmin(user_id):
    user_to_edit = User.query.get_or_404(user_id)

    if user_to_edit.role != Role.USER:
        flash('يمكن تعديل حسابات المستخدمين العاديين فقط من هنا.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    new_full_name = request.form.get('full_name')
    new_email = request.form.get('email')
    new_phone = request.form.get('phone')

    if not new_full_name or len(new_full_name) < 3:
        flash('الاسم الكامل مطلوب ويجب أن يكون 3 أحرف على الأقل.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    if not new_email:
        flash('البريد الإلكتروني مطلوب.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    existing_user_with_email = User.query.filter(User.email == new_email, User.id != user_id).first()
    if existing_user_with_email:
        flash(f'البريد الإلكتروني "{new_email}" مستخدم بالفعل.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    user_to_edit.full_name = new_full_name
    user_to_edit.email = new_email
    user_to_edit.phone = new_phone

    try:
        db.session.commit()
        flash(f'تم تحديث بيانات المستخدم {user_to_edit.username} بنجاح.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error editing user {user_to_edit.username}: {str(e)}")
        flash('حدث خطأ أثناء تحديث بيانات المستخدم.', 'danger')

    return redirect(url_for('main.super_admin_dashboard'))

@bp.route('/super-admin/user/<int:user_id>/reset-password', methods=['POST'], endpoint='reset_user_password_by_superadmin')
@login_required
@super_admin_required
def reset_user_password_by_superadmin(user_id):
    user_to_reset = User.query.get_or_404(user_id)

    if user_to_reset.role != Role.USER:
        flash('يمكن إعادة تعيين كلمة مرور المستخدمين العاديين فقط.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    new_password = request.form.get('password')
    if not new_password or len(new_password) < 6:
        flash('كلمة المرور يجب أن تكون 6 أحرف على الأقل.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    user_to_reset.password = generate_password_hash(new_password)
    try:
        db.session.commit()
        flash(f'تم إعادة تعيين كلمة مرور المستخدم {user_to_reset.username} بنجاح.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error resetting user password for {user_to_reset.username}: {str(e)}")
        flash('حدث خطأ أثناء إعادة تعيين كلمة المرور.', 'danger')

    return redirect(url_for('main.super_admin_dashboard'))

@bp.route('/super-admin/user/<int:user_id>/assign-scripts', methods=['POST'], endpoint='assign_scripts_to_user_by_superadmin')
@login_required
@super_admin_required
def assign_scripts_to_user_by_superadmin(user_id):
    user_to_assign = User.query.get_or_404(user_id)

    if user_to_assign.role != Role.USER:
        flash('يمكن تخصيص السكربتات للمستخدمين العاديين فقط.', 'danger')
        return redirect(url_for('main.super_admin_dashboard'))

    script_ids = request.form.getlist('scripts[]')

    # Clear existing script associations for this user
    UserScript.query.filter_by(user_id=user_id).delete()

    for script_id_str in script_ids:
        try:
            script_id = int(script_id_str)
            script = Script.query.get(script_id)
            if script:
                user_script = UserScript(
                    user_id=user_id,
                    script_id=script.id,
                    assigned_by=current_user.id,
                    assigned_at=datetime.utcnow()
                    # config_data can be set here if there's a way to input it, otherwise defaults to {}
                )
                db.session.add(user_script)
            else:
                flash(f'لم يتم العثور على السكربت بالمعرف {script_id_str}.', 'warning')
        except ValueError:
            flash(f'معرف السكربت غير صالح: {script_id_str}.', 'warning')

    try:
        db.session.commit()
        flash(f'تم تحديث السكربتات المخصصة للمستخدم {user_to_assign.username} بنجاح.', 'success')
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error assigning scripts to user {user_to_assign.username}: {str(e)}")
        flash('حدث خطأ أثناء تخصيص السكربتات.', 'danger')

    return redirect(url_for('main.super_admin_dashboard'))

@bp.route('/client/deals/add', methods=['GET', 'POST'], endpoint='client_add_deal')
@login_required
@client_required
def client_add_deal():
    form = DealForm()
    # إعداد قائمة العقارات المتاحة للمستخدم الحالي
    form.property_id.choices = [
        (prop.id, prop.title) for prop in Property.query.filter_by(user_id=current_user.id).order_by(Property.title).all()
    ]
    form.property_id.choices.insert(0, (0, '-- اختر عقاراً --'))

    if form.validate_on_submit():
        selected_property_id = form.property_id.data
        if not selected_property_id or selected_property_id == 0:
            flash("يرجى اختيار عقار صحيح من القائمة.", "danger")
            return render_template('client/add_deal.html', form=form, title="إضافة صفقة جديدة", now=datetime.utcnow())
        prop_check = Property.query.filter_by(id=selected_property_id, user_id=current_user.id).first()
        if not prop_check:
            flash("العقار المحدد غير صالح.", "danger")
            return render_template('client/add_deal.html', form=form, title="إضافة صفقة جديدة", now=datetime.utcnow())

        new_deal = Deal(
            property_id=selected_property_id,
            user_id=current_user.id, # Broker's ID
            client_name=form.client_name.data,
            stage=form.stage.data,
            notes=form.notes.data
        )
        try:
            db.session.add(new_deal)
            db.session.commit()
            flash(f'تمت إضافة الصفقة للعقار "{prop_check.title}" مع العميل "{new_deal.client_name}" بنجاح!', 'success')
            return redirect(url_for('main.client_deal_tracker'))
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error adding deal: {str(e)}")
            flash('حدث خطأ أثناء إضافة الصفقة. يرجى المحاولة مرة أخرى.', 'danger')
    elif form.is_submitted():
        flash('الرجاء تصحيح الأخطاء في النموذج.', 'danger')

    return render_template('client/add_deal.html', form=form, title="إضافة صفقة جديدة", now=datetime.utcnow())

@bp.route('/super-admin/tickets', methods=['GET'], endpoint='super_admin_list_tickets')
@login_required
@super_admin_required
def super_admin_list_tickets():
    status_filter = request.args.get('status', None)
    priority_filter = request.args.get('priority', None)
    type_filter = request.args.get('type', None)
    search_query = request.args.get('q', '').strip()

    query = Ticket.query
    if status_filter and status_filter != 'all':
        query = query.filter(Ticket.status == status_filter)
    if priority_filter and priority_filter != 'all':
        query = query.filter(Ticket.priority == priority_filter)
    if type_filter and type_filter != 'all':
        query = query.filter(Ticket.ticket_type == type_filter)
    if search_query:
        like_pattern = f"%{search_query}%"
        query = query.filter(
            (Ticket.subject.ilike(like_pattern)) |
            (Ticket.description.ilike(like_pattern))
        )
    tickets = query.order_by(Ticket.updated_at.desc()).all()
    available_statuses = ['all', 'open', 'in_progress', 'closed', 'resolved']
    available_priorities = ['all', 'low', 'medium', 'high', 'urgent']
    available_types = ['all', 'technical', 'billing', 'general_inquiry']
    return render_template('super_admin_list_tickets.html', tickets=tickets, available_statuses=available_statuses, available_priorities=available_priorities, available_types=available_types, status_filter=status_filter, priority_filter=priority_filter, type_filter=type_filter, search_query=search_query)

@bp.route('/super-admin/tickets/<int:ticket_id>', methods=['GET', 'POST'], endpoint='super_admin_view_ticket')
@login_required
@super_admin_required
def super_admin_view_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    if request.method == 'POST':
        message_body = request.form.get('message_body')
        new_status = request.form.get('new_status')
        new_priority = request.form.get('new_priority')
        action_taken = False
        if message_body:
            admin_message = TicketMessage(
                ticket_id=ticket.id,
                user_id=current_user.id,
                message_body=message_body
            )
            db.session.add(admin_message)
            action_taken = True
        if new_status and new_status != ticket.status:
            ticket.status = new_status
            action_taken = True
        if new_priority and new_priority != ticket.priority:
            ticket.priority = new_priority
            action_taken = True
        if action_taken:
            ticket.updated_at = datetime.utcnow()
            db.session.add(ticket)
            db.session.commit()
            flash('تم تحديث التذكرة بنجاح!', 'success')
        else:
            flash('لم يتم إجراء أي تغييرات على التذكرة.', 'info')
        return redirect(url_for('main.super_admin_view_ticket', ticket_id=ticket.id))
    messages = TicketMessage.query.filter_by(ticket_id=ticket.id).order_by(TicketMessage.created_at.asc()).all()
    available_statuses = ['open', 'in_progress', 'closed', 'resolved']
    available_priorities = ['low', 'medium', 'high', 'urgent']
    return render_template('super_admin_view_ticket.html', ticket=ticket, messages=messages, available_statuses=available_statuses, available_priorities=available_priorities)

# --- CLI Commands ---
@bp.cli.command("deactivate-expired-subscriptions")
def deactivate_expired_subscriptions_command():
    """
    Deactivates subscriptions that have passed their end_date.
    """
    try:
        now = datetime.utcnow()
        expired_subscriptions = Subscription.query.filter(
            Subscription.end_date < now,
            Subscription.is_active == True
        ).all()

        if not expired_subscriptions:
            print("No expired subscriptions found to deactivate.")
            return

        count = 0
        for sub in expired_subscriptions:
            sub.is_active = False
            count += 1

        db.session.commit()
        print(f"Deactivated {count} expired subscriptions.")

    except Exception as e:
        db.session.rollback()
        print(f"Error deactivating subscriptions: {str(e)}")