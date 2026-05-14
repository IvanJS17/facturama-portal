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
    app.register_blueprint(issuer_routes.bp)
    app.register_blueprint(issuer_routes.api_bp)
    app.register_blueprint(client_routes.bp)
    app.register_blueprint(product_routes.bp)
    app.register_blueprint(cfdi_routes.bp)
    return app


def issuer_payload(name="Issuer A", rfc="AAA010101AAA"):
    return {
        "legal_name": name,
        "rfc": rfc,
        "tax_regime": "601",
        "zip_code": "01000",
        "email": "",
        "active": True,
    }


def test_issuer_form_actions_point_to_create_and_update_routes(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    new_response = app.test_client().get("/issuers/new")

    assert new_response.status_code == 200
    assert b'<form method="post" class="issuer-fiscal-form" action="/issuers/">' in new_response.data

    edit_response = app.test_client().get(f"/issuers/{issuer_id}/edit")

    assert edit_response.status_code == 200
    assert f'<form method="post" class="issuer-fiscal-form" action="/issuers/{issuer_id}">'.encode() in edit_response.data


def test_issuer_form_includes_fiscal_normalization_js_hook(tmp_path):
    database = make_db(tmp_path)
    app = make_app(database)

    response = app.test_client().get("/issuers/new")

    assert response.status_code == 200
    assert b"issuer-fiscal-form" in response.data


def test_issuer_edit_route_rejects_post_and_update_route_accepts_post(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)
    client = app.test_client()

    wrong_post = client.post(
        f"/issuers/{issuer_id}/edit",
        data={
            "legal_name": "Issuer Updated",
            "rfc": "AAA010101AAA",
            "tax_regime": "601",
            "zip_code": "01000",
            "email": "",
        },
    )

    assert wrong_post.status_code == 405

    correct_post = client.post(
        f"/issuers/{issuer_id}",
        data={
            "legal_name": "Issuer Updated",
            "rfc": "AAA010101AAA",
            "tax_regime": "601",
            "zip_code": "01000",
            "email": "",
            "active": "1",
        },
    )

    assert correct_post.status_code == 302
    updated = database.get_issuer(issuer_id)
    assert updated["legal_name"] == "ISSUER UPDATED"


def test_create_issuer_invalid_fiscal_fields_shows_validation_error_without_500(tmp_path):
    database = make_db(tmp_path)
    app = make_app(database)

    response = app.test_client().post(
        "/issuers/",
        data={
            "legal_name": "",
            "rfc": "BADRFC",
            "tax_regime": "601",
            "zip_code": "12",
            "email": "",
            "active": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Error de validaci" in response.data
    assert database.list_issuers() == []


def test_update_issuer_invalid_fiscal_fields_shows_validation_error_without_500(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    response = app.test_client().post(
        f"/issuers/{issuer_id}",
        data={
            "legal_name": "",
            "rfc": "BADRFC",
            "tax_regime": "601",
            "zip_code": "12",
            "email": "",
            "active": "1",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Error de validaci" in response.data
    updated = database.get_issuer(issuer_id)
    assert updated["legal_name"] == "ISSUER A"


def test_api_create_issuer_invalid_fiscal_fields_returns_400_json(tmp_path):
    database = make_db(tmp_path)
    app = make_app(database)

    response = app.test_client().post(
        "/api/issuers/",
        json={
            "legal_name": "",
            "rfc": "BADRFC",
            "tax_regime": "601",
            "zip_code": "12",
            "email": "",
            "active": True,
        },
    )

    assert response.status_code == 400
    body = response.get_json()
    assert "error" in body
    assert database.list_issuers() == []


def product_payload(issuer_id, name="Service", sku="SKU-1"):
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


def test_issuer_edit_renders_issuer_products_and_add_product_link(tmp_path):
    database = make_db(tmp_path)
    issuer_a = database.save_issuer(issuer_payload(name="Issuer A", rfc="AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload(name="Issuer B", rfc="BBB010101BBB"))
    product_a = database.upsert_product(product_payload(issuer_a, name="Servicio A", sku="A-1"))
    database.upsert_product(product_payload(issuer_b, name="Servicio B", sku="B-1"))
    app = make_app(database)

    response = app.test_client().get(f"/issuers/{issuer_a}/edit")

    assert response.status_code == 200
    assert b"Productos del emisor" in response.data
    assert b"Servicio A" in response.data
    assert b"Servicio B" not in response.data
    assert f"/products/new?issuer_id={issuer_a}".encode() in response.data
    assert f"/products/{product_a}/edit".encode() in response.data
