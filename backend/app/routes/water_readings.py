from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt

from ..extensions import db
from ..models import WaterReading, Unit, Tenant, Lease

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

def _parse_period(val):
    s = str(val or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}", s):
        return None
    year = int(s[0:4])
    month = int(s[5:7])
    if month < 1 or month > 12:
        return None
    return s

def _month_range(d: date):
    start = date(d.year, d.month, 1)
    if d.month == 12:
        end = date(d.year + 1, 1, 1)
    else:
        end = date(d.year, d.month + 1, 1)
    return start, end


def _reading_payload(unit, current, previous):
    prev_val = Decimal(str(previous.reading_value)) if previous else Decimal("0.00")
    cur_val = Decimal(str(current.reading_value)) if current else None

    usage = Decimal("0.00")
    if cur_val is not None:
        if cur_val < prev_val:
            return None, ("reading_less_than_previous", prev_val, cur_val)
        usage = cur_val - prev_val

    rate = Decimal(str(unit.water_rate or 0))
    amount = usage * rate

    return {
        "unit_id": unit.id,
        "property_id": unit.property_id,
        "house_number": unit.house_number,
        "period": current.period if current else None,
        "previous_reading": float(prev_val),
        "current_reading": float(cur_val) if cur_val is not None else None,
        "units_consumed": float(usage),
        "water_rate": float(rate),
        "water_amount": float(amount),
        "current_reading_at": current.reading_at.isoformat() + "Z" if current else None,
    }, None



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
    rate = Decimal(str)
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


def _get_current_and_previous(unit_id: int, period: str, company_id, is_admin):
    q = WaterReading.query.filter(
        WaterReading.unit_id == unit_id,
        WaterReading.deleted_at.is_(None),
    )
    if not is_admin:
        q = q.filter(WaterReading.company_id == company_id)

    current = q.filter(WaterReading.period == period).first()

    previous = (
        q.filter(WaterReading.period < period)
         .order_by(WaterReading.period.desc(), WaterReading.id.desc())
         .first()
    )
    return current, previous

def _water_to_dict(r: WaterReading):
    return {
        "id": r.id,
        "unit_id": r.unit_id,
        "tenant_id": r.tenant_id,
        "company_id": r.company_id,
        "period": r.period,
        "reading_value": float(r.reading_value),
        "reading_at": r.reading_at.isoformat() + "Z",
        "note": r.note,
        "created_at": r.created_at.isoformat() + "Z",
        "deleted_at": r.deleted_at.isoformat() + "Z" if getattr(r, "deleted_at", None) else None,
    }


@bp.post("")
@jwt_required()
def add_water_reading():
    data = request.get_json(silent=True) or {}

    unit_id = data.get("unit_id")
    tenant_id = data.get("tenant_id")
    reading_value = _parse_decimal(data.get("reading_value"))
    period = _parse_period(data.get("period"))
    note = data.get("note") or None

    if not unit_id or reading_value is None or not period:
        return jsonify({"error": "missing_or_invalid_fields"}), 400

    if reading_value < 0:
        return jsonify({"error": "invalid_reading_value"}), 400

    company_id, is_admin = _scope()

    unit = _get_unit_scoped(unit_id, company_id, is_admin)
    if not unit:
        return jsonify({"error": "unit_not_found"}), 404

    # Validate tenant belongs to an active lease in this unit (optional)
    if tenant_id:
        tenant_q = Tenant.query.filter(Tenant.id == int(tenant_id), Tenant.deleted_at.is_(None))
        if not is_admin:
            tenant_q = tenant_q.filter(Tenant.company_id == company_id)
        tenant = tenant_q.first()
        if not tenant:
            return jsonify({"error": "tenant_not_found"}), 404

        lease_q = Lease.query.filter(
            Lease.unit_id == unit.id,
            Lease.tenant_id == tenant.id,
            Lease.is_active == True,
            Lease.deleted_at.is_(None),
        )
        if not is_admin:
            lease_q = lease_q.filter(Lease.company_id == company_id)

        lease = lease_q.order_by(Lease.id.desc()).first()
        if not lease:
            return jsonify({"error": "no_active_lease_for_tenant_unit"}), 409

    # Get existing row for the same unit + period (upsert)
    existing = WaterReading.query.filter(
        WaterReading.unit_id == unit.id,
        WaterReading.period == period,
        WaterReading.deleted_at.is_(None),
    )
    if not is_admin:
        existing = existing.filter(WaterReading.company_id == company_id)

    row = existing.first()

    # Validate reading does not go below the previous period reading
    current, previous = _get_current_and_previous(unit.id, period, company_id, is_admin)

    # If updating this period, ignore this row when deciding "previous"
    # previous is already period < period, so it is safe even on update
    if previous:
        prev_val = Decimal(str(previous.reading_value))
        if reading_value < prev_val:
            return jsonify({
                "error": "reading_less_than_previous",
                "previous_reading": float(prev_val),
            }), 409

    if row:
        row.reading_value = reading_value
        row.reading_at = datetime.utcnow()
        row.tenant_id = int(tenant_id) if tenant_id else None
        row.note = note
        db.session.add(row)
    else:
        row = WaterReading(
            unit_id=unit.id,
            tenant_id=int(tenant_id) if tenant_id else None,
            company_id=unit.company_id,
            period=period,
            reading_value=reading_value,
            reading_at=datetime.utcnow(),
            note=note,
            created_at=datetime.utcnow(),
        )
        db.session.add(row)

    db.session.commit()
    return jsonify({
        "id": row.id,
        "unit_id": unit.id,
        "period": period,
        "reading_value": float(row.reading_value),
    }), 201


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

    data = request.get_json(silent=True) or {}

    if "reading_value" not in data:
        return jsonify({"error": "reading_value_required"}), 400

    new_value = _parse_decimal(data.get("reading_value"))
    if new_value is None or new_value < 0:
        return jsonify({"error": "invalid_reading_value"}), 400

    row.reading_value = new_value
    row.reading_at = datetime.utcnow()

    if "note" in data:
        row.note = data.get("note") or None

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

    row.deleted_at = datetime.utcnow()
    db.session.add(row)
    db.session.commit()

    return jsonify({"status": "deleted"}), 200


@bp.get("/for-unit")
@jwt_required()
def water_for_unit_period():
    company_id, is_admin = _scope()
    unit_id = request.args.get("unit_id", type=int)
    period = _parse_period(request.args.get("period"))

    if not unit_id or not period:
        return jsonify({"error": "missing_or_invalid_fields"}), 400

    unit = _get_unit_scoped(unit_id, company_id, is_admin)
    if not unit:
        return jsonify({"error": "unit_not_found"}), 404

    current, previous = _get_current_and_previous(unit.id, period, company_id, is_admin)
    payload, err = _reading_payload(unit, current, previous)
    if err:
        msg, prev_val, cur_val = err
        return jsonify({
            "error": msg,
            "previous_reading": float(prev_val),
            "current_reading": float(cur_val),
        }), 409

    payload["period"] = period
    return jsonify(payload), 200
