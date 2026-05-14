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
    assert b'<form method="post" action="/issuers/">' in new_response.data

    edit_response = app.test_client().get(f"/issuers/{issuer_id}/edit")

    assert edit_response.status_code == 200
    assert f'<form method="post" action="/issuers/{issuer_id}">'.encode() in edit_response.data


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
