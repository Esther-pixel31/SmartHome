from .extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from sqlalchemy.orm import relationship


class Property(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    location = Column(String(255), nullable=False)
    house_count = Column(Integer, nullable=False)

    units = relationship("Unit", backref="property", lazy=True, cascade="all, delete-orphan")


class Unit(db.Model):
    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey("property.id"), nullable=False, index=True)

    house_number = Column(String(20), nullable=False)
    rent = Column(Numeric(12, 2), nullable=False)
    garbage_fee = Column(Numeric(12, 2), nullable=False)
    water_rate = Column(Numeric(12, 2), nullable=False)
    deposit = Column(Numeric(12, 2), nullable=False)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)