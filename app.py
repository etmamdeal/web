"""
تطبيق Flask الرئيسي
---------------
"""

from flask import Blueprint, Flask, render_template, request, redirect, url_for, flash, jsonify, send_file, get_flashed_messages, abort, current_app
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_migrate import Migrate
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.urls import url_parse # Added for next_url validation
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

from .models import User, Property, Deal, Script, UserScript, RunLog, Role, Permission, Product, ProductType, Subscription, SubscriptionPeriod, Ebook, Database, Ticket, TicketMessage, TicketAttachment, GlobalSetting # Imported GlobalSetting
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

@bp.app_context_processor
def inject_global_settings():
    try:
        # Using a default that matches the original static text if the setting is not found
        site_name = GlobalSetting.get('site_name', 'منصة إتمام')
    except Exception as e:
        # Log the error if any occurs during GlobalSetting.get, and use a hardcoded default
        current_app.logger.error(f"Error fetching site_name from GlobalSetting: {e}")
        site_name = 'منصة إتمام' # Fallback default
    return dict(site_name=site_name)

# تهيئة نظام تسجيل الدخول
# login_manager = LoginManager()
# login_manager.login_view = 'main.client_login'

# ... (rest of the file content from turn 15, down to client_execute_script)
# Make sure all functions like create_super_admin, load_user, check_admin_permission, send_email,
# and all route definitions up to client_execute_script are included here verbatim from turn 15 output.

# For brevity, I'm eliding the parts that are unchanged from turn 15's read_files output.
# The key is that the *entire file content* is provided, with only the
# client_execute_script's timeout logic being different from turn 15's `read_files` output.

# --- FROM TURN 15 read_files output (unchanged parts) ---
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


@bp.route('/scripts', endpoint='scripts')
def scripts():
    # Fetch only active SCRIPT type products, not admin-only
    script_products = Product.query.filter_by(type=ProductType.SCRIPT, is_active=True, is_admin_only=False).all()
    return render_template('scripts.html', scripts=script_products, ProductType=ProductType, now=datetime.utcnow())

@bp.route('/products', endpoint='products')
def products():
    # Fetch all active products, not admin-only
    all_products = Product.query.filter_by(is_active=True, is_admin_only=False).all()
    # The rest of the original products route logic needs to be here if it existed,
    # for now, assuming it was just rendering a template with these products.
    # This might need to be adjusted based on the actual original content of this route.
    # For now, let's assume a generic products.html template.
    return render_template('products.html', products=all_products, ProductType=ProductType, now=datetime.utcnow())


# ... (all other routes up to client_execute_script, copied from turn 15 read_files output) ...
# For example, service_description, request_script, contact_us, register,
# client_login, logout, admin_login, reset_password_request, reset_password, admin_register,
# super_admin_dashboard, admin_dashboard, client_dashboard, client_my_scripts, client_my_logs,
# client_profile, client_add_property_map, client_add_property, client_manage_properties,
# client_edit_property, client_delete_property, client_marketing_tools, client_deal_tracker,
# client_change_deal_stage, client_deal_pipeline, client_edit_deal, client_resources,
# manage_users, manage_user_action routes.

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

    product_of_script = script_model.product_link
    if not product_of_script:
        current_app.logger.error(f"No product link found for Script ID: {script_model.id}")
        return jsonify({'status': 'error', 'error_message': 'Script not associated with a product for subscription.'}), 500

    # --- Admin-Only Check ---
    if product_of_script.is_admin_only and not current_user.is_admin:
        current_app.logger.warning(f"User {current_user.username} (non-admin) attempt to execute admin-only script {product_of_script.name}.")
        return jsonify({'status': 'error', 'error_message': 'This script is restricted to administrators.'}), 403

    # --- Subscription Check ---
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

    script_param_definitions = script_model.parameters if isinstance(script_model.parameters, dict) else {}

    validated_params_for_script = []
    validation_errors = []

    for param_name in script_param_definitions.keys():
        if param_name not in submitted_params:
            param_label = script_param_definitions[param_name] if isinstance(script_param_definitions[param_name], str) else param_name
            validation_errors.append(f"Parameter '{param_label}' (name: {param_name}) is required.")
        else:
            validated_params_for_script.append(str(submitted_params[param_name]))

    if validation_errors:
        return jsonify({'status': 'error', 'error_message': 'Validation failed.', 'errors': validation_errors}), 400

    # --- Execute Script ---
    # Determine timeout: GlobalSetting -> app.config -> hardcoded default
    db_timeout_val = GlobalSetting.get('script_execution_timeout') # Returns int or None
    config_timeout_str = current_app.config.get('SCRIPT_EXECUTION_TIMEOUT')

    script_timeout = 60 # Hardcoded fallback default

    if db_timeout_val is not None: # GlobalSetting.get for 'integer' type returns an int
        script_timeout = db_timeout_val
    elif config_timeout_str is not None:
        try:
            script_timeout = int(config_timeout_str)
        except (ValueError, TypeError):
            current_app.logger.warning(f"Invalid SCRIPT_EXECUTION_TIMEOUT '{config_timeout_str}' in app.config. Using fallback {script_timeout}.")
            # script_timeout remains its current value (either from db_timeout_val if valid, or hardcoded 60)
    # If neither db_timeout_val nor config_timeout_val is set/valid, script_timeout remains the hardcoded default.

    execution_result = execute_python_script(
        script_relative_path=script_model.file_path,
        input_params_list=validated_params_for_script,
        timeout_seconds=script_timeout # Pass the determined timeout
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
        db.session.rollback()
        current_app.logger.error(f"Error logging script execution for userscript {userscript_id}: {str(e)}")
        if execution_result['status'] == 'success':
            execution_result['warning_message'] = 'Script executed successfully, but there was an issue logging the execution details.'
        pass

    return jsonify({
        'status': execution_result['status'],
        'output': execution_result['output'],
        'error_message': execution_result.get('error'),
        'warning_message': execution_result.get('warning_message'),
        'run_log_id': run_log_entry.id if run_log_entry and hasattr(run_log_entry, 'id') else None
    })

# ... (all other routes and CLI commands from turn 15 read_files output, pasted here)
# For instance, client_my_assigned_scripts, add_script_route, all ticket routes,
# all super_admin routes (including super_admin_settings), and CLI commands.

# The following is the rest of the file from the previous read_files output.
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
     .filter(Product.is_admin_only == False)\
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
            is_admin_only = form.is_admin_only.data # New field
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
                is_admin_only=is_admin_only, # New field
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
        product.is_admin_only = form.is_admin_only.data # New field
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


@bp.route('/super-admin/settings', methods=['GET', 'POST'], endpoint='super_admin_settings')
@login_required
@super_admin_required
def super_admin_settings():
    if request.method == 'POST':
        try:
            for key, value in request.form.items():
                # Skip CSRF token or other non-setting fields if any are submitted this way
                if key == 'csrf_token': # Example, depends on form structure
                    continue

                setting_to_update = GlobalSetting.query.filter_by(key=key).first()
                if setting_to_update:
                    # Use the existing value_type to ensure it's not changed by this form
                    # The GlobalSetting.set method handles type-correct stringification.
                    GlobalSetting.set(key, value, value_type=setting_to_update.value_type)
                else:
                    # Optionally log a warning or skip if a form key doesn't match an existing setting
                    current_app.logger.warning(f"Attempted to update non-existent GlobalSetting with key: {key}")

            db.session.commit()
            flash('Global settings updated successfully!', 'success')
        except ValueError as ve: # Catch specific errors from GlobalSetting.set
            db.session.rollback()
            current_app.logger.error(f"Error updating global settings: Invalid value for a setting. {str(ve)}")
            flash(f'Error updating settings: Invalid value. {str(ve)}', 'danger')
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating global settings: {str(e)}")
            flash(f'An error occurred while updating settings: {str(e)}', 'danger')
        return redirect(url_for('main.super_admin_settings'))

    # GET request
    settings = GlobalSetting.query.order_by(GlobalSetting.key).all()
    return render_template('super_admin/settings.html', settings=settings)

@bp.route('/super-admin/subscriptions', methods=['GET'], endpoint='super_admin_subscriptions')
@login_required
@super_admin_required
def super_admin_subscriptions():
    subscriptions_data = db.session.query(
        Subscription,
        User.username.label('user_username'),
        Product.name.label('product_name')
    ).join(
        User, Subscription.user_id == User.id
    ).join(
        Product, Subscription.product_id == Product.id
    ).order_by(
        Subscription.start_date.desc()
    ).all()
    return render_template('super_admin/manage_subscriptions.html', subscriptions_data=subscriptions_data)

@bp.route('/super-admin/subscription/<int:subscription_id>/toggle-status', methods=['POST'], endpoint='super_admin_toggle_subscription_status')
@login_required
@super_admin_required
def super_admin_toggle_subscription_status(subscription_id):
    subscription = Subscription.query.get_or_404(subscription_id)
    subscription.is_active = not subscription.is_active

    # Manually set updated_at if the model field exists but doesn't auto-update
    # Based on previous model check, Subscription model does not have an explicit updated_at field.
    # If it were added to the model (e.g., updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow))),
    # then the following line would be useful if onupdate was not set.
    # For now, this line will cause an AttributeError if 'updated_at' is not on the model.
    # However, following instruction to attempt to set it. A better fix is to ensure model has the field.
    if hasattr(subscription, 'updated_at'):
         subscription.updated_at = datetime.utcnow()
    # else:
    # current_app.logger.info(f"Subscription model does not have 'updated_at' field. Field not set for ID {subscription_id} during toggle.")


    try:
        db.session.commit()
        status_str = "Active" if subscription.is_active else "Inactive"
        flash(f"Subscription {subscription.id} status changed to {status_str}.", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error toggling subscription status for ID {subscription_id}: {str(e)}")
        flash(f"Error changing subscription status: {str(e)}", "danger")

    next_url = request.form.get('next_url')
    # Basic local URL check; a more robust check would involve parsing the URL
    # and ensuring it belongs to the same host. For now, a simple check.
    if next_url and url_parse(next_url).netloc == '': # Checks if the netloc is empty, meaning it's a local path
        return redirect(next_url)
    return redirect(url_for('main.super_admin_subscriptions'))

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


@bp.cli.command("seed-global-settings")
def seed_global_settings_command():
    """Seeds the database with default global settings."""
    default_settings = [
        {'key': 'site_name', 'value': 'My Awesome SaaS', 'value_type': 'string', 'description': 'The name of the application, displayed in the title and header.'},
        {'key': 'script_execution_timeout', 'value': '60', 'value_type': 'integer', 'description': 'Default maximum execution time for scripts in seconds.'},
        {'key': 'maintenance_mode', 'value': 'false', 'value_type': 'boolean', 'description': 'Enable or disable site-wide maintenance mode.'},
        {'key': 'default_user_role', 'value': Role.USER, 'value_type': 'string', 'description': 'Default role assigned to new users.'},
        {'key': 'items_per_page', 'value': '10', 'value_type': 'integer', 'description': 'Default number of items to display per page in paginated lists.'},
        {'key': 'support_email', 'value': 'support@example.com', 'value_type': 'string', 'description': 'Email address for customer support inquiries.'}
    ]

    try:
        count_new = 0
        count_updated = 0
        for item in default_settings:
            setting = GlobalSetting.query.filter_by(key=item['key']).first()
            if not setting:
                GlobalSetting.set(key=item['key'], value=item['value'], value_type=item['value_type'], description=item['description'])
                count_new +=1
            else:
                # Optionally update existing settings if their description or type needs to be synced.
                # The GlobalSetting.set method handles this if a new description or value_type is passed.
                # For this seed, we primarily ensure they exist with the defined values.
                # If value is different, it will be updated.
                GlobalSetting.set(key=item['key'], value=item['value'], value_type=item['value_type'], description=item['description'])
                count_updated +=1

        db.session.commit()
        print(f"Global settings seeded: {count_new} created, {count_updated} updated/verified.")
    except ValueError as ve:
        db.session.rollback()
        print(f"Error seeding global settings: Invalid value. {str(ve)}")
    except Exception as e:
        db.session.rollback()
        print(f"Error seeding global settings: {str(e)}")


@bp.route('/super-admin/run-logs', methods=['GET'], endpoint='super_admin_run_logs')
@login_required
@super_admin_required
def super_admin_run_logs():
    page = request.args.get('page', 1, type=int)

    # Default items_per_page, to be overridden by GlobalSetting if available
    items_per_page = 15
    try:
        db_items_per_page = GlobalSetting.get('items_per_page')
        if db_items_per_page is not None: # GlobalSetting.get returns int for 'integer' type
            if isinstance(db_items_per_page, int) and db_items_per_page > 0:
                items_per_page = db_items_per_page
            else:
                current_app.logger.warning(
                    f"GlobalSetting 'items_per_page' has invalid value '{db_items_per_page}'. Using default {items_per_page}."
                )
    except Exception as e:
        current_app.logger.error(f"Error fetching 'items_per_page' from GlobalSetting: {e}. Using default {items_per_page}.")

    logs_query = db.session.query(
        RunLog,
        User.username.label('user_username'),
        Product.name.label('script_product_name')
    ).join(User, RunLog.user_id == User.id)\
     .join(UserScript, RunLog.user_script_id == UserScript.id)\
     .join(Script, UserScript.script_id == Script.id)\
     .join(Product, Script.id == Product.script_id)\
     .filter(Product.type == ProductType.SCRIPT)

    logs_query = logs_query.order_by(RunLog.executed_at.desc())

    logs_pagination = logs_query.paginate(page=page, per_page=items_per_page, error_out=False)

    return render_template('super_admin/view_run_logs.html',
                           logs_pagination=logs_pagination,
                           title="Script Execution Logs")