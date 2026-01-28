from datetime import date, datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from ..extensions import db
from ..models import Lease, Tenant, Unit
from ..utils.validation import require_fields
from ..utils.pagination import paginate

bp = Blueprint("leases", __name__, url_prefix="/api/leases")


def _scope():
    claims = get_jwt()
    role = claims.get("role", "viewer")
    company_id = claims.get("company_id")
    is_admin = role == "admin"
    return company_id, is_admin


def _include_deleted():
    raw = str(request.args.get("include_deleted", "")).strip().lower()
    return raw in ("1", "true", "yes", "y")


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


def _tenant_in_scope(tenant_id: int):
    company_id, is_admin = _scope()
    q = Tenant.query.filter(Tenant.id == tenant_id)
    if not is_admin:
        q = q.filter(Tenant.company_id == company_id)
    q = q.filter(Tenant.deleted_at.is_(None))
    return q.first()


def _unit_in_scope(unit_id: int):
    company_id, is_admin = _scope()
    q = Unit.query.filter(Unit.id == unit_id)
    if not is_admin:
        q = q.filter(Unit.company_id == company_id)
    q = q.filter(Unit.deleted_at.is_(None))
    return q.first()


def _leases_base_query():
    company_id, is_admin = _scope()
    q = Lease.query
    if not is_admin:
        q = q.filter(Lease.company_id == company_id)
    if not _include_deleted():
        q = q.filter(Lease.deleted_at.is_(None))
    return q


def _overlaps(a_start, a_end, b_start, b_end):
    a_end_eff = a_end
    b_end_eff = b_end
    if a_end_eff is None:
        a_end_eff = date.max
    if b_end_eff is None:
        b_end_eff = date.max
    return a_start <= b_end_eff and b_start <= a_end_eff


@bp.route("", methods=["POST"])
@jwt_required()
def create_lease():
    data = request.get_json()
    err = require_fields(data, ["tenant_id", "unit_id", "start_date"])
    if err:
        return err

    tenant_id = int(data["tenant_id"])
    unit_id = int(data["unit_id"])

    t = _tenant_in_scope(tenant_id)
    if not t:
        return jsonify({"error": "tenant_not_found"}), 404

    u = _unit_in_scope(unit_id)
    if not u:
        return jsonify({"error": "unit_not_found"}), 404

    start = parse_date(data["start_date"], "start_date")
    if not start:
        return jsonify({"error": "invalid_date", "field": "start_date"}), 400

    end = None
    if data.get("end_date"):
        end = parse_date(data.get("end_date"), "end_date")
        if not end:
            return jsonify({"error": "invalid_date", "field": "end_date"}), 400
        if end < start:
            return jsonify({"error": "end_before_start"}), 400

    company_id, is_admin = _scope()
    user_id = int(get_jwt_identity())

    existing = (
        Lease.query
        .filter(Lease.unit_id == unit_id)
        .filter(Lease.deleted_at.is_(None))
    )
    if not is_admin:
        existing = existing.filter(Lease.company_id == company_id)

    existing = existing.order_by(Lease.id.desc()).all()

    for e in existing:
        if _overlaps(start, end, e.start_date, e.end_date):
            return jsonify({"error": "overlapping_lease", "lease_id": e.id}), 409

    active_exists = (
        Lease.query
        .filter(Lease.unit_id == unit_id, Lease.is_active == True)
        .filter(Lease.deleted_at.is_(None))
    )
    if not is_admin:
        active_exists = active_exists.filter(Lease.company_id == company_id)

    active_exists = active_exists.first()
    if active_exists:
        return jsonify({"error": "unit_already_leased", "lease_id": active_exists.id}), 409

    lease = Lease(
        tenant_id=tenant_id,
        unit_id=unit_id,
        start_date=start,
        end_date=end,
        is_active=True,
        company_id=u.company_id,
        created_by_id=user_id,
    )
    db.session.add(lease)
    db.session.commit()
    return jsonify({"id": lease.id}), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_leases():
    active = request.args.get("active")
    query = _leases_base_query()

    if active in ("true", "false"):
        query = query.filter(Lease.is_active == (active == "true"))

    query = query.order_by(Lease.id.desc())
    items, meta, links = paginate(query)

    return jsonify({
        "items": [{
            "id": l.id,
            "tenant_id": l.tenant_id,
            "unit_id": l.unit_id,
            "start_date": l.start_date.isoformat(),
            "end_date": l.end_date.isoformat() if l.end_date else None,
            "is_active": l.is_active,
            "deleted_at": l.deleted_at.isoformat() if l.deleted_at else None,
        } for l in items],
        "meta": meta,
        "links": links,
    })


@bp.route("/<int:lease_id>/end", methods=["POST"])
@jwt_required()
def end_lease(lease_id):
    company_id, is_admin = _scope()

    q = Lease.query.filter(Lease.id == lease_id)
    if not is_admin:
        q = q.filter(Lease.company_id == company_id)
    q = q.filter(Lease.deleted_at.is_(None))
    l = q.first()
    if not l:
        return jsonify({"error": "not_found"}), 404

    data = request.get_json() or {}
    end_d = parse_date(data.get("end_date"), "end_date") if data.get("end_date") else date.today()
    if not end_d:
        return jsonify({"error": "invalid_date", "field": "end_date"}), 400

    if l.start_date and end_d < l.start_date:
        return jsonify({"error": "end_before_start"}), 400

    l.end_date = end_d
    l.is_active = False

    others = (
        Lease.query
        .filter(
            Lease.unit_id == l.unit_id,
            Lease.is_active == True,
            Lease.id != l.id,
            Lease.deleted_at.is_(None),
        )
    )
    if not is_admin:
        others = others.filter(Lease.company_id == company_id)

    others = others.all()
    for o in others:
        o.is_active = False
        if o.end_date is None or o.end_date > end_d:
            o.end_date = end_d

    db.session.commit()
    return jsonify({"message": "lease ended"}), 200


@bp.route("/unit/<int:unit_id>/current", methods=["GET"])
@jwt_required()
def current_lease_for_unit(unit_id):
    u = _unit_in_scope(unit_id)
    if not u:
        return jsonify({"error": "unit_not_found"}), 404

    company_id, is_admin = _scope()

    q = (
        Lease.query
        .filter(Lease.unit_id == unit_id, Lease.is_active == True)
        .filter(Lease.deleted_at.is_(None))
    )
    if not is_admin:
        q = q.filter(Lease.company_id == company_id)

    l = q.order_by(Lease.id.desc()).first()
    if not l:
        return jsonify({"unit_id": unit_id, "current_lease": None}), 200

    t_q = Tenant.query.filter(Tenant.id == l.tenant_id)
    if not is_admin:
        t_q = t_q.filter(Tenant.company_id == company_id)
    t_q = t_q.filter(Tenant.deleted_at.is_(None))
    t = t_q.first()

    return jsonify({
        "unit_id": unit_id,
        "current_lease": {
            "id": l.id,
            "tenant_id": l.tenant_id,
            "start_date": l.start_date.isoformat(),
            "end_date": l.end_date.isoformat() if l.end_date else None,
            "is_active": l.is_active,
            "tenant": {
                "id": t.id,
                "full_name": t.full_name,
                "email": t.email,
                "phone": t.phone,
            } if t else None
        }
    }), 200
