# yourapp/utils/water.py

from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from ..extensions import db
from ..models import WaterReading, Lease


def _to_decimal(value, name: str) -> Decimal:
    try:
        d = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError(f"invalid_{name}")
    if d < 0:
        raise ValueError(f"invalid_{name}")
    return d


def normalize_month(d: date) -> date:
    return date(d.year, d.month, 1)


def parse_month(value: str):
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


def latest_unit_reading(unit_id: int):
    return (
        WaterReading.query
        .filter(WaterReading.unit_id == unit_id)
        .order_by(WaterReading.reading_month.desc(), WaterReading.id.desc())
        .first()
    )


def compute_usage_and_amount(previous: Decimal, current: Decimal, rate: Decimal):
    previous = _to_decimal(previous, "previous_reading")
    current = _to_decimal(current, "current_reading")
    rate = _to_decimal(rate, "rate_per_unit")

    if current < previous:
        raise ValueError("reading_less_than_previous")

    usage = current - previous
    amount = usage * rate
    return usage, amount


def active_tenant_id_for_unit(unit_id: int):
    lease = (
        Lease.query
        .filter(
            Lease.unit_id == unit_id,
            Lease.is_active == True,
            Lease.deleted_at.is_(None),
        )
        .order_by(Lease.id.desc())
        .first()
    )
    return lease.tenant_id if lease else None


def get_water_reading_for_month(unit_id: int, month_start: date):
    month_start = normalize_month(month_start)
    return (
        WaterReading.query
        .filter(
            WaterReading.unit_id == unit_id,
            WaterReading.reading_month == month_start,
        )
        .first()
    )


def create_water_reading(
    unit,
    current_reading,
    reading_month: date,
    tenant_id=None,
    note=None,
):
    """
    What this does (monthly rule):
    - Enforces 1 reading per unit per month (unit_id + reading_month must be unique).
    - Finds the previous reading for the unit (latest past month).
    - usage = current_reading - previous_reading
    - amount = usage * property.water_rate_per_unit
    - Saves one WaterReading row with previous, usage, rate, and amount frozen for that month.
    - If tenant_id not provided, links the reading to the active lease tenant for reporting.
    """

    current_reading = _to_decimal(current_reading, "reading_value")
    reading_month = normalize_month(reading_month)

    exists = get_water_reading_for_month(unit.id, reading_month)
    if exists:
        raise ValueError("reading_already_exists_for_month")

    last = latest_unit_reading(unit.id)
    previous = _to_decimal(last.reading_value, "previous_reading") if last else Decimal("0.00")

    rate = _to_decimal(unit.property.water_rate_per_unit, "rate_per_unit")
    usage, amount = compute_usage_and_amount(previous, current_reading, rate)

    if tenant_id is None:
        tenant_id = active_tenant_id_for_unit(unit.id)

    row = WaterReading(
        unit_id=unit.id,
        tenant_id=tenant_id,
        reading_month=reading_month,
        reading_value=current_reading,
        prev_reading_value=previous,
        usage_units=usage,
        rate_per_unit=rate,
        amount=amount,
        note=note,
    )

    db.session.add(row)
    db.session.commit()
    return row
