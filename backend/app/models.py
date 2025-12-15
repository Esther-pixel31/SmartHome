from .extensions import db
from sqlalchemy import Column, Integer, String, Numeric, ForeignKey
from sqlalchemy.orm import relationship

class Property(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    location = Column(String(255), nullable=False)
    house_count = Column(Integer, nullable=False)

    units = relationship('Unit', backref='property', lazy=True)

class Unit(db.Model):
    id = Column(Integer, primary_key=True)
    property_id = Column(Integer, ForeignKey('property.id'), nullable=False)
    house_number = Column(String(20), nullable=False)
    rent = Column(Numeric, nullable=False)
    garbage_fee = Column(Numeric, nullable=False)
    water_rate = Column(Numeric, nullable=False)
    deposit = Column(Numeric, nullable=False)