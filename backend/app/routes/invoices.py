from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import calendar
import json
from sqlalchemy import func

from ..extensions import db
from ..models import Tenant, Lease, Unit, Property, Payment, WaterReading, Invoice

bp = Blueprint("invoices", __name__, url_prefix="/api/invoices")


def _parse_date(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        raise ValueError("invalid_date")


def _d(x) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _money(x) -> str:
    q = _d(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{q:.2f}"


def _days_overlap(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if end < start:
        return 0
    return (end - start).days + 1


def _lease_active_range(lease: Lease) -> tuple[date, date]:
    start = lease.start_date
    end = lease.end_date or date(9999, 12, 31)
    return start, end


def _month_start(d0: date) -> date:
    return date(d0.year, d0.month, 1)


def _month_end(d0: date) -> date:
    last_day = calendar.monthrange(d0.year, d0.month)[1]
    return date(d0.year, d0.month, last_day)


def _add_month(d0: date) -> date:
    y = d0.year
    m = d0.month + 1
    if m == 13:
        y += 1
        m = 1
    return date(y, m, 1)


def _prorated_monthly_fee_for_range(monthly_fee: Decimal, range_start: date, range_end: date) -> Decimal:
    total = Decimal("0")
    cursor = _month_start(range_start)

    while cursor <= range_end:
        ms = cursor
        me = _month_end(cursor)
        seg_start = max(range_start, ms)
        seg_end = min(range_end, me)

        days_in_month = calendar.monthrange(cursor.year, cursor.month)[1]
        seg_days = (seg_end - seg_start).days + 1

        if seg_days > 0:
            part = (monthly_fee * Decimal(seg_days) / Decimal(days_in_month)).quantize(Decimal("0.01"))
            total += part

        cursor = _add_month(cursor)

    return total.quantize(Decimal("0.01"))


def _rent_for_period(lease: Lease, unit: Unit, period_start: date, period_end: date) -> Decimal:
    monthly_rent = _d(unit.rent)
    lease_start, lease_end = _lease_active_range(lease)
    overlap_days = _days_overlap(lease_start, lease_end, period_start, period_end)
    if overlap_days == 0:
        return Decimal("0")

    active_start = max(period_start, lease_start)
    active_end = min(period_end, lease_end)
    return _prorated_monthly_fee_for_range(monthly_rent, active_start, active_end)


def _garbage_for_period(lease: Lease, unit: Unit, period_start: date, period_end: date) -> Decimal:
    monthly_garbage = _d(unit.garbage_fee)
    lease_start, lease_end = _lease_active_range(lease)
    overlap_days = _days_overlap(lease_start, lease_end, period_start, period_end)
    if overlap_days == 0:
        return Decimal("0")

    active_start = max(period_start, lease_start)
    active_end = min(period_end, lease_end)
    return _prorated_monthly_fee_for_range(monthly_garbage, active_start, active_end)


def _deposit_amount(lease: Lease, unit: Unit) -> Decimal:
    dep = _d(lease.deposit_amount)
    if dep > 0:
        return dep
    return _d(unit.deposit)


def _period_key(d0: date) -> str:
    return f"{d0.year:04d}-{d0.month:02d}"


def _prev_period_key(d0: date) -> str:
    y = d0.year
    m = d0.month - 1
    if m == 0:
        y -= 1
        m = 12
    return f"{y:04d}-{m:02d}"


def _resolve_water_rate(unit: Unit) -> Decimal:
    if _d(unit.water_rate) > 0:
        return _d(unit.water_rate)
    prop = unit.property
    if prop is not None and _d(prop.water_rate_per_unit) > 0:
        return _d(prop.water_rate_per_unit)
    return Decimal("0")


def _water_charge_for_month(company_id: int, unit: Unit, month_key: str) -> dict | None:
    # Needs current and previous reading for usage
    prev_key = _prev_period_key(date(int(month_key[:4]), int(month_key[5:7]), 1))

    current = (
        db.session.query(WaterReading)
        .filter(
            WaterReading.company_id == company_id,
            WaterReading.unit_id == unit.id,
            WaterReading.period == month_key,
            WaterReading.deleted_at.is_(None),
        )
        .first()
    )

    prev = (
        db.session.query(WaterReading)
        .filter(
            WaterReading.company_id == company_id,
            WaterReading.unit_id == unit.id,
            WaterReading.period == prev_key,
            WaterReading.deleted_at.is_(None),
        )
        .first()
    )

    if current is None or prev is None:
        return None

    usage = _d(current.reading_value) - _d(prev.reading_value)
    if usage < 0:
        usage = Decimal("0")

    rate = _resolve_water_rate(unit)
    amount = (usage * rate).quantize(Decimal("0.01"))

    return {
        "code": "WATER",
        "name": "Water",
        "meta": {
            "period": month_key,
            "prev_period": prev_key,
            "prev_reading": _money(prev.reading_value),
            "current_reading": _money(current.reading_value),
            "usage_units": _money(usage),
            "rate": _money(rate),
        },
        "qty": _money(usage),
        "unit_price": _money(rate),
        "amount": _money(amount),
    }


def _latest_balance_snapshot(company_id: int, tenant_id: int, unit_id: int) -> dict:
    p = (
        db.session.query(Payment)
        .filter(
            Payment.tenant_id == tenant_id,
            Payment.unit_id == unit_id,
        )
        .order_by(Payment.paid_at.desc())
        .first()
    )

    if p is None:
        return {"balance_after": "0.00", "credit_after": "0.00", "as_of": None}

    return {
        "balance_after": _money(p.balance_after),
        "credit_after": _money(p.credit_after),
        "as_of": p.paid_at.isoformat() if p.paid_at else None,
    }


def _to_public_tenant(t: Tenant) -> dict:
    return {
        "id": t.id,
        "full_name": t.full_name,
        "email": t.email,
        "phone": t.phone,
    }


def _to_public_unit(u: Unit) -> dict:
    return {
        "id": u.id,
        "property_id": u.property_id,
        "house_number": u.house_number,
        "status": u.status,
        "rent": _money(u.rent),
        "garbage_fee": _money(u.garbage_fee),
        "water_rate": _money(u.water_rate),
        "deposit": _money(u.deposit),
    }


def _to_public_lease(l: Lease) -> dict:
    s, e = _lease_active_range(l)
    return {
        "id": l.id,
        "tenant_id": l.tenant_id,
        "unit_id": l.unit_id,
        "start_date": s.isoformat(),
        "end_date": None if e == date(9999, 12, 31) else e.isoformat(),
        "is_active": bool(l.is_active),
        "deposit_amount": _money(l.deposit_amount),
        "deposit_held": _money(l.deposit_held),
        "deposit_used": _money(l.deposit_used),
        "deposit_refunded": _money(l.deposit_refunded),
        "moved_out_at": l.moved_out_at.isoformat() if l.moved_out_at else None,
    }

def _parse_datetime(s: str) -> datetime:
    # Accepts "2026-02-10T12:30:00" or "2026-02-10 12:30:00"
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        raise ValueError("invalid_datetime")


def _invoice_number(company_id: int) -> str:
    # INV-202602-0007 per company
    now = datetime.utcnow()
    prefix = f"INV-{now.year:04d}{now.month:02d}-"

    last = (
        db.session.query(Invoice.invoice_number)
        .filter(
            Invoice.company_id == company_id,
            Invoice.invoice_number.like(prefix + "%"),
        )
        .order_by(Invoice.invoice_number.desc())
        .first()
    )

    if not last:
        seq = 1
    else:
        tail = str(last[0]).replace(prefix, "")
        try:
            seq = int(tail) + 1
        except Exception:
            seq = 1

    return prefix + f"{seq:04d}"



@bp.route("/preview", methods=["GET"])
@jwt_required()
def preview_invoice():
    claims = get_jwt()
    company_id = claims.get("company_id")

    lease_id = request.args.get("lease_id", type=int)
    period_start_s = request.args.get("period_start", type=str)
    period_end_s = request.args.get("period_end", type=str)
    include_deposit = request.args.get("include_deposit", default=0, type=int) == 1
    include_balance = request.args.get("include_balance", default=1, type=int) == 1

    if not company_id:
        return jsonify({"error": "missing_company_scope"}), 401

    if not lease_id or not period_start_s or not period_end_s:
        return jsonify({"error": "missing_required_params"}), 400

    try:
        period_start = _parse_date(period_start_s)
        period_end = _parse_date(period_end_s)
    except ValueError:
        return jsonify({"error": "invalid_date_format", "expected": "YYYY-MM-DD"}), 400

    if period_end < period_start:
        return jsonify({"error": "invalid_period"}), 400

    lease = (
        db.session.query(Lease)
        .filter(
            Lease.id == lease_id,
            Lease.company_id == company_id,
            Lease.deleted_at.is_(None),
        )
        .first()
    )
    if lease is None:
        return jsonify({"error": "lease_not_found"}), 404

    tenant = lease.tenant
    unit = lease.unit
    if tenant is None or unit is None:
        return jsonify({"error": "lease_missing_relations"}), 400

    if tenant.company_id != company_id or unit.company_id != company_id:
        return jsonify({"error": "forbidden"}), 403

    if unit.property is None:
        unit.property = (
            db.session.query(Property)
            .filter(
                Property.id == unit.property_id,
                Property.company_id == company_id,
                Property.deleted_at.is_(None),
            )
            .first()
        )

    line_items = []

    rent_amt = _rent_for_period(lease, unit, period_start, period_end)
    if rent_amt > 0:
        line_items.append({
            "code": "RENT",
            "name": "Rent",
            "qty": "1",
            "unit_price": _money(rent_amt),
            "amount": _money(rent_amt),
        })

    garbage_amt = _garbage_for_period(lease, unit, period_start, period_end)
    if garbage_amt > 0:
        line_items.append({
            "code": "GARBAGE",
            "name": "Garbage",
            "qty": "1",
            "unit_price": _money(garbage_amt),
            "amount": _money(garbage_amt),
        })

    month_key = _period_key(period_start)
    water_item = _water_charge_for_month(company_id, unit, month_key)
    if water_item is not None:
        if Decimal(water_item["amount"]) > 0:
            line_items.append(water_item)

    if include_deposit:
        dep = _deposit_amount(lease, unit)
        if dep > 0:
            line_items.append({
                "code": "DEPOSIT",
                "name": "Deposit",
                "qty": "1",
                "unit_price": _money(dep),
                "amount": _money(dep),
            })

    subtotal = sum(_d(li["amount"]) for li in line_items) if line_items else Decimal("0")
    total = subtotal

    balance = {"balance_after": "0.00", "credit_after": "0.00", "as_of": None}
    if include_balance:
        balance = _latest_balance_snapshot(company_id, tenant.id, unit.id)

        if _d(balance["balance_after"]) > 0:
            line_items.append({
                "code": "BALANCE",
                "name": "Previous balance",
                "qty": "1",
                "unit_price": balance["balance_after"],
                "amount": balance["balance_after"],
            })
            total += _d(balance["balance_after"])

        if _d(balance["credit_after"]) > 0:
            line_items.append({
                "code": "CREDIT",
                "name": "Credit",
                "qty": "1",
                "unit_price": f"-{_money(balance['credit_after'])}",
                "amount": f"-{_money(balance['credit_after'])}",
            })
            total -= _d(balance["credit_after"])

    payload = {
        "tenant": _to_public_tenant(tenant),
        "unit": _to_public_unit(unit),
        "lease": _to_public_lease(lease),
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "line_items": line_items,
        "totals": {
            "subtotal": _money(subtotal),
            "total": _money(total),
            "currency": "KES",
        },
        "balance_snapshot": balance,
        "meta": {
            "preview": True,
            "water_period": month_key,
        }
    }

    return jsonify(payload), 200

@bp.route("", methods=["POST"])
@jwt_required()
def create_invoice():
    claims = get_jwt()
    company_id = claims.get("company_id")
    if not company_id:
        return jsonify({"error": "missing_company_scope"}), 401

    data = request.get_json() or {}
    lease_id = data.get("lease_id")
    period_start_s = data.get("period_start")
    period_end_s = data.get("period_end")
    include_deposit = int(data.get("include_deposit", 0)) == 1

    issued_at_s = data.get("issued_at")
    due_date_s = data.get("due_date")

    if not lease_id or not period_start_s or not period_end_s:
        return jsonify({"error": "missing_required_fields"}), 400

    try:
        period_start = _parse_date(str(period_start_s))
        period_end = _parse_date(str(period_end_s))
    except ValueError:
        return jsonify({"error": "invalid_date_format", "expected": "YYYY-MM-DD"}), 400

    if period_end < period_start:
        return jsonify({"error": "invalid_period"}), 400

    lease = (
        db.session.query(Lease)
        .filter(
            Lease.id == int(lease_id),
            Lease.company_id == company_id,
            Lease.deleted_at.is_(None),
        )
        .first()
    )
    if lease is None:
        return jsonify({"error": "lease_not_found"}), 404

    tenant = lease.tenant
    unit = lease.unit
    if tenant is None or unit is None:
        return jsonify({"error": "lease_missing_relations"}), 400

    if tenant.company_id != company_id or unit.company_id != company_id:
        return jsonify({"error": "forbidden"}), 403

    dup = (
        db.session.query(Invoice.id)
        .filter(
            Invoice.company_id == company_id,
            Invoice.lease_id == lease.id,
            Invoice.period_start == period_start,
            Invoice.period_end == period_end,
            Invoice.deleted_at.is_(None),
        )
        .first()
    )
    if dup:
        return jsonify({"error": "invoice_already_exists_for_period"}), 409

    if issued_at_s:
        try:
            issued_at = _parse_datetime(str(issued_at_s))
        except ValueError:
            return jsonify({"error": "invalid_issued_at"}), 400
    else:
        issued_at = datetime.utcnow()

    if due_date_s:
        try:
            due_date = _parse_date(str(due_date_s))
        except ValueError:
            return jsonify({"error": "invalid_due_date"}), 400
    else:
        due_date = (issued_at.date() + timedelta(days=7))

    # Build line items using the same logic as preview
    line_items = []

    rent_amt = _rent_for_period(lease, unit, period_start, period_end)
    if rent_amt > 0:
        line_items.append({"code": "RENT", "name": "Rent", "qty": "1", "unit_price": _money(rent_amt), "amount": _money(rent_amt)})

    garbage_amt = _garbage_for_period(lease, unit, period_start, period_end)
    if garbage_amt > 0:
        line_items.append({"code": "GARBAGE", "name": "Garbage", "qty": "1", "unit_price": _money(garbage_amt), "amount": _money(garbage_amt)})

    month_key = _period_key(period_start)
    water_item = _water_charge_for_month(company_id, unit, month_key)
    if water_item is not None and _d(water_item["amount"]) > 0:
        line_items.append(water_item)

    if include_deposit:
        dep = _deposit_amount(lease, unit)
        if dep > 0:
            line_items.append({"code": "DEPOSIT", "name": "Deposit", "qty": "1", "unit_price": _money(dep), "amount": _money(dep)})

    subtotal = sum(_d(li["amount"]) for li in line_items) if line_items else Decimal("0")
    total = subtotal

    inv = Invoice(
        company_id=company_id,
        lease_id=lease.id,
        tenant_id=tenant.id,
        unit_id=unit.id,
        invoice_number=_invoice_number(company_id),
        status="issued",
        period_start=period_start,
        period_end=period_end,
        issued_at=issued_at,
        due_date=due_date,
        currency="KES",
        subtotal=subtotal,
        total=total,
        line_items_json=json.dumps(line_items),
        created_by_id=claims.get("sub") or claims.get("user_id"),
    )

    db.session.add(inv)
    db.session.commit()

    return jsonify({
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "status": inv.status,
        "issued_at": inv.issued_at.isoformat(),
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "period": {"start": inv.period_start.isoformat(), "end": inv.period_end.isoformat()},
        "tenant": _to_public_tenant(tenant),
        "unit": _to_public_unit(unit),
        "lease": _to_public_lease(lease),
        "line_items": line_items,
        "totals": {"subtotal": _money(inv.subtotal), "total": _money(inv.total), "currency": inv.currency},
    }), 201

@bp.route("", methods=["GET"])
@jwt_required()
def list_invoices():
    claims = get_jwt()
    company_id = claims.get("company_id")
    if not company_id:
        return jsonify({"error": "missing_company_scope"}), 401

    limit = request.args.get("limit", default=20, type=int)
    offset = request.args.get("offset", default=0, type=int)

    rows = (
        db.session.query(Invoice)
        .filter(
            Invoice.company_id == company_id,
            Invoice.deleted_at.is_(None),
        )
        .order_by(Invoice.issued_at.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )

    return jsonify({
        "items": [
            {
                "id": r.id,
                "invoice_number": r.invoice_number,
                "status": r.status,
                "issued_at": r.issued_at.isoformat(),
                "due_date": r.due_date.isoformat() if r.due_date else None,
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
                "tenant_id": r.tenant_id,
                "unit_id": r.unit_id,
                "subtotal": _money(r.subtotal),
                "total": _money(r.total),
                "currency": r.currency,
            }
            for r in rows
        ],
        "limit": limit,
        "offset": offset,
    }), 200

@bp.route("/<int:invoice_id>", methods=["GET"])
@jwt_required()
def get_invoice(invoice_id: int):
    claims = get_jwt()
    company_id = claims.get("company_id")
    if not company_id:
        return jsonify({"error": "missing_company_scope"}), 401

    inv = (
        db.session.query(Invoice)
        .filter(
            Invoice.id == invoice_id,
            Invoice.company_id == company_id,
            Invoice.deleted_at.is_(None),
        )
        .first()
    )
    if inv is None:
        return jsonify({"error": "invoice_not_found"}), 404

    lease = db.session.query(Lease).filter(Lease.id == inv.lease_id).first()
    tenant = db.session.query(Tenant).filter(Tenant.id == inv.tenant_id).first()
    unit = db.session.query(Unit).filter(Unit.id == inv.unit_id).first()

    try:
        line_items = json.loads(inv.line_items_json or "[]")
    except Exception:
        line_items = []

    return jsonify({
        "id": inv.id,
        "invoice_number": inv.invoice_number,
        "status": inv.status,
        "issued_at": inv.issued_at.isoformat(),
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "period": {"start": inv.period_start.isoformat(), "end": inv.period_end.isoformat()},
        "tenant": _to_public_tenant(tenant) if tenant else None,
        "unit": _to_public_unit(unit) if unit else None,
        "lease": _to_public_lease(lease) if lease else None,
        "line_items": line_items,
        "totals": {"subtotal": _money(inv.subtotal), "total": _money(inv.total), "currency": inv.currency},
    }), 200
