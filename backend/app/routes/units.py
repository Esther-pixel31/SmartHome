from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from datetime import datetime
from decimal import Decimal, InvalidOperation

from ..extensions import db
from ..models import Unit, Property
from ..utils.pagination import paginate
from ..utils.validation import require_fields
from ..utils.authz import require_any_role

bp = Blueprint("units", __name__, url_prefix="/api/units")


def _scope():
    claims = get_jwt()
    role = claims.get("role", "viewer")
    company_id = claims.get("company_id")
    is_admin = role == "admin"
    return company_id, is_admin


def _include_deleted():
    raw = str(request.args.get("include_deleted", "")).strip().lower()
    return raw in ("1", "true", "yes", "y")


def _scoped_query(model):
    company_id, is_admin = _scope()
    q = model.query
    if not is_admin:
        q = q.filter(model.company_id == company_id)
    if not _include_deleted():
        q = q.filter(model.deleted_at.is_(None))
    return q


def _to_money(val, field):
    try:
        d = Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return None, jsonify({"error": "invalid_number", "field": field}), 400
    if d < 0:
        return None, jsonify({"error": "negative_number", "field": field}), 400
    return d, None, None


def _get_property_in_scope(property_id: int):
    company_id, is_admin = _scope()
    q = Property.query.filter(Property.id == property_id)
    if not is_admin:
        q = q.filter(Property.company_id == company_id)
    q = q.filter(Property.deleted_at.is_(None))
    return q.first()


@bp.route("", methods=["POST"])
@jwt_required()
@require_any_role("admin", "manager")
def create_unit():
    data = request.get_json()
    err = require_fields(data, ["property_id", "house_number", "rent", "garbage_fee", "water_rate", "deposit"])
    if err:
        return err

    prop = _get_property_in_scope(int(data["property_id"]))
    if not prop:
        return jsonify({"error": "property_not_found"}), 404

    rent, e, s = _to_money(data["rent"], "rent")
    if e:
        return e, s
    garbage_fee, e, s = _to_money(data["garbage_fee"], "garbage_fee")
    if e:
        return e, s
    water_rate, e, s = _to_money(data["water_rate"], "water_rate")
    if e:
        return e, s
    deposit, e, s = _to_money(data["deposit"], "deposit")
    if e:
        return e, s

    user_id = int(get_jwt_identity())

    item = Unit(
        property_id=prop.id,
        company_id=prop.company_id,
        house_number=str(data["house_number"]).strip(),
        rent=rent,
        garbage_fee=garbage_fee,
        water_rate=water_rate,
        deposit=deposit,
        created_by_id=user_id,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"id": item.id}), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_units():
    property_id = request.args.get("property_id")
    query = _scoped_query(Unit)

    if property_id:
        prop = _get_property_in_scope(int(property_id))
        if not prop:
            return jsonify({"error": "property_not_found"}), 404
        query = query.filter(Unit.property_id == prop.id)

    query = query.order_by(Unit.id.desc())
    items, meta, links = paginate(query)

    return jsonify({
        "items": [{
            "id": u.id,
            "property_id": u.property_id,
            "house_number": u.house_number,
            "rent": float(u.rent),
            "garbage_fee": float(u.garbage_fee),
            "water_rate": float(u.water_rate),
            "deposit": float(u.deposit),
            "deleted_at": u.deleted_at.isoformat() if u.deleted_at else None,
        } for u in items],
        "meta": meta,
        "links": links,
    })


@bp.route("/<int:unit_id>", methods=["GET"])
@jwt_required()
def get_unit(unit_id):
    u = _scoped_query(Unit).filter(Unit.id == unit_id).first()
    if not u:
        return jsonify({"error": "not_found"}), 404

    return jsonify({
        "id": u.id,
        "property_id": u.property_id,
        "house_number": u.house_number,
        "rent": float(u.rent),
        "garbage_fee": float(u.garbage_fee),
        "water_rate": float(u.water_rate),
        "deposit": float(u.deposit),
        "deleted_at": u.deleted_at.isoformat() if u.deleted_at else None,
    })


@bp.route("/<int:unit_id>", methods=["PUT"])
@jwt_required()
@require_any_role("admin", "manager")
def update_unit(unit_id):
    u = _scoped_query(Unit).filter(Unit.id == unit_id).first()
    if not u:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json()
    err = require_fields(data, ["property_id", "house_number", "rent", "garbage_fee", "water_rate", "deposit"])
    if err:
        return err

    prop = _get_property_in_scope(int(data["property_id"]))
    if not prop:
        return jsonify({"error": "property_not_found"}), 404

    rent, e, s = _to_money(data["rent"], "rent")
    if e:
        return e, s
    garbage_fee, e, s = _to_money(data["garbage_fee"], "garbage_fee")
    if e:
        return e, s
    water_rate, e, s = _to_money(data["water_rate"], "water_rate")
    if e:
        return e, s
    deposit, e, s = _to_money(data["deposit"], "deposit")
    if e:
        return e, s

    u.property_id = prop.id
    u.company_id = prop.company_id
    u.house_number = str(data["house_number"]).strip()
    u.rent = rent
    u.garbage_fee = garbage_fee
    u.water_rate = water_rate
    u.deposit = deposit

    db.session.commit()
    return jsonify({"message": "unit updated"}), 200


@bp.route("/<int:unit_id>", methods=["PATCH"])
@jwt_required()
@require_any_role("admin", "manager")
def patch_unit(unit_id):
    u = _scoped_query(Unit).filter(Unit.id == unit_id).first()
    if not u:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json()
    if data is None:
        return jsonify({"error": "invalid_json"}), 400

    if "property_id" in data and data["property_id"] not in ("", None):
        prop = _get_property_in_scope(int(data["property_id"]))
        if not prop:
            return jsonify({"error": "property_not_found"}), 404
        u.property_id = prop.id
        u.company_id = prop.company_id

    if "house_number" in data and data["house_number"] not in ("", None):
        u.house_number = str(data["house_number"]).strip()

    for key in ["rent", "garbage_fee", "water_rate", "deposit"]:
        if key in data and data[key] not in ("", None):
            val, e, s = _to_money(data[key], key)
            if e:
                return e, s
            setattr(u, key, val)

    db.session.commit()
    return jsonify({"message": "unit updated"}), 200


@bp.route("/<int:unit_id>", methods=["DELETE"])
@jwt_required()
@require_any_role("admin", "manager")
def delete_unit(unit_id):
    u = _scoped_query(Unit).filter(Unit.id == unit_id).first()
    if not u:
        return jsonify({"error": "not_found"}), 404

    u.deleted_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "unit deleted"}), 200
