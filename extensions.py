from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()

# تكوين مدير تسجيل الدخول
login_manager.login_view = 'main.client_login'  # صفحة تسجيل الدخول الافتراضية
login_manager.login_message = "يجب تسجيل الدخول أولاً."
login_manager.login_message_category = "warning"
login_manager.refresh_view = 'client_login'  # صفحة تحديث الجلسة
login_manager.needs_refresh_message = "الرجاء إعادة تسجيل الدخول لتحديث جلستك."
login_manager.needs_refresh_message_category = "info" 