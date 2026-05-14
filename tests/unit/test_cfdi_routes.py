from flask import Flask

from src.models import PortalDatabase
from src.routes import cfdi as cfdi_routes
from src.routes import clients as client_routes
from src.routes import dashboard as dashboard_routes
from src.routes import issuers as issuer_routes
from src.routes import products as product_routes
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
    app = Flask(__name__, template_folder="../../src/templates")
    app.config.update(TESTING=True, SECRET_KEY="test")
    app.extensions["portal_db"] = database
    app.register_blueprint(dashboard_routes.bp)
    app.register_blueprint(client_routes.bp)
    app.register_blueprint(issuer_routes.bp)
    app.register_blueprint(product_routes.bp)
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


def test_new_cfdi_form_posts_to_create_route(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    fake_api = FakeCfdiAPI(database)
    app = make_app(database, fake_api, monkeypatch)

    response = app.test_client().get("/cfdi/new")

    assert response.status_code == 200
    assert b'<form method="post" action="/cfdi/" id="cfdi-form" class="step-shell">' in response.data


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
    assert b"does not belong to selected issuer" in response.data
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


def test_cfdi_list_supports_search_status_issuer_sort_and_safe_invalid_sort(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    issuer_a, issuer_b, client_a, client_b, _, _ = seed_two_issuers(database)
    database.save_cfdi(
        {
            "facturama_id": "folio-zeta",
            "issuer_id": issuer_a,
            "client_id": client_a,
            "recipient_rfc": "ACA010101ABC",
            "recipient_name": "Cliente Zeta",
            "status": "active",
            "total": 100,
        }
    )
    database.save_cfdi(
        {
            "facturama_id": "folio-alfa",
            "issuer_id": issuer_a,
            "client_id": client_a,
            "recipient_rfc": "ACA010101ABC",
            "recipient_name": "Cliente Alfa",
            "status": "canceled",
            "total": 200,
        }
    )
    database.save_cfdi(
        {
            "facturama_id": "folio-other",
            "issuer_id": issuer_b,
            "client_id": client_b,
            "recipient_rfc": "ACB010101ABC",
            "recipient_name": "Cliente Externo",
            "status": "active",
            "total": 300,
        }
    )
    fake_api = FakeCfdiAPI(database)
    app = make_app(database, fake_api, monkeypatch)
    client = app.test_client()

    filtered = client.get(f"/cfdi/?issuer_id={issuer_a}&q=alfa&status=canceled&sort=total_desc")
    assert filtered.status_code == 200
    assert b"ACME A" in filtered.data
    assert b"Cliente Zeta" not in filtered.data
    assert b"Acme B" not in filtered.data
    assert b'name="q"' in filtered.data
    assert b'value="alfa"' in filtered.data
    assert (f'value="{issuer_a}" selected').encode() in filtered.data
    assert b'<option value="canceled" selected>' in filtered.data

    sort_response = client.get(f"/cfdi/?issuer_id={issuer_a}&sort=total_asc")
    assert sort_response.status_code == 200
    assert sort_response.data.find(b"$100.00") < sort_response.data.find(b"$200.00")

    invalid_sort_response = client.get(f"/cfdi/?issuer_id={issuer_a}&sort=bad")
    assert invalid_sort_response.status_code == 200


def test_cfdi_list_search_within_issuer_by_uuid_folio_and_client_rfc(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    issuer_a, issuer_b, client_a, client_b, _, _ = seed_two_issuers(database)
    database.save_cfdi(
        {
            "facturama_id": "remote-a-uuid-001",
            "uuid": "UUID-A-12345",
            "issuer_id": issuer_a,
            "client_id": client_a,
            "recipient_rfc": "ACA010101ABC",
            "recipient_name": "Cliente Alfa",
            "serie": "FAC",
            "folio": 55,
            "status": "active",
            "total": 100,
        }
    )
    database.save_cfdi(
        {
            "facturama_id": "remote-b-uuid-001",
            "uuid": "UUID-B-54321",
            "issuer_id": issuer_b,
            "client_id": client_b,
            "recipient_rfc": "ACB010101ABC",
            "recipient_name": "Cliente Externo",
            "serie": "FAC",
            "folio": 55,
            "status": "active",
            "total": 120,
        }
    )
    fake_api = FakeCfdiAPI(database)
    app = make_app(database, fake_api, monkeypatch)
    client = app.test_client()

    by_uuid = client.get(f"/cfdi/?issuer_id={issuer_a}&q=UUID-A-12345")
    assert by_uuid.status_code == 200
    assert b"ACME A" in by_uuid.data
    assert b"Acme B" not in by_uuid.data

    by_folio = client.get(f"/cfdi/?issuer_id={issuer_a}&q=55")
    assert by_folio.status_code == 200
    assert b"ACME A" in by_folio.data
    assert b"Acme B" not in by_folio.data

    by_client_rfc = client.get(f"/cfdi/?issuer_id={issuer_a}&q=ACA010101ABC")
    assert by_client_rfc.status_code == 200
    assert b"ACME A" in by_client_rfc.data
    assert b"Acme B" not in by_client_rfc.data


def test_cfdi_list_invalid_issuer_and_invalid_query_params_do_not_500(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    issuer_a, _, client_a, _, _, _ = seed_two_issuers(database)
    database.save_cfdi(
        {
            "facturama_id": "cfdi-a",
            "issuer_id": issuer_a,
            "client_id": client_a,
            "recipient_rfc": "ACA010101ABC",
            "recipient_name": "Cliente A",
            "status": "active",
            "total": 100,
        }
    )
    fake_api = FakeCfdiAPI(database)
    app = make_app(database, fake_api, monkeypatch)
    client = app.test_client()

    invalid_issuer = client.get("/cfdi/?issuer_id=abc&q=test&sort=drop")
    assert invalid_issuer.status_code == 200

    unknown_issuer = client.get("/cfdi/?issuer_id=999999&q=test&sort=drop")
    assert unknown_issuer.status_code == 200
