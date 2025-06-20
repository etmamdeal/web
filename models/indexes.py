"""
ملف لتعريف الفهارس (indexes) لتحسين أداء قاعدة البيانات
"""

from . import db
from sqlalchemy import Index, text

# فهارس للمستخدمين
Index('idx_users_username', 'users.username', unique=True)
Index('idx_users_email', 'users.email', unique=True)
Index('idx_users_role', 'users.role')
Index('idx_users_is_active', 'users.is_active')

# فهارس للسكربتات
Index('idx_scripts_name', 'scripts.name', unique=True)
Index('idx_scripts_status', 'scripts.status')
Index('idx_scripts_is_active', 'scripts.is_active')
Index('idx_scripts_created_at', 'scripts.created_at')

# فهارس للعلاقة بين المستخدمين والسكربتات
Index('idx_user_scripts_user_id', 'user_scripts.user_id')
Index('idx_user_scripts_script_id', 'user_scripts.script_id')
Index('idx_user_scripts_composite', 'user_scripts.user_id', 'user_scripts.script_id', unique=True)

# فهارس لسجلات التشغيل
Index('idx_run_logs_user_id', 'run_logs.user_id')
Index('idx_run_logs_script_id', 'run_logs.script_id')
Index('idx_run_logs_status', 'run_logs.status')
Index('idx_run_logs_executed_at', 'run_logs.executed_at')

# فهارس لسجلات الأنشطة
Index('idx_activity_logs_user_id', 'activity_logs.user_id')
Index('idx_activity_logs_action', 'activity_logs.action')
Index('idx_activity_logs_entity', 'activity_logs.entity_type', 'activity_logs.entity_id')
Index('idx_activity_logs_created_at', 'activity_logs.created_at')

# تحسين الاستعلامات المعقدة
def optimize_queries():
    """دالة لتحسين الاستعلامات الشائعة"""
    
    # إنشاء view للإحصائيات
    db.session.execute(text("""
    CREATE VIEW IF NOT EXISTS vw_user_stats AS
    SELECT 
        u.id as user_id,
        COUNT(DISTINCT us.script_id) as scripts_count,
        COUNT(DISTINCT rl.id) as total_runs,
        SUM(CASE WHEN rl.status = 'success' THEN 1 ELSE 0 END) as successful_runs,
        MAX(rl.executed_at) as last_run_date
    FROM users u
    LEFT JOIN user_scripts us ON u.id = us.user_id
    LEFT JOIN run_logs rl ON u.id = rl.user_id
    GROUP BY u.id
    """))
    
    # إنشاء view لإحصائيات السكربتات
    db.session.execute(text("""
    CREATE VIEW IF NOT EXISTS vw_script_stats AS
    SELECT 
        s.id as script_id,
        COUNT(DISTINCT us.user_id) as users_count,
        COUNT(DISTINCT rl.id) as total_runs,
        SUM(CASE WHEN rl.status = 'success' THEN 1 ELSE 0 END) as successful_runs,
        MAX(rl.executed_at) as last_run_date
    FROM scripts s
    LEFT JOIN user_scripts us ON s.id = us.script_id
    LEFT JOIN run_logs rl ON s.id = rl.script_id
    GROUP BY s.id
    """))
    
    db.session.commit()

def create_indexes():
    """دالة لإنشاء جميع الفهارس"""
    try:
        # إنشاء الفهارس
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_users_is_active ON users(is_active)"))
        
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_scripts_name ON scripts(name)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_scripts_status ON scripts(status)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_scripts_is_active ON scripts(is_active)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_scripts_created_at ON scripts(created_at)"))
        
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_user_scripts_user_id ON user_scripts(user_id)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_user_scripts_script_id ON user_scripts(script_id)"))
        db.session.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_scripts_composite ON user_scripts(user_id, script_id)"))
        
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_run_logs_user_id ON run_logs(user_id)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_run_logs_script_id ON run_logs(script_id)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_run_logs_status ON run_logs(status)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_run_logs_executed_at ON run_logs(executed_at)"))
        
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_user_id ON activity_logs(user_id)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_action ON activity_logs(action)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_entity ON activity_logs(entity_type, entity_id)"))
        db.session.execute(text("CREATE INDEX IF NOT EXISTS idx_activity_logs_created_at ON activity_logs(created_at)"))
        
        db.session.commit()
        print("✅ تم إنشاء جميع الفهارس بنجاح")
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ خطأ في إنشاء الفهارس: {str(e)}")
        raise e

def analyze_query_performance():
    """دالة لتحليل أداء الاستعلامات"""
    try:
        # تحليل الجداول
        db.session.execute(text("ANALYZE users"))
        db.session.execute(text("ANALYZE scripts"))
        db.session.execute(text("ANALYZE user_scripts"))
        db.session.execute(text("ANALYZE run_logs"))
        db.session.execute(text("ANALYZE activity_logs"))
        
        # جمع إحصائيات
        db.session.execute(text("ANALYZE"))
        
        print("✅ تم تحليل أداء قاعدة البيانات بنجاح")
        
    except Exception as e:
        print(f"❌ خطأ في تحليل الأداء: {str(e)}")
        raise e 