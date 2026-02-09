from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from ..extensions import db
from ..models import WaterReading, Unit, Tenant, Lease
from ..utils.water import create_water_reading

bp = Blueprint("water_readings", __name__, url_prefix="/api/water-readings")


def _scope():
    claims = get_jwt()
    role = claims.get("role", "viewer")
    company_id = claims.get("company_id")
    is_admin = role == "admin"
    return company_id, is_admin


def _parse_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _month_range(d: date):
    start = date(d.year, d.month, 1)
    if d.month == 12:
        end = date(d.year + 1, 1, 1)
    else:
        end = date(d.year, d.month + 1, 1)
    return start, end


def _water_to_dict(r: WaterReading):
    return {
        "id": r.id,
        "unit_id": r.unit_id,
        "tenant_id": r.tenant_id,
        "reading_value": float(r.reading_value),
        "prev_reading_value": float(r.prev_reading_value),
        "usage_units": float(r.usage_units),
        "rate_per_unit": float(r.rate_per_unit),
        "amount": float(r.amount),
        "reading_at": r.reading_at.isoformat() + "Z",
        "note": r.note,
        "created_at": r.created_at.isoformat() + "Z",
    }


def _get_unit_scoped(unit_id: int, company_id, is_admin):
    q = Unit.query.filter(Unit.id == int(unit_id), Unit.deleted_at.is_(None))
    if not is_admin:
        q = q.filter(Unit.company_id == company_id)
    return q.first()


def _get_reading_scoped(reading_id: int, company_id, is_admin):
    q = (
        WaterReading.query
        .join(Unit, Unit.id == WaterReading.unit_id)
        .filter(WaterReading.id == int(reading_id), Unit.deleted_at.is_(None))
    )
    if not is_admin:
        q = q.filter(Unit.company_id == company_id)
    return q.first()


def _previous_reading_before(unit_id: int, reading_at, exclude_id: int):
    return (
        WaterReading.query
        .filter(
            WaterReading.unit_id == unit_id,
            WaterReading.id != exclude_id,
            WaterReading.reading_at < reading_at,
        )
        .order_by(WaterReading.reading_at.desc(), WaterReading.id.desc())
        .first()
    )


def _next_reading_after(unit_id: int, reading_at, exclude_id: int):
    return (
        WaterReading.query
        .filter(
            WaterReading.unit_id == unit_id,
            WaterReading.id != exclude_id,
            WaterReading.reading_at > reading_at,
        )
        .order_by(WaterReading.reading_at.asc(), WaterReading.id.asc())
        .first()
    )


def _recompute_row(row: WaterReading, unit):
    prev = _previous_reading_before(unit.id, row.reading_at, row.id)
    prev_value = Decimal(str(prev.reading_value)) if prev else Decimal("0.00")

    current_value = Decimal(str(row.reading_value))
    if current_value < prev_value:
        raise ValueError("reading_less_than_previous")

    usage = current_value - prev_value
    rate = Decimal(str(unit.property.water_rate_per_unit))
    amount = usage * rate

    row.prev_reading_value = prev_value
    row.usage_units = usage
    row.rate_per_unit = rate
    row.amount = amount


def _month_duplicate_exists(unit_id: int, reading_at, exclude_id: int):
    start, end = _month_range(reading_at.date())
    return (
        WaterReading.query
        .filter(
            WaterReading.unit_id == unit_id,
            WaterReading.id != exclude_id,
            WaterReading.reading_at >= start,
            WaterReading.reading_at < end,
        )
        .first()
    )


@bp.post("")
@jwt_required()
def add_water_reading():
    data = request.get_json(silent=True) or {}

    unit_id = data.get("unit_id")
    tenant_id = data.get("tenant_id")
    reading_value = _parse_decimal(data.get("reading_value"))
    note = data.get("note") or None

    if not unit_id or reading_value is None:
        return jsonify({"error": "missing_or_invalid_fields"}), 400

    company_id, is_admin = _scope()

    unit = _get_unit_scoped(unit_id, company_id, is_admin)
    if not unit:
        return jsonify({"error": "unit_not_found"}), 404

    today = date.today()
    month_start, month_end = _month_range(today)

    existing = (
        WaterReading.query
        .filter(
            WaterReading.unit_id == unit.id,
            WaterReading.reading_at >= month_start,
            WaterReading.reading_at < month_end,
        )
        .first()
    )
    if existing:
        return jsonify({"error": "reading_already_exists_for_month"}), 409

    if tenant_id:
        tenant_q = Tenant.query.filter(Tenant.id == int(tenant_id), Tenant.deleted_at.is_(None))
        if not is_admin:
            tenant_q = tenant_q.filter(Tenant.company_id == company_id)
        tenant = tenant_q.first()
        if not tenant:
            return jsonify({"error": "tenant_not_found"}), 404

        lease_q = (
            Lease.query
            .filter(
                Lease.unit_id == unit.id,
                Lease.tenant_id == tenant.id,
                Lease.is_active == True,
                Lease.deleted_at.is_(None),
            )
        )
        if not is_admin:
            lease_q = lease_q.filter(Lease.company_id == company_id)

        lease = lease_q.order_by(Lease.id.desc()).first()
        if not lease:
            return jsonify({"error": "no_active_lease_for_tenant_unit"}), 409

    try:
        row = create_water_reading(
            unit=unit,
            current_reading=reading_value,
            tenant_id=int(tenant_id) if tenant_id else None,
            note=note,
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    return jsonify(_water_to_dict(row)), 201


@bp.get("")
@jwt_required()
def list_water_readings():
    company_id, is_admin = _scope()

    unit_id = request.args.get("unit_id", type=int)
    tenant_id = request.args.get("tenant_id", type=int)

    q = WaterReading.query

    if unit_id:
        q = q.filter(WaterReading.unit_id == unit_id)
    if tenant_id:
        q = q.filter(WaterReading.tenant_id == tenant_id)

    if not is_admin:
        q = (
            q.join(Unit, Unit.id == WaterReading.unit_id)
             .filter(Unit.company_id == company_id)
        )

    q = q.order_by(WaterReading.reading_at.desc())

    items = q.limit(200).all()
    return jsonify([_water_to_dict(r) for r in items]), 200


@bp.get("/<int:reading_id>")
@jwt_required()
def view_water_reading(reading_id: int):
    company_id, is_admin = _scope()

    row = _get_reading_scoped(reading_id, company_id, is_admin)
    if not row:
        return jsonify({"error": "water_reading_not_found"}), 404

    return jsonify(_water_to_dict(row)), 200


@bp.patch("/<int:reading_id>")
@jwt_required()
def update_water_reading(reading_id: int):
    company_id, is_admin = _scope()

    row = _get_reading_scoped(reading_id, company_id, is_admin)
    if not row:
        return jsonify({"error": "water_reading_not_found"}), 404

    unit = _get_unit_scoped(row.unit_id, company_id, is_admin)
    if not unit:
        return jsonify({"error": "unit_not_found"}), 404

    data = request.get_json(silent=True) or {}

    if "reading_value" not in data:
        return jsonify({"error": "reading_value_required"}), 400

    new_value = _parse_decimal(data.get("reading_value"))
    if new_value is None:
        return jsonify({"error": "invalid_reading_value"}), 400

    row.reading_value = new_value

    try:
        _recompute_row(row, unit)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    next_row = _next_reading_after(unit.id, row.reading_at, row.id)
    if next_row:
        try:
            _recompute_row(next_row, unit)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        db.session.add(next_row)

    db.session.add(row)
    db.session.commit()

    return jsonify(_water_to_dict(row)), 200


@bp.delete("/<int:reading_id>")
@jwt_required()
def delete_water_reading(reading_id: int):
    company_id, is_admin = _scope()

    row = _get_reading_scoped(reading_id, company_id, is_admin)
    if not row:
        return jsonify({"error": "water_reading_not_found"}), 404

    unit = _get_unit_scoped(row.unit_id, company_id, is_admin)
    if not unit:
        return jsonify({"error": "unit_not_found"}), 404

    next_row = _next_reading_after(unit.id, row.reading_at, row.id)

    db.session.delete(row)

    if next_row:
        try:
            _recompute_row(next_row, unit)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        db.session.add(next_row)

    db.session.commit()

    return jsonify({"status": "deleted"}), 200

