import sqlite3

import pytest

from src.models import PortalDatabase


def make_db(tmp_path):
    database = PortalDatabase(f"sqlite:///{tmp_path / 'portal.db'}")
    database.init_schema()
    return database


def issuer_payload(name, rfc):
    return {
        "legal_name": name,
        "rfc": rfc,
        "tax_regime": "601",
        "zip_code": "01000",
        "email": "",
        "active": True,
    }


def client_payload(issuer_id, name="Client", rfc="XEXX010101000"):
    return {
        "issuer_id": issuer_id,
        "facturama_id": "",
        "legal_name": name,
        "rfc": rfc,
        "email": "",
        "tax_regime": "601",
        "cfdi_use": "G03",
        "zip_code": "01000",
        "raw_payload": {},
    }


def product_payload(issuer_id, name="Service", identification_number="SKU-1"):
    return {
        "issuer_id": issuer_id,
        "facturama_id": "",
        "name": name,
        "identification_number": identification_number,
        "product_code": "01010101",
        "unit_code": "E48",
        "unit": "Servicio",
        "price": 100,
        "tax_object": "02",
        "raw_payload": {},
    }


def column_info(database, table_name):
    with database.connect() as conn:
        return {row["name"]: row for row in conn.execute(f"PRAGMA table_info({table_name})")}


def test_fresh_schema_has_required_issuer_scoped_columns(tmp_path):
    database = make_db(tmp_path)

    client_columns = column_info(database, "clients")
    product_columns = column_info(database, "products")
    cfdi_columns = column_info(database, "cfdis")
    item_columns = column_info(database, "cfdi_items")

    assert client_columns["issuer_id"]["notnull"] == 1
    assert product_columns["issuer_id"]["notnull"] == 1
    assert "client_id" in cfdi_columns
    assert {"cfdi_id", "product_id", "issuer_id", "client_id", "total"} <= set(item_columns)

    with database.connect() as conn:
        client_indexes = conn.execute("PRAGMA index_list(clients)").fetchall()
        assert any(index["unique"] for index in client_indexes)
        product_indexes = conn.execute("PRAGMA index_list(products)").fetchall()
        assert any(index["name"] == "idx_products_issuer_identification" for index in product_indexes)

    database.init_schema()
    assert "issuer_id" in column_info(database, "products")


def test_clients_are_unique_per_issuer_not_globally(tmp_path):
    database = make_db(tmp_path)
    issuer_a = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload("Issuer B", "BBB010101BBB"))

    client_a = database.upsert_client(client_payload(issuer_a, "Same RFC A", "COSC8001137NA"))
    client_b = database.upsert_client(client_payload(issuer_b, "Same RFC B", "COSC8001137NA"))

    assert client_a != client_b
    assert database.get_client_for_issuer(client_a, issuer_a)["legal_name"] == "Same RFC A"
    assert database.get_client_for_issuer(client_a, issuer_b) is None
    assert [row["id"] for row in database.list_clients(issuer_a)] == [client_a]


def test_products_are_scoped_by_issuer_and_list_with_issuer_info(tmp_path):
    database = make_db(tmp_path)
    issuer_a = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload("Issuer B", "BBB010101BBB"))

    product_a = database.upsert_product(product_payload(issuer_a, "Hosting A", "SKU-1"))
    product_b = database.upsert_product(product_payload(issuer_b, "Hosting B", "SKU-1"))
    updated_product_a = database.upsert_product(product_payload(issuer_a, "Hosting A Updated", "SKU-1"))

    assert updated_product_a == product_a
    assert product_a != product_b
    assert database.get_product_for_issuer(product_a, issuer_a)["name"] == "Hosting A Updated"
    assert database.get_product_for_issuer(product_a, issuer_b) is None

    issuer_a_products = database.list_products(issuer_id=issuer_a)
    assert [row["id"] for row in issuer_a_products] == [product_a]
    assert issuer_a_products[0]["issuer_name"] == "Issuer A"


def test_cfdi_client_backfill_and_invoiced_product_history(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    client_id = database.upsert_client(client_payload(issuer_id, "Acme", "ACM010101ABC"))
    product_id = database.upsert_product(product_payload(issuer_id, "Implementation", "IMP-1"))

    cfdi_id = database.save_cfdi(
        {
            "facturama_id": "cfdi-1",
            "uuid": "uuid-1",
            "issuer_id": issuer_id,
            "recipient_rfc": "ACM010101ABC",
            "recipient_name": "Acme",
            "total": 116,
            "items": [
                {
                    "product_id": product_id,
                    "description": "Implementation",
                    "product_code": "01010101",
                    "identification_number": "IMP-1",
                    "quantity": 1,
                    "unit_price": 100,
                    "subtotal": 100,
                    "total": 116,
                }
            ],
        }
    )

    cfdi = database.get_cfdi(cfdi_id)
    assert cfdi["client_id"] == client_id
    assert cfdi["client_name"] == "Acme"

    invoiced_products = database.list_invoiced_products(issuer_id)
    assert len(invoiced_products) == 1
    assert invoiced_products[0]["product_id"] == product_id
    assert invoiced_products[0]["issuer_name"] == "Issuer A"
    assert invoiced_products[0]["billed_client_names"] == "Acme"
    assert invoiced_products[0]["billed_client_rfcs"] == "ACM010101ABC"


def test_legacy_schema_migrates_without_dropping_issuer_id_or_history(tmp_path):
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE issuers (
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
        INSERT INTO issuers
            (legal_name, rfc, tax_regime, zip_code, email, active, created_at, updated_at)
        VALUES ('Issuer A', 'AAA010101AAA', '601', '01000', '', 1, 'now', 'now');

        CREATE TABLE clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            facturama_id TEXT NOT NULL DEFAULT '',
            issuer_id INTEGER,
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
        INSERT INTO clients
            (facturama_id, issuer_id, legal_name, rfc, email, tax_regime, cfdi_use,
             zip_code, raw_payload, created_at, updated_at)
        VALUES ('', NULL, 'Legacy Client', 'LEG010101ABC', '', '601', 'G03',
                '01000', '{}', 'now', 'now');

        CREATE TABLE products (
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
        INSERT INTO products
            (facturama_id, name, identification_number, product_code, unit_code, unit,
             price, tax_object, raw_payload, created_at, updated_at)
        VALUES ('', 'Legacy Product', 'LEG-SKU', '01010101', 'E48', 'Servicio',
                10, '02', '{}', 'now', 'now');

        CREATE TABLE cfdis (
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
            updated_at TEXT NOT NULL
        );
        INSERT INTO cfdis
            (facturama_id, uuid, issuer_id, recipient_rfc, recipient_name, total,
             status, cfdi_type, payment_form, payment_method, raw_payload, created_at, updated_at)
        VALUES ('legacy-cfdi', '', 1, 'LEG010101ABC', 'Legacy Client', 10,
                'active', 'I', '', '', '{}', 'now', 'now');
        """
    )
    conn.commit()
    conn.close()

    database = PortalDatabase(f"sqlite:///{db_path}")
    database.init_schema()
    database.init_schema()

    client = database.list_clients()[0]
    product = database.list_products()[0]
    cfdi = database.list_cfdis()[0]

    assert client["issuer_id"] == 1
    assert product["issuer_id"] == 1
    assert cfdi["client_id"] == client["id"]
    assert column_info(database, "clients")["issuer_id"]["notnull"] == 1
    assert column_info(database, "products")["issuer_id"]["notnull"] == 1


def test_cfdi_item_rejects_product_from_another_issuer(tmp_path):
    database = make_db(tmp_path)
    issuer_a = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload("Issuer B", "BBB010101BBB"))
    database.upsert_client(client_payload(issuer_a, "Acme", "ACM010101ABC"))
    product_b = database.upsert_product(product_payload(issuer_b, "Foreign Product", "B-1"))
    cfdi_id = database.save_cfdi(
        {
            "facturama_id": "cfdi-1",
            "issuer_id": issuer_a,
            "recipient_rfc": "ACM010101ABC",
            "recipient_name": "Acme",
        }
    )

    with pytest.raises(ValueError, match="product does not belong to issuer"):
        database.save_cfdi_item(cfdi_id, {"product_id": product_b, "issuer_id": issuer_a})
