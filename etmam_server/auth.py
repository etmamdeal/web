from functools import wraps
from flask import redirect, url_for, flash, request
from flask_login import current_user

def check_role_and_redirect(user):
    """التحقق من دور المستخدم وتوجيهه للصفحة المناسبة"""
    if not user.is_authenticated:
        return None
        
    if user.is_super_admin:
        return redirect(url_for('admin.super_dashboard'))
    elif user.is_admin:
        return redirect(url_for('main.admin_dashboard'))
    else:
        return redirect(url_for('client.dashboard'))

def super_admin_required(f):
    """للتحقق من صلاحيات السوبر أدمن"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("يجب تسجيل الدخول أولاً.", "danger")
            return redirect(url_for('main.admin_login'))
            
        if not current_user.is_super_admin:
            flash("غير مصرح لك بالدخول هنا.", "danger")
            return check_role_and_redirect(current_user)
            
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """للتحقق من صلاحيات المشرف"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("يجب تسجيل الدخول أولاً.", "danger")
            return redirect(url_for('main.admin_login'))
            
        if not (current_user.is_admin or current_user.is_super_admin): # Allow super_admins
            flash("غير مصرح لك بالدخول هنا. يتطلب دور مشرف أو سوبر أدمن.", "danger")
            return check_role_and_redirect(current_user)
            
        return f(*args, **kwargs)
    return decorated_function

def client_required(f):
    """للتحقق من صلاحيات العميل"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("يجب تسجيل الدخول أولاً.", "danger")
            return redirect(url_for('main.client_login'))
            
        if current_user.is_admin or current_user.is_super_admin:
            flash("هذه الصفحة مخصصة للعملاء فقط.", "danger")
            return check_role_and_redirect(current_user)
            
        return f(*args, **kwargs)
    return decorated_function

def check_permission(permission):
    """للتحقق من صلاحيات محددة"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("يجب تسجيل الدخول أولاً.", "danger")
                return redirect(url_for('main.admin_login'))
                
            if not current_user.has_permission(permission):
                flash("ليس لديك الصلاحية الكافية.", "danger")
                return check_role_and_redirect(current_user)
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator 