"""
Public-facing routes that do not require authentication.
"""
from flask import Blueprint, render_template, current_app
from ..models import Product

public_bp = Blueprint('public', __name__)

@public_bp.route('/')
def homepage():
    try:
        return render_template('index.html')
    except Exception as e:
        current_app.logger.error(f'Error in homepage: {str(e)}')
        return f'<h1>Error displaying page</h1><pre>{str(e)}</pre>', 500

@public_bp.route('/service-description')
def service_description():
    return render_template('service_description.html', title="وصف الخدمة")

@public_bp.route('/products')
def products():
    all_products = Product.query.filter_by(is_active=True).all()
    return render_template('products.html', title="المنتجات", products=all_products)

@public_bp.route('/contact-us')
def contact_us():
    return render_template('contact_us.html', title="اتصل بنا")
