from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models import Property

bp = Blueprint('properties', __name__, url_prefix='/api/properties')

@bp.route('', methods=['POST'])
def create_property():
    data = request.get_json()
    item = Property(
        name=data['name'],
        location=data['location'],
        house_count=data['house_count']
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({ 'id': item.id })

@bp.route('', methods=['GET'])
def list_properties():
    items = Property.query.all()
    return jsonify([{
        'id': p.id,
        'name': p.name,
        'location': p.location,
        'house_count': p.house_count
    } for p in items])
