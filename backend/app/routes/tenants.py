from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity
from datetime import datetime
import re

from ..extensions import db
from ..models import Tenant, Lease, Unit, Property
from ..utils.pagination import paginate
from ..utils.validation import require_fields

bp = Blueprint("tenants", __name__, url_prefix="/api/tenants")


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


def _clean_phone(phone: str):
    p = str(phone).strip()
    p = re.sub(r"\s+", "", p)
    if len(p) < 7:
        return None
    return p


@bp.route("", methods=["POST"])
@jwt_required()
def create_tenant():
    data = request.get_json()
    err = require_fields(data, ["full_name", "phone"])
    if err:
        return err

    phone = _clean_phone(data["phone"])
    if not phone:
        return jsonify({"error": "invalid_phone"}), 400

    email = None
    if data.get("email"):
        email = str(data["email"]).strip().lower()
        if "@" not in email:
            return jsonify({"error": "invalid_email"}), 400

    company_id, is_admin = _scope()
    user_id = int(get_jwt_identity())

    t = Tenant(
        full_name=str(data["full_name"]).strip(),
        phone=phone,
        email=email,
        company_id=company_id,
        created_by_id=user_id,
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({"id": t.id}), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_tenants():
    q = request.args.get("q", "").strip()
    query = _scoped_query(Tenant)

    if q:
        like = f"%{q}%"
        query = query.filter(
            (Tenant.full_name.ilike(like)) |
            (Tenant.phone.ilike(like))
        )

    query = query.order_by(Tenant.id.desc())
    items, meta, links = paginate(query)

    return jsonify({
        "items": [{
            "id": t.id,
            "full_name": t.full_name,
            "phone": t.phone,
            "email": t.email,
            "deleted_at": t.deleted_at.isoformat() if t.deleted_at else None,
        } for t in items],
        "meta": meta,
        "links": links,
    })


@bp.route("/<int:tenant_id>", methods=["GET"])
@jwt_required()
def get_tenant(tenant_id):
    t = _scoped_query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        return jsonify({"error": "not_found"}), 404

    return jsonify({
        "id": t.id,
        "full_name": t.full_name,
        "phone": t.phone,
        "email": t.email,
        "deleted_at": t.deleted_at.isoformat() if t.deleted_at else None,
    })


@bp.route("/<int:tenant_id>", methods=["PATCH"])
@jwt_required()
def patch_tenant(tenant_id):
    t = _scoped_query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json()
    if data is None:
        return jsonify({"error": "invalid_json"}), 400

    if "full_name" in data and data["full_name"] not in ("", None):
        t.full_name = str(data["full_name"]).strip()

    if "phone" in data and data["phone"] not in ("", None):
        phone = _clean_phone(data["phone"])
        if not phone:
            return jsonify({"error": "invalid_phone"}), 400
        t.phone = phone

    if "email" in data:
        if data["email"]:
            email = str(data["email"]).strip().lower()
            if "@" not in email:
                return jsonify({"error": "invalid_email"}), 400
            t.email = email
        else:
            t.email = None

    db.session.commit()
    return jsonify({"message": "tenant updated"}), 200


@bp.route("/<int:tenant_id>", methods=["DELETE"])
@jwt_required()
def delete_tenant(tenant_id):
    t = _scoped_query(Tenant).filter(Tenant.id == tenant_id).first()
    if not t:
        return jsonify({"error": "not_found"}), 404

    t.deleted_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "tenant deleted"}), 200


@bp.route("/<int:tenant_id>/leases", methods=["GET"])
@jwt_required()
def tenant_leases(tenant_id):
    company_id, is_admin = _scope()

    tenant = Tenant.query.filter(Tenant.id == tenant_id)
    if not is_admin:
        tenant = tenant.filter(Tenant.company_id == company_id)
    if not _include_deleted():
        tenant = tenant.filter(Tenant.deleted_at.is_(None))

    tenant = tenant.first()
    if not tenant:
        return jsonify({"error": "not_found"}), 404

    lq = Lease.query.filter(Lease.tenant_id == tenant_id)
    if not is_admin:
        lq = lq.filter(Lease.company_id == company_id)
    if not _include_deleted():
        lq = lq.filter(Lease.deleted_at.is_(None))

    leases = lq.order_by(Lease.id.desc()).all()

    unit_ids = [l.unit_id for l in leases]
    uq = Unit.query
    if unit_ids:
        uq = uq.filter(Unit.id.in_(unit_ids))
    else:
        uq = uq.filter(Unit.id == -1)

    if not is_admin:
        uq = uq.filter(Unit.company_id == company_id)
    if not _include_deleted():
        uq = uq.filter(Unit.deleted_at.is_(None))

    units = uq.all()
    unit_map = {u.id: u for u in units}

    property_ids = list({u.property_id for u in units})
    pq = Property.query
    if property_ids:
        pq = pq.filter(Property.id.in_(property_ids))
    else:
        pq = pq.filter(Property.id == -1)

    if not is_admin:
        pq = pq.filter(Property.company_id == company_id)
    if not _include_deleted():
        pq = pq.filter(Property.deleted_at.is_(None))

    props = pq.all()
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
