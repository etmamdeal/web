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
    try:
        # استخدام الإعدادات المقدمة أو الافتراضية
        smtp_config = config or {
            'SMTP_SERVER': 'smtppro.zoho.sa',
            'SMTP_PORT': 465,
            'SMTP_USERNAME': 'ai_agents@etmamdeal.com',
            'SMTP_PASSWORD': 'TKxLhzQ2zRtp'
        }
        
        msg = MIMEText(body, 'plain', 'utf-8')
        msg['Subject'] = subject
        msg['From'] = smtp_config['SMTP_USERNAME']
        msg['To'] = to_email
        
        with smtplib.SMTP_SSL(smtp_config['SMTP_SERVER'], 
                             smtp_config['SMTP_PORT']) as server:
            server.login(smtp_config['SMTP_USERNAME'],
                        smtp_config['SMTP_PASSWORD'])
            server.send_message(msg)
            
        return True
        
    except Exception as e:
        # إعادة المحاولة في حالة الفشل
        retry_in = 60 * (self.request.retries + 1)  # زيادة وقت الانتظار مع كل محاولة
        self.retry(exc=e, countdown=retry_in) 