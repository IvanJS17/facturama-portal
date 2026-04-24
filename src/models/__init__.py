"""SQLite models and repository helpers for the Facturama portal."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_sqlite_url(database_url: str) -> str:
    """Convert a sqlite:/// URL into a local filesystem path."""
    if not database_url or database_url == "sqlite://":
        return "instance/facturama_portal.db"
    if database_url.startswith("sqlite:///"):
        return database_url.removeprefix("sqlite:///")
    if database_url.startswith("sqlite://"):
        return database_url.removeprefix("sqlite://")
    return database_url


@dataclass
class IssuerProfile:
    id: int | None
    legal_name: str
    rfc: str
    tax_regime: str
    zip_code: str
    email: str = ""
    active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class PortalClient:
    id: int | None
    facturama_id: str
    legal_name: str
    rfc: str
    email: str
    tax_regime: str
    cfdi_use: str
    zip_code: str
    raw_payload: dict[str, Any]
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Product:
    id: int | None
    facturama_id: str
    name: str
    identification_number: str
    product_code: str
    unit_code: str
    unit: str
    price: float
    tax_object: str
    raw_payload: dict[str, Any]
    created_at: str = ""
    updated_at: str = ""


@dataclass
class CfdiRecord:
    id: int | None
    facturama_id: str
    uuid: str
    issuer_id: int | None
    recipient_rfc: str
    recipient_name: str
    total: float
    status: str
    cfdi_type: str
    payment_form: str
    payment_method: str
    raw_payload: dict[str, Any]
    created_at: str = ""
    updated_at: str = ""


class PortalDatabase:
    """Small repository layer over SQLite."""

    def __init__(self, database_url: str):
        self.path = Path(parse_sqlite_url(database_url))
        if self.path.parent and str(self.path.parent) not in ("", "."):
            self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS issuers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    legal_name TEXT NOT NULL,
                    rfc TEXT NOT NULL UNIQUE,
                    tax_regime TEXT NOT NULL,
                    zip_code TEXT NOT NULL,
                    email TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    facturama_id TEXT NOT NULL DEFAULT '',
                    legal_name TEXT NOT NULL,
                    rfc TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL DEFAULT '',
                    tax_regime TEXT NOT NULL,
                    cfdi_use TEXT NOT NULL,
                    zip_code TEXT NOT NULL,
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    facturama_id TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    identification_number TEXT NOT NULL DEFAULT '',
                    product_code TEXT NOT NULL,
                    unit_code TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    price REAL NOT NULL,
                    tax_object TEXT NOT NULL,
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS cfdis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    facturama_id TEXT NOT NULL UNIQUE,
                    uuid TEXT NOT NULL DEFAULT '',
                    issuer_id INTEGER,
                    recipient_rfc TEXT NOT NULL,
                    recipient_name TEXT NOT NULL,
                    total REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    cfdi_type TEXT NOT NULL DEFAULT 'I',
                    payment_form TEXT NOT NULL DEFAULT '',
                    payment_method TEXT NOT NULL DEFAULT '',
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (issuer_id) REFERENCES issuers(id)
                );
                """
            )

    def list_issuers(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM issuers ORDER BY active DESC, legal_name").fetchall()

    def get_issuer(self, issuer_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM issuers WHERE id = ?", (issuer_id,)).fetchone()

    def save_issuer(self, data: dict[str, Any], issuer_id: int | None = None) -> int:
        now = utc_now()
        values = (
            data["legal_name"].strip(),
            data["rfc"].strip().upper(),
            data["tax_regime"].strip(),
            data["zip_code"].strip(),
            data.get("email", "").strip(),
            1 if data.get("active", True) else 0,
            now,
        )
        with self.connect() as conn:
            if issuer_id:
                conn.execute(
                    """
                    UPDATE issuers
                    SET legal_name = ?, rfc = ?, tax_regime = ?, zip_code = ?,
                        email = ?, active = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, issuer_id),
                )
                return issuer_id
            cursor = conn.execute(
                """
                INSERT INTO issuers
                    (legal_name, rfc, tax_regime, zip_code, email, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*values[:-1], now, now),
            )
            return int(cursor.lastrowid)

    def delete_issuer(self, issuer_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM issuers WHERE id = ?", (issuer_id,))

    def list_clients(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM clients ORDER BY legal_name").fetchall()

    def get_client(self, client_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()

    def upsert_client(self, data: dict[str, Any], client_id: int | None = None) -> int:
        now = utc_now()
        raw_payload = json.dumps(data.get("raw_payload", {}), ensure_ascii=True)
        values = (
            data.get("facturama_id", "").strip(),
            data["legal_name"].strip(),
            data["rfc"].strip().upper(),
            data.get("email", "").strip(),
            data["tax_regime"].strip(),
            data["cfdi_use"].strip(),
            data["zip_code"].strip(),
            raw_payload,
            now,
        )
        with self.connect() as conn:
            if client_id:
                conn.execute(
                    """
                    UPDATE clients
                    SET facturama_id = ?, legal_name = ?, rfc = ?, email = ?,
                        tax_regime = ?, cfdi_use = ?, zip_code = ?, raw_payload = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, client_id),
                )
                return client_id
            cursor = conn.execute(
                """
                INSERT INTO clients
                    (facturama_id, legal_name, rfc, email, tax_regime, cfdi_use,
                     zip_code, raw_payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rfc) DO UPDATE SET
                    facturama_id = excluded.facturama_id,
                    legal_name = excluded.legal_name,
                    email = excluded.email,
                    tax_regime = excluded.tax_regime,
                    cfdi_use = excluded.cfdi_use,
                    zip_code = excluded.zip_code,
                    raw_payload = excluded.raw_payload,
                    updated_at = excluded.updated_at
                """,
                (*values[:-1], now, now),
            )
            if cursor.lastrowid:
                return int(cursor.lastrowid)
            row = conn.execute("SELECT id FROM clients WHERE rfc = ?", (data["rfc"].strip().upper(),)).fetchone()
            return int(row["id"])

    def delete_client(self, client_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))

    def list_products(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM products ORDER BY name").fetchall()

    def get_product(self, product_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()

    def upsert_product(self, data: dict[str, Any], product_id: int | None = None) -> int:
        now = utc_now()
        raw_payload = json.dumps(data.get("raw_payload", {}), ensure_ascii=True)
        values = (
            data.get("facturama_id", "").strip(),
            data["name"].strip(),
            data.get("identification_number", "").strip(),
            data["product_code"].strip(),
            data["unit_code"].strip(),
            data["unit"].strip(),
            float(data["price"]),
            data["tax_object"].strip(),
            raw_payload,
            now,
        )
        with self.connect() as conn:
            if product_id:
                conn.execute(
                    """
                    UPDATE products
                    SET facturama_id = ?, name = ?, identification_number = ?,
                        product_code = ?, unit_code = ?, unit = ?, price = ?,
                        tax_object = ?, raw_payload = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, product_id),
                )
                return product_id
            cursor = conn.execute(
                """
                INSERT INTO products
                    (facturama_id, name, identification_number, product_code, unit_code,
                     unit, price, tax_object, raw_payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*values[:-1], now, now),
            )
            return int(cursor.lastrowid)

    def delete_product(self, product_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM products WHERE id = ?", (product_id,))

    def list_cfdis(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT c.*, i.legal_name AS issuer_name
                FROM cfdis c
                LEFT JOIN issuers i ON i.id = c.issuer_id
                ORDER BY c.created_at DESC
                """
            ).fetchall()

    def get_cfdi(self, cfdi_id: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM cfdis WHERE facturama_id = ?", (cfdi_id,)).fetchone()

    def save_cfdi(self, data: dict[str, Any]) -> int:
        now = utc_now()
        facturama_id = str(data.get("facturama_id") or data.get("Id") or data.get("id") or "")
        raw_payload = json.dumps(data.get("raw_payload", data), ensure_ascii=True)
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO cfdis
                    (facturama_id, uuid, issuer_id, recipient_rfc, recipient_name, total,
                     status, cfdi_type, payment_form, payment_method, raw_payload,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(facturama_id) DO UPDATE SET
                    uuid = excluded.uuid,
                    issuer_id = excluded.issuer_id,
                    recipient_rfc = excluded.recipient_rfc,
                    recipient_name = excluded.recipient_name,
                    total = excluded.total,
                    status = excluded.status,
                    cfdi_type = excluded.cfdi_type,
                    payment_form = excluded.payment_form,
                    payment_method = excluded.payment_method,
                    raw_payload = excluded.raw_payload,
                    updated_at = excluded.updated_at
                """,
                (
                    facturama_id,
                    data.get("uuid", ""),
                    data.get("issuer_id"),
                    data.get("recipient_rfc", ""),
                    data.get("recipient_name", ""),
                    float(data.get("total") or 0),
                    data.get("status", "active"),
                    data.get("cfdi_type", "I"),
                    data.get("payment_form", ""),
                    data.get("payment_method", ""),
                    raw_payload,
                    now,
                    now,
                ),
            )
            return int(cursor.lastrowid or 0)

    def mark_cfdi_cancelled(self, cfdi_id: str, raw_response: dict[str, Any] | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE cfdis SET status = ?, raw_payload = ?, updated_at = ? WHERE facturama_id = ?",
                ("cancelled", json.dumps(raw_response or {}, ensure_ascii=True), utc_now(), cfdi_id),
            )


def to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """Convert sqlite row to a mutable dict."""
    return dict(row) if row else None


__all__ = [
    "CfdiRecord",
    "IssuerProfile",
    "PortalClient",
    "PortalDatabase",
    "Product",
    "asdict",
    "parse_sqlite_url",
    "to_dict",
]
