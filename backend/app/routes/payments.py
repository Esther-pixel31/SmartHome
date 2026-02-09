from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from ..utils.billing import _allocate_monthly

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt, get_jwt_identity

from ..extensions import db
from ..models import Payment, Tenant, Unit, Lease

bp = Blueprint("payments", __name__, url_prefix="/api/payments")


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


def _normalize_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _parse_month(value: str):
    # accepts "YYYY-MM" or "YYYY-MM-01"
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
        "water_paid": float(p.water_paid or 0),
        "garbage_paid": float(p.garbage_paid or 0),
        "rent_paid": float(p.rent_paid or 0),
        "balance_after": float(p.balance_after or 0),
        "credit_after": float(p.credit_after or 0),
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
    method = data.get("method") or None
    reference = data.get("reference") or None
    note = data.get("note") or None

    if not tenant_id or not unit_id or amount is None or not paid_for_month:
        return jsonify({"error": "missing_or_invalid_fields"}), 400
    if amount <= 0:
        return jsonify({"error": "invalid_amount"}), 400

    company_id, is_admin = _scope()

    tenant_q = Tenant.query.filter(Tenant.id == int(tenant_id), Tenant.deleted_at.is_(None))
    unit_q = Unit.query.filter(Unit.id == int(unit_id), Unit.deleted_at.is_(None))

    if not is_admin:
        tenant_q = tenant_q.filter(Tenant.company_id == company_id)
        unit_q = unit_q.filter(Unit.company_id == company_id)

    tenant = tenant_q.first()
    if not tenant:
        return jsonify({"error": "tenant_not_found"}), 404

    unit = unit_q.first()
    if not unit:
        return jsonify({"error": "unit_not_found"}), 404

    # require an active lease tying this tenant to this unit
    lease_q = (
        Lease.query
        .filter(
            Lease.tenant_id == tenant.id,
            Lease.unit_id == unit.id,
            Lease.is_active == True,
            Lease.deleted_at.is_(None),
        )
    )
    if not is_admin:
        lease_q = lease_q.filter(Lease.company_id == company_id)

    lease = lease_q.order_by(Lease.id.desc()).first()
    if not lease:
        return jsonify({"error": "no_active_lease_for_tenant_unit"}), 409

    rent_due = _parse_decimal(unit.rent) or Decimal("0.00")
    water_due = _parse_decimal(unit.water_rate) or Decimal("0.00")
    garbage_due = _parse_decimal(unit.garbage_fee) or Decimal("0.00")

    water_paid, garbage_paid, rent_paid, balance_after, credit_after = allocate_monthly(
    amount_paid=amount,
    rent_due=rent_due,
    water_due=water_due,
    garbage_due=garbage_due,
    )


    p = Payment(
        tenant_id=tenant.id,
        unit_id=unit.id,
        amount=amount,
        currency=currency,
        paid_for_month=_normalize_month(paid_for_month),
        water_paid=water_paid,
        garbage_paid=garbage_paid,
        rent_paid=rent_paid,
        balance_after=balance_after,
        credit_after=credit_after,
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
    company_id, is_admin = _scope()

    tenant_id = request.args.get("tenant_id", type=int)
    unit_id = request.args.get("unit_id", type=int)

    q = Payment.query

    if tenant_id:
        q = q.filter(Payment.tenant_id == tenant_id)
    if unit_id:
        q = q.filter(Payment.unit_id == unit_id)

    if not is_admin:
        # enforce company scope through joins
        q = (
            q.join(Tenant, Tenant.id == Payment.tenant_id)
             .filter(Tenant.company_id == company_id)
        )

    q = q.order_by(Payment.paid_at.desc())

    items = q.limit(200).all()
    return jsonify([_payment_to_dict(p) for p in items]), 200
