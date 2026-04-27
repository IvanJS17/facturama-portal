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
    assert clients[0]["issuer_name"] == "Issuer A"
