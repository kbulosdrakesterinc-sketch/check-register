from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]

TENS = [
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
]

SCALES = [
    (1_000_000_000, "billion"),
    (1_000_000, "million"),
    (1_000, "thousand"),
]


def _int_to_words(value: int) -> str:
    if value < 20:
        return ONES[value]
    if value < 100:
        tens, rest = divmod(value, 10)
        return TENS[tens] if rest == 0 else f"{TENS[tens]} {ONES[rest]}"
    if value < 1000:
        hundreds, rest = divmod(value, 100)
        return f"{ONES[hundreds]} hundred" if rest == 0 else f"{ONES[hundreds]} hundred {_int_to_words(rest)}"

    for scale, label in SCALES:
        if value >= scale:
            lead, rest = divmod(value, scale)
            words = f"{_int_to_words(lead)} {label}"
            return words if rest == 0 else f"{words} {_int_to_words(rest)}"

    return str(value)


def peso_amount_to_words(raw_amount: str) -> str:
    clean = raw_amount.replace(",", "").strip()
    if not clean:
        return ""

    try:
        amount = Decimal(clean).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return ""

    if amount < 0:
        return ""

    pesos = int(amount)
    centavos = int((amount - Decimal(pesos)) * 100)
    words = _int_to_words(pesos).title()
    return f"{words} & {centavos:02d}/100 Only"
