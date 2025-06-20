from app import app, db, User
from werkzeug.security import generate_password_hash

# إنشاء حساب مشرف
with app.app_context():
    # التحقق من عدم وجود المشرف مسبقاً
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin_user = User(
            username='admin',
            password=generate_password_hash('admin123'),
            full_name='المشرف العام',
            email='admin@etmamdeal.com',
            phone='0500000000',
            is_admin=True,
            is_active=True
        )
        db.session.add(admin_user)
        db.session.commit()
        print("✅ تم إنشاء حساب المشرف بنجاح!")
        print("Username: admin")
        print("Password: admin123")
    else:
        print("⚠️ حساب المشرف موجود مسبقاً!")
        print("Username: admin") 