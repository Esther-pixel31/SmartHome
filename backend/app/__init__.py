from flask import Flask
from .extensions import db, jwt, migrate
from .routes.auth import bp as auth_bp
from .routes.properties import bp as properties_bp
from .routes.units import bp as units_bp
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(properties_bp)
    app.register_blueprint(units_bp)

    return app
