from flask import Flask

from src.models import PortalDatabase
from src.routes import cfdi as cfdi_routes
from src.services.facturama_api import FacturamaAPI
from src.utils.config import Config


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


class FakeCfdiAPI:
    def __init__(self, database):
        self.database = database
        self.created_payloads = []

    def create_cfdi(self, payload):
        self.created_payloads.append(payload)
        return {
            "Id": f"remote-{len(self.created_payloads)}",
            "Total": payload["Total"],
            "Complement": {"TaxStampUuid": "uuid-1"},
            "Status": "active",
        }

    def cache_cfdi_result(self, result, issuer_id, request_payload, local_data=None):
        config = Config(facturama_user="user", facturama_password="password")
        FacturamaAPI(config, self.database).cache_cfdi_result(result, issuer_id, request_payload, local_data)


def make_app(database, fake_api, monkeypatch):
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test")
    app.extensions["portal_db"] = database
    app.register_blueprint(cfdi_routes.bp)
    app.register_blueprint(cfdi_routes.api_bp)
    monkeypatch.setattr(cfdi_routes, "api", lambda: fake_api)
    return app


def seed_two_issuers(database):
    issuer_a = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload("Issuer B", "BBB010101BBB"))
    client_a = database.upsert_client(client_payload(issuer_a, "Acme A", "ACA010101ABC"))
    client_b = database.upsert_client(client_payload(issuer_b, "Acme B", "ACB010101ABC"))
    product_a = database.upsert_product(product_payload(issuer_a, "Service A", "A-1"))
    product_b = database.upsert_product(product_payload(issuer_b, "Service B", "B-1"))
    return issuer_a, issuer_b, client_a, client_b, product_a, product_b


def cfdi_payload(issuer_id, client_id, product_id):
    return {
        "issuer_id": issuer_id,
        "client_id": client_id,
        "product_id": product_id,
        "series_id": 0,
        "quantity": 2,
        "unit_price": 125,
        "iva_rate": 0.16,
        "payment_form": "03",
        "payment_method": "PUE",
        "description": "Scoped service",
    }


def ensure_series(database, issuer_id, name="FAC", start_folio=1):
    return database.create_series(issuer_id, name, start_folio)


def test_api_create_cfdi_rejects_client_from_another_issuer(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    issuer_a, _, _, client_b, product_a, _ = seed_two_issuers(database)
    series_id = ensure_series(database, issuer_a)
    fake_api = FakeCfdiAPI(database)
    app = make_app(database, fake_api, monkeypatch)
    payload = cfdi_payload(issuer_a, client_b, product_a)
    payload["series_id"] = series_id

    response = app.test_client().post(
        "/api/cfdi/",
        json=payload,
    )

    assert response.status_code == 400
    assert response.get_json() == {"error": "Selected client does not belong to selected issuer"}
    assert fake_api.created_payloads == []


def test_web_create_cfdi_rejects_product_from_another_issuer(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    issuer_a, _, client_a, _, _, product_b = seed_two_issuers(database)
    series_id = ensure_series(database, issuer_a)
    fake_api = FakeCfdiAPI(database)
    app = make_app(database, fake_api, monkeypatch)
    payload = cfdi_payload(issuer_a, client_a, product_b)
    payload["series_id"] = series_id

    response = app.test_client().post(
        "/cfdi/",
        data=payload,
    )

    assert response.status_code == 400
    assert b"Selected product does not belong to selected issuer" in response.data
    assert fake_api.created_payloads == []


def test_api_create_cfdi_persists_client_and_item_links(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    issuer_a, _, client_a, _, product_a, _ = seed_two_issuers(database)
    series_id = ensure_series(database, issuer_a, "FAC", 10)
    fake_api = FakeCfdiAPI(database)
    app = make_app(database, fake_api, monkeypatch)
    payload = cfdi_payload(issuer_a, client_a, product_a)
    payload["series_id"] = series_id

    response = app.test_client().post(
        "/api/cfdi/",
        json=payload,
    )

    assert response.status_code == 201
    cfdis = database.list_cfdis(recipient_rfc="ACA010101ABC", status="active")
    assert len(cfdis) == 1
    assert cfdis[0]["client_id"] == client_a
    assert cfdis[0]["issuer_id"] == issuer_a
    assert cfdis[0]["total"] == 290
    assert cfdis[0]["serie"] == "FAC"
    assert cfdis[0]["folio"] == 10

    with database.connect() as conn:
        item = conn.execute("SELECT * FROM cfdi_items WHERE cfdi_id = ?", (cfdis[0]["id"],)).fetchone()
    assert item["product_id"] == product_a
    assert item["issuer_id"] == issuer_a
    assert item["client_id"] == client_a
    assert item["quantity"] == 2
    assert item["unit_price"] == 125
    assert item["subtotal"] == 250
    assert item["total"] == 290
    assert fake_api.created_payloads[0]["Serie"] == "FAC"
    assert fake_api.created_payloads[0]["Folio"] == "10"
