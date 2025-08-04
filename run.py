"""
تشغيل التطبيق مع دعم WebSocket
----------------------------
"""

from etmam_server import create_app

app = create_app()
print("📂 قاعدة البيانات المستخدمة:", app.config['SQLALCHEMY_DATABASE_URI'])

if __name__ == '__main__':
    app.run(debug=True) 