import platform
import subprocess
from pathlib import Path
from typing import Any


DATE_EXTRA_CHAR_SPACING_PX = 1


PRINTER_STATUS_MESSAGES = {
    "PRINTER_STATUS_PAUSED": "Paused",
    "PRINTER_STATUS_ERROR": "Error",
    "PRINTER_STATUS_PENDING_DELETION": "Pending deletion",
    "PRINTER_STATUS_PAPER_JAM": "Paper jam",
    "PRINTER_STATUS_PAPER_OUT": "Out of paper",
    "PRINTER_STATUS_MANUAL_FEED": "Manual feed",
    "PRINTER_STATUS_PAPER_PROBLEM": "Paper problem",
    "PRINTER_STATUS_OFFLINE": "Offline",
    "PRINTER_STATUS_IO_ACTIVE": "Busy",
    "PRINTER_STATUS_BUSY": "Busy",
    "PRINTER_STATUS_PRINTING": "Printing",
    "PRINTER_STATUS_OUTPUT_BIN_FULL": "Output bin full",
    "PRINTER_STATUS_NOT_AVAILABLE": "Not available",
    "PRINTER_STATUS_WAITING": "Waiting",
    "PRINTER_STATUS_PROCESSING": "Processing",
    "PRINTER_STATUS_INITIALIZING": "Initializing",
    "PRINTER_STATUS_WARMING_UP": "Warming up",
    "PRINTER_STATUS_TONER_LOW": "Toner low",
    "PRINTER_STATUS_NO_TONER": "No toner",
    "PRINTER_STATUS_PAGE_PUNT": "Page punt",
    "PRINTER_STATUS_USER_INTERVENTION": "Needs attention",
    "PRINTER_STATUS_OUT_OF_MEMORY": "Out of memory",
    "PRINTER_STATUS_DOOR_OPEN": "Door open",
    "PRINTER_STATUS_SERVER_UNKNOWN": "Server unknown",
    "PRINTER_STATUS_POWER_SAVE": "Power save",
}


def installed_printers() -> list[str]:
    if platform.system() != "Windows":
        return []

    try:
        import win32print

        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        return sorted(printer[2] for printer in win32print.EnumPrinters(flags))
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []

    if result.returncode != 0:
        return []

    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def printer_status(printer_name: str | None) -> str:
    if not printer_name:
        return "No printer selected"
    if platform.system() != "Windows":
        return "Status unavailable on this OS"

    try:
        import win32print

        handle = win32print.OpenPrinter(printer_name)
        try:
            info = win32print.GetPrinter(handle, 2)
        finally:
            win32print.ClosePrinter(handle)

        attributes = int(info.get("Attributes", 0))
        if attributes & getattr(win32print, "PRINTER_ATTRIBUTE_WORK_OFFLINE", 0):
            return "Offline"

        status = int(info.get("Status", 0))
        if status == 0:
            return "Available"

        messages = []
        for constant, message in PRINTER_STATUS_MESSAGES.items():
            value = getattr(win32print, constant, 0)
            if value and status & value:
                messages.append(message)
        return ", ".join(messages) if messages else f"Status code {status}"
    except Exception:
        pass

    safe_name = printer_name.replace("'", "''")
    command = (
        f"$p = Get-Printer -Name '{safe_name}' -ErrorAction Stop; "
        "if ($p.WorkOffline) { 'Offline' } else { [string]$p.PrinterStatus }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", command],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return "Status unavailable"

    status = result.stdout.strip()
    if result.returncode != 0 or not status:
        return "Status unavailable"
    return "Available" if status.lower() == "normal" else status


def connect_network_printer(printer_path: str) -> None:
    target = printer_path.strip()
    if not target:
        raise RuntimeError("Enter a shared printer path such as \\\\SERVER\\PrinterName.")
    if platform.system() != "Windows":
        raise RuntimeError("Network printer connection is currently implemented for Windows only.")
    if not target.startswith("\\\\"):
        raise RuntimeError(
            "Enter a Windows shared printer path such as \\\\SERVER\\PrinterName. "
            "For direct IP printers, add the printer in Windows first, then click Refresh."
        )

    safe_target = target.replace("'", "''")
    command = f"Add-Printer -ConnectionName '{safe_target}'"
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise RuntimeError(details or f"Could not connect to {target}.")


def print_check_direct(
    printer_name: str | None,
    template: dict[str, Any],
    values: dict[str, str],
    font_name: str,
    font_size: int,
    signature_path: str | None = None,
) -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Direct printing is currently implemented for Windows only.")
    if not printer_name:
        raise RuntimeError("Select a printer before printing.")

    try:
        import win32con
        import win32print
        import win32ui
        from PIL import Image, ImageDraw, ImageFont, ImageWin
    except Exception as exc:
        raise RuntimeError("Direct printing requires pywin32 and Pillow. Run: pip install -r requirements.txt") from exc

    handle = win32print.OpenPrinter(printer_name)
    try:
        win32print.GetPrinter(handle, 2)
    finally:
        win32print.ClosePrinter(handle)

    dc = win32ui.CreateDC()
    try:
        dc.CreatePrinterDC(printer_name)
        dpi_x = dc.GetDeviceCaps(win32con.LOGPIXELSX)
        dpi_y = dc.GetDeviceCaps(win32con.LOGPIXELSY)
        offset_x = dc.GetDeviceCaps(win32con.PHYSICALOFFSETX)
        offset_y = dc.GetDeviceCaps(win32con.PHYSICALOFFSETY)
        printable_width = dc.GetDeviceCaps(win32con.HORZRES)

        rotation = str(template.get("print_rotation", "0"))
        width_mm = float(template.get("width_mm", 203.2))
        height_mm = float(template.get("height_mm", 88.9))
        offset_x_mm = float(template.get("offset_x_mm", 0))
        offset_y_mm = float(template.get("offset_y_mm", 0))
        feed_offset_x_mm = float(template.get("feed_offset_x_mm", 0))
        feed_offset_y_mm = float(template.get("feed_offset_y_mm", 0))
        text_color = _normalize_hex_color(template.get("text_color"))

        image_width = round(width_mm * dpi_x / 25.4)
        image_height = round(height_mm * dpi_y / 25.4)
        page = Image.new("RGB", (image_width, image_height), "white")
        draw = ImageDraw.Draw(page)

        font_pixel_size = max(8, round(font_size * dpi_y / 72))
        draw_font = _load_pillow_font(font_name, font_pixel_size)

        fields = template.get("fields", {})
        text_map = {
            "date": values.get("date", ""),
            "payee": values.get("payee", ""),
            "amount_numeric": values.get("amount", ""),
            "amount_words": values.get("amount_words", ""),
            "memo": values.get("memo", ""),
        }

        def px_x(value: float) -> int:
            return round(value * dpi_x / 25.4)

        def px_y(value: float) -> int:
            return round(value * dpi_y / 25.4)

        for field, text in text_map.items():
            position = fields.get(field, {})
            x_mm = float(position.get("x", 0)) + offset_x_mm
            y_mm = float(position.get("y", 0)) + offset_y_mm
            field_width = float(position.get("w", 0))
            if field == "date" and field_width and len(text) > 1:
                for index, (char, slot) in enumerate(_date_print_slots(text)):
                    draw.text(
                        (px_x(x_mm + _date_slot_x(slot, field_width)) + index * DATE_EXTRA_CHAR_SPACING_PX, px_y(y_mm)),
                        char,
                        fill=text_color,
                        font=draw_font,
                    )
            else:
                draw.text((px_x(x_mm), px_y(y_mm)), text, fill=text_color, font=draw_font)

        if signature_path and fields.get("signature"):
            path = Path(signature_path)
            if path.exists():
                sig = fields["signature"]
                signature = Image.open(path).convert("RGBA")
                w = px_x(float(sig.get("w", 40)))
                h = px_y(float(sig.get("h", 12)))
                signature.thumbnail((w, h))
                page.paste(
                    signature,
                    (px_x(float(sig.get("x", 0)) + offset_x_mm), px_y(float(sig.get("y", 0)) + offset_y_mm)),
                    signature,
                )

        if rotation == "90":
            page = page.rotate(90, expand=True)
        elif rotation == "270":
            page = page.rotate(270, expand=True)

        dib = ImageWin.Dib(page)
        dc.StartDoc("Check Register Print")
        dc.StartPage()
        try:
            feed_offset_x = px_x(feed_offset_x_mm)
            feed_offset_y = px_y(feed_offset_y_mm)
            if rotation in {"90", "270"}:
                left = round((printable_width - page.width) / 2) + feed_offset_x
                top = feed_offset_y
            else:
                left = -offset_x + feed_offset_x
                top = -offset_y + feed_offset_y
            dib.draw(dc.GetHandleOutput(), (left, top, left + page.width, top + page.height))
        finally:
            dc.EndPage()
            dc.EndDoc()
    except Exception as exc:
        raise RuntimeError(f"Could not send direct print job to {printer_name}: {exc}") from exc
    finally:
        dc.DeleteDC()


def _load_pillow_font(font_name: str, font_size: int):
    from PIL import ImageFont

    candidates = []
    if font_name:
        candidates.append(font_name)
        if not font_name.lower().endswith((".ttf", ".otf")):
            candidates.append(f"{font_name}.ttf")
    candidates.extend(["arial.ttf", "calibri.ttf"])

    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, font_size)
        except Exception:
            continue

    return ImageFont.load_default()


def _normalize_hex_color(value: Any) -> str:
    if not value:
        return "#000000"
    text = str(value).strip()
    if len(text) == 7 and text.startswith("#") and all(char in "0123456789abcdefABCDEF" for char in text[1:]):
        return text
    return "#000000"


def _date_print_slots(text: str) -> list[tuple[str, int]]:
    if len(text) == 8 and text.isdigit():
        return [(char, slot) for char, slot in zip(text, [0, 1, 3, 4, 6, 7, 8, 9])]
    return [(char, index) for index, char in enumerate(text)]


def _date_slot_x(slot: int, field_width: float) -> float:
    return field_width * slot / 9


def print_pdf(pdf_path: Path, printer_name: str | None) -> None:
    if platform.system() != "Windows":
        raise RuntimeError("Direct printing is currently implemented for Windows only. Open the PDF and print manually.")

    if not printer_name:
        raise RuntimeError("Select a printer before printing.")

    try:
        import win32api

        win32api.ShellExecute(0, "printto", str(pdf_path), f'"{printer_name}"', ".", 0)
        return
    except Exception as exc:
        raise RuntimeError(f"Could not send PDF to printer: {exc}") from exc
