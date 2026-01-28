"""scope audit soft delete

Revision ID: 1ed9f01ccb63
Revises: 808f76cf4f37
Create Date: 2026-01-28 20:10:37.362523

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '1ed9f01ccb63'
down_revision = '808f76cf4f37'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table( "company",sa.Column("id", sa.Integer(), primary_key=True),sa.Column("name", sa.String(length=160), nullable=False),)
    op.create_index("ix_company_name", "company", ["name"], unique=True)
    op.add_column("user", sa.Column("company_id", sa.Integer(), nullable=True))
    op.add_column("user", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'")))
    op.add_column("user", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'")))
    op.add_column("user", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column("user", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_user_company_id", "user", ["company_id"])
    op.create_index("ix_user_created_by_id", "user", ["created_by_id"])
    op.create_index("ix_user_deleted_at", "user", ["deleted_at"])

    op.add_column("property", sa.Column("company_id", sa.Integer(), nullable=True))
    op.add_column("property", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'")))
    op.add_column("property", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'")))
    op.add_column("property", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column("property", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_property_company_id", "property", ["company_id"])
    op.create_index("ix_property_created_by_id", "property", ["created_by_id"])
    op.create_index("ix_property_deleted_at", "property", ["deleted_at"])

    op.add_column("unit", sa.Column("company_id", sa.Integer(), nullable=True))
    op.add_column("unit", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'")))
    op.add_column("unit", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'")))
    op.add_column("unit", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column("unit", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_unit_company_id", "unit", ["company_id"])
    op.create_index("ix_unit_created_by_id", "unit", ["created_by_id"])
    op.create_index("ix_unit_deleted_at", "unit", ["deleted_at"])

    op.add_column("tenant", sa.Column("company_id", sa.Integer(), nullable=True))
    op.add_column("tenant", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'")))
    op.add_column("tenant", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'")))
    op.add_column("tenant", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column("tenant", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_tenant_company_id", "tenant", ["company_id"])
    op.create_index("ix_tenant_created_by_id", "tenant", ["created_by_id"])
    op.create_index("ix_tenant_deleted_at", "tenant", ["deleted_at"])

    op.add_column("lease", sa.Column("company_id", sa.Integer(), nullable=True))
    op.add_column("lease", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'")))
    op.add_column("lease", sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("'1970-01-01 00:00:00'")))
    op.add_column("lease", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.add_column("lease", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index("ix_lease_company_id", "lease", ["company_id"])
    op.create_index("ix_lease_created_by_id", "lease", ["created_by_id"])
    op.create_index("ix_lease_deleted_at", "lease", ["deleted_at"])

    op.create_foreign_key("fk_user_company_id", "user", "company", ["company_id"], ["id"])
    op.create_foreign_key("fk_user_created_by_id", "user", "user", ["created_by_id"], ["id"])

    op.create_foreign_key("fk_property_company_id", "property", "company", ["company_id"], ["id"])
    op.create_foreign_key("fk_property_created_by_id", "property", "user", ["created_by_id"], ["id"])

    op.create_foreign_key("fk_unit_company_id", "unit", "company", ["company_id"], ["id"])
    op.create_foreign_key("fk_unit_created_by_id", "unit", "user", ["created_by_id"], ["id"])

    op.create_foreign_key("fk_tenant_company_id", "tenant", "company", ["company_id"], ["id"])
    op.create_foreign_key("fk_tenant_created_by_id", "tenant", "user", ["created_by_id"], ["id"])

    op.create_foreign_key("fk_lease_company_id", "lease", "company", ["company_id"], ["id"])
    op.create_foreign_key("fk_lease_created_by_id", "lease", "user", ["created_by_id"], ["id"])

    op.execute("INSERT INTO company (name) VALUES ('Default Company')")

    op.execute("UPDATE \"user\" SET company_id = (SELECT id FROM company WHERE name = 'Default Company') WHERE company_id IS NULL")
    op.execute("UPDATE property SET company_id = (SELECT id FROM company WHERE name = 'Default Company') WHERE company_id IS NULL")
    op.execute("UPDATE unit SET company_id = (SELECT id FROM company WHERE name = 'Default Company') WHERE company_id IS NULL")
    op.execute("UPDATE tenant SET company_id = (SELECT id FROM company WHERE name = 'Default Company') WHERE company_id IS NULL")
    op.execute("UPDATE lease SET company_id = (SELECT id FROM company WHERE name = 'Default Company') WHERE company_id IS NULL")

    op.alter_column("user", "company_id", nullable=False)
    op.alter_column("property", "company_id", nullable=False)
    op.alter_column("unit", "company_id", nullable=False)
    op.alter_column("tenant", "company_id", nullable=False)
    op.alter_column("lease", "company_id", nullable=False)

def downgrade():
    pass