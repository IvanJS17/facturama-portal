from flask import Flask

from src.models import PortalDatabase
from src.routes import cfdi as cfdi_routes
from src.routes import clients as client_routes
from src.routes import dashboard as dashboard_routes
from src.routes import issuers as issuer_routes
from src.routes import products as product_routes
from src.utils.config import Config


def make_db(tmp_path):
    database = PortalDatabase(f"sqlite:///{tmp_path / 'portal.db'}")
    database.init_schema()
    return database


def make_app(database):
    app = Flask(__name__, template_folder="../../src/templates")
    app.config.update(
        TESTING=True,
        SECRET_KEY="***",
        PORTAL_CONFIG=Config(
            facturama_user="test",
            facturama_password="test",
        ),
    )
    app.extensions["portal_db"] = database
    app.register_blueprint(dashboard_routes.bp)
    app.register_blueprint(cfdi_routes.bp)
    app.register_blueprint(cfdi_routes.api_bp)
    app.register_blueprint(client_routes.bp)
    app.register_blueprint(client_routes.api_bp)
    app.register_blueprint(issuer_routes.bp)
    app.register_blueprint(issuer_routes.api_bp)
    app.register_blueprint(product_routes.bp)
    app.register_blueprint(product_routes.api_bp)
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


def seed_invoice(database):
    issuer_a = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload("Issuer B", "BBB010101BBB"))
    client_a = database.upsert_client(client_payload(issuer_a, "Cliente A", "CLA010101ABC"))
    client_b = database.upsert_client(client_payload(issuer_b, "Cliente B", "CLB010101ABC"))
    product_a = database.upsert_product(product_payload(issuer_a, "Servicio A", "A-1"))
    product_b = database.upsert_product(product_payload(issuer_b, "Servicio B", "B-1"))
    database.save_cfdi(
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
    database.save_cfdi(
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
    return issuer_a, issuer_b, product_a, product_b


# --- Tests ---


def test_dashboard_shows_emisor_column(tmp_path):
    database = make_db(tmp_path)
    seed_invoice(database)
    app = make_app(database)

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"<th>Emisor</th>" in response.data


def test_dashboard_shows_cliente_column(tmp_path):
    database = make_db(tmp_path)
    seed_invoice(database)
    app = make_app(database)

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"<th>Cliente</th>" in response.data


def test_dashboard_shows_rfc_column(tmp_path):
    database = make_db(tmp_path)
    seed_invoice(database)
    app = make_app(database)

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"<th>RFC</th>" in response.data


def test_dashboard_shows_folio_column(tmp_path):
    database = make_db(tmp_path)
    seed_invoice(database)
    app = make_app(database)

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"<th>Folio</th>" in response.data


def test_dashboard_has_issuer_name_in_row(tmp_path):
    database = make_db(tmp_path)
    seed_invoice(database)
    app = make_app(database)

    response = app.test_client().get("/")

    assert response.status_code == 200
    # The template renders issuer_name in a <strong> tag
    assert b"ISSUER A" in response.data


def test_dashboard_has_client_name_in_row(tmp_path):
    database = make_db(tmp_path)
    seed_invoice(database)
    app = make_app(database)

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"CLIENTE A" in response.data


def test_dashboard_has_recipient_rfc(tmp_path):
    database = make_db(tmp_path)
    seed_invoice(database)
    app = make_app(database)

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"CLA010101ABC" in response.data


def test_dashboard_folio_abbreviation(tmp_path):
    database = make_db(tmp_path)
    issuer = database.save_issuer(issuer_payload("Issuer X", "XXX010101XXX"))
    client = database.upsert_client(client_payload(issuer, "Cliente X", "CLX010101XXX"))
    product = database.upsert_product(product_payload(issuer, "Servicio X", "X-1"))
    database.save_cfdi(
        {
            "facturama_id": "cfdi-folio-1234",
            "issuer_id": issuer,
            "client_id": client,
            "recipient_rfc": "CLX010101XXX",
            "recipient_name": "Cliente X",
            "folio": 1234,
            "total": 116,
            "items": [
                {
                    "product_id": product,
                    "issuer_id": issuer,
                    "client_id": client,
                    "name": "Servicio X",
                    "description": "Servicio X",
                    "product_code": "01010101",
                    "identification_number": "X-1",
                    "quantity": 1,
                    "unit_price": 100,
                    "subtotal": 100,
                    "total": 116,
                }
            ],
        }
    )
    app = make_app(database)

    response = app.test_client().get("/")

    assert response.status_code == 200
    # folio=1234 -> '...1234' in the HTML
    assert b"...1234" in response.data


def test_dashboard_renders_csd_expiration_alerts_with_severity_and_edit_link(tmp_path):
    database = make_db(tmp_path)
    issuer_expired = database.save_issuer(issuer_payload("Issuer Expired", "EXP010101AAA"))
    issuer_soon = database.save_issuer(issuer_payload("Issuer Soon", "SOO010101AAA"))
    issuer_mid = database.save_issuer(issuer_payload("Issuer Mid", "MID010101AAA"))
    issuer_late = database.save_issuer(issuer_payload("Issuer Late", "LAT010101AAA"))

    database.save_issuer_csd_metadata(
        issuer_expired,
        {
            "rfc": "EXP010101AAA",
            "serial": "EXP-1",
            "subject": "CN=Expired",
            "valid_from": "2025-01-01T00:00:00+00:00",
            "valid_to": "2026-05-10T00:00:00+00:00",
        },
    )
    database.save_issuer_csd_metadata(
        issuer_soon,
        {
            "rfc": "SOO010101AAA",
            "serial": "SOON-1",
            "subject": "CN=Soon",
            "valid_from": "2025-01-01T00:00:00+00:00",
            "valid_to": "2026-05-30T00:00:00+00:00",
        },
    )
    database.save_issuer_csd_metadata(
        issuer_mid,
        {
            "rfc": "MID010101AAA",
            "serial": "MID-1",
            "subject": "CN=Mid",
            "valid_from": "2025-01-01T00:00:00+00:00",
            "valid_to": "2026-07-10T00:00:00+00:00",
        },
    )
    database.save_issuer_csd_metadata(
        issuer_late,
        {
            "rfc": "LAT010101AAA",
            "serial": "LAT-1",
            "subject": "CN=Late",
            "valid_from": "2025-01-01T00:00:00+00:00",
            "valid_to": "2026-08-10T00:00:00+00:00",
        },
    )
    app = make_app(database)
    app.config["CSD_ALERT_REFERENCE_DATE"] = "2026-05-14"

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert "Sellos CSD próximos a vencer".encode() in response.data
    assert b"Vencido" in response.data
    assert "0-30 días".encode() in response.data
    assert "31-60 días".encode() in response.data
    assert "61-90 días".encode() in response.data
    assert b"/issuers/" in response.data
    assert b"/edit" in response.data


def test_dashboard_uses_configurable_csd_window_days(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    database.save_issuer_csd_metadata(
        issuer_id,
        {
            "rfc": "AAA010101AAA",
            "serial": "A-1",
            "subject": "CN=A",
            "valid_from": "2025-01-01T00:00:00+00:00",
            "valid_to": "2026-07-10T00:00:00+00:00",
        },
    )
    app = make_app(database)
    app.config["CSD_ALERT_REFERENCE_DATE"] = "2026-05-14"
    app.config["CSD_EXPIRATION_ALERT_DAYS"] = 30

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b"A-1" not in response.data
    assert "No hay CSD vencidos o próximos a vencer en esta ventana.".encode() in response.data
