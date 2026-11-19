from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


_CENT = Decimal("0.01")
_MAX_ANNUAL_CTC = Decimal("9999999999.99")


def normalize_annual_ctc(value):
    if isinstance(value, bool):
        raise ValueError("Annual CTC must be a non-negative amount.")

    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            raise ValueError("Annual CTC must be a non-negative finite amount.")
        amount = amount.quantize(_CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("Annual CTC must be a non-negative finite amount.") from exc

    if amount > _MAX_ANNUAL_CTC:
        raise ValueError("Annual CTC exceeds the maximum supported amount.")
    return amount
