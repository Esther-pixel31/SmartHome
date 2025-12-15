from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models import Unit

bp = Blueprint('units', __name__, url_prefix='/api/units')

@bp.route('', methods=['POST'])
def create_unit():
    data = request.get_json()
    item = Unit(
        property_id=data['property_id'],
        house_number=data['house_number'],
        rent=data['rent'],
        garbage_fee=data['garbage_fee'],
        water_rate=data['water_rate'],
        deposit=data['deposit']
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({ 'id': item.id })
