from .extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey, Index, UniqueConstraint, DateTime, Boolean, Date
from sqlalchemy.orm import relationship, declared_attr
from datetime import datetime

# ---------- Mixins ----------

class ScopeMixin:
    company_id = Column(Integer, ForeignKey("company.id"), nullable=False, index=True)

class AuditMixin:
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_id = Column(Integer, ForeignKey("user.id"), nullable=True, index=True)

    @declared_attr
    def created_by(cls):
        return relationship("User", foreign_keys=[cls.created_by_id], lazy=True)


class SoftDeleteMixin:
    deleted_at = Column(DateTime, nullable=True, index=True)

# ---------- New: Company ----------

class Company(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False, unique=True, index=True)

    users = relationship("User", backref="company", lazy=True)
    properties = relationship("Property", backref="company", lazy=True)

# ---------- Models ----------

class Property(db.Model, ScopeMixin, AuditMixin, SoftDeleteMixin):
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    location = Column(String(255), nullable=False)
    house_count = Column(Integer, nullable=False)

    __table_args__ = (
        Index("ix_property_name", "name"),
        Index("ix_property_location", "location"),
    )

    units = relationship("Unit", backref="property", lazy=True, cascade="all, delete-orphan")


class Unit(db.Model, ScopeMixin, AuditMixin, SoftDeleteMixin):
    id = Column(Integer, primary_key=True)

    property_id = Column(Integer, ForeignKey("property.id"), nullable=False, index=True)

    house_number = Column(String(20), nullable=False)
    rent = Column(Numeric(12, 2), nullable=False)
    garbage_fee = Column(Numeric(12, 2), nullable=False)
    water_rate = Column(Numeric(12, 2), nullable=False)
    deposit = Column(Numeric(12, 2), nullable=False)

    __table_args__ = (
        UniqueConstraint("property_id", "house_number", name="uq_unit_property_house_number"),
    )


class User(db.Model, ScopeMixin, AuditMixin, SoftDeleteMixin):
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="viewer")  # viewer, staff, admin

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Tenant(db.Model, ScopeMixin, AuditMixin, SoftDeleteMixin):
    id = Column(Integer, primary_key=True)
    full_name = Column(String(160), nullable=False)
    phone = Column(String(40), nullable=False)
    email = Column(String(255), nullable=True)

    __table_args__ = (
        Index("ix_tenant_full_name", "full_name"),
        Index("ix_tenant_phone", "phone"),
    )

    leases = relationship("Lease", backref="tenant", lazy=True, cascade="all, delete-orphan")


class Lease(db.Model, ScopeMixin, AuditMixin, SoftDeleteMixin):
    id = Column(Integer, primary_key=True)

    tenant_id = Column(Integer, ForeignKey("tenant.id"), nullable=False, index=True)
    unit_id = Column(Integer, ForeignKey("unit.id"), nullable=False, index=True)

    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)

    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_lease_is_active", "is_active"),
    )

    unit = relationship("Unit", backref=db.backref("leases", lazy=True, cascade="all, delete-orphan"))


class RevokedToken(db.Model):
    id = Column(Integer, primary_key=True)
    jti = Column(String(36), unique=True, nullable=False, index=True)
    token_type = Column(String(10), nullable=False)  # access or refresh
    user_id = Column(Integer, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
