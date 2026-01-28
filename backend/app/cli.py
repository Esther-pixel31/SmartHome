from datetime import datetime
import click
from flask import current_app
from .extensions import db
from .models import RevokedToken

def register_cli(app):
    @app.cli.command("cleanup-revoked-tokens")
    def cleanup_revoked_tokens():
        now = datetime.utcnow()
        deleted = (
            db.session.query(RevokedToken)
            .filter(RevokedToken.expires_at < now)
            .delete(synchronize_session=False)
        )
        db.session.commit()
        click.echo(f"deleted={deleted}")
