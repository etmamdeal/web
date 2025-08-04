import json # Added for EditProductForm
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, FloatField, BooleanField, SelectField, IntegerField, DecimalField, DateField # Added IntegerField, DecimalField, DateField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, NumberRange, Optional # Added Optional
from flask_login import current_user
from .models import User, Product, ProductType
from werkzeug.security import check_password_hash
from flask_wtf.file import FileAllowed, MultipleFileField
from .extensions import db


class LoginForm(FlaskForm):
    """Form for users to login."""
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember_me = BooleanField('Remember Me')
    submit = SubmitField('Log In')


class RegistrationForm(FlaskForm):
    """Form for new users to register."""
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=25)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    full_name = StringField('Full Name', validators=[DataRequired(), Length(max=120)])
    phone = StringField('Phone Number', validators=[DataRequired(), Length(min=10, max=15)])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    subscription_plan = SelectField('نوع الباقة', choices=[('basic', 'الأساسية'), ('advanced', 'المتقدمة'), ('professional', 'الاحترافية')], validators=[DataRequired()])
    submit = SubmitField('Sign Up')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('That username is taken. Please choose a different one.')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is already registered.')


class RequestResetForm(FlaskForm):
    """Form for users to request a password reset email."""
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is None:
            raise ValidationError('There is no account with that email. You must register first.')


class ResetPasswordForm(FlaskForm):
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Reset Password')


class ProfileForm(FlaskForm):
    full_name = StringField('Full Name', validators=[DataRequired(), Length(min=3, max=120)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    phone = StringField('Phone', validators=[Length(min=10, max=20)]) # Basic length validation
    submit_profile = SubmitField('Update Profile')

    def validate_email(self, email):
        if email.data != current_user.email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('That email is already taken by another account.')

class ChangePasswordForm(FlaskForm):
    current_password = PasswordField('Current Password', validators=[DataRequired()])
    new_password = PasswordField('New Password', validators=[DataRequired(), Length(min=6)])
    confirm_new_password = PasswordField('Confirm New Password',
                                        validators=[DataRequired(), EqualTo('new_password', message='New passwords must match.')])
    submit_password = SubmitField('Change Password')

    def validate_current_password(self, current_password):
        if not current_user.is_authenticated or not hasattr(current_user, 'password'): # Ensure current_user is valid and has password
            raise ValidationError('Authentication error.') # Or handle as appropriate
        if not check_password_hash(current_user.password, current_password.data):
            raise ValidationError('Incorrect current password.')

class EditProductForm(FlaskForm):
    name = StringField('Product Name', validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField('Description', validators=[DataRequired()])
    price = FloatField('Price (SAR)', validators=[DataRequired(), NumberRange(min=0)])
    is_active = BooleanField('Product Active (visible in store)')
    script_parameters = TextAreaField('Script Parameters (JSON)',
                                     description="Edit parameters if this is a Script product. Must be valid JSON.",
                                     render_kw={"rows": 5})
    submit = SubmitField('Update Product')

    def validate_script_parameters(self, script_parameters):
        if script_parameters.data and script_parameters.data.strip():
            try:
                json.loads(script_parameters.data)
            except json.JSONDecodeError:
                raise ValidationError('Invalid JSON format for script parameters.')

class PropertyForm(FlaskForm):
    title = StringField('Property Title', validators=[DataRequired(), Length(min=5, max=200)])
    type = SelectField('Property Type',
                       choices=[
                           ('', '-- اختر نوع العقار --'),
                           ('Residential', 'سكني (شقة، فيلا، ...)'),
                           ('Commercial', 'تجاري (مكتب، محل، ...)'),
                           ('Land', 'أرض'),
                           ('Other', 'أخرى')
                       ],
                       validators=[DataRequired(message="Please select a property type.")])
    price = FloatField('Price (SAR)', validators=[DataRequired(), NumberRange(min=0)])
    area = FloatField('Area (sqm)', validators=[Optional(), NumberRange(min=0)]) # Optional
    rooms = IntegerField('Number of Rooms', validators=[Optional(), NumberRange(min=0)]) # Optional
    description = TextAreaField('Description / Notes', validators=[Optional(), Length(max=5000)])
    images = MultipleFileField('صور العقار', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'], 'الصور فقط!')])
    # Latitude and Longitude will be handled by hidden fields in the template, not part of this WTForm directly
    submit = SubmitField('Save Property')

    def validate_type(self, field):
        if not field.data: # Handles the default empty choice
            raise ValidationError("Please select a valid property type.")


DEAL_STAGES = [
    ('New Lead', 'فرصة جديدة'),
    ('Showing Scheduled', 'تم جدولة المعاينة'),
    ('Negotiation', 'تفاوض'),
    ('Contract Signing', 'توقيع العقد'),
    ('Pending - Finance/Inspection', 'بانتظار التمويل/الفحص'),
    ('Closed - Won', 'مغلقة - ناجحة'),
    ('Closed - Lost', 'مغلقة - لم تتم'),
    ('On Hold', 'معلقة')
]

class DealForm(FlaskForm):
    property_id = SelectField('العقار', coerce=int, validators=[DataRequired(message="يرجى اختيار العقار")])
    client_id = SelectField('العميل', coerce=int, validators=[DataRequired(message="يرجى اختيار العميل")])
    stage = SelectField('مرحلة الصفقة', choices=DEAL_STAGES, validators=[DataRequired()])
    listed_price = FloatField('السعر المعروض', validators=[DataRequired(), NumberRange(min=0)])
    suggested_price = FloatField('السعر المقترح', validators=[Optional(), NumberRange(min=0)])
    actual_price = FloatField('السعر الفعلي للصفقة', validators=[Optional(), NumberRange(min=0)])
    commission_rate = DecimalField('نسبة الوساطة (%)', validators=[DataRequired(), NumberRange(min=0, max=5)], default=2.5, places=2)
    commission_value = FloatField('قيمة مبلغ الوساطة', validators=[Optional()], render_kw={'readonly': True})

    # تواريخ الأحداث
    created_at = DateField('تاريخ إنشاء الصفقة', validators=[Optional()])
    visit_date = DateField('تاريخ الزيارة الميدانية', validators=[Optional()])
    photo_date = DateField('تاريخ تصوير العقار', validators=[Optional()])
    contract_created_at = DateField('تاريخ إنشاء العقد في الهيئة', validators=[Optional()])
    ad_license_date = DateField('تاريخ استخراج الترخيص الإعلاني', validators=[Optional()])
    contract_signed_at = DateField('تاريخ توقيع العقد بين المالك والمشتري', validators=[Optional()])
    closed_at = DateField('تاريخ إقفال الصفقة', validators=[Optional()])

    # الأحداث الهامة (مربعات تحقق)
    event_initial_contact = BooleanField('التواصل المبدئي مع العميل')
    event_contract_signed = BooleanField('توقيع عقد الهيئة العامة للعقار')
    event_property_shown = BooleanField('عرض العقار ميدانيًا للعميل')
    event_meeting_owner = BooleanField('اجتماع العميل مع المالك')
    event_closed = BooleanField('إقفال الصفقة')

    # إدارة العقود
    contract_number = StringField('رقم عقد الوساطة', validators=[Optional(), Length(max=100)])
    contract_date = DateField('تاريخ إنشاء العقد', validators=[Optional()])
    contract_duration = IntegerField('مدة العقد (يوم)', validators=[Optional(), NumberRange(min=1, max=365)])
    ad_license_number = StringField('رقم الترخيص الإعلاني', validators=[Optional(), Length(max=100)])

    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    submit = SubmitField('حفظ الصفقة')

class ClientForm(FlaskForm):
    full_name = StringField('اسم العميل', validators=[DataRequired(), Length(min=2, max=120)])
    city = StringField('المدينة', validators=[DataRequired(), Length(min=2, max=100)])
    district = StringField('الحي', validators=[DataRequired(), Length(min=2, max=100)])
    phone = StringField('رقم الجوال', validators=[DataRequired(), Length(min=8, max=20)])
    email = StringField('البريد الإلكتروني', validators=[Optional(), Email(), Length(max=120)])
    notes = TextAreaField('ملاحظات', validators=[Optional(), Length(max=2000)])
    submit = SubmitField('حفظ العميل')
