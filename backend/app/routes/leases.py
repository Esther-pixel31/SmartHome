from datetime import date
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from ..extensions import db
from ..models import Lease, Tenant, Unit
from ..utils.validation import require_fields

bp = Blueprint("leases", __name__, url_prefix="/api/leases")


def parse_date(value, field):
    try:
        return date.fromisoformat(str(value))
    except Exception:
        return None


@bp.route("", methods=["POST"])
@jwt_required()
def create_lease():
    data = request.get_json()
    err = require_fields(data, ["tenant_id", "unit_id", "start_date"])
    if err:
        return err

    tenant_id = int(data["tenant_id"])
    unit_id = int(data["unit_id"])

    Tenant.query.get_or_404(tenant_id)
    Unit.query.get_or_404(unit_id)

    start_date = parse_date(data["start_date"], "start_date")
    if not start_date:
        return jsonify({"error": "invalid_date", "field": "start_date"}), 400

    active_exists = Lease.query.filter_by(unit_id=unit_id, is_active=True).first()
    if active_exists:
        return jsonify({"error": "unit_already_leased", "lease_id": active_exists.id}), 409

    lease = Lease(
        tenant_id=tenant_id,
        unit_id=unit_id,
        start_date=start_date,
        end_date=parse_date(data.get("end_date"), "end_date") if data.get("end_date") else None,
        is_active=True,
    )
    db.session.add(lease)
    db.session.commit()
    return jsonify({"id": lease.id}), 201


@bp.route("", methods=["GET"])
@jwt_required()
def list_leases():
    active = request.args.get("active")
    query = Lease.query
    if active in ("true", "false"):
        query = query.filter_by(is_active=(active == "true"))

    items = query.order_by(Lease.id.desc()).all()
    return jsonify([{
        "id": l.id,
        "tenant_id": l.tenant_id,
        "unit_id": l.unit_id,
        "start_date": l.start_date.isoformat(),
        "end_date": l.end_date.isoformat() if l.end_date else None,
        "is_active": l.is_active,
    } for l in items])


@bp.route("/<int:lease_id>/end", methods=["POST"])
@jwt_required()
def end_lease(lease_id):
    l = Lease.query.get_or_404(lease_id)
    data = request.get_json() or {}

    end_date = parse_date(data.get("end_date"), "end_date") if data.get("end_date") else date.today()

    if l.start_date and end_date < l.start_date:
        return jsonify({"error": "end_before_start"}), 400

    l.end_date = end_date
    l.is_active = False

    others = Lease.query.filter(
        Lease.unit_id == l.unit_id,
        Lease.is_active == True,
        Lease.id != l.id
    ).all()
    for o in others:
        o.is_active = False
        if o.end_date is None:
            o.end_date = end_date

    db.session.commit()
    return jsonify({"message": "lease ended"})


