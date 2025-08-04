from .app import create_app, db
from flask_migrate import Migrate
from etmam_server.models import *

app = create_app()
migrate = Migrate(app, db)
