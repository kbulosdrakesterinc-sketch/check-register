from pathlib import Path


DATE_EXTRA_CHAR_SPACING_PT = 1


def mm_to_points(value: float) -> float:
    return value * 72 / 25.4


def normalize_hex_color(value: str | None) -> str:
    if not value:
        return "#000000"
    value = value.strip()
    if len(value) == 7 and value.startswith("#") and all(char in "0123456789abcdefABCDEF" for char in value[1:]):
        return value
    return "#000000"


def generate_check_pdf(
    output_path: Path,
    template: dict,
    values: dict[str, str],
    font_name: str,
    font_size: int,
    signature_path: str | None = None,
) -> None:
    try:
        from reportlab.lib.colors import HexColor, lightgrey
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError("PDF generation requires reportlab. Run: pip install -r requirements.txt") from exc

    width = mm_to_points(float(template["width_mm"]))
    height = mm_to_points(float(template["height_mm"]))
    fields = template["fields"]
    offset_x = float(template.get("offset_x_mm", 0))
    offset_y = float(template.get("offset_y_mm", 0))
    text_color = normalize_hex_color(template.get("text_color"))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(output_path), pagesize=(width, height))

    pdf.setStrokeColor(lightgrey)
    pdf.rect(0.5, 0.5, width - 1, height - 1, stroke=1, fill=0)

    try:
        pdf.setFont(font_name, font_size)
    except Exception:
        pdf.setFont("Helvetica", font_size)

    pdf.setFillColor(HexColor(text_color))

    for key, value_key in [
        ("date", "date"),
        ("payee", "payee"),
        ("amount_numeric", "amount"),
        ("amount_words", "amount_words"),
        ("memo", "memo"),
    ]:
        position = fields.get(key, {})
        text = values.get(value_key, "")
        x = mm_to_points(float(position.get("x", 0)) + offset_x)
        y = height - mm_to_points(float(position.get("y", 0)) + offset_y)
        field_width = float(position.get("w", 0))
        if key == "date" and field_width and len(text) > 1:
            for index, (char, slot) in enumerate(date_print_slots(text)):
                pdf.drawString(x + mm_to_points(date_slot_x(slot, field_width)) + index * DATE_EXTRA_CHAR_SPACING_PT, y, char)
        else:
            pdf.drawString(x, y, text)

    if signature_path and fields.get("signature"):
        sig = fields["signature"]
        path = Path(signature_path)
        if path.exists():
            x = mm_to_points(float(sig.get("x", 0)) + offset_x)
            y = height - mm_to_points(float(sig.get("y", 0)) + offset_y)
            w = mm_to_points(float(sig.get("w", 40)))
            h = mm_to_points(float(sig.get("h", 12)))
            pdf.drawImage(str(path), x, y - h, width=w, height=h, preserveAspectRatio=True, mask="auto")

    pdf.showPage()
    pdf.save()


def date_print_slots(text: str) -> list[tuple[str, int]]:
    if len(text) == 8 and text.isdigit():
        return [(char, slot) for char, slot in zip(text, [0, 1, 3, 4, 6, 7, 8, 9])]
    return [(char, index) for index, char in enumerate(text)]


def date_slot_x(slot: int, field_width: float) -> float:
    return field_width * slot / 9
