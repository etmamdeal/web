from datetime import datetime, timedelta
from flask import current_app # Added
from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from itsdangerous import URLSafeTimedSerializer as Serializer # Added
import json
from .extensions import db
from werkzeug.security import generate_password_hash, check_password_hash

class Permission:
    VIEW_DASHBOARD = 'view_dashboard'
    MANAGE_SCRIPTS = 'manage_scripts'
    ASSIGN_SCRIPTS = 'assign_scripts'
    MANAGE_USERS = 'manage_users'
    MANAGE_ADMINS = 'manage_admins'
    VIEW_LOGS = 'view_logs'
    MANAGE_SETTINGS = 'manage_settings'
    MANAGE_TICKETS = 'manage_tickets' # Permission for support agents
    SUBMIT_TICKETS = 'submit_tickets' # Permission for users

    @staticmethod
    def get_all_permissions():
        permissions = [getattr(Permission, perm) for perm in dir(Permission) if perm.isupper() and not perm.startswith('_')]
        return list(set(permissions)) # Ensure uniqueness

class Role:
    SUPER_ADMIN = 'super_admin'
    ADMIN = 'admin'
    USER = 'user'
    SUPPORT_AGENT = 'support_agent' # New role

    @staticmethod
    def get_default_permissions(role):
        if role == Role.SUPER_ADMIN:
            return Permission.get_all_permissions()
        elif role == Role.ADMIN:
            return [
                Permission.VIEW_DASHBOARD,
                Permission.MANAGE_SCRIPTS,
                Permission.ASSIGN_SCRIPTS,
                Permission.MANAGE_USERS,
                Permission.VIEW_LOGS,
                Permission.MANAGE_TICKETS # Admins can also manage tickets
            ]
        elif role == Role.SUPPORT_AGENT:
            return [
                Permission.VIEW_DASHBOARD, # Agent might need to see some dashboard
                Permission.MANAGE_TICKETS,
                Permission.VIEW_LOGS # Might be useful for diagnostics
            ]
        elif role == Role.USER: # Changed from else to explicit elif
            return [Permission.SUBMIT_TICKETS]
        return []


class Script(db.Model):
    __tablename__ = 'scripts'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    parameters = db.Column(db.JSON, nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    user_script_associations = db.relationship('UserScript', back_populates='script')
    run_logs = db.relationship('RunLog', backref='script_log', lazy='dynamic')

    run_logs = db.relationship('RunLog', backref='script_log', lazy='dynamic')

    run_logs = db.relationship('RunLog', backref='script_log', lazy='dynamic')

    run_logs = db.relationship('RunLog', backref='script_log', lazy='dynamic')

    run_logs = db.relationship('RunLog', backref='script_log', lazy='dynamic')

    __table_args__ = (
        db.Index('idx_scripts_created_at', 'created_at'),
    )

    def __repr__(self):
        return f'<Script {self.name}>'

class UserScript(db.Model):
    __tablename__ = 'user_script'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    script_id = db.Column(db.Integer, db.ForeignKey('scripts.id', ondelete='CASCADE'), nullable=False)
    config_data = db.Column(db.JSON, default=lambda: {})
    assigned_at = db.Column(db.DateTime, default=datetime.now)
    assigned_by = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id], back_populates='script_configurations')
    script = db.relationship('Script', foreign_keys=[script_id], back_populates='user_script_associations')
    assigner = db.relationship('User', foreign_keys=[assigned_by], backref='assigned_user_scripts')
    # run_logs backref is created by RunLog.user_script (on RunLog model)

    __table_args__ = (
        db.Index('idx_user_scripts_user_id', 'user_id'),
        db.Index('idx_user_scripts_script_id', 'script_id'),
        db.Index('idx_user_scripts_composite', 'user_id', 'script_id', unique=True),
        db.UniqueConstraint('user_id', 'script_id', name='uq_user_script_user_id_script_id'),
    )

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), nullable=True)
    role = db.Column(db.String(20), default=Role.USER, nullable=False, index=True)
    permissions = db.Column(db.Text, default='[]') # Consider db.JSON if appropriate for DB
    is_active = db.Column(db.Boolean, default=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    last_login = db.Column(db.DateTime, nullable=True)
    subscription_plan = db.Column(db.String(20), default='basic', nullable=False, index=True)

    script_configurations = db.relationship('UserScript', back_populates='user', foreign_keys=[UserScript.user_id], cascade="all, delete-orphan")
    # products_created, products_modified, subscriptions, run_logs, assigned_user_scripts are backrefs
    # created_tickets, sent_ticket_messages, ticket_attachments_uploaded are new backrefs from Ticket system

    __table_args__ = (
        db.Index('idx_users_username', 'username', unique=True),
        db.Index('idx_users_email', 'email', unique=True),
        db.Index('idx_users_role', 'role'),
        db.Index('idx_users_is_active', 'is_active'),
    )

    def set_password(self, password):
        self.password = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password, password)

    @property
    def is_admin(self):
        return self.role in [Role.ADMIN, Role.SUPER_ADMIN]

    @property
    def is_super_admin(self):
        return self.role == Role.SUPER_ADMIN

    @property
    def is_support_agent(self):
        return self.role == Role.SUPPORT_AGENT

    def get_permissions(self):
        if not self.permissions:
            return []
        try:
            return json.loads(self.permissions)
        except (json.JSONDecodeError, TypeError): # More specific exception
            return []

    def set_permissions(self, permissions_list):
        self.permissions = json.dumps(list(set(permissions_list))) # Ensure unique permissions

    def has_permission(self, permission_to_check):
        if self.is_super_admin: # Super admin has all permissions implicitly
            return True
        # Admins and Support Agents also get their role-based default permissions
        # plus any explicitly assigned ones. Users only get explicit ones (or via SUBMIT_TICKETS default).
        current_perms = self.get_permissions()
        if permission_to_check in current_perms:
            return True
        # Check default permissions for the role if not found in specific user perms
        # This is useful if a user's role changes and their explicit permissions aren't updated yet.
        # Or if we want roles to inherently grant some perms not listed in user.permissions.
        # However, the __init__ method already sets default permissions, so this might be redundant
        # unless user.permissions can be manually emptied.
        # For now, rely on user.permissions being correctly populated.
        return False


    def update_last_login(self):
        self.last_login = datetime.now()
        # db.session.commit() # Committing here can cause issues, better to commit in route/service layer

    def __init__(self, **kwargs):
        super(User, self).__init__(**kwargs)
        if 'password' in kwargs:
            self.set_password(kwargs['password'])

    def get_reset_password_token(self, expires_sec=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_password_token(token, expires_sec=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, max_age=expires_sec)
            user_id = data.get('user_id')
        except Exception: # Catches SignatureExpired, BadTimeSignature, BadSignature, etc.
            return None
        return User.query.get(user_id)

class RunLog(db.Model):
    __tablename__ = 'run_log'
    id = db.Column(db.Integer, primary_key=True)
    script_id = db.Column(db.Integer, db.ForeignKey('scripts.id', name='fk_runlog_script'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', name='fk_runlog_user'), nullable=False)

    # Link to UserScript if this specific assignment's execution is being logged
    user_script_id = db.Column(db.Integer, db.ForeignKey('user_script.id'), nullable=False) # Kept as nullable=False

    status = db.Column(db.String(20), nullable=False)  # e.g., 'success', 'error', 'timeout'

    input_parameters = db.Column(db.Text, nullable=True) # To store JSON string of input params

    output = db.Column(db.Text, nullable=True)
    error = db.Column(db.Text, nullable=True)
    executed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False) # Changed default to utcnow, added nullable=False

    # Relationships
    user = db.relationship('User', backref=db.backref('run_logs', cascade="all, delete-orphan"))
    script = db.relationship('Script', backref=db.backref('script_run_logs', cascade="all, delete-orphan")) # Renamed backref
    user_script = db.relationship('UserScript', backref=db.backref('run_logs', cascade="all, delete-orphan"), foreign_keys=[user_script_id])

    __table_args__ = (
        db.Index('idx_run_logs_user_id', 'user_id'),
        db.Index('idx_run_logs_script_id', 'script_id'),
        db.Index('idx_run_logs_status', 'status'),
        db.Index('idx_run_logs_executed_at', 'executed_at'),
    )

    def __repr__(self):
        return f'<RunLog {self.id} for Script {self.script_id} by User {self.user_id} at {self.executed_at}>'

class ProductType:
    SCRIPT = 'script'
    EBOOK = 'ebook'
    DATABASE = 'database'

    @staticmethod
    def get_all_types():
        return [ProductType.SCRIPT, ProductType.EBOOK, ProductType.DATABASE]

class SubscriptionPeriod:
    ONE_MONTH = 1
    THREE_MONTHS = 3
    SIX_MONTHS = 6
    TWELVE_MONTHS = 12

    @staticmethod
    def get_all_periods():
        return [
            SubscriptionPeriod.ONE_MONTH, SubscriptionPeriod.THREE_MONTHS,
            SubscriptionPeriod.SIX_MONTHS, SubscriptionPeriod.TWELVE_MONTHS
        ]

class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Float, nullable=False)
    image_url = db.Column(db.String(200), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    last_modified = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)
    last_modified_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    script_id = db.Column(db.Integer, db.ForeignKey('scripts.id'), nullable=True)
    
    creator = db.relationship('User', foreign_keys=[created_by], backref='products_created')
    modifier = db.relationship('User', foreign_keys=[last_modified_by], backref='products_modified')
    script_definition = db.relationship('Script', foreign_keys=[script_id], backref=db.backref('product_link', uselist=False))
    subscriptions = db.relationship('Subscription', backref='product', lazy='dynamic')

    ebook_details = db.relationship('Ebook', back_populates='product', uselist=False, cascade='all, delete-orphan')
    database_details = db.relationship('Database', back_populates='product', uselist=False, cascade='all, delete-orphan')

class Subscription(db.Model):
    __tablename__ = 'subscriptions'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    period_months = db.Column(db.Integer, nullable=False)
    start_date = db.Column(db.DateTime, nullable=False, default=datetime.now)
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)
    
    user = db.relationship('User', backref='subscriptions')

    def __init__(self, **kwargs):
        super(Subscription, self).__init__(**kwargs)
        if not self.end_date:
            self.end_date = self.start_date + timedelta(days=30 * self.period_months)

    @property
    def is_expired(self):
        return datetime.now() > self.end_date

class Ebook(db.Model):
    __tablename__ = 'ebooks'
    product_id = db.Column(db.Integer, db.ForeignKey('product.id', ondelete='CASCADE'), primary_key=True)
    author = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=True)
    file_path = db.Column(db.String(200), nullable=False)
    cover_path = db.Column(db.String(200), nullable=True)

    product = db.relationship('Product', back_populates='ebook_details')
    
    def __repr__(self):
        return f'<EbookDetails for Product ID: {self.product_id}>'

class Database(db.Model):
    __tablename__ = 'databases'
    product_id = db.Column(db.Integer, db.ForeignKey('product.id', ondelete='CASCADE'), primary_key=True)
    db_technology_type = db.Column(db.String(50), nullable=True)
    size = db.Column(db.String(50), nullable=True)
    file_path = db.Column(db.String(200), nullable=False)

    product = db.relationship('Product', back_populates='database_details')
    
    def __repr__(self):
        return f'<DatabaseDetails for Product ID: {self.product_id}>'

# Support Ticket System Models
class Ticket(db.Model):
    __tablename__ = 'ticket'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    ticket_type = db.Column(db.String(50), nullable=False) # e.g., 'technical', 'billing', 'general_inquiry'
    subject = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), nullable=False, default='open') # e.g., 'open', 'in_progress', 'closed', 'resolved'
    priority = db.Column(db.String(50), nullable=False, default='medium') # e.g., 'low', 'medium', 'high', 'urgent'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = db.relationship('User', backref=db.backref('created_tickets', lazy='dynamic', cascade="all, delete-orphan"))
    messages = db.relationship('TicketMessage', backref='ticket', lazy='dynamic', cascade='all, delete-orphan')
    attachments = db.relationship('TicketAttachment', backref='ticket', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Ticket {self.id} - {self.subject[:30]}>'

class TicketMessage(db.Model):
    __tablename__ = 'ticket_message'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) # User who sent the message
    message_body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    # 'ticket' backref is implicitly created by Ticket.messages
    sender = db.relationship('User', backref=db.backref('sent_ticket_messages', lazy='dynamic'))

    def __repr__(self):
        return f'<TicketMessage {self.id} for Ticket {self.ticket_id}>'

class TicketAttachment(db.Model):
    __tablename__ = 'ticket_attachment'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id', ondelete='CASCADE'), nullable=False)
    # message_id = db.Column(db.Integer, db.ForeignKey('ticket_message.id'), nullable=True) # Optional: if attachment is tied to a specific message
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) # User who uploaded
    file_path = db.Column(db.String(255), nullable=False) # Path to the stored file (e.g., in UPLOAD_FOLDER/attachments)
    original_filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    # 'ticket' backref is implicitly created by Ticket.attachments
    uploader = db.relationship('User', backref=db.backref('ticket_attachments_uploaded', lazy='dynamic'))
    # ticket_message = db.relationship('TicketMessage', backref='attachments') # Optional: if linked to message

    def __repr__(self):
        return f'<TicketAttachment {self.id} - {self.original_filename}>'

# New Real Estate Broker Models

class Property(db.Model):
    __tablename__ = 'properties' # Changed from 'property' to 'properties'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False) # Assumes 'users' table
    title = db.Column(db.String(200), nullable=False)
    type = db.Column(db.String(50), nullable=False) # E.g., 'Residential', 'Commercial', 'Land'
    price = db.Column(db.Float, nullable=False) # Consider db.Numeric for precision if DB supports well
    area = db.Column(db.Float, nullable=True) # Square meters
    rooms = db.Column(db.Integer, nullable=True) # Number of rooms, applicable for some types
    description = db.Column(db.Text, nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    images = db.Column(db.JSON, nullable=True)  # قائمة أسماء الصور
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    # user = db.relationship('User', backref=db.backref('properties', lazy=True)) # If needed
    # deals = db.relationship('Deal', backref='property', lazy='dynamic', cascade='all, delete-orphan') # If needed

    def __repr__(self):
        return f'<Property {self.id}: {self.title}>'

class Deal(db.Model):
    __tablename__ = 'deals'
    id = db.Column(db.Integer, primary_key=True)
    property_id = db.Column(db.Integer, db.ForeignKey('properties.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('user_client.id'), nullable=False)
    client_name = db.Column(db.String(120), nullable=True)
    stage = db.Column(db.String(50), nullable=False, default='New Lead')
    notes = db.Column(db.Text, nullable=True)
    # الأسعار والمعايير المالية
    listed_price = db.Column(db.Float, nullable=True)
    suggested_price = db.Column(db.Float, nullable=True)
    actual_price = db.Column(db.Float, nullable=True)
    commission_rate = db.Column(db.Float, nullable=True)
    commission_value = db.Column(db.Float, nullable=True)
    # التواريخ
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    visit_date = db.Column(db.DateTime, nullable=True)
    photo_date = db.Column(db.DateTime, nullable=True)
    contract_created_at = db.Column(db.DateTime, nullable=True)
    ad_license_date = db.Column(db.DateTime, nullable=True)
    contract_signed_at = db.Column(db.DateTime, nullable=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    # الأحداث الهامة
    event_initial_contact = db.Column(db.Boolean, default=False)
    event_contract_signed = db.Column(db.Boolean, default=False)
    event_property_shown = db.Column(db.Boolean, default=False)
    event_meeting_owner = db.Column(db.Boolean, default=False)
    event_closed = db.Column(db.Boolean, default=False)
    # إدارة العقود
    contract_number = db.Column(db.String(100), nullable=True)
    contract_date = db.Column(db.DateTime, nullable=True)
    contract_duration = db.Column(db.Integer, nullable=True)
    ad_license_number = db.Column(db.String(100), nullable=True)
    # العلاقات
    property = db.relationship('Property', backref=db.backref('deals', lazy=True))
    client = db.relationship('UserClient', backref=db.backref('deals', lazy=True))
    user = db.relationship('User', backref=db.backref('deals', lazy=True))
    def __repr__(self):
        return f'<Deal {self.id} for Property {self.property_id}>'

class UserClient(db.Model):
    __tablename__ = 'user_client'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    district = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref=db.backref('clients', lazy='dynamic', cascade="all, delete-orphan"))

    def __repr__(self):
        return f'<UserClient {self.full_name} (User {self.user_id})>'
