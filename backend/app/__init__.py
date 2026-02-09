from flask import Flask
from .extensions import db, jwt, migrate
from .routes.auth import bp as auth_bp
from .routes.properties import bp as properties_bp
from .routes.units import bp as units_bp
from .routes.tenants import bp as tenants_bp
from .routes.leases import bp as leases_bp
from .routes.payments import bp as payments_bp
from .models import RevokedToken
from flask_jwt_extended import get_jwt
from .cli import register_cli
from config import Config

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    register_cli(app)

    @jwt.token_in_blocklist_loader
    def token_in_blocklist(jwt_header, jwt_payload):
        jti = jwt_payload.get("jti")
        if not jti:
            return True
        return db.session.query(
            db.session.query(RevokedToken.id).filter_by(jti=jti).exists()
        ).scalar()

    app.register_blueprint(auth_bp)
    app.register_blueprint(properties_bp)
    app.register_blueprint(units_bp)
    app.register_blueprint(tenants_bp)
    app.register_blueprint(leases_bp)
    app.register_blueprint(payments_bp)
    return app
