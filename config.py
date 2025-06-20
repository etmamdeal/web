"""
ملف التكوين الرئيسي للتطبيق
---------------------------

يحتوي على جميع إعدادات التطبيق مثل:
- إعدادات قاعدة البيانات
- مفاتيح الأمان
- إعدادات التسجيل
- خيارات التحسين
"""

import os
from datetime import timedelta

class Config:
    # إعدادات Celery
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL') or 'redis://localhost:6379/0'
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND') or 'redis://localhost:6379/0'
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'
    CELERY_ACCEPT_CONTENT = ['json']
    CELERY_TIMEZONE = 'Asia/Riyadh'
    CELERY_ENABLE_UTC = True
    
    # إعدادات أساسية
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'مفتاح-سري-افتراضي-للتطوير'
    FLASK_APP = 'app.py'
    
    # إعدادات قاعدة البيانات
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///database.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True  # تمكين تسجيل الاستعلامات للتحسين
    SQLALCHEMY_ECHO = False  # تعطيل طباعة الاستعلامات في وضع الإنتاج
    
    # تحسين الأداء
    DATABASE_QUERY_TIMEOUT = 0.5  # الحد الأقصى لوقت الاستعلام (بالثواني)
    SLOW_DB_QUERY_TIME = 0.5  # وقت الاستعلام البطيء (للتسجيل)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # الحد الأقصى لحجم الملف (16 ميجابايت)
    
    # إعدادات الجلسة
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # إعدادات التسجيل
    LOG_TO_STDOUT = os.environ.get('LOG_TO_STDOUT')
    LOG_LEVEL = 'INFO'
    LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'
    LOG_FILE = 'logs/etmam.log'
    LOG_MAX_SIZE = 10 * 1024 * 1024  # 10 ميجابايت
    LOG_BACKUP_COUNT = 10
    
    # إعدادات البريد الإلكتروني
    MAIL_SERVER = os.environ.get('MAIL_SERVER')
    MAIL_PORT = int(os.environ.get('MAIL_PORT') or 25)
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS') is not None
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER')
    
    # إعدادات التخزين المؤقت
    CACHE_TYPE = 'redis'
    CACHE_REDIS_URL = os.environ.get('REDIS_URL') or 'redis://localhost:6379/0'
    CACHE_DEFAULT_TIMEOUT = 300
    
    # إعدادات الأمان
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    SECURITY_PASSWORD_SALT = os.environ.get('SECURITY_PASSWORD_SALT') or 'ملح-افتراضي-للتطوير'
    
    # إعدادات تحميل الملفات
    UPLOAD_FOLDER = 'uploads'
    ALLOWED_EXTENSIONS = {'py', 'txt', 'json', 'yaml', 'yml'}
    
    # إعدادات التحسين
    OPTIMIZE_DB_QUERIES = True
    USE_DB_INDEXES = True
    ENABLE_QUERY_CACHING = True

    # Script Execution Settings
    SCRIPT_EXECUTION_TIMEOUT = 60 # Default timeout for script execution in seconds
    
    @staticmethod
    def init_app(app):
        """تهيئة إضافية للتطبيق
        
        المعلمات:
            app: تطبيق Flask
        """
        # إنشاء مجلدات مطلوبة
        if not os.path.exists('logs'):
            os.makedirs('logs', exist_ok=True) # Use makedirs with exist_ok=True

        # Ensure base uploads folder and scripts subfolder exist
        base_upload_folder = app.config.get('UPLOAD_FOLDER', 'uploads')
        scripts_upload_folder = os.path.join(base_upload_folder, 'scripts')
        os.makedirs(base_upload_folder, exist_ok=True)
        os.makedirs(scripts_upload_folder, exist_ok=True)
            
        # إعداد التسجيل
        if not app.debug and not app.testing:
            if app.config['LOG_TO_STDOUT']:
                stream_handler = logging.StreamHandler()
                stream_handler.setLevel(logging.INFO)
                app.logger.addHandler(stream_handler)
            else:
                if not os.path.exists('logs'):
                    os.mkdir('logs')
                file_handler = RotatingFileHandler(
                    app.config['LOG_FILE'],
                    maxBytes=app.config['LOG_MAX_SIZE'],
                    backupCount=app.config['LOG_BACKUP_COUNT']
                )
                file_handler.setFormatter(logging.Formatter(app.config['LOG_FORMAT']))
                file_handler.setLevel(logging.INFO)
                app.logger.addHandler(file_handler)
                
            app.logger.setLevel(logging.INFO)
            app.logger.info('بدء تشغيل نظام إتمام')

class DevelopmentConfig(Config):
    """إعدادات بيئة التطوير"""
    DEBUG = True
    SQLALCHEMY_ECHO = True
    TEMPLATES_AUTO_RELOAD = True

class ProductionConfig(Config):
    """إعدادات بيئة الإنتاج"""
    DEBUG = False
    TESTING = False
    SQLALCHEMY_ECHO = False
    
    # تحسينات الأمان
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    
    # تحسينات الأداء
    SQLALCHEMY_POOL_RECYCLE = 299
    SQLALCHEMY_POOL_TIMEOUT = 20
    SQLALCHEMY_POOL_SIZE = 30
    SQLALCHEMY_MAX_OVERFLOW = 10

class TestingConfig(Config):
    """إعدادات بيئة الاختبار"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False