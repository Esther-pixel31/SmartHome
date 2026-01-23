from flask import Blueprint, request, jsonify
from ..extensions import db
from ..models import Property, Unit
from ..utils.validation import require_fields
from flask_jwt_extended import jwt_required

bp = Blueprint("properties", __name__, url_prefix="/api/properties")


@bp.route("", methods=["POST"])
@jwt_required()
def create_property():
    data = request.get_json()
    err = require_fields(data, ["name", "location", "house_count"])
    if err:
        return err

    item = Property(
        name=data["name"].strip(),
        location=data["location"].strip(),
        house_count=int(data["house_count"]),
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"id": item.id}), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_properties():
    q = request.args.get("q", "").strip()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 20))

    query = Property.query
    if q:
        like = f"%{q}%"
        query = query.filter((Property.name.ilike(like)) | (Property.location.ilike(like)))

    pagination = query.order_by(Property.id.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "items": [{
            "id": p.id,
            "name": p.name,
            "location": p.location,
            "house_count": p.house_count,
        } for p in pagination.items],
        "page": pagination.page,
        "per_page": pagination.per_page,
        "total": pagination.total,
        "pages": pagination.pages,
    })


@bp.route("/<int:property_id>", methods=["GET"])
@jwt_required()
def get_property(property_id):
    p = Property.query.get_or_404(property_id)
    return jsonify({
        "id": p.id,
        "name": p.name,
        "location": p.location,
        "house_count": p.house_count,
    })


@bp.route("/<int:property_id>", methods=["PUT"])
@jwt_required()
def update_property(property_id):
    item = Property.query.get_or_404(property_id)
    data = request.get_json()
    err = require_fields(data, ["name", "location", "house_count"])
    if err:
        return err

    item.name = data["name"].strip()
    item.location = data["location"].strip()
    item.house_count = int(data["house_count"])

    db.session.commit()
    return jsonify({
        "id": item.id,
        "name": item.name,
        "location": item.location,
        "house_count": item.house_count,
    })


@bp.route("/<int:property_id>", methods=["PATCH"])
@jwt_required()
def patch_property(property_id):
    item = Property.query.get_or_404(property_id)
    data = request.get_json()
    if data is None:
        return jsonify({"error": "invalid_json"}), 400

    if "name" in data and data["name"] not in ("", None):
        item.name = str(data["name"]).strip()
    if "location" in data and data["location"] not in ("", None):
        item.location = str(data["location"]).strip()
    if "house_count" in data and data["house_count"] not in ("", None):
        item.house_count = int(data["house_count"])

    db.session.commit()
    return jsonify({
        "id": item.id,
        "name": item.name,
        "location": item.location,
        "house_count": item.house_count,
    })


@bp.route("/<int:property_id>", methods=["DELETE"])
@jwt_required()
def delete_property(property_id):
    item = Property.query.get_or_404(property_id)
    db.session.delete(item)
    db.session.commit()
    return jsonify({"message": "property deleted"})


@bp.route("/<int:property_id>/units", methods=["GET"])
@jwt_required()
def list_units_for_property(property_id):
    Property.query.get_or_404(property_id)

    items = Unit.query.filter_by(property_id=property_id).order_by(Unit.id.desc()).all()
    return jsonify([{
        "id": u.id,
        "property_id": u.property_id,
        "house_number": u.house_number,
        "rent": float(u.rent),
        "garbage_fee": float(u.garbage_fee),
        "water_rate": float(u.water_rate),
        "deposit": float(u.deposit),
    } for u in items])
