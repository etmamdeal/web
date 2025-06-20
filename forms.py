import json # Added for EditProductForm
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, FloatField, BooleanField, SelectField, IntegerField, DateField # Added DateField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, NumberRange, Optional # Added Optional
from flask_login import current_user
from .models import User, Product, ProductType
from werkzeug.security import check_password_hash
from flask_wtf.file import FileAllowed, MultipleFileField, FileField # Added FileField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError, NumberRange, Optional, FileRequired # Added FileRequired
from .extensions import db


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
    is_admin_only = BooleanField('Admin-Only Product (visible only to admins)', default=False, validators=[Optional()])
    script_parameters = TextAreaField('Script Parameters (JSON)',
                                     description="عدّل معلمات السكربت إذا كان هذا المنتج سكربتًا. استخدم JSON غني لتحديد 'label', 'type', 'required', 'default', 'placeholder' لكل متغير. اتركها فارغة إذا لم تكن هناك حاجة لمتغيرات.",
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
    ('New Lead', 'New Lead'),
    ('Showing Scheduled', 'Showing Scheduled'),
    ('Negotiation', 'Negotiation'),
    ('Contract Signing', 'Contract Signing'),
    ('Pending - Finance/Inspection', 'Pending - Finance/Inspection'),
    ('Closed - Won', 'Closed - Won'),
    ('Closed - Lost', 'Closed - Lost'),
    ('On Hold', 'On Hold')
]

class DealForm(FlaskForm):
    property_id = SelectField('Associated Property', coerce=int, validators=[DataRequired(message="Please select a property.")])
    client_name = StringField('Client Name (Buyer/Renter)', validators=[DataRequired(), Length(min=2, max=120)])
    stage = SelectField('Deal Stage', choices=DEAL_STAGES, validators=[DataRequired()])
    notes = TextAreaField('Notes', validators=[Optional(), Length(max=5000)])
    submit = SubmitField('Save Deal')


class AddScriptForm(FlaskForm):
    name = StringField('اسم السكربت (للعرض في المتجر)', validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField('وصف السكربت', validators=[DataRequired()])
    price = FloatField('سعر المنتج (بالريال السعودي)', validators=[DataRequired(), NumberRange(min=0.0)])
    script_file = FileField('ملف السكربت (Python .py)', validators=[FileRequired(), FileAllowed(['py'], 'ملفات Python فقط!')])
    parameters = TextAreaField('معلمات السكربت (بصيغة JSON)', validators=[Optional()], description='أدخل كائن JSON يصف المتغيرات. لكل متغير، يمكنك تحديد: \'label\' (اسم العرض)، \'type\' (مثل \'text\', \'number\', \'date\'), \'required\' (true/false)، \'default\' (قيمة افتراضية)، \'placeholder\' (نص مساعد). مثال: {"api_key": {"label": "مفتاح API", "type": "password", "required": true, "placeholder": "أدخل مفتاح API الخاص بك"}, "count": {"label": "العدد", "type": "number", "default": 10}}')
    is_active = BooleanField('تفعيل المنتج (جعله ظاهرًا في المتجر)', default=True)
    is_admin_only = BooleanField('سكربت خاص بالمسؤولين (يظهر للمسؤولين فقط)', default=False, validators=[Optional()])
    submit = SubmitField('إضافة السكربت')

    def validate_parameters(self, parameters):
        if parameters.data and parameters.data.strip():
            try:
                json.loads(parameters.data)
            except json.JSONDecodeError:
                raise ValidationError('صيغة JSON لمعلمات السكربت غير صحيحة.')


class AddSubscriptionForm(FlaskForm):
    user_id = SelectField('User', coerce=int, validators=[DataRequired()], description='Select the user to assign the subscription to.')
    product_id = SelectField('Script Product', coerce=int, validators=[DataRequired()], description='Select the script product for the subscription.')
    period_months = IntegerField('Subscription Period (Months)', validators=[DataRequired(), NumberRange(min=1)], default=1, description='Enter the duration of the subscription in months.')
    start_date = DateField('Start Date (Optional)', validators=[Optional()], format='%Y-%m-%d', description='Leave blank for today. Format: YYYY-MM-DD.')
    submit = SubmitField('Add Subscription')


class EditSubscriptionForm(FlaskForm):
    period_months = IntegerField('Subscription Period (Months)',
                                 validators=[DataRequired(), NumberRange(min=1)],
                                 description='Enter the new total duration of the subscription in months. End date will be recalculated from start date.')
    start_date = DateField('Start Date',
                           validators=[DataRequired()],
                           format='%Y-%m-%d',
                           description='Format: YYYY-MM-DD. Changing this will affect the end date based on the period.')
    end_date = DateField('End Date (Calculated)',
                         validators=[Optional()],
                         format='%Y-%m-%d',
                         render_kw={'readonly': True},
                         description='This date is calculated based on start date and period. Adjust period or start date to change it.')
    is_active = BooleanField('Is Active', validators=[Optional()], default=True) # Default to active, can be unchecked
    submit = SubmitField('Update Subscription')
