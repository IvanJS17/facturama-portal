from flask import Flask

from src.models import PortalDatabase
from src.routes import cfdi as cfdi_routes
from src.routes import clients as client_routes
from src.routes import dashboard as dashboard_routes
from src.routes import issuers as issuer_routes
from src.routes import products as product_routes


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


def test_products_list_filters_catalog_and_invoiced_clients_by_issuer(tmp_path):
    database = make_db(tmp_path)
    issuer_a, issuer_b, _, _ = seed_invoice(database)
    app = make_app(database)

    response = app.test_client().get(f"/products/?issuer_id={issuer_a}")

    assert response.status_code == 200
    assert b"Servicio A" in response.data
    assert b"CLIENTE A" in response.data
    assert b"AAA010101AAA" in response.data
    assert b"Servicio B" not in response.data
    assert b"Cliente B" not in response.data
    assert f"/products/new?issuer_id={issuer_a}".encode() in response.data


def test_new_product_preselects_issuer_from_query_string(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    app = make_app(database)

    response = app.test_client().get(f"/products/new?issuer_id={issuer_id}")

    assert response.status_code == 200
    assert f'value="{issuer_id}" selected'.encode() in response.data
    assert f"/products/?issuer_id={issuer_id}".encode() in response.data


def test_create_product_requires_valid_issuer(tmp_path):
    database = make_db(tmp_path)
    app = make_app(database)
    payload = product_payload(issuer_id=999, name="Servicio", sku="S-1")

    response = app.test_client().post("/products/", data=payload)

    assert response.status_code == 400
    assert b"Selecciona un emisor" in response.data
    assert database.list_products() == []


def test_api_products_filter_by_issuer(tmp_path):
    database = make_db(tmp_path)
    issuer_a, issuer_b, product_a, _ = seed_invoice(database)
    app = make_app(database)

    response = app.test_client().get(f"/api/products/?issuer_id={issuer_a}")

    assert response.status_code == 200
    data = response.get_json()
    assert [row["id"] for row in data] == [product_a]
    assert all(row["issuer_id"] == issuer_a for row in data)


def test_product_form_actions_point_to_create_and_update_routes(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    app = make_app(database)

    new_response = app.test_client().get("/products/new")

    assert new_response.status_code == 200
    assert b'<form method="post" action="/products/">' in new_response.data

    product_id = database.upsert_product(product_payload(issuer_id, "Servicio A", "A-1"))
    edit_response = app.test_client().get(f"/products/{product_id}/edit")

    assert edit_response.status_code == 200
    assert f'<form method="post" action="/products/{product_id}">'.encode() in edit_response.data


def test_products_list_supports_search_sort_and_safe_invalid_sort(tmp_path):
    database = make_db(tmp_path)
    issuer_a = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload("Issuer B", "BBB010101BBB"))
    database.upsert_product(product_payload(issuer_a, "Servicio Zeta", "SKU-Z"))
    database.upsert_product(product_payload(issuer_a, "Servicio Alfa", "SKU-A"))
    database.upsert_product(product_payload(issuer_b, "Servicio Externo", "SKU-X"))
    app = make_app(database)
    client = app.test_client()

    search_response = client.get(f"/products/?issuer_id={issuer_a}&q=sku-a")
    assert search_response.status_code == 200
    assert b"Servicio Alfa" in search_response.data
    assert b"Servicio Zeta" not in search_response.data
    assert b"Servicio Externo" not in search_response.data
    assert b'name="q"' in search_response.data
    assert b'value="sku-a"' in search_response.data
    assert (f'value="{issuer_a}" selected').encode() in search_response.data

    sort_response = client.get(f"/products/?issuer_id={issuer_a}&sort=name_desc")
    assert sort_response.status_code == 200
    assert sort_response.data.find(b"Servicio Zeta") < sort_response.data.find(b"Servicio Alfa")

    invalid_sort_response = client.get(f"/products/?issuer_id={issuer_a}&sort=bad")
    assert invalid_sort_response.status_code == 200
    assert invalid_sort_response.data.find(b"Servicio Alfa") < invalid_sort_response.data.find(b"Servicio Zeta")
