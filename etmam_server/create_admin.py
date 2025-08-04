from etmam_server import create_app, db
from etmam_server.models import User, Role

app = create_app()

# بيانات السوبر أدمن الجديدة
username = 'superadmin'
password = 'superadmin123'
email = 'superadmin@etmamdeal.com'

with app.app_context():
    # التحقق من عدم وجود السوبر أدمن مسبقاً
    super_admin = User.query.filter_by(username=username).first()
    if not super_admin:
        super_admin_user = User(
            username=username,
            password=password,  # سيتم تشفيرها تلقائياً
            full_name='سوبر أدمن',
            email=email,
            phone='0555555555',
            role=Role.SUPER_ADMIN,
            is_active=True
        )
        db.session.add(super_admin_user)
        db.session.commit()
        print("✅ تم إنشاء حساب السوبر أدمن بنجاح!")
        print(f"Username: {username}")
        print(f"Password: {password}")
    else:
        print("⚠️ حساب السوبر أدمن موجود مسبقاً!")
        print(f"Username: {username}")

# إنشاء حساب مشرف
with app.app_context():
    # التحقق من عدم وجود المشرف مسبقاً
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin_user = User(
            username='admin',
            password='admin123', # سيتم تشفيرها بواسطة __init__
            full_name='المشرف العام',
            email='admin@etmamdeal.com',
            phone='0500000000',
            role=Role.ADMIN, # استخدام Role enum
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