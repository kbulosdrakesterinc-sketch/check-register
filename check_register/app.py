from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import colorchooser, filedialog, font, messagebox, ttk

from PIL import Image, ImageTk

from .amount_words import peso_amount_to_words
from .printing import connect_network_printer, installed_printers, print_check_direct, printer_status
from .rendering import generate_check_pdf
from .storage import APP_DIR, DEFAULT_TEMPLATE, Store, Template


FIELD_LABELS = {
    "date": "Date",
    "payee": "Payee",
    "amount_numeric": "Numeric Amount",
    "amount_words": "Amount In Words",
    "memo": "Memo",
    "signature": "Signature",
}

DATE_EXTRA_CHAR_SPACING_PX = 1
DATE_YEAR_GROUP_PADDING_MM = 1
DATE_YEAR_DIGIT_PADDING_MM = (0, 0.5, 1.5, 2.5)
CONTROLS_PANE_HEIGHT = 300


class CheckRegisterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Check Register")
        self.geometry("1180x760")
        self.minsize(1040, 680)

        self.store = Store()
        self.current_template: Template | None = None
        self.signature_path = tk.StringVar(value="")
        self.preview_image: ImageTk.PhotoImage | None = None
        self.background_image_path = tk.StringVar(value="")
        self.printer_status = tk.StringVar(value="No printer selected")
        self.print_status = tk.StringVar(value="Idle")
        self.network_printer_path = tk.StringVar(value="")
        self.text_color = tk.StringVar(value=DEFAULT_TEMPLATE["text_color"])
        self.print_rotation = tk.StringVar(value="0")
        self.offset_x_mm = tk.DoubleVar(value=0)
        self.offset_y_mm = tk.DoubleVar(value=0)
        self.feed_offset_x_mm = tk.DoubleVar(value=0)
        self.feed_offset_y_mm = tk.DoubleVar(value=0)
        self.show_preview_labels = tk.BooleanVar(value=False)
        self._formatting_amount = False
        self.payee_options: list[str] = []
        self.payee_matches: list[str] = []
        self.payee_suggestion_index = -1

        self.vars = {
            "printer": tk.StringVar(),
            "template": tk.StringVar(),
            "font_family": tk.StringVar(value="Helvetica"),
            "font_size": tk.IntVar(value=11),
            "check_number": tk.StringVar(),
            "date": tk.StringVar(value=date.today().strftime("%m/%d/%Y")),
            "payee": tk.StringVar(),
            "amount": tk.StringVar(),
            "amount_words": tk.StringVar(),
            "memo": tk.StringVar(),
            "use_signature": tk.BooleanVar(value=False),
        }
        self.position_vars: dict[str, dict[str, tk.DoubleVar]] = {}

        self._build_ui()
        self._load_printers()
        self._load_templates()
        self._load_history()
        self._wire_updates()
        self.refresh_preview()

    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill=tk.BOTH, expand=True)

        controls = ttk.Frame(root, padding=(12, 8))
        preview = ttk.Frame(root, padding=(12, 6))
        controls.configure(height=CONTROLS_PANE_HEIGHT)
        controls.pack_propagate(False)
        controls.pack(fill=tk.X)
        preview.pack(fill=tk.BOTH, expand=True)

        self._build_controls(controls)
        self._build_preview(preview)

    def _build_controls(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)

        entry_container, entry_tab = self._scrollable_tab(notebook, padding=(4, 4))
        format_container, format_tab = self._scrollable_tab(notebook, padding=(8, 4))
        history_tab = ttk.Frame(notebook, padding=(8, 4))
        notebook.add(entry_container, text="Check Entry")
        notebook.add(format_container, text="Format")
        notebook.add(history_tab, text="History")

        self._build_entry_tab(entry_tab)
        self._build_format_tab(format_tab)
        self._build_history_tab(history_tab)

    def _scrollable_tab(self, parent: ttk.Notebook, padding: tuple[int, int]) -> tuple[ttk.Frame, ttk.Frame]:
        container = ttk.Frame(parent)
        canvas = tk.Canvas(container, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        content = ttk.Frame(canvas, padding=padding)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        def update_scroll_region(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content_width(event: tk.Event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        content.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", fit_content_width)

        def bind_mousewheel(_event: tk.Event) -> None:
            canvas.bind_all("<MouseWheel>", on_mousewheel)

        def unbind_mousewheel(_event: tk.Event) -> None:
            canvas.unbind_all("<MouseWheel>")

        def on_mousewheel(event: tk.Event) -> None:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind("<Enter>", bind_mousewheel)
        canvas.bind("<Leave>", unbind_mousewheel)
        content.bind("<Enter>", bind_mousewheel)
        content.bind("<Leave>", unbind_mousewheel)

        return container, content

    def _build_entry_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        row = 0
        self._label(parent, "Printer", row)
        self.printer_combo = ttk.Combobox(parent, textvariable=self.vars["printer"], state="readonly")
        self.printer_combo.grid(row=row, column=1, sticky="ew", pady=2)
        self.printer_combo.bind("<<ComboboxSelected>>", lambda _event: self._update_printer_status())
        self.printer_status_label = ttk.Label(parent, textvariable=self.printer_status, foreground="#555")
        self.printer_status_label.grid(row=row, column=2, sticky="w", padx=(8, 0), pady=2)
        ttk.Button(parent, text="Refresh", command=self._load_printers).grid(row=row, column=3, padx=(8, 0))

        row += 1
        self._label(parent, "Check Format", row)
        self.template_combo = ttk.Combobox(parent, textvariable=self.vars["template"], state="readonly")
        self.template_combo.grid(row=row, column=1, columnspan=3, sticky="ew", pady=2)
        self.template_combo.bind("<<ComboboxSelected>>", lambda _event: self._select_template())

        row += 1
        self._label(parent, "Font", row)
        families = sorted(font.families())
        self.font_combo = ttk.Combobox(parent, textvariable=self.vars["font_family"], values=families)
        self.font_combo.grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)
        ttk.Spinbox(parent, from_=7, to=24, textvariable=self.vars["font_size"], width=6).grid(row=row, column=3, padx=(6, 0))

        for label, key in [
            ("Date", "date"),
            ("Payee", "payee"),
            ("Amount", "amount"),
            ("Amount Words", "amount_words"),
            ("Memo", "memo"),
        ]:
            row += 1
            self._label(parent, label, row)
            if key == "payee":
                widget = ttk.Entry(parent, textvariable=self.vars[key])
                self.payee_entry = widget
                widget.bind("<KeyRelease>", self._filter_payee_options)
                widget.bind("<Down>", self._move_payee_suggestion_down)
                widget.bind("<Up>", self._move_payee_suggestion_up)
                widget.bind("<Return>", self._accept_payee_suggestion)
                widget.bind("<Escape>", self._hide_payee_suggestions)
            elif key == "amount_words":
                widget = ttk.Entry(parent, textvariable=self.vars[key])
            else:
                widget = ttk.Entry(parent, textvariable=self.vars[key])
            widget.grid(row=row, column=1, columnspan=3, sticky="ew", pady=2)
            if key == "payee":
                self.payee_suggestion_listbox = tk.Listbox(parent, height=4, exportselection=False)
                self.payee_suggestion_listbox.grid(row=row + 1, column=1, columnspan=3, sticky="ew", pady=(0, 2))
                self.payee_suggestion_listbox.grid_remove()
                self.payee_suggestion_listbox.bind("<ButtonRelease-1>", self._accept_clicked_payee_suggestion)
                row += 1
            if key == "amount":
                self.amount_entry = widget

        # row += 1
        # ttk.Checkbutton(
        #     parent,
        #     text="Use e-signature image only after bank approval",
        #     variable=self.vars["use_signature"],
        #     command=self.refresh_preview,
        # ).grid(row=row, column=0, columnspan=4, sticky="w", pady=(6, 1))

        # row += 1
        # self._label(parent, "Signature File", row)
        # ttk.Entry(parent, textvariable=self.signature_path).grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)
        # ttk.Button(parent, text="Browse", command=self._browse_signature).grid(row=row, column=3, padx=(6, 0))

        row += 1
        actions = ttk.Frame(parent)
        actions.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Button(actions, text="Generate PDF", command=self.generate_pdf).pack(side=tk.LEFT)
        ttk.Button(actions, text="Print", command=self.print_check).pack(side=tk.LEFT, padx=8)

        row += 1
        self._label(parent, "Print Status", row)
        self.print_status_label = ttk.Label(parent, textvariable=self.print_status, foreground="#555")
        self.print_status_label.grid(row=row, column=1, columnspan=3, sticky="w", pady=(6, 0))

        self.status = tk.StringVar(value="Ready")
        row += 1
        ttk.Label(parent, textvariable=self.status, foreground="#555").grid(row=row, column=0, columnspan=4, sticky="w", pady=(4, 0))

    def _build_format_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        ttk.Label(parent, text="Load Template").grid(row=0, column=0, sticky="w", pady=4)
        self.format_template_combo = ttk.Combobox(parent, textvariable=self.vars["template"], state="readonly")
        self.format_template_combo.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)
        self.format_template_combo.bind("<<ComboboxSelected>>", lambda _event: self._select_template())
        ttk.Button(parent, text="Load", command=self._select_template).grid(row=0, column=3, sticky="w", padx=(6, 0))

        ttk.Label(parent, text="Template Name").grid(row=1, column=0, sticky="w", pady=4)
        self.template_name = tk.StringVar()
        ttk.Entry(parent, textvariable=self.template_name).grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)

        self.width_mm = tk.DoubleVar(value=DEFAULT_TEMPLATE["width_mm"])
        self.height_mm = tk.DoubleVar(value=DEFAULT_TEMPLATE["height_mm"])
        ttk.Label(parent, text="Width mm").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.width_mm, width=10).grid(row=2, column=1, sticky="w")
        ttk.Label(parent, text="Height mm").grid(row=2, column=2, sticky="w", padx=(12, 4))
        ttk.Entry(parent, textvariable=self.height_mm, width=10).grid(row=2, column=3, sticky="w")

        ttk.Label(parent, text="Print Rotation").grid(row=3, column=0, sticky="w", pady=4)
        rotation_combo = ttk.Combobox(
            parent,
            textvariable=self.print_rotation,
            state="readonly",
            values=("0", "90", "270"),
            width=10,
        )
        rotation_combo.grid(row=3, column=1, sticky="w", pady=4)
        rotation_combo.bind("<<ComboboxSelected>>", lambda _event: self._apply_format_values())
        ttk.Label(parent, text="0=landscape feed, 90/270=portrait feed").grid(row=3, column=2, columnspan=2, sticky="w", padx=(12, 0))

        ttk.Label(parent, text="Font Color").grid(row=4, column=0, sticky="w", pady=4)
        color_frame = ttk.Frame(parent)
        color_frame.grid(row=4, column=1, columnspan=3, sticky="w", pady=4)
        self.color_swatch = tk.Label(color_frame, width=3, relief=tk.SOLID, borderwidth=1, background=self.text_color.get())
        self.color_swatch.pack(side=tk.LEFT, padx=(0, 8))
        ttk.Entry(color_frame, textvariable=self.text_color, width=10).pack(side=tk.LEFT)
        ttk.Button(color_frame, text="Select", command=self._choose_text_color).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(parent, text="Alignment Offset").grid(row=5, column=0, sticky="w", pady=4)
        offset_frame = ttk.Frame(parent)
        offset_frame.grid(row=5, column=1, columnspan=3, sticky="w", pady=4)
        ttk.Label(offset_frame, text="X").pack(side=tk.LEFT)
        ttk.Spinbox(offset_frame, from_=-50, to=50, increment=0.5, textvariable=self.offset_x_mm, width=8, command=self._apply_format_values).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(offset_frame, text="Y").pack(side=tk.LEFT)
        ttk.Spinbox(offset_frame, from_=-50, to=50, increment=0.5, textvariable=self.offset_y_mm, width=8, command=self._apply_format_values).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(offset_frame, text="mm, +X right, +Y down").pack(side=tk.LEFT)

        ttk.Label(parent, text="Feed Offset").grid(row=6, column=0, sticky="w", pady=4)
        feed_offset_frame = ttk.Frame(parent)
        feed_offset_frame.grid(row=6, column=1, columnspan=3, sticky="w", pady=4)
        ttk.Label(feed_offset_frame, text="X").pack(side=tk.LEFT)
        ttk.Spinbox(feed_offset_frame, from_=-100, to=100, increment=0.5, textvariable=self.feed_offset_x_mm, width=8, command=self._apply_format_values).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(feed_offset_frame, text="Y").pack(side=tk.LEFT)
        ttk.Spinbox(feed_offset_frame, from_=-100, to=100, increment=0.5, textvariable=self.feed_offset_y_mm, width=8, command=self._apply_format_values).pack(side=tk.LEFT, padx=(4, 10))
        ttk.Label(feed_offset_frame, text="mm, moves whole print image").pack(side=tk.LEFT)

        ttk.Checkbutton(
            parent,
            text="Show preview labels",
            variable=self.show_preview_labels,
            command=self.refresh_preview,
        ).grid(row=7, column=0, columnspan=4, sticky="w", pady=4)

        ttk.Label(parent, text="Check Image").grid(row=8, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.background_image_path).grid(row=8, column=1, columnspan=2, sticky="ew", pady=4)
        image_actions = ttk.Frame(parent)
        image_actions.grid(row=8, column=3, sticky="w", padx=(6, 0))
        ttk.Button(image_actions, text="Browse", command=self._browse_check_image).pack(side=tk.LEFT)
        ttk.Button(image_actions, text="Clear", command=self._clear_check_image).pack(side=tk.LEFT, padx=(6, 0))

        table = ttk.Frame(parent)
        table.grid(row=9, column=0, columnspan=4, sticky="nsew", pady=(14, 0))
        parent.rowconfigure(9, weight=1)

        for column, text in enumerate(["Field", "X mm", "Y mm", "W mm", "H mm"]):
            ttk.Label(table, text=text, font=("", 9, "bold")).grid(row=0, column=column, sticky="w", padx=4, pady=3)

        for index, field in enumerate(["date", "payee", "amount_numeric", "amount_words", "memo", "signature"], start=1):
            ttk.Label(table, text=FIELD_LABELS[field]).grid(row=index, column=0, sticky="w", padx=4, pady=3)
            self.position_vars[field] = {
                "x": tk.DoubleVar(),
                "y": tk.DoubleVar(),
                "w": tk.DoubleVar(),
                "h": tk.DoubleVar(),
            }
            for column, key in enumerate(["x", "y", "w", "h"], start=1):
                ttk.Entry(table, textvariable=self.position_vars[field][key], width=8).grid(row=index, column=column, padx=4, pady=3)

        buttons = ttk.Frame(parent)
        buttons.grid(row=10, column=0, columnspan=4, sticky="ew", pady=(16, 0))
        ttk.Button(buttons, text="Apply To Preview", command=self._apply_format_values).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Save Format", command=self._save_current_template).pack(side=tk.LEFT, padx=8)
        ttk.Button(buttons, text="Duplicate As New", command=self._duplicate_template).pack(side=tk.LEFT)

    def _build_history_tab(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        actions = ttk.Frame(parent)
        actions.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(actions, text="Refresh History", command=self._load_history).pack(side=tk.LEFT)

        columns = ("printed_at", "check_date", "payee", "amount", "printer", "template", "pdf_path")
        self.history_tree = ttk.Treeview(parent, columns=columns, show="headings", height=7)
        self.history_tree.grid(row=1, column=0, sticky="nsew")

        headings = {
            "printed_at": "Printed At",
            "check_date": "Date",
            "payee": "Payee",
            "amount": "Amount",
            "printer": "Printer Used",
            "template": "Template",
            "pdf_path": "PDF",
        }
        widths = {
            "printed_at": 140,
            "check_date": 90,
            "payee": 170,
            "amount": 100,
            "printer": 220,
            "template": 130,
            "pdf_path": 220,
        }
        for column in columns:
            self.history_tree.heading(column, text=headings[column])
            self.history_tree.column(column, width=widths[column], minwidth=70, stretch=column in {"payee", "printer", "pdf_path"})

        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=self.history_tree.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        self.history_tree.configure(yscrollcommand=scrollbar.set)

    def _build_preview(self, parent: ttk.Frame) -> None:
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="Live Check Preview", font=("", 13, "bold")).grid(row=0, column=0, sticky="w")
        self.canvas = tk.Canvas(parent, bg="#f5f5f0", highlightthickness=1, highlightbackground="#ccc")
        self.canvas.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.canvas.bind("<Configure>", lambda _event: self.refresh_preview())

    def _label(self, parent: ttk.Frame, text: str, row: int) -> None:
        ttk.Label(parent, text=text).grid(row=row, column=0, sticky="w", pady=2, padx=(0, 8))

    def _wire_updates(self) -> None:
        self.vars["amount"].trace_add("write", lambda *_args: self._on_amount_change())
        for key in ["font_family", "font_size", "date", "payee", "amount_words", "memo"]:
            self.vars[key].trace_add("write", lambda *_args: self._on_value_change())

    def _on_amount_change(self) -> None:
        if self._formatting_amount:
            return

        raw_amount = self.vars["amount"].get()
        cursor_index = self._amount_cursor_index()
        logical_cursor = self._logical_amount_cursor(raw_amount, cursor_index)
        formatted = self._amount_with_commas(raw_amount)
        if formatted != raw_amount:
            self._formatting_amount = True
            self.vars["amount"].set(formatted)
            self._formatting_amount = False
            self._restore_amount_cursor(formatted, logical_cursor)

        words = peso_amount_to_words(self.vars["amount"].get())
        if words and self.vars["amount_words"].get() != words:
            self.vars["amount_words"].set(words)
            return

        self.refresh_preview()

    def _on_value_change(self) -> None:
        self.refresh_preview()

    def _amount_with_commas(self, raw_amount: str) -> str:
        clean = raw_amount.replace(",", "").strip()
        if not clean or clean == ".":
            return clean
        if clean.count(".") > 1:
            return raw_amount

        whole, dot, decimal = clean.partition(".")
        if whole and not whole.isdigit():
            return raw_amount
        if decimal and not decimal.isdigit():
            return raw_amount

        formatted_whole = f"{int(whole or '0'):,}"
        return f"{formatted_whole}{dot}{decimal}"

    def _amount_cursor_index(self) -> int:
        if not hasattr(self, "amount_entry"):
            return len(self.vars["amount"].get())
        try:
            return int(self.amount_entry.index(tk.INSERT))
        except tk.TclError:
            return len(self.vars["amount"].get())

    def _logical_amount_cursor(self, amount: str, cursor_index: int) -> int:
        return sum(1 for char in amount[:cursor_index] if char != ",")

    def _restore_amount_cursor(self, amount: str, logical_cursor: int) -> None:
        if not hasattr(self, "amount_entry"):
            return

        if logical_cursor <= 0:
            target_index = 0
        else:
            target_index = len(amount)
            seen = 0
            for index, char in enumerate(amount):
                if char != ",":
                    seen += 1
                if seen >= logical_cursor:
                    target_index = index + 1
                    break

        try:
            self.amount_entry.icursor(target_index)
            self.after_idle(lambda index=target_index: self.amount_entry.icursor(index))
        except tk.TclError:
            pass

    def _load_printers(self) -> None:
        printers = installed_printers()
        last_printer = self.store.setting("last_printer")
        if last_printer and last_printer not in printers:
            printers = [last_printer, *printers]
        self.printer_combo["values"] = printers
        if last_printer:
            self.vars["printer"].set(last_printer)
        elif printers and not self.vars["printer"].get():
            self.vars["printer"].set(printers[0])
        self._update_printer_status()

    def _update_printer_status(self) -> None:
        selected_printer = self.vars["printer"].get()
        if selected_printer:
            self.store.set_setting("last_printer", selected_printer)
        status = printer_status(selected_printer)
        self.printer_status.set(status)
        color = "#19733a" if status == "Available" else "#9a5b00"
        if status in {"Offline", "Not available", "Status unavailable", "No printer selected"} or "Error" in status:
            color = "#a32020"
        self.printer_status_label.configure(foreground=color)

    def _connect_network_printer(self) -> None:
        try:
            connect_network_printer(self.network_printer_path.get())
        except Exception as exc:
            messagebox.showerror("Printer connection failed", str(exc))
            return

        self.status.set("Network printer connected. Refreshing printer list...")
        self._load_printers()
        target = self.network_printer_path.get().strip()
        if target:
            self.vars["printer"].set(target)
            self._update_printer_status()

    def _load_templates(self) -> None:
        templates = self.store.templates()
        names = [template.name for template in templates]
        self.template_combo["values"] = names
        self.format_template_combo["values"] = names
        if names:
            last_template = self.store.setting("last_template")
            self.vars["template"].set(last_template if last_template in names else names[0])
            self._select_template()

    def _load_history(self) -> None:
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)

        for record in self.store.check_records():
            self.history_tree.insert(
                "",
                tk.END,
                values=(
                    record.printed_at,
                    record.check_date,
                    record.payee,
                    record.amount,
                    record.printer,
                    record.template_name,
                    record.pdf_path,
                ),
            )
        self._load_payees()

    def _load_payees(self) -> None:
        if hasattr(self, "payee_entry"):
            self.payee_options = self.store.payees()

    def _filter_payee_options(self, event: tk.Event) -> None:
        if event.keysym in {"Escape", "Return", "Tab", "Up", "Down", "Left", "Right"}:
            return
        if not hasattr(self, "payee_suggestion_listbox"):
            return

        typed = self.vars["payee"].get().strip().lower()
        if typed:
            matches = [payee for payee in self.payee_options if typed in payee.lower()]
        else:
            matches = self.payee_options

        self._show_payee_suggestions(matches)

    def _show_payee_suggestions(self, matches: list[str]) -> None:
        self.payee_matches = matches[:8]
        self.payee_suggestion_index = 0 if self.payee_matches else -1
        self.payee_suggestion_listbox.delete(0, tk.END)
        for payee in self.payee_matches:
            self.payee_suggestion_listbox.insert(tk.END, payee)

        if self.payee_matches:
            self.payee_suggestion_listbox.selection_set(self.payee_suggestion_index)
            self.payee_suggestion_listbox.grid()
        else:
            self.payee_suggestion_listbox.grid_remove()

        if hasattr(self, "payee_entry"):
            self.payee_entry.focus_set()

    def _move_payee_suggestion_down(self, _event: tk.Event) -> str:
        self._move_payee_suggestion(1)
        return "break"

    def _move_payee_suggestion_up(self, _event: tk.Event) -> str:
        self._move_payee_suggestion(-1)
        return "break"

    def _move_payee_suggestion(self, step: int) -> None:
        if not self.payee_matches:
            self._show_payee_suggestions(self.payee_options)
            return
        self.payee_suggestion_index = (self.payee_suggestion_index + step) % len(self.payee_matches)
        self.payee_suggestion_listbox.selection_clear(0, tk.END)
        self.payee_suggestion_listbox.selection_set(self.payee_suggestion_index)
        self.payee_suggestion_listbox.see(self.payee_suggestion_index)
        self.payee_entry.focus_set()

    def _accept_payee_suggestion(self, _event: tk.Event | None = None) -> str:
        if 0 <= self.payee_suggestion_index < len(self.payee_matches):
            self.vars["payee"].set(self.payee_matches[self.payee_suggestion_index])
            self._hide_payee_suggestions()
            self.payee_entry.icursor(tk.END)
            self.refresh_preview()
            return "break"
        return ""

    def _accept_clicked_payee_suggestion(self, _event: tk.Event) -> None:
        selection = self.payee_suggestion_listbox.curselection()
        if selection:
            self.payee_suggestion_index = int(selection[0])
            self._accept_payee_suggestion()

    def _hide_payee_suggestions(self, _event: tk.Event | None = None) -> str:
        if hasattr(self, "payee_suggestion_listbox"):
            self.payee_suggestion_listbox.grid_remove()
        self.payee_matches = []
        self.payee_suggestion_index = -1
        if hasattr(self, "payee_entry"):
            self.payee_entry.focus_set()
        return "break"

    def _select_template(self) -> None:
        selected = self.store.template_by_name(self.vars["template"].get())
        if not selected:
            return
        self._ensure_template_defaults(selected.data)
        self.current_template = selected
        self.store.set_setting("last_template", selected.name)
        self.template_name.set(selected.name)
        self._populate_format_values(selected.data)
        self.refresh_preview()

    def _ensure_template_defaults(self, data: dict) -> None:
        data.setdefault("print_rotation", DEFAULT_TEMPLATE["print_rotation"])
        data.setdefault("background_image_path", "")
        data.setdefault("text_color", DEFAULT_TEMPLATE["text_color"])
        data.setdefault("offset_x_mm", DEFAULT_TEMPLATE["offset_x_mm"])
        data.setdefault("offset_y_mm", DEFAULT_TEMPLATE["offset_y_mm"])
        data.setdefault("feed_offset_x_mm", DEFAULT_TEMPLATE["feed_offset_x_mm"])
        data.setdefault("feed_offset_y_mm", DEFAULT_TEMPLATE["feed_offset_y_mm"])
        data.setdefault("fields", {})
        for field, defaults in DEFAULT_TEMPLATE["fields"].items():
            data["fields"].setdefault(field, {})
            for key, value in defaults.items():
                data["fields"][field].setdefault(key, value)
        self._upgrade_legacy_date_field(data)

    def _upgrade_legacy_date_field(self, data: dict) -> None:
        date_field = data["fields"].get("date", {})
        legacy_x = float(date_field.get("x", -1)) == 155
        legacy_y = float(date_field.get("y", -1)) == 23
        legacy_w = float(date_field.get("w", -1)) in {31, 36}
        if legacy_x and legacy_y and legacy_w:
            date_field.update({"x": 155, "y": 23, "w": 36})

        if float(date_field.get("x", -1)) == 166 and float(date_field.get("y", -1)) == 18.5:
            date_field.update({"x": 155, "y": 23, "w": 36})

        numeric_field = data["fields"].get("amount_numeric", {})
        if float(numeric_field.get("x", -1)) == 165 and float(numeric_field.get("y", -1)) == 34:
            numeric_field.update({"x": 150, "y": 33})
        if float(numeric_field.get("x", -1)) == 157 and float(numeric_field.get("y", -1)) == 40:
            numeric_field.update({"x": 150, "y": 33})

        words_field = data["fields"].get("amount_words", {})
        if float(words_field.get("x", -1)) == 22 and float(words_field.get("y", -1)) == 47:
            words_field.update({"x": 23, "y": 44})
        if float(words_field.get("x", -1)) == 28 and float(words_field.get("y", -1)) == 51:
            words_field.update({"x": 23, "y": 44})

        payee_field = data["fields"].get("payee", {})
        if float(payee_field.get("x", -1)) == 28 and float(payee_field.get("y", -1)) == 34:
            payee_field.update({"x": 29, "y": 32})
        if float(payee_field.get("x", -1)) == 28 and float(payee_field.get("y", -1)) == 32:
            payee_field.update({"x": 29, "y": 32})

    def _populate_format_values(self, data: dict) -> None:
        self.width_mm.set(float(data.get("width_mm", DEFAULT_TEMPLATE["width_mm"])))
        self.height_mm.set(float(data.get("height_mm", DEFAULT_TEMPLATE["height_mm"])))
        self.background_image_path.set(data.get("background_image_path", ""))
        self.text_color.set(self._normalized_color(data.get("text_color", DEFAULT_TEMPLATE["text_color"])))
        self._update_color_swatch()
        self.print_rotation.set(str(data.get("print_rotation", "0")))
        self.offset_x_mm.set(float(data.get("offset_x_mm", 0)))
        self.offset_y_mm.set(float(data.get("offset_y_mm", 0)))
        self.feed_offset_x_mm.set(float(data.get("feed_offset_x_mm", 0)))
        self.feed_offset_y_mm.set(float(data.get("feed_offset_y_mm", 0)))
        fields = data.get("fields", {})
        for field, values in self.position_vars.items():
            field_data = fields.get(field, {})
            for key, var in values.items():
                var.set(float(field_data.get(key, 0)))

    def _template_from_form(self) -> dict:
        fields = {}
        for field, values in self.position_vars.items():
            fields[field] = {key: var.get() for key, var in values.items()}
        return {
            "name": self.template_name.get().strip() or "Untitled Check Format",
            "width_mm": self.width_mm.get(),
            "height_mm": self.height_mm.get(),
            "background_image_path": self.background_image_path.get().strip(),
            "text_color": self._normalized_color(self.text_color.get()),
            "print_rotation": self.print_rotation.get(),
            "offset_x_mm": self.offset_x_mm.get(),
            "offset_y_mm": self.offset_y_mm.get(),
            "feed_offset_x_mm": self.feed_offset_x_mm.get(),
            "feed_offset_y_mm": self.feed_offset_y_mm.get(),
            "fields": fields,
        }

    def _apply_format_values(self) -> None:
        data = self._template_from_form()
        self.text_color.set(data["text_color"])
        self._update_color_swatch()
        template_id = self.current_template.id if self.current_template else 0
        self.current_template = Template(template_id, data["name"], data)
        self.refresh_preview()

    def _active_template_data(self) -> dict:
        if not self.position_vars:
            return self.current_template.data if self.current_template else DEFAULT_TEMPLATE
        data = self._template_from_form()
        template_id = self.current_template.id if self.current_template else 0
        self.current_template = Template(template_id, data["name"], data)
        return data

    def _save_current_template(self) -> None:
        data = self._template_from_form()
        self.store.save_template(data["name"], data)
        self.status.set(f"Saved format: {data['name']}")
        self._load_templates()
        self.vars["template"].set(data["name"])
        self._select_template()

    def _duplicate_template(self) -> None:
        base = self._template_from_form()
        base["name"] = f"{base['name']} Copy"
        self.template_name.set(base["name"])
        self.store.save_template(base["name"], base)
        self._load_templates()
        self.vars["template"].set(base["name"])
        self._select_template()

    def _browse_signature(self) -> None:
        path = filedialog.askopenfilename(
            title="Select signature image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")],
        )
        if path:
            self.signature_path.set(path)
            self.refresh_preview()

    def _browse_check_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Select scanned check image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp"), ("All files", "*.*")],
        )
        if path:
            self.background_image_path.set(path)
            self._apply_format_values()

    def _clear_check_image(self) -> None:
        self.background_image_path.set("")
        self._apply_format_values()

    def _choose_text_color(self) -> None:
        _rgb, color = colorchooser.askcolor(color=self._normalized_color(self.text_color.get()), title="Select Font Color")
        if color:
            self.text_color.set(color)
            self._apply_format_values()

    def _normalized_color(self, value: str | None) -> str:
        if not value:
            return DEFAULT_TEMPLATE["text_color"]
        value = value.strip()
        if len(value) == 7 and value.startswith("#") and all(char in "0123456789abcdefABCDEF" for char in value[1:]):
            return value
        return DEFAULT_TEMPLATE["text_color"]

    def _update_color_swatch(self) -> None:
        if hasattr(self, "color_swatch"):
            self.color_swatch.configure(background=self._normalized_color(self.text_color.get()))

    def values(self) -> dict[str, str]:
        return {
            "check_number": self.vars["check_number"].get(),
            "date": self.vars["date"].get(),
            "payee": self.vars["payee"].get(),
            "amount": self.vars["amount"].get(),
            "amount_words": self.vars["amount_words"].get(),
            "memo": self.vars["memo"].get(),
        }

    def print_values(self) -> dict[str, str]:
        values = self.values()
        values["date"] = self._date_digits(values["date"])
        return values

    def _date_digits(self, raw_date: str) -> str:
        digits = "".join(ch for ch in raw_date if ch.isdigit())
        if len(digits) == 8:
            return digits
        return raw_date

    def refresh_preview(self) -> None:
        if not hasattr(self, "canvas"):
            return
        template = self.current_template.data if self.current_template else DEFAULT_TEMPLATE
        values = self.print_values() if hasattr(self, "vars") else {}
        self.canvas.delete("all")

        width_mm = float(template.get("width_mm", 203.2))
        height_mm = float(template.get("height_mm", 88.9))
        canvas_w = max(self.canvas.winfo_width(), 600)
        canvas_h = max(self.canvas.winfo_height(), 360)
        margin = 36
        scale = min((canvas_w - margin * 2) / width_mm, (canvas_h - margin * 2) / height_mm)
        check_w = width_mm * scale
        check_h = height_mm * scale
        left = (canvas_w - check_w) / 2
        top = (canvas_h - check_h) / 2

        background_path = template.get("background_image_path", "")
        if background_path:
            try:
                image = Image.open(background_path)
                image = image.resize((round(check_w), round(check_h)), Image.Resampling.LANCZOS)
                self.preview_image = ImageTk.PhotoImage(image)
                self.canvas.create_rectangle(left, top, left + check_w, top + check_h, fill="#fffdf5", outline="#9c927d", width=2)
                self.canvas.create_image(left, top, image=self.preview_image, anchor="nw")
            except Exception:
                self.preview_image = None
                self._draw_blank_check(left, top, check_w, check_h, scale)
                self.canvas.create_text(left + 8, top + 8, text="Check image could not be loaded", anchor="nw", fill="#a33", font=("Arial", 9))
        else:
            self.preview_image = None
            self._draw_blank_check(left, top, check_w, check_h, scale)

        fields = template.get("fields", {})
        offset_x = float(template.get("offset_x_mm", 0))
        offset_y = float(template.get("offset_y_mm", 0))
        text_color = self._normalized_color(template.get("text_color", DEFAULT_TEMPLATE["text_color"]))
        preview_font = (self.vars["font_family"].get(), self.vars["font_size"].get())
        text_map = {
            "date": values.get("date", ""),
            "payee": values.get("payee", ""),
            "amount_numeric": values.get("amount", ""),
            "amount_words": values.get("amount_words", ""),
            "memo": values.get("memo", ""),
        }

        for field, text in text_map.items():
            position = fields.get(field, {})
            x = left + (float(position.get("x", 0)) + offset_x) * scale
            y = top + (float(position.get("y", 0)) + offset_y) * scale
            field_width = float(position.get("w", 0))
            if field == "date" and field_width and len(text) > 1:
                for index, (char, slot) in enumerate(self._date_print_slots(text)):
                    self.canvas.create_text(
                        x
                        + self._date_slot_x(slot, field_width, scale)
                        + index * DATE_EXTRA_CHAR_SPACING_PX
                        + self._date_group_padding_mm(index) * scale,
                        y,
                        text=char,
                        anchor="nw",
                        fill=text_color,
                        font=preview_font,
                    )
            else:
                self.canvas.create_text(x, y, text=text, anchor="nw", fill=text_color, font=preview_font)
            if self.show_preview_labels.get():
                self.canvas.create_text(x, y - 10, text=FIELD_LABELS[field], anchor="sw", fill="#9a9386", font=("Arial", 7))

        if self.vars["use_signature"].get():
            sig = fields.get("signature", {})
            x = left + (float(sig.get("x", 0)) + offset_x) * scale
            y = top + (float(sig.get("y", 0)) + offset_y) * scale
            w = float(sig.get("w", 40)) * scale
            h = float(sig.get("h", 12)) * scale
            self.canvas.create_rectangle(x, y, x + w, y + h, outline="#666", dash=(4, 2))
            self.canvas.create_text(x + w / 2, y + h / 2, text="Signature image", fill="#333", font=("Arial", 9))

    def _draw_blank_check(self, left: float, top: float, check_w: float, check_h: float, scale: float) -> None:
        self.canvas.create_rectangle(left, top, left + check_w, top + check_h, fill="#fffdf5", outline="#9c927d", width=2)
        self.canvas.create_line(left + 16 * scale, top + 62 * scale, left + 128 * scale, top + 62 * scale, fill="#d9d1bc")
        self.canvas.create_text(left + 10 * scale, top + check_h - 8 * scale, text="MICR / bank encoded area", anchor="w", fill="#b2aa98", font=("Arial", 8))

    def _date_print_slots(self, text: str) -> list[tuple[str, int]]:
        if len(text) == 8 and text.isdigit():
            return [(char, slot) for char, slot in zip(text, [0, 1, 3, 4, 6, 7, 8, 9])]
        return [(char, index) for index, char in enumerate(text)]

    def _date_slot_x(self, slot: int, field_width: float, scale: float) -> float:
        return field_width * scale * slot / 9

    def _date_group_padding_mm(self, index: int) -> float:
        if index < 4:
            return 0
        year_index = min(index - 4, len(DATE_YEAR_DIGIT_PADDING_MM) - 1)
        return DATE_YEAR_GROUP_PADDING_MM + DATE_YEAR_DIGIT_PADDING_MM[year_index]

    def _pdf_output_path(self) -> Path:
        check_no = self.vars["check_number"].get().strip() or "draft"
        safe_check_no = "".join(ch for ch in check_no if ch.isalnum() or ch in ("-", "_"))
        return APP_DIR / "pdf" / f"check-{safe_check_no}.pdf"

    def generate_pdf(self) -> Path | None:
        if not self.current_template:
            messagebox.showerror("Missing format", "Select or save a check format first.")
            return None
        template_data = self._active_template_data()
        path = self._pdf_output_path()
        signature = self.signature_path.get() if self.vars["use_signature"].get() else None
        try:
            generate_check_pdf(
                path,
                template_data,
                self.print_values(),
                self.vars["font_family"].get(),
                self.vars["font_size"].get(),
                signature,
            )
        except Exception as exc:
            messagebox.showerror("PDF generation failed", str(exc))
            return None
        self.status.set(f"Generated PDF: {path}")
        return path

    def _set_print_status(self, status: str, color: str = "#555") -> None:
        self.print_status.set(status)
        self.print_status_label.configure(foreground=color)
        self.update_idletasks()

    def print_check(self) -> None:
        if self.vars["use_signature"].get():
            approved = messagebox.askyesno(
                "Confirm e-signature approval",
                "Only print checks with an e-signature if your bank has approved it. Continue?",
            )
            if not approved:
                self._set_print_status("Cancelled", "#9a5b00")
                return

        self._set_print_status("Generating PDF...", "#555")
        pdf_path = self.generate_pdf()
        if not pdf_path:
            self._set_print_status("PDF generation failed", "#a32020")
            return

        selected_printer = self.vars["printer"].get()
        template_data = self._active_template_data()
        rotation = template_data.get("print_rotation", "0")
        self._set_print_status(f"Sending direct print job to {selected_printer} with rotation {rotation}...", "#555")
        try:
            print_check_direct(
                selected_printer,
                template_data,
                self.print_values(),
                self.vars["font_family"].get(),
                self.vars["font_size"].get(),
                self.signature_path.get() if self.vars["use_signature"].get() else None,
            )
        except Exception as exc:
            self._set_print_status("Print failed", "#a32020")
            messagebox.showerror("Print failed", str(exc))
            return

        self._set_print_status(f"Direct print job sent to {selected_printer}", "#19733a")
        template_id = self.current_template.id if self.current_template else None
        self.store.set_setting("last_printer", selected_printer)
        self.store.record_print(self.values(), template_id, selected_printer, pdf_path)
        self._load_history()
        self.status.set("Print request recorded in history.")
        self.after(1500, self._update_printer_status)


def main() -> None:
    app = CheckRegisterApp()
    app.mainloop()
