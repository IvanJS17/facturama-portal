"""Tests for CFDI detail page showing products/items, and product-issuer guardrails."""

import re

from flask import Flask

from src.models import PortalDatabase
from src.routes import cfdi as cfdi_routes
from src.routes import clients as client_routes
from src.routes import dashboard as dashboard_routes
from src.routes import issuers as issuer_routes
from src.routes import products as product_routes


# ---------------------------------------------------------------------------
# helpers (duplicated from test_products_routes to keep this file self-contained)
# ---------------------------------------------------------------------------

def make_db(tmp_path):
    database = PortalDatabase(f"sqlite:///{tmp_path / 'portal.db'}")
    database.init_schema()
    return database


def make_app(database):
    app = Flask(__name__, template_folder="../../src/templates")
    app.config.update(TESTING=True, SECRET_KEY="***")
    app.extensions["portal_db"] = database
    app.register_blueprint(dashboard_routes.bp)
    app.register_blueprint(client_routes.bp)
    app.register_blueprint(issuer_routes.bp)
    app.register_blueprint(product_routes.bp)
    app.register_blueprint(product_routes.api_bp)
    app.register_blueprint(cfdi_routes.bp)
    return app


def issuer_payload(name, rfc):
    return {
        "legal_name": name,
        "rfc": rfc,
        "tax_regime": "601",
        "zip_code": "01000",
        "email": "",
        "active": True,
    }


def client_payload(issuer_id, name, rfc):
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


def product_payload(issuer_id, name, sku):
    return {
        "issuer_id": issuer_id,
        "facturama_id": "",
        "name": name,
        "identification_number": sku,
        "product_code": "01010101",
        "unit_code": "E48",
        "unit": "Servicio",
        "price": 100,
        "tax_object": "02",
        "raw_payload": {},
    }


def seed_all(database):
    """Seed database with two issuers, clients, products, and CFDIs with items.

    Returns a dict with keys: issuer_a, issuer_b, client_a, client_b,
    product_a, product_b, cfdi_a, cfdi_b.
    """
    issuer_a = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload("Issuer B", "BBB010101BBB"))
    client_a = database.upsert_client(client_payload(issuer_a, "Cliente A", "CLA010101ABC"))
    client_b = database.upsert_client(client_payload(issuer_b, "Cliente B", "CLB010101ABC"))
    product_a = database.upsert_product(product_payload(issuer_a, "Servicio A", "A-1"))
    product_b = database.upsert_product(product_payload(issuer_b, "Servicio B", "B-1"))

    # create invoice series for each issuer (required for CFDI creation route)
    database.create_series(issuer_a, "FAC", 1)
    database.create_series(issuer_b, "FAC", 1)

    cfdi_a = database.save_cfdi(
        {
            "facturama_id": "cfdi-a",
            "issuer_id": issuer_a,
            "client_id": client_a,
            "recipient_rfc": "CLA010101ABC",
            "recipient_name": "Cliente A",
            "total": 116,
            "items": [
                {
                    "product_id": product_a,
                    "issuer_id": issuer_a,
                    "client_id": client_a,
                    "name": "Servicio A",
                    "description": "Servicio A",
                    "product_code": "01010101",
                    "identification_number": "A-1",
                    "quantity": 1,
                    "unit_price": 100,
                    "subtotal": 100,
                    "total": 116,
                }
            ],
        }
    )
    cfdi_b = database.save_cfdi(
        {
            "facturama_id": "cfdi-b",
            "issuer_id": issuer_b,
            "client_id": client_b,
            "recipient_rfc": "CLB010101ABC",
            "recipient_name": "Cliente B",
            "total": 232,
            "items": [
                {
                    "product_id": product_b,
                    "issuer_id": issuer_b,
                    "client_id": client_b,
                    "name": "Servicio B",
                    "description": "Servicio B",
                    "product_code": "01010101",
                    "identification_number": "B-1",
                    "quantity": 2,
                    "unit_price": 100,
                    "subtotal": 200,
                    "total": 232,
                }
            ],
        }
    )
    return {
        "issuer_a": issuer_a,
        "issuer_b": issuer_b,
        "client_a": client_a,
        "client_b": client_b,
        "product_a": product_a,
        "product_b": product_b,
        "cfdi_a": cfdi_a,
        "cfdi_b": cfdi_b,
    }


def _html_without_raw_payload(html: bytes) -> bytes:
    """Remove the <details>…</details> block containing the raw_payload JSON.

    This lets us assert that product data lives in the rendered table, not
    just in the machine-readable JSON blob.
    """
    text = html.decode("utf-8", errors="replace")
    # remove everything from <details> to </details> (including nested tags)
    text = re.sub(r"<details>.*?</details>", "", text, flags=re.DOTALL)
    return text.encode("utf-8")


# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def test_cfdi_detail_shows_product_name(tmp_path):
    database = make_db(tmp_path)
    ids = seed_all(database)
    app = make_app(database)

    response = app.test_client().get(f"/cfdi/{ids['cfdi_a']}/detail")
    assert response.status_code == 200

    html = response.data
    # product name must appear outside the raw-payload JSON block
    clean = _html_without_raw_payload(html)
    assert b"Servicio A" in clean
    # and it should be rendered as a table cell
    assert b">Servicio A</td>" in clean


def test_cfdi_detail_shows_product_code(tmp_path):
    database = make_db(tmp_path)
    ids = seed_all(database)
    app = make_app(database)

    response = app.test_client().get(f"/cfdi/{ids['cfdi_a']}/detail")
    assert response.status_code == 200

    html = _html_without_raw_payload(response.data)
    assert b"01010101" in html
    # confirm it sits inside a <td> (table cell, not in a heading or label)
    assert b">01010101</td>" in html


def test_cfdi_detail_shows_quantity(tmp_path):
    database = make_db(tmp_path)
    ids = seed_all(database)
    app = make_app(database)

    response = app.test_client().get(f"/cfdi/{ids['cfdi_a']}/detail")
    assert response.status_code == 200

    html = _html_without_raw_payload(response.data)
    # The first CFDI has quantity=1 (stored as REAL → renders "1.0").
    # The template renders: <td>{{ item.quantity }}</td>
    # Look for the number inside its own <td> to avoid false positives.
    assert re.search(rb">\s*1(?:\.0)?\s*</td>", html)


def test_cfdi_detail_shows_unit_price(tmp_path):
    database = make_db(tmp_path)
    ids = seed_all(database)
    app = make_app(database)

    response = app.test_client().get(f"/cfdi/{ids['cfdi_a']}/detail")
    assert response.status_code == 200

    html = _html_without_raw_payload(response.data)
    # unit_price=100 → renders "$100.00"
    assert b"$100.00" in html


def test_cfdi_detail_shows_subtotal_and_total(tmp_path):
    database = make_db(tmp_path)
    ids = seed_all(database)
    app = make_app(database)

    response = app.test_client().get(f"/cfdi/{ids['cfdi_a']}/detail")
    assert response.status_code == 200

    html = _html_without_raw_payload(response.data)
    # subtotal=100 ($100.00) and total=116 ($116.00) are distinct columns
    assert b"$100.00" in html
    assert b"$116.00" in html


def test_cfdi_detail_items_section_present(tmp_path):
    database = make_db(tmp_path)
    ids = seed_all(database)
    app = make_app(database)

    response = app.test_client().get(f"/cfdi/{ids['cfdi_a']}/detail")
    assert response.status_code == 200

    # The template heading is "Conceptos / Productos"
    assert b"Conceptos" in response.data or b"Productos" in response.data


def test_product_issuer_mismatch_rejected(tmp_path):
    """Creating a CFDI with a product that belongs to a different issuer
    must return HTTP 400."""
    database = make_db(tmp_path)
    ids = seed_all(database)
    app = make_app(database)

    # Post with issuer_a but product_b (which belongs to issuer_b).
    response = app.test_client().post(
        "/cfdi/",
        data={
            "issuer_id": str(ids["issuer_a"]),
            "client_id": str(ids["client_a"]),
            "product_id": str(ids["product_b"]),
            "series_id": "999",  # not reached, but _required_int needs an int
        },
    )
    assert response.status_code == 400


def test_get_cfdi_items_db_method(tmp_path):
    """Direct call to db().get_cfdi_items(cfdi_id) returns correctly shaped rows."""
    database = make_db(tmp_path)
    ids = seed_all(database)

    items = database.get_cfdi_items(ids["cfdi_a"])
    assert isinstance(items, list)
    assert len(items) == 1

    item = items[0]
    # joined columns from products table
    assert item["product_name"] == "Servicio A"
    assert item["product_code"] == "01010101"
    # item-level columns
    assert item["quantity"] == 1
    assert item["unit_price"] == 100
    assert item["subtotal"] == 100
    assert item["total"] == 116
