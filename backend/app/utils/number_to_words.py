"""Indian-numbering-system (lakh/crore) number-to-words, matching the
'INR Forty Nine Thousand Eight Hundred Fifty Five Rupees Only/-' style
used on the reference invoices."""

_ONES = [
    "", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
    "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
    "Seventeen", "Eighteen", "Nineteen",
]
_TENS = [
    "", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety",
]


def _two_digits(n):
    if n < 20:
        return _ONES[n]
    return (_TENS[n // 10] + (" " + _ONES[n % 10] if n % 10 else "")).strip()


def _three_digits(n):
    if n >= 100:
        return (_ONES[n // 100] + " Hundred" + (" " + _two_digits(n % 100) if n % 100 else "")).strip()
    return _two_digits(n)


def number_to_words_inr(amount):
    """amount: float or int rupees. Returns e.g. 'Forty Nine Thousand Eight
    Hundred Fifty Five Rupees Only'."""
    rupees = int(round(amount))
    paise = int(round((amount - int(amount)) * 100))

    if rupees == 0:
        words = "Zero"
    else:
        parts = []
        crore, rupees = divmod(rupees, 10_000_000)
        lakh, rupees = divmod(rupees, 100_000)
        thousand, rupees = divmod(rupees, 1000)
        hundred = rupees

        if crore:
            parts.append(_three_digits(crore) + " Crore")
        if lakh:
            parts.append(_three_digits(lakh) + " Lakh")
        if thousand:
            parts.append(_three_digits(thousand) + " Thousand")
        if hundred:
            parts.append(_three_digits(hundred))
        words = " ".join(parts)

    result = f"{words} Rupees"
    if paise:
        result += f" and {_two_digits(paise)} Paise"
    return result + " Only"
