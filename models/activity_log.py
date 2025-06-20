from datetime import datetime
from . import db

class ActivityLog(db.Model):
    """نموذج لتتبع الأنشطة في النظام"""
    
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)  # نوع النشاط
    entity_type = db.Column(db.String(50))  # نوع الكيان (مستخدم، سكربت، إلخ)
    entity_id = db.Column(db.Integer)  # معرف الكيان
    details = db.Column(db.Text)  # تفاصيل النشاط
    ip_address = db.Column(db.String(45))  # عنوان IP
    user_agent = db.Column(db.String(200))  # معلومات المتصفح
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    # العلاقات
    user = db.relationship('User', backref=db.backref('activities', lazy=True))
    
    def __init__(self, user_id, action, entity_type=None, entity_id=None, details=None, ip_address=None, user_agent=None):
        self.user_id = user_id
        self.action = action
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.details = details
        self.ip_address = ip_address
        self.user_agent = user_agent
    
    @classmethod
    def log_activity(cls, user_id, action, **kwargs):
        """تسجيل نشاط جديد"""
        activity = cls(
            user_id=user_id,
            action=action,
            entity_type=kwargs.get('entity_type'),
            entity_id=kwargs.get('entity_id'),
            details=kwargs.get('details'),
            ip_address=kwargs.get('ip_address'),
            user_agent=kwargs.get('user_agent')
        )
        db.session.add(activity)
        try:
            db.session.commit()
            return activity
        except Exception as e:
            db.session.rollback()
            raise e
    
    def to_dict(self):
        """تحويل النشاط إلى قاموس"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'action': self.action,
            'entity_type': self.entity_type,
            'entity_id': self.entity_id,
            'details': self.details,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'created_at': self.created_at.isoformat()
        }
    
    @classmethod
    def get_user_activities(cls, user_id, limit=10):
        """الحصول على أنشطة مستخدم محدد"""
        return cls.query.filter_by(user_id=user_id)\
            .order_by(cls.created_at.desc())\
            .limit(limit)\
            .all()
    
    @classmethod
    def get_entity_activities(cls, entity_type, entity_id, limit=10):
        """الحصول على أنشطة كيان محدد"""
        return cls.query.filter_by(entity_type=entity_type, entity_id=entity_id)\
            .order_by(cls.created_at.desc())\
            .limit(limit)\
            .all()
    
    def __repr__(self):
        return f'<Activity {self.action} by User {self.user_id}>' 