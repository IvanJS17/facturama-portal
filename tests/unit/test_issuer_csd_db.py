from src.models import PortalDatabase


def make_db(tmp_path):
    database = PortalDatabase(f"sqlite:///{tmp_path / 'portal.db'}")
    database.init_schema()
    return database


def issuer_payload(name="Issuer A", rfc="AAA010101AAA"):
    return {
        "legal_name": name,
        "rfc": rfc,
        "tax_regime": "601",
        "zip_code": "01000",
        "email": "",
        "active": True,
    }


def test_save_and_list_latest_issuer_csd(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload())

    database.save_issuer_csd_metadata(
        issuer_id,
        {
            "rfc": "AAA010101AAA",
            "serial": "SERIAL-1",
            "subject": "CN=Acme",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "2027-01-01T00:00:00+00:00",
        },
    )
    database.save_issuer_csd_metadata(
        issuer_id,
        {
            "rfc": "AAA010101AAA",
            "serial": "SERIAL-2",
            "subject": "CN=Acme2",
            "valid_from": "2026-02-01T00:00:00+00:00",
            "valid_to": "2027-02-01T00:00:00+00:00",
        },
    )

    rows = database.list_issuer_csd_metadata(issuer_id)
    assert len(rows) == 2
    assert rows[0]["certificate_number"] == "SERIAL-2"

    latest = database.get_latest_issuer_csd(issuer_id)
    assert latest["certificate_number"] == "SERIAL-2"
    assert latest["rfc"] == "AAA010101AAA"
