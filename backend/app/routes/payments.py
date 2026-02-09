from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from ..extensions import db
from ..models import Payment, Tenant, Unit

bp = Blueprint("payments", __name__, url_prefix="/api/payments")

def _parse_decimal(value):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None

def _parse_month(value: str):
    # accept "YYYY-MM" or "YYYY-MM-01"
    if not value or not isinstance(value, str):
        return None
    try:
        if len(value) == 7:
            y, m = value.split("-")
            return date(int(y), int(m), 1)
        d = datetime.strptime(value, "%Y-%m-%d").date()
        return date(d.year, d.month, 1)
    except Exception:
        return None

def _payment_to_dict(p: Payment):
    return {
        "id": p.id,
        "tenant_id": p.tenant_id,
        "unit_id": p.unit_id,
        "amount": float(p.amount),
        "currency": p.currency,
        "paid_for_month": p.paid_for_month.isoformat(),
        "paid_at": p.paid_at.isoformat() + "Z",
        "method": p.method,
        "reference": p.reference,
        "note": p.note,
        "created_at": p.created_at.isoformat() + "Z",
    }

@bp.post("")
@jwt_required()
def create_payment():
    data = request.get_json(silent=True) or {}

    tenant_id = data.get("tenant_id")
    unit_id = data.get("unit_id")
    amount = _parse_decimal(data.get("amount"))
    currency = (data.get("currency") or "KES").strip().upper()
    paid_for_month = _parse_month(data.get("paid_for_month"))
    method = (data.get("method") or None)
    reference = (data.get("reference") or None)
    note = (data.get("note") or None)

    if not tenant_id or not unit_id or amount is None or not paid_for_month:
        return jsonify({"error": "missing_or_invalid_fields"}), 400

    if amount <= 0:
        return jsonify({"error": "invalid_amount"}), 400

    tenant = Tenant.query.get(tenant_id)
    if not tenant:
        return jsonify({"error": "tenant_not_found"}), 404

    unit = Unit.query.get(unit_id)
    if not unit:
        return jsonify({"error": "unit_not_found"}), 404

    # optional safety: tenant must belong to the unit
    if getattr(tenant, "unit_id", None) and tenant.unit_id != unit.id:
        return jsonify({"error": "tenant_not_in_unit"}), 409

    p = Payment(
        tenant_id=tenant.id,
        unit_id=unit.id,
        amount=amount,
        currency=currency,
        paid_for_month=Payment.normalize_month(paid_for_month),
        method=method,
        reference=reference,
        note=note,
    )
    db.session.add(p)
    db.session.commit()

    return jsonify(_payment_to_dict(p)), 201

@bp.get("")
@jwt_required()
def list_payments():
    tenant_id = request.args.get("tenant_id", type=int)
    unit_id = request.args.get("unit_id", type=int)

    q = Payment.query

    if tenant_id:
        q = q.filter(Payment.tenant_id == tenant_id)
    if unit_id:
        q = q.filter(Payment.unit_id == unit_id)

    q = q.order_by(Payment.paid_at.desc())

    items = q.limit(200).all()
    return jsonify([_payment_to_dict(p) for p in items]), 200
