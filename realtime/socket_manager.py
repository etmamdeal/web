"""
إدارة اتصالات WebSocket للتزامن في الوقت الفعلي
--------------------------------------------

يوفر هذا الملف وظائف لإدارة اتصالات WebSocket وتزامن البيانات
"""

from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import current_user
from flask import current_app
import json
import logging

logger = logging.getLogger(__name__)
socketio = SocketIO()

class RealTimeManager:
    """مدير التزامن في الوقت الفعلي"""
    
    def __init__(self, app=None):
        if app:
            self.init_app(app)
    
    def init_app(self, app):
        """تهيئة مدير WebSocket مع التطبيق"""
        socketio.init_app(app, cors_allowed_origins="*", async_mode='gevent')
        self._register_handlers()
    
    def _register_handlers(self):
        """تسجيل معالجات الأحداث"""
        
        @socketio.on('connect')
        def handle_connect():
            """معالجة اتصال العميل"""
            if current_user.is_authenticated:
                join_room(f'user_{current_user.id}')
                if current_user.is_admin:
                    join_room('admin_room')
                logger.info(f'تم اتصال المستخدم {current_user.id}')
        
        @socketio.on('disconnect')
        def handle_disconnect():
            """معالجة قطع اتصال العميل"""
            if current_user.is_authenticated:
                leave_room(f'user_{current_user.id}')
                if current_user.is_admin:
                    leave_room('admin_room')
                logger.info(f'تم قطع اتصال المستخدم {current_user.id}')
    
    def emit_to_user(self, user_id, event, data):
        """
        إرسال حدث لمستخدم محدد
        
        المعلمات:
            user_id: معرف المستخدم
            event: نوع الحدث
            data: البيانات المرسلة
        """
        try:
            socketio.emit(event, data, room=f'user_{user_id}')
            logger.debug(f'تم إرسال {event} إلى المستخدم {user_id}')
        except Exception as e:
            logger.error(f'خطأ في إرسال {event}: {str(e)}')
    
    def emit_to_admins(self, event, data):
        """
        إرسال حدث لجميع المشرفين
        
        المعلمات:
            event: نوع الحدث
            data: البيانات المرسلة
        """
        try:
            socketio.emit(event, data, room='admin_room')
            logger.debug(f'تم إرسال {event} إلى المشرفين')
        except Exception as e:
            logger.error(f'خطأ في إرسال {event}: {str(e)}')
    
    def broadcast(self, event, data, include_sender=False):
        """
        إرسال حدث لجميع المستخدمين المتصلين
        
        المعلمات:
            event: نوع الحدث
            data: البيانات المرسلة
            include_sender: تضمين المرسل في البث
        """
        try:
            socketio.emit(event, data, broadcast=True, include_self=include_sender)
            logger.debug(f'تم بث {event} للجميع')
        except Exception as e:
            logger.error(f'خطأ في بث {event}: {str(e)}')

# إنشاء نسخة عامة من مدير التزامن
realtime = RealTimeManager() 