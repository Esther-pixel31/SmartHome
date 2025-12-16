from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models import Property

bp = Blueprint('properties', __name__, url_prefix='/api/properties')

session = db.session

@bp.route('', methods=['POST'])
def create_property():
    data = request.get_json()
    item = Property(
        name=data['name'],
        location=data['location'],
        house_count=data['house_count']
    )
    session.add(item)
    session.commit()
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

@bp.route('/<int:property_id>', methods=['PUT'])
def update_property(property_id):
    item = Property.query.get_or_404(property_id)
    data = request.get_json()

    item.name = data.get('name', item.name)
    item.location = data.get('location', item.location)
    item.house_count = data.get('house_count', item.house_count)

    session.commit()

    return jsonify({
        'id': item.id,
        'name': item.name,
        'location': item.location,
        'house_count': item.house_count
    })

@bp.route('/<int:property_id>', methods=['DELETE'])
def delete_property(property_id):
    item = Property.query.get_or_404(property_id)

    session.delete(item)
    session.commit()

    return jsonify({ 'message': 'property deleted' })


@bp.route('/<int:property_id>', methods=['PATCH'])
def patch_property(property_id):
    item = Property.query.get_or_404(property_id)
    data = request.get_json()

    if 'name' in data:
        item.name = data['name']
    if 'location' in data:
        item.location = data['location']
    if 'house_count' in data:
        item.house_count = data['house_count']

    session.commit()

    return jsonify({
        'id': item.id,
        'name': item.name,
        'location': item.location,
        'house_count': item.house_count
    })
