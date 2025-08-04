"""
Routes for client-specific functionality.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from ..models import Property, Deal, UserClient, Script, Product, Ebook, Database, Subscription
from ..forms import ProfileForm, ChangePasswordForm, PropertyForm, DealForm, ClientForm
from ..extensions import db
from ..auth import client_required
from werkzeug.utils import secure_filename
from ..utils import allowed_file
import os
import csv

client_bp = Blueprint('client', __name__, url_prefix='/client')

@client_bp.route('/dashboard')
@login_required
@client_required
def dashboard():
    from ..models import Property, Deal
    total_properties = Property.query.filter_by(user_id=current_user.id).count()
    completed_deals = Deal.query.filter_by(user_id=current_user.id, event_closed=True, stage='Closed - Won').count()
    unfinished_deals = Deal.query.filter(Deal.user_id==current_user.id).filter((Deal.event_closed==False) | (Deal.stage=='Closed - Lost')).count()
    total_revenue = Deal.query.filter_by(user_id=current_user.id, event_closed=True, stage='Closed - Won').with_entities(db.func.sum(Deal.commission_value)).scalar() or 0
    return render_template('client/dashboard.html',
        total_properties=total_properties,
        completed_deals=completed_deals,
        unfinished_deals=unfinished_deals,
        total_revenue=total_revenue
    )

@client_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@client_required
def profile():
    form = ProfileForm(obj=current_user)
    change_password_form = ChangePasswordForm()
    if form.validate_on_submit() and 'submit_profile' in request.form:
        current_user.full_name = form.full_name.data
        current_user.email = form.email.data
        current_user.phone = form.phone.data
        db.session.commit()
        flash('تم تحديث ملفك الشخصي بنجاح!', 'success')
        return redirect(url_for('client.profile'))
    if change_password_form.validate_on_submit() and 'submit_password' in request.form:
        if current_user.check_password(change_password_form.current_password.data):
            current_user.set_password(change_password_form.new_password.data)
            db.session.commit()
            flash('تم تغيير كلمة المرور بنجاح!', 'success')
            return redirect(url_for('client.profile'))
        else:
            flash('كلمة المرور الحالية غير صحيحة.', 'danger')
    return render_template('client/profile.html', title="ملفي الشخصي", form=form, change_password_form=change_password_form)

@client_bp.route('/deal-pipeline')
@login_required
@client_required
def deal_pipeline():
    status = request.args.get('status')
    deals_query = Deal.query.join(Property).filter(Property.user_id == current_user.id)
    if status == 'completed':
        deals_query = deals_query.filter(Deal.event_closed == True, Deal.stage == 'Closed - Won')
    elif status == 'unfinished':
        deals_query = deals_query.filter((Deal.event_closed == False) | (Deal.stage == 'Closed - Lost'))
    elif status == 'pending':
        deals_query = deals_query.filter((Deal.event_closed == False) & (Deal.stage != 'Closed - Lost'))
    deals = deals_query.order_by(Deal.created_at.desc()).all()
    return render_template('client/deal_pipeline.html', title="متابعة الصفقات", deals=deals)

@client_bp.route('/property-map')
@login_required
@client_required
def property_map():
    properties = Property.query.filter_by(user_id=current_user.id).order_by(Property.created_at.desc()).all()
    form = PropertyForm()
    return render_template('client/property_map.html', title="إضافة / عرض العقارات على الخريطة", form=form, properties=properties)

@client_bp.route('/add-property', methods=['POST'])
@login_required
@client_required
def add_property():
    form = PropertyForm()
    if form.validate_on_submit():
        images = []
        if 'images' in request.files:
            files = request.files.getlist('images')
            # حفظ الصور في مجلد static/properties/<user_id>/ بدلاً من uploads
            static_folder = os.path.join(current_app.root_path, 'static', 'properties', str(current_user.id))
            os.makedirs(static_folder, exist_ok=True)
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file_path = os.path.join(static_folder, filename)
                    file.save(file_path)
                    images.append(filename)
        new_property = Property(
            user_id=current_user.id,
            title=form.title.data,
            type=form.type.data,
            price=form.price.data,
            area=form.area.data,
            rooms=form.rooms.data,
            description=form.description.data,
            latitude=float(request.form.get('latitude', 0)),
            longitude=float(request.form.get('longitude', 0)),
            images=images
        )
        db.session.add(new_property)
        db.session.commit()
        flash('تمت إضافة العقار بنجاح!', 'success')
        return redirect(url_for('client.property_map'))
    else:
        flash('حدث خطأ في البيانات المدخلة. يرجى التحقق والمحاولة مجدداً.', 'danger')
        return redirect(url_for('client.property_map'))

@client_bp.route('/edit-property/<int:property_id>', methods=['GET', 'POST'])
@login_required
@client_required
def edit_property(property_id):
    prop = Property.query.filter_by(id=property_id, user_id=current_user.id).first_or_404()
    form = PropertyForm(obj=prop)
    if form.validate_on_submit():
        prop.title = form.title.data
        prop.type = form.type.data
        prop.price = form.price.data
        prop.area = form.area.data
        prop.rooms = form.rooms.data
        prop.description = form.description.data
        prop.latitude = float(request.form.get('latitude', prop.latitude))
        prop.longitude = float(request.form.get('longitude', prop.longitude))
        db.session.commit()
        flash('تم تحديث بيانات العقار بنجاح!', 'success')
        return redirect(url_for('client.manage_properties'))
    current_lat = prop.latitude
    current_lng = prop.longitude
    return render_template('client/edit_property.html', form=form, property_id=property_id, property_title=prop.title, current_lat=current_lat, current_lng=current_lng)

@client_bp.route('/delete-property/<int:property_id>', methods=['POST'])
@login_required
@client_required
def delete_property(property_id):
    prop = Property.query.filter_by(id=property_id, user_id=current_user.id).first_or_404()
    db.session.delete(prop)
    db.session.commit()
    flash('تم حذف العقار بنجاح.', 'success')
    return redirect(url_for('client.manage_properties'))

@client_bp.route('/subscription-management')
@login_required
@client_required
def subscription_management():
    plan = current_user.subscription_plan
    plan_names = {
        'basic': 'الأساسية',
        'advanced': 'المتقدمة',
        'professional': 'الاحترافية'
    }
    plan_features = {
        'basic': [
            'إدارة العروض العقارية',
            'إدارة الصفقات والعملاء',
            'وصول محدود للأدوات التسويقية',
            'دعم فني عبر التذاكر'
        ],
        'advanced': [
            'كل مزايا الباقة الأساسية',
            'وصول موسع للأدوات التسويقية',
            'تقارير دورية',
            'دعم فني أسرع'
        ],
        'professional': [
            'كل مزايا الباقة المتقدمة',
            'وصول كامل للسكربتات والكتب',
            'قواعد بيانات حصرية',
            'دعم فني ذو أولوية'
        ]
    }
    return render_template('client/subscription_management.html', plan=plan, plan_name=plan_names.get(plan, plan), features=plan_features.get(plan, []))

@client_bp.route('/clients', methods=['GET', 'POST'])
@login_required
@client_required
def list_clients():
    import csv
    # دعم رفع ملف CSV
    if request.method == 'POST' and request.form.get('csv_upload') == '1' and 'csv_file' in request.files:
        file = request.files['csv_file']
        if file.filename.endswith('.csv'):
            try:
                decoded = file.read().decode('utf-8-sig')
                reader = csv.DictReader(decoded.splitlines())
                added = 0
                for row in reader:
                    if not row.get('full_name') or not row.get('city') or not row.get('district') or not row.get('phone'):
                        continue  # الحقول الأساسية مطلوبة
                    new_client = UserClient(
                        user_id=current_user.id,
                        full_name=row.get('full_name', '').strip(),
                        city=row.get('city', '').strip(),
                        district=row.get('district', '').strip(),
                        phone=row.get('phone', '').strip(),
                        email=row.get('email', '').strip(),
                        notes=row.get('notes', '').strip()
                    )
                    db.session.add(new_client)
                    added += 1
                db.session.commit()
                flash(f'تمت إضافة {added} عميل بنجاح من ملف CSV.', 'success')
            except Exception as e:
                flash('حدث خطأ أثناء معالجة الملف. تأكد من صحة البيانات وصيغة الأعمدة.', 'danger')
            return redirect(url_for('client.list_clients'))
        else:
            flash('الملف المرفوع ليس بصيغة CSV.', 'danger')
            return redirect(url_for('client.list_clients'))
    clients = UserClient.query.filter_by(user_id=current_user.id).order_by(UserClient.created_at.desc()).all()
    return render_template('client/client_list.html', clients=clients)

@client_bp.route('/add-client', methods=['GET', 'POST'])
@login_required
@client_required
def add_client():
    import csv
    form = ClientForm()
    # دعم رفع ملف CSV
    if request.method == 'POST' and request.form.get('csv_upload') == '1' and 'csv_file' in request.files:
        file = request.files['csv_file']
        if file.filename.endswith('.csv'):
            try:
                decoded = file.read().decode('utf-8-sig')
                reader = csv.DictReader(decoded.splitlines())
                added = 0
                for row in reader:
                    if not row.get('full_name') or not row.get('city') or not row.get('district') or not row.get('phone'):
                        continue  # الحقول الأساسية مطلوبة
                    new_client = UserClient(
                        user_id=current_user.id,
                        full_name=row.get('full_name', '').strip(),
                        city=row.get('city', '').strip(),
                        district=row.get('district', '').strip(),
                        phone=row.get('phone', '').strip(),
                        email=row.get('email', '').strip(),
                        notes=row.get('notes', '').strip()
                    )
                    db.session.add(new_client)
                    added += 1
                db.session.commit()
                flash(f'تمت إضافة {added} عميل بنجاح من ملف CSV.', 'success')
            except Exception as e:
                flash('حدث خطأ أثناء معالجة الملف. تأكد من صحة البيانات وصيغة الأعمدة.', 'danger')
            return redirect(url_for('client.add_client'))
        else:
            flash('الملف المرفوع ليس بصيغة CSV.', 'danger')
            return redirect(url_for('client.add_client'))
    # إضافة عميل يدوي
    if form.validate_on_submit():
        new_client = UserClient(
            user_id=current_user.id,
            full_name=form.full_name.data,
            city=form.city.data,
            district=form.district.data,
            phone=form.phone.data,
            email=form.email.data,
            notes=form.notes.data
        )
        db.session.add(new_client)
        db.session.commit()
        flash('تمت إضافة العميل بنجاح!', 'success')
        return redirect(url_for('client.list_clients'))
    return render_template('client/add_client.html', form=form)

@client_bp.route('/edit-client/<int:client_id>', methods=['GET', 'POST'])
@login_required
@client_required
def edit_client(client_id):
    client = UserClient.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    form = ClientForm(obj=client)
    if form.validate_on_submit():
        client.full_name = form.full_name.data
        client.city = form.city.data
        client.district = form.district.data
        client.phone = form.phone.data
        client.email = form.email.data
        client.notes = form.notes.data
        db.session.commit()
        flash('تم تحديث بيانات العميل بنجاح!', 'success')
        return redirect(url_for('client.list_clients'))
    return render_template('client/edit_client.html', form=form, client=client)

@client_bp.route('/delete-client/<int:client_id>', methods=['POST'])
@login_required
@client_required
def delete_client(client_id):
    client = UserClient.query.filter_by(id=client_id, user_id=current_user.id).first_or_404()
    db.session.delete(client)
    db.session.commit()
    flash('تم حذف العميل بنجاح.', 'success')
    return redirect(url_for('client.list_clients'))

@client_bp.route('/marketing-tools')
@login_required
@client_required
def marketing_tools():
    # السكربتات المخصصة للمستخدم
    user_script_ids = [us.script_id for us in current_user.script_configurations]
    scripts = Script.query.filter(Script.id.in_(user_script_ids)).order_by(Script.created_at.desc()).all() if user_script_ids else []
    # المنتجات الرقمية المخصصة للمستخدم (عبر الاشتراكات النشطة)
    active_subs = Subscription.query.filter_by(user_id=current_user.id, is_active=True).all()
    product_ids = [sub.product_id for sub in active_subs]
    products = Product.query.filter(Product.id.in_(product_ids)).order_by(Product.created_at.desc()).all() if product_ids else []
    ebooks = Ebook.query.filter(Ebook.product_id.in_(product_ids)).all() if product_ids else []
    databases = Database.query.filter(Database.product_id.in_(product_ids)).all() if product_ids else []
    return render_template('client/marketing_tools.html', scripts=scripts, products=products, ebooks=ebooks, databases=databases)

@client_bp.route('/add-deal', methods=['GET', 'POST'])
@login_required
@client_required
def add_deal():
    from ..models import Property, UserClient, Deal
    from ..forms import DealForm
    properties = Property.query.filter_by(user_id=current_user.id).all()
    clients = UserClient.query.filter_by(user_id=current_user.id).all()
    form = DealForm()
    form.property_id.choices = [(p.id, p.title) for p in properties]
    form.client_id.choices = [(c.id, c.full_name) for c in clients]
    if form.validate_on_submit():
        new_deal = Deal(
            property_id=form.property_id.data,
            user_id=current_user.id,
            client_id=form.client_id.data,
            client_name=next((c.full_name for c in clients if c.id == form.client_id.data), None),
            stage='New Lead',
            notes=form.notes.data,
            listed_price=form.listed_price.data,
            suggested_price=form.suggested_price.data,
            actual_price=form.actual_price.data,
            commission_rate=float(form.commission_rate.data) if form.commission_rate.data else None,
            commission_value=form.commission_value.data,
            created_at=form.created_at.data,
            visit_date=form.visit_date.data,
            photo_date=form.photo_date.data,
            contract_created_at=form.contract_created_at.data,
            ad_license_date=form.ad_license_date.data,
            contract_signed_at=form.contract_signed_at.data,
            closed_at=form.closed_at.data,
            event_initial_contact=form.event_initial_contact.data,
            event_contract_signed=form.event_contract_signed.data,
            event_property_shown=form.event_property_shown.data,
            event_meeting_owner=form.event_meeting_owner.data,
            event_closed=form.event_closed.data,
            contract_number=form.contract_number.data,
            contract_date=form.contract_date.data,
            contract_duration=form.contract_duration.data,
            ad_license_number=form.ad_license_number.data
        )
        db.session.add(new_deal)
        db.session.commit()
        flash('تمت إضافة الصفقة بنجاح!', 'success')
        return redirect(url_for('client.deal_pipeline'))
    return render_template('client/add_deal.html', form=form)

@client_bp.route('/view-deal/<int:deal_id>')
@login_required
@client_required
def view_deal(deal_id):
    deal = Deal.query.filter_by(id=deal_id, user_id=current_user.id).first_or_404()
    return render_template('client/view_deal.html', deal=deal)

@client_bp.route('/edit-deal/<int:deal_id>', methods=['GET', 'POST'])
@login_required
@client_required
def edit_deal(deal_id):
    deal = Deal.query.filter_by(id=deal_id, user_id=current_user.id).first_or_404()
    form = DealForm(obj=deal)
    properties = Property.query.filter_by(user_id=current_user.id).all()
    clients = UserClient.query.filter_by(user_id=current_user.id).all()
    form.property_id.choices = [(p.id, p.title) for p in properties]
    form.client_id.choices = [(c.id, c.full_name) for c in clients]
    if form.validate_on_submit():
        deal.property_id = form.property_id.data
        deal.client_id = form.client_id.data
        deal.client_name = next((c.full_name for c in clients if c.id == form.client_id.data), None)
        deal.stage = form.stage.data
        deal.notes = form.notes.data
        deal.listed_price = form.listed_price.data
        deal.suggested_price = form.suggested_price.data
        deal.actual_price = form.actual_price.data
        deal.commission_rate = float(form.commission_rate.data) if form.commission_rate.data else None
        deal.commission_value = form.commission_value.data
        deal.created_at = form.created_at.data
        deal.visit_date = form.visit_date.data
        deal.photo_date = form.photo_date.data
        deal.contract_created_at = form.contract_created_at.data
        deal.ad_license_date = form.ad_license_date.data
        deal.contract_signed_at = form.contract_signed_at.data
        deal.closed_at = form.closed_at.data
        deal.event_initial_contact = form.event_initial_contact.data
        deal.event_contract_signed = form.event_contract_signed.data
        deal.event_property_shown = form.event_property_shown.data
        deal.event_meeting_owner = form.event_meeting_owner.data
        deal.event_closed = form.event_closed.data
        deal.contract_number = form.contract_number.data
        deal.contract_date = form.contract_date.data
        deal.contract_duration = form.contract_duration.data
        deal.ad_license_number = form.ad_license_number.data
        db.session.commit()
        flash('تم تحديث بيانات الصفقة بنجاح!', 'success')
        return redirect(url_for('client.deal_pipeline'))
    return render_template('client/edit_deal.html', form=form, deal=deal)

@client_bp.route('/delete-deal/<int:deal_id>', methods=['POST'])
@login_required
@client_required
def delete_deal(deal_id):
    deal = Deal.query.filter_by(id=deal_id, user_id=current_user.id).first_or_404()
    db.session.delete(deal)
    db.session.commit()
    flash('تم حذف الصفقة بنجاح.', 'success')
    return redirect(url_for('client.deal_pipeline'))

@client_bp.route('/archive-deal/<int:deal_id>', methods=['POST'])
@login_required
@client_required
def archive_deal(deal_id):
    deal = Deal.query.filter_by(id=deal_id, user_id=current_user.id).first_or_404()
    deal.stage = 'Archived'
    db.session.commit()
    flash('تمت أرشفة الصفقة بنجاح.', 'success')
    return redirect(url_for('client.deal_pipeline'))

@client_bp.route('/offers')
@login_required
@client_required
def offers():
    properties = Property.query.filter_by(user_id=current_user.id).order_by(Property.created_at.desc()).all()
    return render_template('client/offers.html', properties=properties)

@client_bp.route('/manage-properties')
@login_required
@client_required
def manage_properties():
    type_filter = request.args.get('type_filter', 'all')
    page = request.args.get('page', 1, type=int)
    query = Property.query.filter_by(user_id=current_user.id)
    available_types = ['Residential', 'Commercial', 'Land', 'Other']
    if type_filter and type_filter != 'all':
        query = query.filter_by(type=type_filter)
    properties_pagination = query.order_by(Property.created_at.desc()).paginate(page=page, per_page=9)
    return render_template('client/property_list.html',
        properties_pagination=properties_pagination,
        available_types=available_types,
        current_type_filter=type_filter
    )
