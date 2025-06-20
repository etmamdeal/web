import os
from flask import Flask, render_template
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-secret-key'

@app.route('/')
def homepage():
    try:
        # محاولة عرض الصفحة الرئيسية بدون متغيرات معقدة
        return render_template('index.html', 
                             now=datetime.now(), 
                             admin_login_url='/admin_login',
                             current_user=None)
    except Exception as e:
        return f'<h1>خطأ في عرض الصفحة</h1><pre>{str(e)}</pre>'

@app.route('/simple')
def simple():
    return '<h1>صفحة بسيطة تعمل!</h1>'

if __name__ == '__main__':
    print("🔍 تشغيل تطبيق التشخيص على http://127.0.0.1:9000")
    app.run(debug=True, host='127.0.0.1', port=9000) 