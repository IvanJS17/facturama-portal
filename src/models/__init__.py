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


def _table_columns(conn: sqlite3.Connection, table_name: str) -> dict[str, sqlite3.Row]:
    return {row["name"]: row for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _table_sql(conn: sqlite3.Connection, table_name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return str(row["sql"] or "") if row else ""


def _first_issuer_id(conn: sqlite3.Connection) -> int | None:
    row = conn.execute("SELECT id FROM issuers ORDER BY id LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _ensure_migration_issuer(conn: sqlite3.Connection) -> int:
    issuer_id = _first_issuer_id(conn)
    if issuer_id is not None:
        return issuer_id
    now = utc_now()
    cursor = conn.execute(
        """
        INSERT INTO issuers
            (legal_name, rfc, tax_regime, zip_code, email, active, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("Migrated issuer", "XAXX010101000", "601", "00000", "", 1, now, now),
    )
    return int(cursor.lastrowid)


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
                """
            )
            conn.commit()
            conn.execute("PRAGMA foreign_keys = OFF")
            try:
                self._migrate_clients(conn)
                self._migrate_products(conn)
                self._migrate_cfdis(conn)
                self._ensure_cfdi_items(conn)
                self._ensure_invoice_series(conn)
            finally:
                conn.execute("PRAGMA foreign_keys = ON")

    def _migrate_clients(self, conn: sqlite3.Connection) -> None:
        exists = bool(_table_sql(conn, "clients"))
        columns = _table_columns(conn, "clients") if exists else {}
        needs_rebuild = (
            not exists
            or "issuer_id" not in columns
            or not columns["issuer_id"]["notnull"]
            or "UNIQUE(rfc, issuer_id)" not in _table_sql(conn, "clients")
            or "rfc TEXT NOT NULL UNIQUE" in _table_sql(conn, "clients")
        )
        if not needs_rebuild:
            return

        issuer_id = _first_issuer_id(conn)
        if exists:
            orphan_count = conn.execute(
                "SELECT COUNT(*) AS total FROM clients WHERE issuer_id IS NULL"
                if "issuer_id" in columns
                else "SELECT COUNT(*) AS total FROM clients"
            ).fetchone()["total"]
            if orphan_count:
                issuer_id = _ensure_migration_issuer(conn)

        conn.executescript(
            """
            DROP TABLE IF EXISTS clients_migrated;
            CREATE TABLE clients_migrated (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                facturama_id TEXT NOT NULL DEFAULT '',
                issuer_id INTEGER NOT NULL,
                legal_name TEXT NOT NULL,
                rfc TEXT NOT NULL,
                email TEXT NOT NULL DEFAULT '',
                tax_regime TEXT NOT NULL,
                cfdi_use TEXT NOT NULL,
                zip_code TEXT NOT NULL,
                raw_payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(rfc, issuer_id),
                FOREIGN KEY (issuer_id) REFERENCES issuers(id)
            );
            """
        )
        if exists:
            selected_issuer_sql = "COALESCE(issuer_id, ?)" if "issuer_id" in columns else "?"
            conn.execute(
                f"""
                INSERT INTO clients_migrated
                    (id, facturama_id, issuer_id, legal_name, rfc, email, tax_regime,
                     cfdi_use, zip_code, raw_payload, created_at, updated_at)
                SELECT id, facturama_id, {selected_issuer_sql}, legal_name, rfc, email,
                       tax_regime, cfdi_use, zip_code, raw_payload, created_at, updated_at
                FROM clients
                """,
                (issuer_id,),
            )
            conn.execute("DROP TABLE clients")
        conn.execute("ALTER TABLE clients_migrated RENAME TO clients")

    def _migrate_products(self, conn: sqlite3.Connection) -> None:
        exists = bool(_table_sql(conn, "products"))
        columns = _table_columns(conn, "products") if exists else {}
        needs_rebuild = not exists or "issuer_id" not in columns or not columns["issuer_id"]["notnull"]
        if needs_rebuild:
            issuer_id = _first_issuer_id(conn)
            if exists:
                orphan_count = conn.execute(
                    "SELECT COUNT(*) AS total FROM products WHERE issuer_id IS NULL"
                    if "issuer_id" in columns
                    else "SELECT COUNT(*) AS total FROM products"
                ).fetchone()["total"]
                if orphan_count:
                    issuer_id = _ensure_migration_issuer(conn)
            conn.executescript(
                """
                DROP TABLE IF EXISTS products_migrated;
                CREATE TABLE products_migrated (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    facturama_id TEXT NOT NULL DEFAULT '',
                    issuer_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    identification_number TEXT NOT NULL DEFAULT '',
                    product_code TEXT NOT NULL,
                    unit_code TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    price REAL NOT NULL,
                    tax_object TEXT NOT NULL,
                    raw_payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (issuer_id) REFERENCES issuers(id)
                );
                """
            )
            if exists:
                selected_issuer_sql = "COALESCE(issuer_id, ?)" if "issuer_id" in columns else "?"
                conn.execute(
                    f"""
                    INSERT INTO products_migrated
                        (id, facturama_id, issuer_id, name, identification_number, product_code,
                         unit_code, unit, price, tax_object, raw_payload, created_at, updated_at)
                    SELECT id, facturama_id, {selected_issuer_sql}, name, identification_number,
                           product_code, unit_code, unit, price, tax_object, raw_payload,
                           created_at, updated_at
                    FROM products
                    """,
                    (issuer_id,),
                )
                conn.execute("DROP TABLE products")
            conn.execute("ALTER TABLE products_migrated RENAME TO products")

        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_products_issuer_identification
            ON products(issuer_id, identification_number)
            WHERE identification_number <> ''
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_products_issuer_product_code
            ON products(issuer_id, product_code)
            """
        )

    def _migrate_cfdis(self, conn: sqlite3.Connection) -> None:
        exists = bool(_table_sql(conn, "cfdis"))
        columns = _table_columns(conn, "cfdis") if exists else {}
        needs_rebuild = (
            not exists
            or "client_id" not in columns
            or "issuer_id" not in columns
            or "serie" not in columns
            or "folio" not in columns
            or "FOREIGN KEY (client_id) REFERENCES clients(id)" not in _table_sql(conn, "cfdis")
        )
        if not needs_rebuild:
            return
        conn.executescript(
            """
            DROP TABLE IF EXISTS cfdis_migrated;
            CREATE TABLE cfdis_migrated (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                facturama_id TEXT NOT NULL UNIQUE,
                uuid TEXT NOT NULL DEFAULT '',
                issuer_id INTEGER,
                client_id INTEGER,
                recipient_rfc TEXT NOT NULL,
                recipient_name TEXT NOT NULL,
                total REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                cfdi_type TEXT NOT NULL DEFAULT 'I',
                payment_form TEXT NOT NULL DEFAULT '',
                payment_method TEXT NOT NULL DEFAULT '',
                serie TEXT NOT NULL DEFAULT 'FAC',
                folio INTEGER NOT NULL DEFAULT 1,
                raw_payload TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (issuer_id) REFERENCES issuers(id),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );
            """
        )
        if exists:
            client_id_sql = "client_id" if "client_id" in columns else "NULL"
            serie_sql = "serie" if "serie" in columns else "'FAC'"
            folio_sql = "folio" if "folio" in columns else "1"
            conn.execute(
                f"""
                INSERT INTO cfdis_migrated
                    (id, facturama_id, uuid, issuer_id, client_id, recipient_rfc,
                     recipient_name, total, status, cfdi_type, payment_form, payment_method,
                     serie, folio,
                     raw_payload, created_at, updated_at)
                SELECT id, facturama_id, uuid, issuer_id, {client_id_sql}, recipient_rfc,
                       recipient_name, total, status, cfdi_type, payment_form, payment_method,
                       {serie_sql}, {folio_sql},
                       raw_payload, created_at, updated_at
                FROM cfdis
                """
            )
            conn.execute(
                """
                UPDATE cfdis_migrated
                SET folio = 1
                WHERE folio IS NULL OR folio < 1
                """
            )
            conn.execute(
                """
                UPDATE cfdis_migrated
                SET serie = 'FAC'
                WHERE TRIM(COALESCE(serie, '')) = ''
                """
            )
            conn.execute(
                """
                UPDATE cfdis_migrated
                SET client_id = (
                    SELECT cl.id
                    FROM clients cl
                    WHERE cl.rfc = cfdis_migrated.recipient_rfc
                      AND cl.issuer_id = cfdis_migrated.issuer_id
                    ORDER BY cl.id
                    LIMIT 1
                )
                WHERE client_id IS NULL
                """
            )
            conn.execute("DROP TABLE cfdis")
        conn.execute("ALTER TABLE cfdis_migrated RENAME TO cfdis")

    def _ensure_invoice_series(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS invoice_series (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                issuer_id INTEGER NOT NULL,
                series TEXT NOT NULL DEFAULT 'FAC',
                next_folio INTEGER NOT NULL DEFAULT 1,
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (issuer_id) REFERENCES issuers(id),
                UNIQUE(issuer_id, series)
            );
            """
        )

    def list_series(self, issuer_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT *
                FROM invoice_series
                WHERE issuer_id = ?
                ORDER BY active DESC, series
                """,
                (issuer_id,),
            ).fetchall()

    def create_series(self, issuer_id: int, series: str, start_folio: int = 1) -> int:
        cleaned_series = (series or "FAC").strip().upper()
        if not cleaned_series:
            cleaned_series = "FAC"
        safe_start_folio = max(int(start_folio or 1), 1)
        now = utc_now()
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO invoice_series
                    (issuer_id, series, next_folio, active, created_at, updated_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (issuer_id, cleaned_series, safe_start_folio, now, now),
            )
            return int(cursor.lastrowid)

    def get_series(self, series_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM invoice_series WHERE id = ?", (series_id,)).fetchone()

    def get_next_folio(self, issuer_id: int, series: str) -> int:
        cleaned_series = (series or "FAC").strip().upper()
        if not cleaned_series:
            cleaned_series = "FAC"
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT id, next_folio
                FROM invoice_series
                WHERE issuer_id = ? AND series = ? AND active = 1
                """,
                (issuer_id, cleaned_series),
            ).fetchone()
            if row is None:
                raise ValueError("Invoice series not found for issuer")
            current_folio = max(int(row["next_folio"] or 1), 1)
            conn.execute(
                """
                UPDATE invoice_series
                SET next_folio = ?, updated_at = ?
                WHERE id = ?
                """,
                (current_folio + 1, utc_now(), int(row["id"])),
            )
            return current_folio

    def _ensure_cfdi_items(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS cfdi_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cfdi_id INTEGER NOT NULL,
                product_id INTEGER,
                issuer_id INTEGER NOT NULL,
                client_id INTEGER,
                description TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                product_code TEXT NOT NULL DEFAULT '',
                identification_number TEXT NOT NULL DEFAULT '',
                quantity REAL NOT NULL DEFAULT 0,
                unit_price REAL NOT NULL DEFAULT 0,
                subtotal REAL NOT NULL DEFAULT 0,
                total REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (cfdi_id) REFERENCES cfdis(id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (issuer_id) REFERENCES issuers(id),
                FOREIGN KEY (client_id) REFERENCES clients(id)
            );
            CREATE INDEX IF NOT EXISTS idx_cfdi_items_product ON cfdi_items(product_id);
            CREATE INDEX IF NOT EXISTS idx_cfdi_items_issuer ON cfdi_items(issuer_id);
            CREATE INDEX IF NOT EXISTS idx_cfdi_items_client ON cfdi_items(client_id);
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

    def list_clients(self, issuer_id: int | None = None) -> list[sqlite3.Row]:
        base = """
            SELECT c.*, i.legal_name AS issuer_name, i.rfc AS issuer_rfc
            FROM clients c
            LEFT JOIN issuers i ON i.id = c.issuer_id
        """
        if issuer_id is not None:
            with self.connect() as conn:
                return conn.execute(
                    f"{base} WHERE c.issuer_id = ? ORDER BY c.legal_name",
                    (issuer_id,),
                ).fetchall()
        with self.connect() as conn:
            return conn.execute(f"{base} ORDER BY c.legal_name").fetchall()

    def get_client(self, client_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT c.*, i.legal_name AS issuer_name, i.rfc AS issuer_rfc
                FROM clients c
                LEFT JOIN issuers i ON i.id = c.issuer_id
                WHERE c.id = ?
                """,
                (client_id,),
            ).fetchone()

    def get_client_for_issuer(self, client_id: int, issuer_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT c.*, i.legal_name AS issuer_name, i.rfc AS issuer_rfc
                FROM clients c
                LEFT JOIN issuers i ON i.id = c.issuer_id
                WHERE c.id = ? AND c.issuer_id = ?
                """,
                (client_id, issuer_id),
            ).fetchone()

    def upsert_client(self, data: dict[str, Any], client_id: int | None = None) -> int:
        now = utc_now()
        raw_payload = json.dumps(data.get("raw_payload", {}), ensure_ascii=True)
        issuer_id = data.get("issuer_id")
        if issuer_id is None:
            raise ValueError("issuer_id is required for clients")
        values = (
            data.get("facturama_id", "").strip(),
            issuer_id,
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
                    SET facturama_id = ?, issuer_id = ?, legal_name = ?, rfc = ?, email = ?,
                        tax_regime = ?, cfdi_use = ?, zip_code = ?, raw_payload = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, client_id),
                )
                return client_id
            conn.execute(
                """
                INSERT INTO clients
                    (facturama_id, issuer_id, legal_name, rfc, email, tax_regime, cfdi_use,
                     zip_code, raw_payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rfc, issuer_id) DO UPDATE SET
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
            row = conn.execute(
                "SELECT id FROM clients WHERE rfc = ? AND issuer_id = ?",
                (data["rfc"].strip().upper(), data.get("issuer_id")),
            ).fetchone()
            return int(row["id"])

    def delete_client(self, client_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM clients WHERE id = ?", (client_id,))

    def _default_issuer_id(self, conn: sqlite3.Connection) -> int | None:
        return _first_issuer_id(conn)

    def list_products(self, issuer_id: int | None = None) -> list[sqlite3.Row]:
        base = """
            SELECT p.*, i.legal_name AS issuer_name, i.rfc AS issuer_rfc
            FROM products p
            LEFT JOIN issuers i ON i.id = p.issuer_id
        """
        if issuer_id is not None:
            with self.connect() as conn:
                return conn.execute(
                    f"{base} WHERE p.issuer_id = ? ORDER BY p.name",
                    (issuer_id,),
                ).fetchall()
        with self.connect() as conn:
            return conn.execute(f"{base} ORDER BY p.name").fetchall()

    def get_product(self, product_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT p.*, i.legal_name AS issuer_name, i.rfc AS issuer_rfc
                FROM products p
                LEFT JOIN issuers i ON i.id = p.issuer_id
                WHERE p.id = ?
                """,
                (product_id,),
            ).fetchone()

    def get_product_for_issuer(self, product_id: int, issuer_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT p.*, i.legal_name AS issuer_name, i.rfc AS issuer_rfc
                FROM products p
                LEFT JOIN issuers i ON i.id = p.issuer_id
                WHERE p.id = ? AND p.issuer_id = ?
                """,
                (product_id, issuer_id),
            ).fetchone()

    def upsert_product(self, data: dict[str, Any], product_id: int | None = None) -> int:
        now = utc_now()
        raw_payload = json.dumps(data.get("raw_payload", {}), ensure_ascii=True)
        with self.connect() as conn:
            issuer_id = data.get("issuer_id") or self._default_issuer_id(conn)
            if issuer_id is None:
                raise ValueError("issuer_id is required for products")
            values = (
                data.get("facturama_id", "").strip(),
                issuer_id,
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
            if product_id:
                conn.execute(
                    """
                    UPDATE products
                    SET facturama_id = ?, issuer_id = ?, name = ?, identification_number = ?,
                        product_code = ?, unit_code = ?, unit = ?, price = ?,
                        tax_object = ?, raw_payload = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (*values, product_id),
                )
                return product_id
            identification_number = values[3]
            if identification_number:
                existing = conn.execute(
                    """
                    SELECT id FROM products
                    WHERE issuer_id = ? AND identification_number = ?
                    """,
                    (issuer_id, identification_number),
                ).fetchone()
                if existing:
                    conn.execute(
                        """
                        UPDATE products
                        SET facturama_id = ?, issuer_id = ?, name = ?, identification_number = ?,
                            product_code = ?, unit_code = ?, unit = ?, price = ?,
                            tax_object = ?, raw_payload = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (*values, int(existing["id"])),
                    )
                    return int(existing["id"])
            cursor = conn.execute(
                """
                INSERT INTO products
                    (facturama_id, issuer_id, name, identification_number, product_code, unit_code,
                     unit, price, tax_object, raw_payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*values[:-1], now, now),
            )
            return int(cursor.lastrowid)

    def delete_product(self, product_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM products WHERE id = ?", (product_id,))

    def list_cfdis(self, recipient_rfc: str = "", status: str = "") -> list[sqlite3.Row]:
        where_clauses: list[str] = []
        params: list[str] = []
        recipient_rfc = recipient_rfc.strip()
        status = status.strip()

        if recipient_rfc:
            where_clauses.append("UPPER(c.recipient_rfc) LIKE ?")
            params.append(f"%{recipient_rfc.upper()}%")
        if status:
            where_clauses.append("c.status = ?")
            params.append(status)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT c.*,
                       i.rfc        AS issuer_rfc,
                       i.legal_name AS issuer_name,
                       cl.legal_name AS client_name
                FROM cfdis c
                LEFT JOIN issuers i ON i.id = c.issuer_id
                LEFT JOIN clients cl ON cl.id = c.client_id
                {where_sql}
                ORDER BY c.created_at DESC
                """,
                params,
            ).fetchall()

    def get_cfdi(self, cfdi_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT c.*, i.rfc AS issuer_rfc, i.legal_name AS issuer_name,
                       cl.legal_name AS client_name
                FROM cfdis c
                LEFT JOIN issuers i ON i.id = c.issuer_id
                LEFT JOIN clients cl ON cl.id = c.client_id
                WHERE c.id = ?
                """,
                (cfdi_id,),
            ).fetchone()

    def save_cfdi(self, data: dict[str, Any]) -> int:
        now = utc_now()
        facturama_id = str(data.get("facturama_id") or data.get("Id") or data.get("id") or "")
        raw_payload = json.dumps(data.get("raw_payload", data), ensure_ascii=True)
        with self.connect() as conn:
            issuer_id = data.get("issuer_id")
            recipient_rfc = data.get("recipient_rfc", "").strip().upper()
            client_id = data.get("client_id")
            if client_id is None and issuer_id is not None and recipient_rfc:
                client = conn.execute(
                    """
                    SELECT id FROM clients
                    WHERE rfc = ? AND issuer_id = ?
                    ORDER BY id
                    LIMIT 1
                    """,
                    (recipient_rfc, issuer_id),
                ).fetchone()
                client_id = int(client["id"]) if client else None
            conn.execute(
                """
                INSERT INTO cfdis
                    (facturama_id, uuid, issuer_id, client_id, recipient_rfc, recipient_name, total,
                     status, cfdi_type, payment_form, payment_method, serie, folio, raw_payload,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(facturama_id) DO UPDATE SET
                    uuid = excluded.uuid,
                    issuer_id = excluded.issuer_id,
                    client_id = excluded.client_id,
                    recipient_rfc = excluded.recipient_rfc,
                    recipient_name = excluded.recipient_name,
                    total = excluded.total,
                    status = excluded.status,
                    cfdi_type = excluded.cfdi_type,
                    payment_form = excluded.payment_form,
                    payment_method = excluded.payment_method,
                    serie = excluded.serie,
                    folio = excluded.folio,
                    raw_payload = excluded.raw_payload,
                    updated_at = excluded.updated_at
                """,
                (
                    facturama_id,
                    data.get("uuid", ""),
                    issuer_id,
                    client_id,
                    recipient_rfc,
                    data.get("recipient_name", ""),
                    float(data.get("total") or 0),
                    data.get("status", "active"),
                    data.get("cfdi_type", "I"),
                    data.get("payment_form", ""),
                    data.get("payment_method", ""),
                    str(data.get("serie", "FAC")).strip().upper() or "FAC",
                    max(int(data.get("folio") or 1), 1),
                    raw_payload,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT id FROM cfdis WHERE facturama_id = ?", (facturama_id,)).fetchone()
            cfdi_id = int(row["id"])
            if "items" in data:
                conn.execute("DELETE FROM cfdi_items WHERE cfdi_id = ?", (cfdi_id,))
            for item in data.get("items", []):
                self._save_cfdi_item(
                    conn,
                    cfdi_id,
                    {
                        **item,
                        "issuer_id": item.get("issuer_id", issuer_id),
                        "client_id": item.get("client_id", client_id),
                    },
                )
            return cfdi_id

    def _save_cfdi_item(self, conn: sqlite3.Connection, cfdi_id: int, data: dict[str, Any]) -> int:
        now = utc_now()
        product_id = data.get("product_id")
        issuer_id = data.get("issuer_id")
        client_id = data.get("client_id")
        if issuer_id is None and product_id is not None:
            product = conn.execute("SELECT issuer_id FROM products WHERE id = ?", (product_id,)).fetchone()
            issuer_id = int(product["issuer_id"]) if product else None
        if issuer_id is None:
            cfdi = conn.execute("SELECT issuer_id FROM cfdis WHERE id = ?", (cfdi_id,)).fetchone()
            issuer_id = int(cfdi["issuer_id"]) if cfdi and cfdi["issuer_id"] is not None else None
        if issuer_id is None:
            raise ValueError("issuer_id is required for CFDI items")
        if client_id is None:
            cfdi = conn.execute("SELECT client_id FROM cfdis WHERE id = ?", (cfdi_id,)).fetchone()
            client_id = int(cfdi["client_id"]) if cfdi and cfdi["client_id"] is not None else None
        if product_id is not None:
            product = conn.execute(
                "SELECT id FROM products WHERE id = ? AND issuer_id = ?",
                (product_id, issuer_id),
            ).fetchone()
            if product is None:
                raise ValueError("product does not belong to issuer")
        cursor = conn.execute(
            """
            INSERT INTO cfdi_items
                (cfdi_id, product_id, issuer_id, client_id, description, name,
                 product_code, identification_number, quantity, unit_price,
                 subtotal, total, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cfdi_id,
                product_id,
                issuer_id,
                client_id,
                data.get("description", ""),
                data.get("name", data.get("description", "")),
                data.get("product_code", ""),
                data.get("identification_number", ""),
                float(data.get("quantity") or 0),
                float(data.get("unit_price") or data.get("price") or 0),
                float(data.get("subtotal") or 0),
                float(data.get("total") or 0),
                now,
            ),
        )
        return int(cursor.lastrowid)

    def save_cfdi_item(self, cfdi_id: int, data: dict[str, Any]) -> int:
        with self.connect() as conn:
            return self._save_cfdi_item(conn, cfdi_id, data)

    def list_invoiced_products(self, issuer_id: int | None = None) -> list[sqlite3.Row]:
        where_sql = "WHERE ci.issuer_id = ?" if issuer_id is not None else ""
        params = (issuer_id,) if issuer_id is not None else ()
        with self.connect() as conn:
            return conn.execute(
                f"""
                SELECT
                    COALESCE(p.id, ci.product_id) AS product_id,
                    COALESCE(p.name, ci.name, ci.description) AS name,
                    COALESCE(p.product_code, ci.product_code) AS product_code,
                    COALESCE(p.identification_number, ci.identification_number) AS identification_number,
                    ci.issuer_id,
                    i.legal_name AS issuer_name,
                    i.rfc AS issuer_rfc,
                    COUNT(*) AS invoice_count,
                    SUM(ci.quantity) AS quantity,
                    SUM(ci.total) AS total,
                    GROUP_CONCAT(DISTINCT COALESCE(cl.legal_name, c.recipient_name)) AS billed_client_names,
                    GROUP_CONCAT(DISTINCT COALESCE(cl.rfc, c.recipient_rfc)) AS billed_client_rfcs
                FROM cfdi_items ci
                JOIN cfdis c ON c.id = ci.cfdi_id
                LEFT JOIN products p ON p.id = ci.product_id
                LEFT JOIN issuers i ON i.id = ci.issuer_id
                LEFT JOIN clients cl ON cl.id = ci.client_id
                {where_sql}
                GROUP BY ci.issuer_id, COALESCE(p.id, ci.product_id), COALESCE(p.name, ci.name, ci.description),
                         COALESCE(p.product_code, ci.product_code),
                         COALESCE(p.identification_number, ci.identification_number)
                ORDER BY name
                """,
                params,
            ).fetchall()

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
