from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from datetime import datetime
from ..extensions import db
from ..models import Property, Unit, Lease, Tenant
from ..utils.pagination import paginate
from ..utils.validation import require_fields

bp = Blueprint("properties", __name__, url_prefix="/api/properties")


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


@bp.route("", methods=["POST"])
@jwt_required()
def create_property():
    data = request.get_json()
    err = require_fields(data, ["name", "location", "house_count"])
    if err:
        return err

    company_id, is_admin = _scope()
    user_id = int(get_jwt_identity())

    item = Property(
        name=str(data["name"]).strip(),
        location=str(data["location"]).strip(),
        house_count=int(data["house_count"]),
        company_id=company_id,
        created_by_id=user_id,
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"id": item.id}), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_properties():
    q = request.args.get("q", "").strip()
    query = _scoped_query(Property)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (Property.name.ilike(like)) |
            (Property.location.ilike(like))
        )

    query = query.order_by(Property.id.desc())

    items, meta, links = paginate(query)

    return jsonify({
        "items": [{
            "id": p.id,
            "name": p.name,
            "location": p.location,
            "house_count": p.house_count,
            "deleted_at": p.deleted_at.isoformat() if p.deleted_at else None,
        } for p in items],
        "meta": meta,
        "links": links,
    })


@bp.route("/<int:property_id>", methods=["GET"])
@jwt_required()
def get_property(property_id):
    p = _scoped_query(Property).filter(Property.id == property_id).first()
    if not p:
        return jsonify({"error": "not_found"}), 404

    return jsonify({
        "id": p.id,
        "name": p.name,
        "location": p.location,
        "house_count": p.house_count,
        "deleted_at": p.deleted_at.isoformat() if p.deleted_at else None,
    })


@bp.route("/<int:property_id>", methods=["PUT"])
@jwt_required()
def update_property(property_id):
    item = _scoped_query(Property).filter(Property.id == property_id).first()
    if not item:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json()
    err = require_fields(data, ["name", "location", "house_count"])
    if err:
        return err

    item.name = str(data["name"]).strip()
    item.location = str(data["location"]).strip()
    item.house_count = int(data["house_count"])

    db.session.commit()
    return jsonify({
        "id": item.id,
        "name": item.name,
        "location": item.location,
        "house_count": item.house_count,
        "deleted_at": item.deleted_at.isoformat() if item.deleted_at else None,
    })


@bp.route("/<int:property_id>", methods=["PATCH"])
@jwt_required()
def patch_property(property_id):
    item = _scoped_query(Property).filter(Property.id == property_id).first()
    if not item:
        return jsonify({"error": "not_found"}), 404

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
        "deleted_at": item.deleted_at.isoformat() if item.deleted_at else None,
    })


@bp.route("/<int:property_id>", methods=["DELETE"])
@jwt_required()
def delete_property(property_id):
    item = _scoped_query(Property).filter(Property.id == property_id).first()
    if not item:
        return jsonify({"error": "not_found"}), 404

    item.deleted_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "property deleted"}), 200


@bp.route("/<int:property_id>/units", methods=["GET"])
@jwt_required()
def property_units(property_id):
    company_id, is_admin = _scope()

    p_query = Property.query.filter(Property.id == property_id)
    if not is_admin:
        p_query = p_query.filter(Property.company_id == company_id)
    if not _include_deleted():
        p_query = p_query.filter(Property.deleted_at.is_(None))

    p = p_query.first()
    if not p:
        return jsonify({"error": "not_found"}), 404

    u_query = Unit.query.filter(Unit.property_id == property_id)
    if not is_admin:
        u_query = u_query.filter(Unit.company_id == company_id)
    if not _include_deleted():
        u_query = u_query.filter(Unit.deleted_at.is_(None))

    units = u_query.order_by(Unit.id.asc()).all()
    unit_ids = [u.id for u in units]

    l_query = Lease.query
    if unit_ids:
        l_query = l_query.filter(Lease.unit_id.in_(unit_ids), Lease.is_active == True)
    else:
        l_query = l_query.filter(Lease.id == -1)

    if not is_admin:
        l_query = l_query.filter(Lease.company_id == company_id)
    if not _include_deleted():
        l_query = l_query.filter(Lease.deleted_at.is_(None))

    active_leases = l_query.order_by(Lease.id.desc()).all()

    lease_map = {}
    for l in active_leases:
        if l.unit_id not in lease_map:
            lease_map[l.unit_id] = l

    tenant_ids = [l.tenant_id for l in lease_map.values()]
    t_query = Tenant.query
    if tenant_ids:
        t_query = t_query.filter(Tenant.id.in_(tenant_ids))
    else:
        t_query = t_query.filter(Tenant.id == -1)

    if not is_admin:
        t_query = t_query.filter(Tenant.company_id == company_id)
    if not _include_deleted():
        t_query = t_query.filter(Tenant.deleted_at.is_(None))

    tenants = t_query.all()
    tenant_map = {t.id: t for t in tenants}

    payload = []
    for u in units:
        l = lease_map.get(u.id)
        t = tenant_map.get(l.tenant_id) if l else None

        payload.append({
            "id": u.id,
            "house_number": u.house_number,
            "rent": float(u.rent),
            "deposit": float(u.deposit),
            "garbage_fee": float(u.garbage_fee),
            "water_rate": float(u.water_rate),
            "is_occupied": bool(l),
            "current_tenant": {
                "id": t.id,
                "full_name": t.full_name,
                "email": t.email,
                "phone": t.phone
            } if t else None
        })

    return jsonify(payload)
