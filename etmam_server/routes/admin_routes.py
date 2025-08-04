"""
Routes for admin and super admin functionality.
"""
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from ..models import User, Product, Role, Permission, ProductType
from ..extensions import db
from ..auth import super_admin_required, admin_required

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    users = User.query.all()
    all_products = Product.query.all()
    return render_template('admin_dashboard.html', title='Admin Dashboard', users=users, all_products=all_products)

@admin_bp.route('/super-dashboard')
@login_required
@super_admin_required
def super_dashboard():
    stats = {
        'admins_count': User.query.filter(User.role.in_([Role.ADMIN, Role.SUPER_ADMIN])).count(),
        'users_count': User.query.filter_by(role=Role.USER).count(),
        'active_scripts': Product.query.filter_by(type='script', is_active=True).count(),
        'total_scripts': Product.query.filter_by(type='script').count()
    }
    admins = User.query.filter(User.role.in_([Role.ADMIN, Role.SUPER_ADMIN])).all()
    users = User.query.filter_by(role=Role.USER).all()
    all_products = Product.query.all()
    return render_template('super_admin_dashboard.html', title='Super Admin Dashboard', stats=stats, admins=admins, users=users, all_products=all_products, Permission=Permission, ProductType=ProductType, permissions=Permission.get_all_permissions())

@admin_bp.route('/manage-users')
@login_required
@super_admin_required
def manage_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template('manage_users.html', title='Manage Users', users=users)

@admin_bp.route('/toggle-user-status/<int:user_id>', methods=['POST'])
@login_required
@super_admin_required
def toggle_user_status(user_id):
    user_to_toggle = User.query.get_or_404(user_id)
    if user_to_toggle == current_user:
        flash("You cannot deactivate your own account.", 'danger')
        return redirect(url_for('admin.manage_users'))
    user_to_toggle.is_active = not user_to_toggle.is_active
    db.session.commit()
    flash(f"User {user_to_toggle.username}'s status has been updated.", 'success')
    return redirect(url_for('admin.manage_users'))

@admin_bp.route('/toggle-admin-status/<int:admin_id>', methods=['POST'])
@login_required
@super_admin_required
def toggle_admin_status(admin_id):
    admin_to_toggle = User.query.get_or_404(admin_id)
    if not admin_to_toggle.is_admin:
        flash('This action can only be performed on admins.', 'danger')
        return redirect(url_for('admin.super_dashboard'))
    if admin_to_toggle.id == current_user.id:
        flash("You cannot deactivate your own account.", 'danger')
        return redirect(url_for('admin.super_dashboard'))
    admin_to_toggle.is_active = not admin_to_toggle.is_active
    db.session.commit()
    status = "activated" if admin_to_toggle.is_active else "deactivated"
    flash(f"Admin {admin_to_toggle.username} has been {status}.", 'success')
    return redirect(url_for('admin.super_dashboard'))
