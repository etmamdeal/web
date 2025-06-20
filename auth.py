from functools import wraps
from flask import redirect, url_for, flash, request
from flask_login import current_user

def check_role_and_redirect():
    """التحقق من دور المستخدم وتوجيهه للصفحة المناسبة"""
    if not current_user.is_authenticated:
        return None
        
    if current_user.is_super_admin:
        return 'main.super_admin_dashboard'
    elif current_user.is_admin:
        return 'main.admin_dashboard'
    else:
        return 'main.client_dashboard'

def super_admin_required(f):
    """للتحقق من صلاحيات السوبر أدمن"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("يجب تسجيل الدخول أولاً.", "danger")
            return redirect(url_for('main.admin_login'))
            
        if not current_user.is_super_admin:
            flash("غير مصرح لك بالدخول هنا.", "danger")
            dashboard = check_role_and_redirect()
            return redirect(url_for(dashboard)) if dashboard else redirect(url_for('main.homepage'))
            
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
            # If the user is some other authenticated user (e.g., client), redirect to their dashboard
            # If unauthenticated, they'd be caught by the is_authenticated check earlier.
            # However, the is_authenticated check already redirects to admin_login for unauthenticated.
            # So, this path is for authenticated non-admins/non-super_admins.
            if current_user.is_authenticated and not (current_user.is_admin or current_user.is_super_admin):
                 dashboard_url = check_role_and_redirect()
                 return redirect(url_for(dashboard_url if dashboard_url else 'main.homepage'))
            # Default fallback if other conditions aren't met, though is_authenticated should handle it.
            return redirect(url_for('main.homepage'))
            
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
            dashboard = check_role_and_redirect()
            return redirect(url_for(dashboard))
            
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
                dashboard = check_role_and_redirect()
                return redirect(url_for(dashboard)) if dashboard else redirect(url_for('main.homepage'))
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator 