import os
import smtplib
from email.mime.text import MIMEText
from functools import wraps
from flask import current_app, flash, redirect, url_for
from flask_login import current_user
from .tasks import send_email_task

def send_email(subject, body, to_email=None):
    """إرسال بريد إلكتروني باستخدام نظام المهام غير المتزامنة"""
    try:
        # إرسال المهمة إلى Celery
        send_email_task.delay(
            subject=subject,
            body=body,
            to_email=to_email or current_app.config['ADMIN_EMAIL'],
            config={
                'SMTP_SERVER': current_app.config['SMTP_SERVER'],
                'SMTP_PORT': current_app.config['SMTP_PORT'],
                'SMTP_USERNAME': current_app.config['SMTP_USERNAME'],
                'SMTP_PASSWORD': current_app.config['SMTP_PASSWORD']
            }
        )
        return True
    except Exception as e:
        print(f"خطأ في جدولة مهمة البريد: {str(e)}")
        return False

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
    """التحقق من محتوى السكربت والتأكد من أنه آمن"""
    # قائمة الكلمات المحظورة التي قد تشكل خطراً
    forbidden_words = [
        'os.system', 'subprocess', 'eval', 'exec',
        'import os', 'import subprocess', '__import__',
        'open(', 'file.', 'socket.', 'sys.'
    ]
    
    content_lower = content.lower()
    for word in forbidden_words:
        if word.lower() in content_lower:
            return False, f"الكلمة المحظورة: {word}"
    
    return True, "السكربت آمن"