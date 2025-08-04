"""
This file is now primarily for initializing the main Blueprint and context processors.
Routes have been moved to the 'routes' package.
"""

from flask import Blueprint
from datetime import datetime
from etmam_server.models import User
from etmam_server.extensions import login_manager

bp = Blueprint('main', __name__)

@bp.app_context_processor
def inject_now():
    return {'now': datetime.utcnow()}

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))
