from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from ..extensions import db
from ..models import Tenant, Lease, Unit, Property
from ..utils.validation import require_fields

bp = Blueprint("tenants", __name__, url_prefix="/api/tenants")


@bp.route("", methods=["POST"])
@jwt_required()
def create_tenant():
    data = request.get_json()
    err = require_fields(data, ["full_name", "phone"])
    if err:
        return err

    t = Tenant(
        full_name=str(data["full_name"]).strip(),
        phone=str(data["phone"]).strip(),
        email=str(data["email"]).strip().lower() if data.get("email") else None,
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({"id": t.id}), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_tenants():
    q = request.args.get("q", "").strip()
    query = Tenant.query
    if q:
        like = f"%{q}%"
        query = query.filter((Tenant.full_name.ilike(like)) | (Tenant.phone.ilike(like)))
    items = query.order_by(Tenant.id.desc()).all()
    return jsonify([{
        "id": t.id,
        "full_name": t.full_name,
        "phone": t.phone,
        "email": t.email,
    } for t in items])


@bp.route("/<int:tenant_id>", methods=["GET"])
@jwt_required()
def get_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    return jsonify({
        "id": t.id,
        "full_name": t.full_name,
        "phone": t.phone,
        "email": t.email,
    })


@bp.route("/<int:tenant_id>", methods=["PATCH"])
@jwt_required()
def patch_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    data = request.get_json()
    if data is None:
        return jsonify({"error": "invalid_json"}), 400

    if "full_name" in data and data["full_name"] not in ("", None):
        t.full_name = str(data["full_name"]).strip()
    if "phone" in data and data["phone"] not in ("", None):
        t.phone = str(data["phone"]).strip()
    if "email" in data:
        t.email = str(data["email"]).strip().lower() if data["email"] else None

    db.session.commit()
    return jsonify({"message": "tenant updated"})


@bp.route("/<int:tenant_id>", methods=["DELETE"])
@jwt_required()
def delete_tenant(tenant_id):
    t = Tenant.query.get_or_404(tenant_id)
    db.session.delete(t)
    db.session.commit()
    return jsonify({"message": "tenant deleted"})


@bp.route("/<int:tenant_id>/leases", methods=["GET"])
@jwt_required()
def tenant_leases(tenant_id):
    Tenant.query.get_or_404(tenant_id)

    leases = (
        Lease.query
        .filter_by(tenant_id=tenant_id)
        .order_by(Lease.id.desc())
        .all()
    )

    unit_ids = [l.unit_id for l in leases]
    units = Unit.query.filter(Unit.id.in_(unit_ids)).all() if unit_ids else []
    unit_map = {u.id: u for u in units}

    property_ids = list({u.property_id for u in units})
    props = Property.query.filter(Property.id.in_(property_ids)).all() if property_ids else []
    prop_map = {p.id: p for p in props}

    payload = []
    for l in leases:
        u = unit_map.get(l.unit_id)
        p = prop_map.get(u.property_id) if u else None

        payload.append({
            "id": l.id,
            "tenant_id": l.tenant_id,
            "unit_id": l.unit_id,
            "start_date": l.start_date.isoformat(),
            "end_date": l.end_date.isoformat() if l.end_date else None,
            "is_active": l.is_active,
            "unit": {
                "id": u.id,
                "property_id": u.property_id,
                "house_number": u.house_number,
                "rent": float(u.rent),
                "deposit": float(u.deposit),
                "garbage_fee": float(u.garbage_fee),
                "water_rate": float(u.water_rate),
                "property": {
                    "id": p.id,
                    "name": p.name,
                    "location": p.location,
                    "house_count": p.house_count,
                } if p else None
            } if u else None
        })

    return jsonify(payload)

