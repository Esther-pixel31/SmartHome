from alembic import op
import sqlalchemy as sa

revision = "f72eadda9909"
down_revision = "64c798f5c3ca"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "user",
        sa.Column("role", sa.String(length=20), nullable=False, server_default="viewer")
    )

    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.alter_column("user", "role", server_default=None)


def downgrade():
    op.drop_column("user", "role")
