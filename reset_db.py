import os
import shutil
from app import app, db

def backup_database():
    db_path = 'database.db'
    backup_path = 'database.db.backup'
    try:
        if os.path.exists(db_path) and not os.path.exists(backup_path):
            shutil.copy2(db_path, backup_path)
            print(f"✅ تم إنشاء نسخة احتياطية: {backup_path}")
    except Exception as e:
        print(f"⚠️ فشل إنشاء نسخة احتياطية: {e}")

# إنشاء نسخة احتياطية أولاً
backup_database()

# محاولة حذف مجلد instance
instance_path = 'instance'
try:
    if os.path.exists(instance_path):
        shutil.rmtree(instance_path)
        print(f"✅ تم حذف مجلد قاعدة البيانات: {instance_path}")
except Exception as e:
    print(f"⚠️ لم يتم حذف المجلد: {e}")

# محاولة حذف ملف قاعدة البيانات
db_path = 'database.db'
try:
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"✅ تم حذف قاعدة البيانات القديمة: {db_path}")
except Exception as e:
    print(f"⚠️ لم يتم حذف الملف: {e}")

# إنشاء قاعدة بيانات جديدة
print("🔄 إنشاء قاعدة بيانات جديدة...")
with app.app_context():
    try:
        db.drop_all()  # حذف جميع الجداول أولاً
        db.create_all()  # إنشاء الجداول من جديد
        print("✅ تم إنشاء قاعدة البيانات الجديدة بنجاح!")
        print("🔄 الآن قم بتشغيل create_admin.py لإنشاء حساب المشرف")
    except Exception as e:
        print(f"⚠️ فشل إنشاء قاعدة البيانات: {e}")
        # محاولة استعادة النسخة الاحتياطية
        backup_path = 'database.db.backup'
        if os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, db_path)
                print("✅ تم استعادة النسخة الاحتياطية")
            except Exception as e:
                print(f"⚠️ فشل استعادة النسخة الاحتياطية: {e}") 