"""
حزمة etmam_server
---------------
""" 

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_socketio import SocketIO
from flask_wtf import CSRFProtect
import os
from .models import User, Script, UserScript, RunLog, Role, Permission
from .forms import *
from .extensions import db, login_manager
from .app import bp, create_super_admin

# تهيئة قاعدة البيانات والإضافات
migrate = Migrate()
socketio = SocketIO()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    
    # تكوين التطبيق
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///app.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # تهيئة الإضافات
    db.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')
    login_manager.init_app(app)
    login_manager.login_view = 'main.client_login'
    csrf.init_app(app)
    
    # استيراد وتسجيل المسارات
    app.register_blueprint(bp)
    
    # إنشاء قاعدة البيانات
    with app.app_context():
        db.create_all()
        
        # إنشاء حساب السوبر أدمن إذا لم يكن موجوداً
        create_super_admin()
    
    return app 

__all__ = ['create_app'] 