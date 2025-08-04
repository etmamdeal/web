import click
from flask.cli import with_appcontext
from .extensions import db
from .models import User, Role, Permission
import json

@click.command(name='create_super_admin')
@with_appcontext
def create_super_admin_command():
    """Creates the super admin user interactively."""
    try:
        # Check if a super admin already exists
        if User.query.filter_by(role=Role.SUPER_ADMIN).first():
            if not click.confirm('A super admin user already exists. Do you want to create another one?'):
                return

        # Get details interactively
        username = click.prompt('Enter username', default='super_admin')
        email = click.prompt('Enter email', default=f'{username}@etmamdeal.com')
        password = click.prompt('Enter password', hide_input=True, confirmation_prompt=True)
        full_name = click.prompt('Enter full name', default='Super Admin')
        phone = click.prompt('Enter phone number', default='0500000000')

        # Create the super admin user
        super_admin = User(
            username=username,
            password=password,  # The model's __init__ will hash this
            email=email,
            full_name=full_name,
            phone=phone,
            role=Role.SUPER_ADMIN,
            is_active=True,
            permissions=json.dumps(Permission.get_all_permissions())
        )
        db.session.add(super_admin)
        db.session.commit()
        click.echo(f'Super admin user "{username}" created successfully!')

    except Exception as e:
        db.session.rollback()
        click.echo(f'Error creating super admin user: {str(e)}')
 