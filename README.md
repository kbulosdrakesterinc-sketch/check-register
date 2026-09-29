# Check Register Desktop App

A local Python desktop app for preparing and printing checks with configurable check formats.

## Features

- Select an installed printer.
- Remember and reselect the latest printer used when reopening the app.
- Show whether the selected printer is available, offline, busy, or needs attention.
- Connect a LAN/Wi-Fi shared printer by entering a Windows printer share path.
- Show print progress while generating the PDF and sending the print request.
- View recent printed checks in a History tab.
- Reuse previous payees from an editable Payee dropdown.
- Create, save, select, and load multiple check formats with per-field X/Y placement.
- Attach a scanned bank-check image to each format for live preview alignment.
- Choose font family and size.
- Choose font color per check format.
- Enter check details and see a live preview on a check canvas.
- Convert numeric Philippine peso amounts into words automatically.
- Generate a printable PDF.
- Optional e-signature image placement, with a bank-approval reminder.
- Store check formats and print records locally in SQLite.

## Setup

Python 3.12+ is recommended.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m check_register
```

The app will still open without optional packages, but PDF output requires `reportlab`.
On Windows, you can also double-click `run_check_register.bat`.

Data is stored in `%LOCALAPPDATA%\CheckRegister` by default. For portable/testing runs, set `CHECK_REGISTER_HOME` before launching.

The built-in **Default PH Check** template is refreshed from the app's code defaults whenever the app starts. Custom duplicated templates are not changed.

## Check Image Preview

Open the **Format** tab, choose **Check Image**, and select a scanned image of the blank bank check. The app stretches that image to the selected check width/height, then overlays the preview text using the configured millimeter positions.

The check image is for preview/calibration only. Generated PDFs still print only the entered fields and optional signature, which is the safer default when printing onto real check stock.

## Print Status

When printing, the app shows the current stage: generating the PDF, sending the direct print job, sent, cancelled, or failed. The **Print** button sends text directly to the selected Windows printer, which is more reliable than handing a PDF to an external PDF reader.

Printed checks are recorded in the **History** tab with check number, date, payee, amount, printer, template, generated PDF path, and print timestamp.

## LAN And Wi-Fi Printers

Printers connected by USB, Wi-Fi, or LAN should appear in the printer list after they are installed in Windows. Click **Refresh** after adding a printer.

For a shared network printer, enter a Windows share path such as `\\OFFICE-PC\CheckPrinter` in **LAN/Wi-Fi Printer**, then click **Connect**. For direct IP printers, add the printer in Windows first so the correct printer driver is installed, then refresh the app.

## Paper Feed And Date Boxes

The check layout itself is landscape because the check is wider than it is tall. Some printers still require the physical check to be fed short-edge first. Use **Print Rotation** in the Format tab:

- `0` for landscape/horizontal feed.
- `90` or `270` for portrait/short-edge feed, depending on which side your printer prints on.

Always test with a photocopy or blank paper before printing on real check stock.

For boxed bank-check dates, the app prints only the digits, so `09/28/2026` becomes `09282026`. The **date** field width still reserves the two separator gaps between MM, DD, and YYYY.

Use **Alignment Offset** in the Format tab to nudge the whole layout after a test print. Positive X moves all printed fields to the right; positive Y moves them down. Start with small changes such as `1` or `2` mm.

Use **Feed Offset** when the fields are aligned with each other but the whole print lands off the physical check. This is most useful for rear/manual portrait feeding, where the app now centers the rotated check image in the printer's printable width. Positive X moves the whole print image right; positive Y moves it down.

Preview helper labels are hidden by default so the preview better matches the printed check. Enable **Show preview labels** in the Format tab when calibrating field positions.

For the rear/manual feed shown in the current Epson setup, feed the check short-edge first and use **Print Rotation = 90**. If the print lands upside down, switch to `270`. The app renders the check text as an image before printing so these rotations are applied reliably.

## Notes On E-Signatures

The app can place a signature image on the check, but whether a bank accepts this for physical checks depends on that bank's policies, specimen signature rules, account agreement, and clearing requirements. Enable it only after written approval from the bank.
