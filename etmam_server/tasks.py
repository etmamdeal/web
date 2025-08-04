"""
تنفيذ المهام غير المتزامنة في النظام
------------------------------------

يحتوي هذا الملف على تعريفات المهام التي تنفذ في الخلفية باستخدام Celery
"""

from celery import Celery
import smtplib
from email.mime.text import MIMEText
from flask import current_app

# إنشاء تطبيق Celery
celery = Celery('tasks', broker='redis://localhost:6379/0')

@celery.task(bind=True, max_retries=3)
def send_email_task(self, subject, body, to_email, config=None):
    """
    مهمة إرسال البريد الإلكتروني بشكل غير متزامن
    
    المعلمات:
        subject: عنوان البريد
        body: محتوى البريد
        to_email: البريد المستلم
        config: إعدادات SMTP (اختياري)
    """
    # The config should be loaded from the application context
    app = current_app._get_current_object()
    try:
        # Use Flask-Mail for sending emails, which is configured from the app
        msg = Message(subject, recipients=[to_email], body=body)
        mail.send(msg)
        return True
        
    except Exception as e:
        # إعادة المحاولة في حالة الفشل
        retry_in = 60 * (self.request.retries + 1)  # زيادة وقت الانتظار مع كل محاولة
        self.retry(exc=e, countdown=retry_in) 