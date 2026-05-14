from io import BytesIO

from flask import Flask

from src.models import PortalDatabase
from src.routes import clients as client_routes
from src.routes import dashboard as dashboard_routes
from src.routes import issuers as issuer_routes


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
    app.register_blueprint(issuer_routes.api_bp)
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


class FakeFacturamaAPI:
    def __init__(self, duplicate=False):
        self.duplicate = duplicate

    def upload_csd(self, certificate_b64, private_key_b64, private_key_password):
        if self.duplicate:
            raise ValueError("duplicate")
        return {"status": "ok"}


def test_issuer_edit_shows_csd_section_only_for_edit(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)
    client = app.test_client()

    new_response = client.get("/issuers/new")
    edit_response = client.get(f"/issuers/{issuer_id}/edit")

    assert b"Sellos CSD" not in new_response.data
    assert b"Sellos CSD" in edit_response.data


def test_upload_csd_success_persists_metadata_and_flashes_success(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    monkeypatch.setattr(
        issuer_routes,
        "parse_csd_certificate",
        lambda data: {
            "rfc": "AAA010101AAA",
            "serial": "ABC123",
            "subject": "CN=Acme",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "2027-01-01T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(issuer_routes, "api", lambda: FakeFacturamaAPI())

    response = app.test_client().post(
        f"/issuers/{issuer_id}/csd",
        data={
            "csd_password": "secret",
            "certificate_file": (BytesIO(b"fake-cer"), "cert.cer"),
            "private_key_file": (BytesIO(b"fake-key"), "key.key"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Sello CSD actualizado" in response.data
    latest = database.get_latest_issuer_csd(issuer_id)
    assert latest["certificate_number"] == "ABC123"
    assert latest["rfc"] == "AAA010101AAA"


def test_upload_csd_rejects_rfc_mismatch_with_controlled_error(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    monkeypatch.setattr(
        issuer_routes,
        "parse_csd_certificate",
        lambda data: {
            "rfc": "BBB010101BBB",
            "serial": "ABC123",
            "subject": "CN=Acme",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "2027-01-01T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(issuer_routes, "api", lambda: FakeFacturamaAPI())

    response = app.test_client().post(
        f"/issuers/{issuer_id}/csd",
        data={
            "csd_password": "secret",
            "certificate_file": (BytesIO(b"fake-cer"), "cert.cer"),
            "private_key_file": (BytesIO(b"fake-key"), "key.key"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"RFC del certificado no coincide" in response.data
    assert database.get_latest_issuer_csd(issuer_id) is None


def test_upload_csd_duplicate_in_api_is_non_fatal(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    monkeypatch.setattr(
        issuer_routes,
        "parse_csd_certificate",
        lambda data: {
            "rfc": "AAA010101AAA",
            "serial": "ABC123",
            "subject": "CN=Acme",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "2027-01-01T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(issuer_routes, "api", lambda: FakeFacturamaAPI(duplicate=True))

    response = app.test_client().post(
        f"/issuers/{issuer_id}/csd",
        data={
            "csd_password": "secret",
            "certificate_file": (BytesIO(b"fake-cer"), "cert.cer"),
            "private_key_file": (BytesIO(b"fake-key"), "key.key"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"ya existia en Facturama" in response.data
    assert database.get_latest_issuer_csd(issuer_id)["certificate_number"] == "ABC123"
