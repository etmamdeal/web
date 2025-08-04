from flask import Flask
from .config import Config
from .extensions import db, login_manager, migrate, csrf, socketio, mail
import os

def create_app(config_class=Config):
    """
    Application Factory: Creates and inits the Flask application.
    """
    app = Flask(__name__, instance_relative_config=True)
    
    # Load config from the config object
    app.config.from_object(config_class)
    
    # Create instance folder
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    # Init Flask extensions
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')
    mail.init_app(app)

    import etmam_server.app  # فقط لتفعيل user_loader

    # Configure login manager
    login_manager.login_view = 'main.client_login'
    login_manager.login_message = "يرجى تسجيل الدخول للوصول إلى هذه الصفحة."
    login_manager.login_message_category = "info"

    @app.context_processor
    def inject_now():
        from datetime import datetime
        return {'now': datetime.utcnow()}

    with app.app_context():
        # Import and register Blueprints
        from .routes.public_routes import public_bp
        from .routes.auth_routes import auth_bp
        from .routes.client_routes import client_bp
        from .routes.admin_routes import admin_bp
        
        app.register_blueprint(public_bp)
        app.register_blueprint(auth_bp)
        app.register_blueprint(client_bp)
        app.register_blueprint(admin_bp)

        # Import and register CLI commands
        from .commands import create_super_admin_command
        app.cli.add_command(create_super_admin_command)

    return app

__all__ = ['create_app']