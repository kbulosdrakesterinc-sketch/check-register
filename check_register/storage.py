import json
import os
import sqlite3
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


APP_DIR = Path(os.environ.get("CHECK_REGISTER_HOME") or os.environ.get("LOCALAPPDATA", Path.home())) / "CheckRegister"
DB_PATH = APP_DIR / "check_register.sqlite3"


DEFAULT_TEMPLATE = {
    "name": "Default PH Check",
    "width_mm": 203.2,
    "height_mm": 88.9,
    "background_image_path": "",
    "text_color": "#000000",
    "print_rotation": "90",
    "offset_x_mm": 0,
    "offset_y_mm": 0,
    "feed_offset_x_mm": 0,
    "feed_offset_y_mm": 0,
    "fields": {
        "date": {"x": 156, "y": 17, "w": 36, "h": 0},
        "payee": {"x": 29, "y": 26},
        "amount_numeric": {"x": 150, "y": 25},
        "amount_words": {"x": 22, "y": 35},
        "memo": {"x": 25, "y": 72},
        "signature": {"x": 145, "y": 66, "w": 42, "h": 14},
    },
}


@dataclass
class Template:
    id: int
    name: str
    data: dict[str, Any]


@dataclass
class CheckRecord:
    id: int
    template_name: str
    printer: str
    check_number: str
    check_date: str
    payee: str
    amount: str
    amount_words: str
    memo: str
    pdf_path: str
    printed_at: str


class Store:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        APP_DIR.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self.conn.executescript(
            """
            create table if not exists templates (
                id integer primary key autoincrement,
                name text not null unique,
                data text not null,
                created_at text not null,
                updated_at text not null
            );

            create table if not exists check_records (
                id integer primary key autoincrement,
                template_id integer,
                printer text,
                check_number text,
                check_date text,
                payee text,
                amount text,
                amount_words text,
                memo text,
                pdf_path text,
                printed_at text not null
            );

            create table if not exists settings (
                key text primary key,
                value text not null,
                updated_at text not null
            );
            """
        )
        self.conn.commit()
        if not self.templates():
            self.save_template(DEFAULT_TEMPLATE["name"], DEFAULT_TEMPLATE)
        else:
            self.refresh_builtin_default_template()

    def refresh_builtin_default_template(self) -> None:
        row = self.conn.execute("select data from templates where name = ?", (DEFAULT_TEMPLATE["name"],)).fetchone()
        if not row:
            self.save_template(DEFAULT_TEMPLATE["name"], DEFAULT_TEMPLATE)
            return

        current = json.loads(row["data"])
        refreshed = deepcopy(DEFAULT_TEMPLATE)
        refreshed["background_image_path"] = current.get("background_image_path", "")
        self.save_template(DEFAULT_TEMPLATE["name"], refreshed)

    def templates(self) -> list[Template]:
        rows = self.conn.execute("select id, name, data from templates order by name").fetchall()
        return [Template(row["id"], row["name"], json.loads(row["data"])) for row in rows]

    def template_by_name(self, name: str) -> Template | None:
        row = self.conn.execute("select id, name, data from templates where name = ?", (name,)).fetchone()
        if not row:
            return None
        return Template(row["id"], row["name"], json.loads(row["data"]))

    def save_template(self, name: str, data: dict[str, Any]) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        payload = json.dumps(data, indent=2, sort_keys=True)
        self.conn.execute(
            """
            insert into templates (name, data, created_at, updated_at)
            values (?, ?, ?, ?)
            on conflict(name) do update set data = excluded.data, updated_at = excluded.updated_at
            """,
            (name, payload, now, now),
        )
        self.conn.commit()

    def record_print(self, values: dict[str, str], template_id: int | None, printer: str, pdf_path: Path) -> None:
        self.conn.execute(
            """
            insert into check_records (
                template_id, printer, check_number, check_date, payee, amount,
                amount_words, memo, pdf_path, printed_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                template_id,
                printer,
                values.get("check_number", ""),
                values.get("date", ""),
                values.get("payee", ""),
                values.get("amount", ""),
                values.get("amount_words", ""),
                values.get("memo", ""),
                str(pdf_path),
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        self.conn.commit()

    def setting(self, key: str, default: str = "") -> str:
        row = self.conn.execute("select value from settings where key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            """
            insert into settings (key, value, updated_at)
            values (?, ?, ?)
            on conflict(key) do update set value = excluded.value, updated_at = excluded.updated_at
            """,
            (key, value, now),
        )
        self.conn.commit()

    def check_records(self, limit: int = 200) -> list[CheckRecord]:
        rows = self.conn.execute(
            """
            select
                r.id,
                coalesce(t.name, '') as template_name,
                r.printer,
                r.check_number,
                r.check_date,
                r.payee,
                r.amount,
                r.amount_words,
                r.memo,
                r.pdf_path,
                r.printed_at
            from check_records r
            left join templates t on t.id = r.template_id
            order by r.printed_at desc, r.id desc
            limit ?
            """,
            (limit,),
        ).fetchall()
        return [
            CheckRecord(
                id=row["id"],
                template_name=row["template_name"],
                printer=row["printer"],
                check_number=row["check_number"],
                check_date=row["check_date"],
                payee=row["payee"],
                amount=row["amount"],
                amount_words=row["amount_words"],
                memo=row["memo"],
                pdf_path=row["pdf_path"],
                printed_at=row["printed_at"],
            )
            for row in rows
        ]

    def payees(self, limit: int = 200) -> list[str]:
        rows = self.conn.execute(
            """
            select payee, max(printed_at) as last_printed_at
            from check_records
            where trim(coalesce(payee, '')) != ''
            group by payee
            order by last_printed_at desc, payee collate nocase
            limit ?
            """,
            (limit,),
        ).fetchall()
        return [row["payee"] for row in rows]
