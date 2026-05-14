from io import BytesIO

from flask import Flask

from src.models import PortalDatabase
from src.routes import clients as client_routes
from src.routes import dashboard as dashboard_routes
from src.routes import issuers as issuer_routes
from src.services.csd_parser import CSDParserError
from src.services.facturama_api import FacturamaAPIError


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
    def __init__(self, duplicate=False, fail=False):
        self.duplicate = duplicate
        self.fail = fail

    def upload_csd(self, certificate_b64, private_key_b64, private_key_password):
        if self.duplicate:
            raise ValueError("duplicate")
        if self.fail:
            raise FacturamaAPIError("Upload CSD failed: boom")
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


def test_issuer_new_renders_csd_first_section_and_bulk_link(tmp_path):
    database = make_db(tmp_path)
    app = make_app(database)

    response = app.test_client().get("/issuers/new")

    assert response.status_code == 200
    assert b"CSD del emisor" in response.data
    assert b'name="certificate_file"' in response.data
    assert b'name="private_key_file"' in response.data
    assert b'name="csd_password"' in response.data
    assert b"/issuers/bulk-csd" in response.data


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


def test_upload_csd_handles_non_duplicate_facturama_error_with_controlled_flash(tmp_path, monkeypatch):
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
    monkeypatch.setattr(issuer_routes, "api", lambda: FakeFacturamaAPI(fail=True))

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
    assert b"No se pudo subir el CSD a Facturama" in response.data
    assert database.get_latest_issuer_csd(issuer_id) is None


def test_upload_csd_rejects_missing_password_or_files(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    response = app.test_client().post(
        f"/issuers/{issuer_id}/csd",
        data={
            "csd_password": "",
            "certificate_file": (BytesIO(b"fake-cer"), "cert.cer"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Debes adjuntar .cer, .key y password del CSD" in response.data


def test_upload_csd_rejects_empty_files(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    response = app.test_client().post(
        f"/issuers/{issuer_id}/csd",
        data={
            "csd_password": "secret",
            "certificate_file": (BytesIO(b""), "cert.cer"),
            "private_key_file": (BytesIO(b"fake-key"), "key.key"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Los archivos CSD no pueden estar vacios" in response.data


def test_upload_csd_rejects_wrong_extensions(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    response = app.test_client().post(
        f"/issuers/{issuer_id}/csd",
        data={
            "csd_password": "secret",
            "certificate_file": (BytesIO(b"fake-cer"), "cert.txt"),
            "private_key_file": (BytesIO(b"fake-key"), "key.pem"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"El certificado debe tener extension .cer" in response.data


def test_upload_csd_rejects_oversized_files(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    large_blob = b"x" * 70000
    response = app.test_client().post(
        f"/issuers/{issuer_id}/csd",
        data={
            "csd_password": "secret",
            "certificate_file": (BytesIO(large_blob), "cert.cer"),
            "private_key_file": (BytesIO(b"fake-key"), "key.key"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"El archivo cert.cer excede el tamano maximo permitido" in response.data


def test_upload_csd_handles_parser_error_with_controlled_flash(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())
    app = make_app(database)

    def _raise_parser_error(_data):
        raise CSDParserError("No se pudo leer el certificado .cer")

    monkeypatch.setattr(issuer_routes, "parse_csd_certificate", _raise_parser_error)

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
    assert b"No se pudo leer el certificado .cer" in response.data


def test_create_issuer_with_csd_files_prefills_from_certificate_and_persists_csd(tmp_path, monkeypatch):
    database = make_db(tmp_path)
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
        "/issuers/",
        data={
            "legal_name": " nombre sera sobrescrito ",
            "rfc": "bbb010101bbb",
            "tax_regime": "601",
            "zip_code": "01000",
            "email": "conta@example.com",
            "csd_password": "secret",
            "certificate_file": (BytesIO(b"fake-cer"), "cert.cer"),
            "private_key_file": (BytesIO(b"fake-key"), "key.key"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Emisor guardado." in response.data
    issuer = database.list_issuers()[0]
    assert issuer["rfc"] == "AAA010101AAA"
    assert issuer["legal_name"] == "CN=ACME"
    latest = database.get_latest_issuer_csd(issuer["id"])
    assert latest["certificate_number"] == "ABC123"


def test_create_issuer_with_csd_missing_required_non_csd_fields_fails_without_persisting(tmp_path, monkeypatch):
    database = make_db(tmp_path)
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
        "/issuers/",
        data={
            "tax_regime": "601",
            "zip_code": "",
            "email": "conta@example.com",
            "csd_password": "secret",
            "certificate_file": (BytesIO(b"fake-cer"), "cert.cer"),
            "private_key_file": (BytesIO(b"fake-key"), "key.key"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Error de validaci" in response.data
    assert database.list_issuers() == []


def test_create_issuer_with_csd_upload_failure_rolls_back_insert(tmp_path, monkeypatch):
    database = make_db(tmp_path)
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
    monkeypatch.setattr(issuer_routes, "api", lambda: FakeFacturamaAPI(fail=True))

    response = app.test_client().post(
        "/issuers/",
        data={
            "legal_name": "Acme",
            "rfc": "AAA010101AAA",
            "tax_regime": "601",
            "zip_code": "01000",
            "email": "conta@example.com",
            "csd_password": "secret",
            "certificate_file": (BytesIO(b"fake-cer"), "cert.cer"),
            "private_key_file": (BytesIO(b"fake-key"), "key.key"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"No se pudo subir el CSD a Facturama" in response.data
    assert database.list_issuers() == []


def test_bulk_csd_onboarding_reports_incomplete_rows_not_silently_skipped(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    app = make_app(database)

    monkeypatch.setattr(
        issuer_routes,
        "parse_csd_certificate",
        lambda data: {
            "rfc": "AAA010101AAA",
            "serial": "SER-1",
            "subject": "CN=Uno",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "2027-01-01T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(issuer_routes, "api", lambda: FakeFacturamaAPI())

    response = app.test_client().post(
        "/issuers/bulk-csd",
        data={
            "default_tax_regime": "601",
            "default_zip_code": "01000",
            "default_email": "conta@example.com",
            "certificate_file_1": (BytesIO(b"cer-1"), "a.cer"),
            "private_key_file_1": (BytesIO(b"key-1"), "a.key"),
            "csd_password_1": "s1",
            "private_key_file_2": (BytesIO(b"key-2"), "b.key"),
            "csd_password_2": "s2",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Fila 1: OK" in response.data
    assert b"Fila 2: ERROR" in response.data
    assert b"Procesadas 2 filas" in response.data
    issuers = database.list_issuers()
    assert len(issuers) == 1


def test_bulk_csd_onboarding_creates_multiple_issuers_and_reports_per_row_success(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    app = make_app(database)

    monkeypatch.setattr(
        issuer_routes,
        "parse_csd_certificate",
        lambda data: {
            "rfc": "AAA010101AAA" if data == b"cer-1" else "BBB010101BBB",
            "serial": "SER-1" if data == b"cer-1" else "SER-2",
            "subject": "CN=Uno" if data == b"cer-1" else "CN=Dos",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "2027-01-01T00:00:00+00:00",
        },
    )
    monkeypatch.setattr(issuer_routes, "api", lambda: FakeFacturamaAPI())

    response = app.test_client().post(
        "/issuers/bulk-csd",
        data={
            "default_tax_regime": "601",
            "default_zip_code": "01000",
            "default_email": "conta@example.com",
            "certificate_file_1": (BytesIO(b"cer-1"), "a.cer"),
            "private_key_file_1": (BytesIO(b"key-1"), "a.key"),
            "csd_password_1": "s1",
            "certificate_file_2": (BytesIO(b"cer-2"), "b.cer"),
            "private_key_file_2": (BytesIO(b"key-2"), "b.key"),
            "csd_password_2": "s2",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Fila 1: OK" in response.data
    assert b"Fila 2: OK" in response.data
    issuers = database.list_issuers()
    assert len(issuers) == 2


def test_bulk_csd_onboarding_continues_when_one_row_fails(tmp_path, monkeypatch):
    database = make_db(tmp_path)
    app = make_app(database)

    def _parse(data):
        if data == b"bad":
            raise CSDParserError("No se pudo leer el certificado .cer")
        return {
            "rfc": "AAA010101AAA",
            "serial": "SER-1",
            "subject": "CN=Uno",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "2027-01-01T00:00:00+00:00",
        }

    monkeypatch.setattr(issuer_routes, "parse_csd_certificate", _parse)
    monkeypatch.setattr(issuer_routes, "api", lambda: FakeFacturamaAPI())

    response = app.test_client().post(
        "/issuers/bulk-csd",
        data={
            "default_tax_regime": "601",
            "default_zip_code": "01000",
            "default_email": "conta@example.com",
            "certificate_file_1": (BytesIO(b"good"), "a.cer"),
            "private_key_file_1": (BytesIO(b"key-1"), "a.key"),
            "csd_password_1": "s1",
            "certificate_file_2": (BytesIO(b"bad"), "b.cer"),
            "private_key_file_2": (BytesIO(b"key-2"), "b.key"),
            "csd_password_2": "s2",
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Fila 1: OK" in response.data
    assert b"Fila 2: ERROR" in response.data
    issuers = database.list_issuers()
    assert len(issuers) == 1
