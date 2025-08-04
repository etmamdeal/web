import os
import smtplib
from email.mime.text import MIMEText
from functools import wraps
from flask import current_app, flash, redirect, url_for
from flask_login import current_user
from .tasks import send_email_task
import subprocess
import sys
from flask_mail import Message
from .extensions import mail  # Assuming you have a mail extension
import threading

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            app.logger.error(f"Failed to send email: {e}")

def send_email(subject, recipients, text_body, html_body):
    """Sends an email by printing it to the console for development."""
    print("--- SENDING EMAIL ---")
    print(f"Subject: {subject}")
    print(f"Recipients: {recipients}")
    print("--- TEXT BODY ---")
    print(text_body)
    print("--- HTML BODY ---")
    print(html_body)
    print("--- END EMAIL ---")

    # Original Flask-Mail logic commented out for development
    # app = current_app._get_current_object()
    # msg = Message(subject, recipients=recipients)
    # msg.body = text_body
    # msg.html = html_body
    # # Send email in a background thread to avoid blocking
    # thr = threading.Thread(target=send_async_email, args=[app, msg])
    # thr.start()

def execute_python_script(script_path, *args):
    """
    Executes a Python script in a separate process and returns its output.
    """
    try:
        # Ensure the python executable used is the same one running the app
        python_executable = sys.executable
        result = subprocess.run(
            [python_executable, script_path, *args],
            capture_output=True,
            text=True,
            check=True,  # This will raise CalledProcessError if the script returns a non-zero exit code
            encoding='utf-8' # Specify encoding for cross-platform compatibility
        )
        return result.stdout
    except FileNotFoundError:
        return f"Error: Script not found at {script_path}"
    except subprocess.CalledProcessError as e:
        # Log the detailed error from stderr
        error_message = f"Error executing script: {script_path}\n"
        error_message += f"Exit Code: {e.returncode}\n"
        error_message += f"Output (stdout):\n{e.stdout}\n"
        error_message += f"Error (stderr):\n{e.stderr}\n"
        # Depending on your logging setup, you might want to log this
        # For now, returning it to be displayed or logged by the caller
        return error_message
    except Exception as e:
        return f"An unexpected error occurred: {str(e)}"

def admin_required(f):
    """مصمم للتحقق من صلاحيات المشرف"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash("غير مصرح لك بالوصول إلى هذه الصفحة")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename):
    """التحقق من امتداد الملف المسموح به"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

def create_script_folder(user_id):
    """إنشاء مجلد للمستخدم لتخزين السكربتات"""
    folder_path = os.path.join(current_app.config['UPLOAD_FOLDER'], str(user_id))
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    return folder_path

def format_datetime(value, format='%Y-%m-%d %H:%M:%S'):
    """تنسيق التاريخ والوقت"""
    if value is None:
        return ""
    return value.strftime(format)

def get_script_path(user_id, script_name):
    """الحصول على المسار الكامل للسكربت"""
    return os.path.join(create_script_folder(user_id), script_name)

def validate_script_content(content):
    """التحقق من محتوى السكربت والتأكد من أنه آمن - نسخة محسنة."""
    # قائمة سوداء موسعة للكلمات والوحدات النمطية الخطرة
    forbidden_keywords = [
        # وحدات خطرة
        'os', 'subprocess', 'sys', 'shutil', 'socket', 'urllib', 'requests', 'http', 'ftplib', 'glob',
        # دوال خطرة
        'eval', 'exec', 'execfile', 'compile', 'open', 'input', '__import__',
        # الوصول للملفات
        'file', 'read', 'write', 'load', 'dump',
        # كلمات مفتاحية قد تدل على عمليات غير مرغوبة
        'system', 'popen', 'spawn', 'fork', 'kill', 'signal'
    ]
    
    # استخدام تحليل الشجرة النحوية المجردة (AST) لتحديد الاستيرادات والوصول للخصائص
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            # منع استيراد وحدات خطرة
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name in forbidden_keywords:
                        return False, f"استيراد الوحدة النمطية المحظورة: {alias.name}"
            # منع الوصول إلى خصائص خطرة (مثل os.system)
            if isinstance(node, ast.Attribute):
                if node.attr in forbidden_keywords:
                     return False, f"الوصول إلى الخاصية المحظورة: {node.attr}"
            # منع استدعاء دوال خطرة
            if isinstance(node, ast.Call) and hasattr(node.func, 'id') and node.func.id in forbidden_keywords:
                return False, f"استدعاء الدالة المحظورة: {node.func.id}"
    except SyntaxError as e:
        return False, f"خطأ في بناء الجملة: {e}"

    # فحص بسيط للمحتوى كخط دفاع أخير
    content_lower = content.lower()
    for keyword in forbidden_keywords:
        # البحث عن الكلمة ككلمة كاملة أو كجزء من استدعاء (مثل os.)
        if f'{keyword}(' in content_lower or f'{keyword}.' in content_lower:
            return False, f"تم العثور على الكلمة الرئيسية المحظورة: {keyword}"
            
    return True, "السكربت آمن"