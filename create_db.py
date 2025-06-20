from app import app, db
from models import User

with app.app_context():
    db.drop_all()  # حذف جميع الجداول الموجودة
    db.create_all()  # إنشاء جميع الجداول من جديد
    
    # إنشاء حساب المشرف الافتراضي
    admin = User(
        username='admin',
        password='admin123',  # تأكد من تغيير كلمة المرور في الإنتاج
        full_name='System Administrator',
        email='admin@example.com',
        is_admin=True
    )
    db.session.add(admin)
    db.session.commit()
    
print("تم إعادة تهيئة قاعدة البيانات بنجاح!") 