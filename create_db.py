from etmam_server import create_app, db
from etmam_server.models import User, Role

app = create_app()

with app.app_context():
    # حذف جميع الجداول الموجودة
    db.drop_all()
    # إنشاء جميع الجداول من جديد
    db.create_all()
    
    # إنشاء حساب المشرف الافتراضي
    admin = User(
        username='admin',
        password='admin123',  # سيتم تشفيرها بواسطة __init__
        full_name='System Administrator',
        email='admin@example.com',
        role=Role.ADMIN, # استخدام Role enum
        is_active=True
    )
    db.session.add(admin)
    db.session.commit()
    
print("تم إعادة تهيئة قاعدة البيانات بنجاح!")
print("Username: admin, Password: admin123") 