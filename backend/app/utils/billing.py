from decimal import Decimal

def _allocate_monthly(amount_paid: Decimal, rent_due: Decimal, water_due: Decimal, garbage_due: Decimal):
    remaining = amount_paid

    water_paid = min(water_due, remaining)
    remaining -= water_paid

    garbage_paid = min(garbage_due, remaining)
    remaining -= garbage_paid

    rent_paid = min(rent_due, remaining)
    remaining -= rent_paid

    total_due = rent_due + water_due + garbage_due
    total_applied = water_paid + garbage_paid + rent_paid

    balance_after = total_due - total_applied
    if balance_after < 0:
        balance_after = Decimal("0.00")

    credit_after = amount_paid - total_applied
    if credit_after < 0:
        credit_after = Decimal("0.00")

    return water_paid, garbage_paid, rent_paid, balance_after, credit_after

