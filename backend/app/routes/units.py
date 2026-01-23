from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models import Unit, Property
from ..utils.validation import require_fields
from flask_jwt_extended import jwt_required

bp = Blueprint("units", __name__, url_prefix="/api/units")


@bp.route("", methods=["POST"])
@jwt_required()
def create_unit():
    data = request.get_json()
    err = require_fields(data, ["property_id", "house_number", "rent", "garbage_fee", "water_rate", "deposit"])
    if err:
        return err

    Property.query.get_or_404(int(data["property_id"]))

    item = Unit(
        property_id=int(data["property_id"]),
        house_number=str(data["house_number"]).strip(),
        rent=data["rent"],
        garbage_fee=data["garbage_fee"],
        water_rate=data["water_rate"],
        deposit=data["deposit"],
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"id": item.id}), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_units():
    property_id = request.args.get("property_id")
    query = Unit.query
    if property_id:
        query = query.filter_by(property_id=int(property_id))

    items = query.order_by(Unit.id.desc()).all()
    return jsonify([{
        "id": u.id,
        "property_id": u.property_id,
        "house_number": u.house_number,
        "rent": float(u.rent),
        "garbage_fee": float(u.garbage_fee),
        "water_rate": float(u.water_rate),
        "deposit": float(u.deposit),
    } for u in items])


@bp.route("/<int:unit_id>", methods=["GET"])
@jwt_required()
def get_unit(unit_id):
    u = Unit.query.get_or_404(unit_id)
    return jsonify({
        "id": u.id,
        "property_id": u.property_id,
        "house_number": u.house_number,
        "rent": float(u.rent),
        "garbage_fee": float(u.garbage_fee),
        "water_rate": float(u.water_rate),
        "deposit": float(u.deposit),
    })


@bp.route("/<int:unit_id>", methods=["PUT"])
@jwt_required()
def update_unit(unit_id):
    u = Unit.query.get_or_404(unit_id)
    data = request.get_json()
    err = require_fields(data, ["property_id", "house_number", "rent", "garbage_fee", "water_rate", "deposit"])
    if err:
        return err

    Property.query.get_or_404(int(data["property_id"]))

    u.property_id = int(data["property_id"])
    u.house_number = str(data["house_number"]).strip()
    u.rent = data["rent"]
    u.garbage_fee = data["garbage_fee"]
    u.water_rate = data["water_rate"]
    u.deposit = data["deposit"]

    db.session.commit()
    return jsonify({"message": "unit updated"})


@bp.route("/<int:unit_id>", methods=["PATCH"])
@jwt_required()
def patch_unit(unit_id):
    u = Unit.query.get_or_404(unit_id)
    data = request.get_json()
    if data is None:
        return jsonify({"error": "invalid_json"}), 400

    if "property_id" in data and data["property_id"] not in ("", None):
        Property.query.get_or_404(int(data["property_id"]))
        u.property_id = int(data["property_id"])

    if "house_number" in data and data["house_number"] not in ("", None):
        u.house_number = str(data["house_number"]).strip()

    for key in ["rent", "garbage_fee", "water_rate", "deposit"]:
        if key in data and data[key] not in ("", None):
            setattr(u, key, data[key])

    db.session.commit()
    return jsonify({"message": "unit updated"})


@bp.route("/<int:unit_id>", methods=["DELETE"])
@jwt_required()
def delete_unit(unit_id):
    u = Unit.query.get_or_404(unit_id)
    db.session.delete(u)
    db.session.commit()
    return jsonify({"message": "unit deleted"})
