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


def test_list_expiring_issuer_csds_returns_latest_active_with_days_to_expiration(tmp_path):
    database = make_db(tmp_path)
    issuer_a = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload("Issuer B", "BBB010101BBB"))
    issuer_c = database.save_issuer(issuer_payload("Issuer C", "CCC010101CCC"))

    # Old record should be ignored when a newer active record exists.
    database.save_issuer_csd_metadata(
        issuer_a,
        {
            "rfc": "AAA010101AAA",
            "serial": "OLD-A",
            "subject": "CN=Old A",
            "valid_from": "2025-01-01T00:00:00+00:00",
            "valid_to": "2026-01-10T00:00:00+00:00",
        },
    )
    database.save_issuer_csd_metadata(
        issuer_a,
        {
            "rfc": "AAA010101AAA",
            "serial": "NEW-A",
            "subject": "CN=New A",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "2026-05-20T00:00:00+00:00",
        },
    )
    database.save_issuer_csd_metadata(
        issuer_b,
        {
            "rfc": "BBB010101BBB",
            "serial": "B-EXPIRED",
            "subject": "CN=B",
            "valid_from": "2025-01-01T00:00:00+00:00",
            "valid_to": "2026-05-10T00:00:00+00:00",
        },
    )
    database.save_issuer_csd_metadata(
        issuer_c,
        {
            "rfc": "CCC010101CCC",
            "serial": "C-FAR",
            "subject": "CN=C",
            "valid_from": "2025-01-01T00:00:00+00:00",
            "valid_to": "2027-01-01T00:00:00+00:00",
        },
    )

    rows = database.list_expiring_issuer_csds(reference_date="2026-05-14", window_days=90)

    assert len(rows) == 2
    assert rows[0]["issuer_rfc"] == "BBB010101BBB"
    assert rows[0]["certificate_number"] == "B-EXPIRED"
    assert rows[0]["days_to_expiration"] == -4
    assert rows[1]["issuer_rfc"] == "AAA010101AAA"
    assert rows[1]["certificate_number"] == "NEW-A"
    assert rows[1]["days_to_expiration"] == 6


def test_list_expiring_issuer_csds_respects_window_days(tmp_path):
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    database.save_issuer_csd_metadata(
        issuer_id,
        {
            "rfc": "AAA010101AAA",
            "serial": "SERIAL-1",
            "subject": "CN=Acme",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": "2026-06-29T00:00:00+00:00",
        },
    )

    assert database.list_expiring_issuer_csds(reference_date="2026-05-14", window_days=30) == []
    rows = database.list_expiring_issuer_csds(reference_date="2026-05-14", window_days=60)
    assert len(rows) == 1
    assert rows[0]["days_to_expiration"] == 46
