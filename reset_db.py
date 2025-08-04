import os
import shutil
from etmam_server import create_app, db

app = create_app()

def backup_database():
    # Get the database path from the app's configuration
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
    if not db_uri.startswith('sqlite:///'):
        print("⚠️ Backup is only supported for SQLite databases.")
        return

    db_path = db_uri.replace('sqlite:///', '')
    instance_folder = os.path.dirname(db_path)
    db_filename = os.path.basename(db_path)
    backup_path = os.path.join(instance_folder, f'{db_filename}.backup')

    try:
        if os.path.exists(db_path) and not os.path.exists(backup_path):
            shutil.copy2(db_path, backup_path)
            print(f"✅ تم إنشاء نسخة احتياطية: {backup_path}")
    except Exception as e:
        print(f"⚠️ فشل إنشاء نسخة احتياطية: {e}")

# إنشاء نسخة احتياطية أولاً
backup_database()

# محاولة حذف مجلد instance
instance_path = os.path.join(os.path.dirname(__file__), 'etmam_server', 'instance')
try:
    if os.path.exists(instance_path):
        # We only want to delete the db file, not the whole instance folder
        db_file_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        if os.path.exists(db_file_path):
            os.remove(db_file_path)
            print(f"✅ تم حذف ملف قاعدة البيانات: {db_file_path}")
except Exception as e:
    print(f"⚠️ لم يتم حذف ملف قاعدة البيانات: {e}")

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
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
        db_path = db_uri.replace('sqlite:///', '')
        backup_path = f"{db_path}.backup"
        if os.path.exists(backup_path):
            try:
                shutil.copy2(backup_path, db_path)
                print("✅ تم استعادة النسخة الاحتياطية")
            except Exception as restore_e:
                print(f"⚠️ فشل استعادة النسخة الاحتياطية: {restore_e}") 