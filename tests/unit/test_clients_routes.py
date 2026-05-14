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
    app.register_blueprint(client_routes.api_bp)
    app.register_blueprint(issuer_routes.bp)
    app.register_blueprint(cfdi_routes.bp)
    app.register_blueprint(product_routes.bp)
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


def client_payload(issuer_id=None):
    data = {
        "legal_name": "Cliente Emisor A",
        "rfc": "CEA010101ABC",
        "email": "cliente@example.com",
        "tax_regime": "601",
        "cfdi_use": "G03",
        "zip_code": "01000",
    }
    if issuer_id is not None:
        data["issuer_id"] = str(issuer_id)
    return data


def test_new_client_preselects_issuer_from_query_string(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    response = app.test_client().get(f"/clients/new?issuer_id={issuer_id}")

    assert response.status_code == 200
    assert f'value="{issuer_id}" selected'.encode() in response.data
    assert f"/clients/?issuer_id={issuer_id}".encode() in response.data


def test_issuer_list_links_to_scoped_clients_and_new_client(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    response = app.test_client().get("/issuers/")

    assert response.status_code == 200
    assert f"/clients/?issuer_id={issuer_id}".encode() in response.data
    assert f"/clients/new?issuer_id={issuer_id}".encode() in response.data
    assert b"Ver clientes" in response.data
    assert b"Agregar cliente" in response.data


def test_create_client_requires_valid_issuer(tmp_path):
    database = make_db(tmp_path)
    app = make_app(database)

    response = app.test_client().post("/clients/", data=client_payload())

    assert response.status_code == 400
    assert b"Selecciona un emisor" in response.data
    assert database.list_clients() == []


def test_create_client_saves_under_selected_issuer_and_redirects_to_edit(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    response = app.test_client().post("/clients/", data=client_payload(issuer_id))

    assert response.status_code == 302
    clients = database.list_clients(issuer_id=issuer_id)
    assert len(clients) == 1
    assert clients[0]["issuer_id"] == issuer_id
    assert clients[0]["issuer_name"] == "ISSUER A"


def test_client_form_actions_point_to_create_and_update_routes(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    new_response = app.test_client().get("/clients/new")

    assert new_response.status_code == 200
    assert b'<form method="post" class="client-fiscal-form" action="/clients/">' in new_response.data

    client_id = database.upsert_client(client_payload(issuer_id))
    edit_response = app.test_client().get(f"/clients/{client_id}/edit")

    assert edit_response.status_code == 200
    assert f'<form method="post" class="client-fiscal-form" action="/clients/{client_id}">'.encode() in edit_response.data


def test_client_form_includes_fiscal_normalization_js_and_issuer_zip_data(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload(name="Issuer Zip", rfc="IZP010101AAA"))
    app = make_app(database)

    response = app.test_client().get(f"/clients/new?issuer_id={issuer_id}")

    assert response.status_code == 200
    assert b'id="issuer-zip-codes"' in response.data
    assert b'"%d":"01000"' % issuer_id in response.data
    assert b"client-fiscal-form" in response.data


def test_create_client_invalid_fiscal_fields_shows_validation_error_without_500(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    response = app.test_client().post(
        "/clients/",
        data={
            "issuer_id": str(issuer_id),
            "legal_name": "",
            "rfc": "BADRFC",
            "email": "cliente@example.com",
            "tax_regime": "601",
            "cfdi_use": "G03",
            "zip_code": "12",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Error de validaci" in response.data
    assert database.list_clients(issuer_id=issuer_id) == []


def test_update_client_invalid_fiscal_fields_shows_validation_error_without_500(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    client_id = database.upsert_client(client_payload(issuer_id))
    app = make_app(database)

    response = app.test_client().post(
        f"/clients/{client_id}",
        data={
            "issuer_id": str(issuer_id),
            "legal_name": "",
            "rfc": "BADRFC",
            "email": "cliente@example.com",
            "tax_regime": "601",
            "cfdi_use": "G03",
            "zip_code": "12",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Error de validaci" in response.data
    client = database.get_client(client_id)
    assert client["legal_name"] == "CLIENTE EMISOR A"


def test_api_create_client_invalid_fiscal_fields_returns_400_json(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    response = app.test_client().post(
        "/api/clients/",
        json={
            "issuer_id": issuer_id,
            "legal_name": "",
            "rfc": "BADRFC",
            "email": "cliente@example.com",
            "tax_regime": "601",
            "cfdi_use": "G03",
            "zip_code": "12",
        },
    )

    assert response.status_code == 400
    body = response.get_json()
    assert "error" in body
    assert database.list_clients(issuer_id=issuer_id) == []


def test_create_client_enforces_generic_rfc_defaults_server_side(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload(name="Issuer Generic", rfc="IGE010101AAA"))
    app = make_app(database)

    response = app.test_client().post(
        "/clients/",
        data={
            "issuer_id": str(issuer_id),
            "legal_name": "otro nombre",
            "rfc": "xaxx010101000",
            "email": "cliente@example.com",
            "tax_regime": "601",
            "cfdi_use": "G03",
            "zip_code": "99999",
        },
    )

    assert response.status_code == 302
    saved = database.list_clients(issuer_id=issuer_id)[0]
    assert saved["rfc"] == "XAXX010101000"
    assert saved["legal_name"] == "PÚBLICO EN GENERAL"
    assert saved["tax_regime"] == "616"
    assert saved["cfdi_use"] == "S01"
    assert saved["zip_code"] == "01000"


def test_update_client_enforces_generic_rfc_defaults_server_side(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload(name="Issuer Generic", rfc="IGE010101AAA"))
    client_id = database.upsert_client(client_payload(issuer_id))
    app = make_app(database)

    response = app.test_client().post(
        f"/clients/{client_id}",
        data={
            "issuer_id": str(issuer_id),
            "legal_name": "nombre libre",
            "rfc": "XAXX010101000",
            "email": "cliente@example.com",
            "tax_regime": "601",
            "cfdi_use": "G03",
            "zip_code": "88888",
        },
    )

    assert response.status_code == 302
    saved = database.get_client(client_id)
    assert saved["legal_name"] == "PÚBLICO EN GENERAL"
    assert saved["tax_regime"] == "616"
    assert saved["cfdi_use"] == "S01"
    assert saved["zip_code"] == "01000"


def test_api_create_client_enforces_generic_rfc_defaults_server_side(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload(name="Issuer Generic", rfc="IGE010101AAA"))
    app = make_app(database)

    response = app.test_client().post(
        "/api/clients/",
        json={
            "issuer_id": issuer_id,
            "legal_name": "cliente libre",
            "rfc": "xaxx010101000",
            "email": "cliente@example.com",
            "tax_regime": "601",
            "cfdi_use": "G03",
            "zip_code": "77777",
        },
    )

    assert response.status_code == 201
    client_id = response.get_json()["id"]
    saved = database.get_client(client_id)
    assert saved["legal_name"] == "PÚBLICO EN GENERAL"
    assert saved["tax_regime"] == "616"
    assert saved["cfdi_use"] == "S01"
    assert saved["zip_code"] == "01000"


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


def test_new_client_form_shows_products_for_preselected_issuer(tmp_path):
    database = make_db(tmp_path)
    issuer_a = database.save_issuer(issuer_payload(name="Issuer A", rfc="AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload(name="Issuer B", rfc="BBB010101BBB"))
    product_a = database.upsert_product(product_payload(issuer_a, name="Servicio A", sku="A-1"))
    database.upsert_product(product_payload(issuer_b, name="Servicio B", sku="B-1"))
    app = make_app(database)

    response = app.test_client().get(f"/clients/new?issuer_id={issuer_a}")

    assert response.status_code == 200
    assert f'value="{product_a}"'.encode() in response.data
    assert b"Servicio A" in response.data
    assert b"Servicio B" not in response.data


def test_create_client_persists_selected_product_associations(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    product_1 = database.upsert_product(product_payload(issuer_id, name="Servicio 1", sku="S-1"))
    product_2 = database.upsert_product(product_payload(issuer_id, name="Servicio 2", sku="S-2"))
    app = make_app(database)

    response = app.test_client().post(
        "/clients/",
        data={**client_payload(issuer_id), "product_ids": [str(product_1), str(product_2)]},
    )

    assert response.status_code == 302
    client_id = database.list_clients(issuer_id=issuer_id)[0]["id"]
    linked = database.list_client_products(client_id)
    assert [row["id"] for row in linked] == [product_1, product_2]


def test_edit_client_form_shows_current_issuer_products_and_selected_associations(tmp_path):
    database = make_db(tmp_path)
    issuer_a = database.save_issuer(issuer_payload(name="Issuer A", rfc="AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload(name="Issuer B", rfc="BBB010101BBB"))
    client_id = database.upsert_client(client_payload(issuer_a))
    product_a = database.upsert_product(product_payload(issuer_a, name="Servicio A", sku="A-1"))
    database.upsert_product(product_payload(issuer_b, name="Servicio B", sku="B-1"))
    database.set_client_products(client_id, [product_a])
    app = make_app(database)

    response = app.test_client().get(f"/clients/{client_id}/edit")

    assert response.status_code == 200
    assert b"Servicio A" in response.data
    assert b"Servicio B" not in response.data
    assert f'value="{product_a}" checked'.encode() in response.data


def test_update_client_rejects_cross_issuer_product_association(tmp_path):
    database = make_db(tmp_path)
    issuer_a = database.save_issuer(issuer_payload(name="Issuer A", rfc="AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload(name="Issuer B", rfc="BBB010101BBB"))
    client_id = database.upsert_client(client_payload(issuer_a))
    product_a = database.upsert_product(product_payload(issuer_a, name="Servicio A", sku="A-1"))
    product_b = database.upsert_product(product_payload(issuer_b, name="Servicio B", sku="B-1"))
    database.set_client_products(client_id, [product_a])
    app = make_app(database)

    response = app.test_client().post(
        f"/clients/{client_id}",
        data={**client_payload(issuer_a), "product_ids": [str(product_b)]},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"selected issuer" in response.data
    linked = database.list_client_products(client_id)
    assert [row["id"] for row in linked] == [product_a]
