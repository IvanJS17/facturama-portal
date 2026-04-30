"""Tests for invoice series CRUD, folio auto-increment, and CFDI creation with series/folio."""

import threading
import time

import pytest

from src.models import PortalDatabase


# ---------------------------------------------------------------------------
# helpers (mirror the fixtures/conveniences from test_models_schema.py)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# 1. test_create_series_and_list
# ---------------------------------------------------------------------------

def test_create_series_and_list(tmp_path):
    """Create 2 series for an issuer, list them, verify fields."""
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))

    series_id_1 = database.create_series(issuer_id, "FAC", 1)
    series_id_2 = database.create_series(issuer_id, "NCR", 500)

    # Verify each series individually
    series_1 = database.get_series(series_id_1)
    assert series_1 is not None
    assert series_1["issuer_id"] == issuer_id
    assert series_1["series"] == "FAC"
    assert series_1["next_folio"] == 1
    assert series_1["active"] == 1

    series_2 = database.get_series(series_id_2)
    assert series_2 is not None
    assert series_2["issuer_id"] == issuer_id
    assert series_2["series"] == "NCR"
    assert series_2["next_folio"] == 500
    assert series_2["active"] == 1

    # List both series for this issuer
    listed = database.list_series(issuer_id)
    assert len(listed) == 2
    listed_ids = {row["id"] for row in listed}
    assert series_id_1 in listed_ids
    assert series_id_2 in listed_ids

    # Verify listed rows contain expected columns
    for row in listed:
        assert "id" in row.keys()
        assert "issuer_id" in row.keys()
        assert "series" in row.keys()
        assert "next_folio" in row.keys()
        assert "active" in row.keys()
        assert "created_at" in row.keys()
        assert "updated_at" in row.keys()


# ---------------------------------------------------------------------------
# 2. test_folio_auto_increment
# ---------------------------------------------------------------------------

def test_folio_auto_increment(tmp_path):
    """Create series starting at 100, get_next_folio 3 times, verify increment."""
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    series_id = database.create_series(issuer_id, "FAC", 100)

    # First call returns the starting folio
    folio_1 = database.get_next_folio(issuer_id, "FAC")
    assert folio_1 == 100

    folio_2 = database.get_next_folio(issuer_id, "FAC")
    assert folio_2 == 101

    folio_3 = database.get_next_folio(issuer_id, "FAC")
    assert folio_3 == 102

    # next_folio column should now be 103
    series = database.get_series(series_id)
    assert series["next_folio"] == 103


# ---------------------------------------------------------------------------
# 3. test_series_unique_per_issuer
# ---------------------------------------------------------------------------

def test_series_unique_per_issuer(tmp_path):
    """Creating the same series name for the same issuer should raise IntegrityError."""
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))

    database.create_series(issuer_id, "FAC", 1)

    # Second create with same series name should fail (UNIQUE constraint)
    with pytest.raises(Exception):
        database.create_series(issuer_id, "FAC", 50)

    # But the same series name for a different issuer should succeed
    issuer_b = database.save_issuer(issuer_payload("Issuer B", "BBB010101BBB"))
    series_id_b = database.create_series(issuer_b, "FAC", 10)
    assert series_id_b is not None
    series_b = database.get_series(series_id_b)
    assert series_b["series"] == "FAC"
    assert series_b["issuer_id"] == issuer_b


# ---------------------------------------------------------------------------
# 4. test_cfdi_creation_with_series
# ---------------------------------------------------------------------------

def test_cfdi_creation_with_series(tmp_path):
    """Save a CFDI with serie='FAC' and folio=1; verify columns are populated."""
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    client_id = database.upsert_client(client_payload(issuer_id, "Acme", "ACM010101ABC"))
    product_id = database.upsert_product(product_payload(issuer_id, "Service", "SKU-1"))

    # Create a series first
    database.create_series(issuer_id, "FAC", 1)

    cfdi_data = {
        "facturama_id": "cfdi-test-series",
        "uuid": "uuid-series-test",
        "issuer_id": issuer_id,
        "recipient_rfc": "ACM010101ABC",
        "recipient_name": "Acme",
        "total": 116,
        "serie": "FAC",
        "folio": 1,
        "items": [
            {
                "product_id": product_id,
                "description": "Test service",
                "product_code": "01010101",
                "identification_number": "SKU-1",
                "quantity": 1,
                "unit_price": 100,
                "subtotal": 100,
                "total": 116,
            }
        ],
    }

    cfdi_id = database.save_cfdi(cfdi_data)
    cfdi = database.get_cfdi(cfdi_id)

    assert cfdi is not None
    assert cfdi["serie"] == "FAC", f"Expected serie='FAC', got {cfdi['serie']!r}"
    assert cfdi["folio"] == 1, f"Expected folio=1, got {cfdi['folio']!r}"
    assert cfdi["issuer_id"] == issuer_id
    assert cfdi["client_id"] == client_id
    assert cfdi["recipient_rfc"] == "ACM010101ABC"
    assert cfdi["total"] == 116

    # Also verify that serie and folio survive a re-save (upsert via ON CONFLICT)
    cfdi_data_update = {**cfdi_data, "total": 232}
    cfdi_id_2 = database.save_cfdi(cfdi_data_update)
    assert cfdi_id_2 == cfdi_id  # same facturama_id → upsert
    cfdi_updated = database.get_cfdi(cfdi_id)
    assert cfdi_updated["total"] == 232
    assert cfdi_updated["serie"] == "FAC"
    assert cfdi_updated["folio"] == 1


# ---------------------------------------------------------------------------
# 5. test_get_next_folio_atomic
# ---------------------------------------------------------------------------

def test_get_next_folio_atomic(tmp_path):
    """Two parallel calls for same series do NOT return the same folio."""
    database = make_db(tmp_path)
    issuer_id = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    database.create_series(issuer_id, "FAC", 1)

    results_lock = threading.Lock()
    results: list[int] = []
    errors: list[Exception] = []

    def fetch_folio():
        try:
            # Each thread needs its own connection, so recreate the db wrapper
            local_db = PortalDatabase(f"sqlite:///{database.path}")
            folio = local_db.get_next_folio(issuer_id, "FAC")
            with results_lock:
                results.append(folio)
        except Exception as exc:
            with results_lock:
                errors.append(exc)

    num_threads = 10
    threads = [threading.Thread(target=fetch_folio) for _ in range(num_threads)]

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0, f"Errors during concurrent folio fetch: {errors}"
    assert len(results) == num_threads

    # All folios must be unique
    assert len(set(results)) == num_threads, (
        f"Folios were not unique across {num_threads} threads: {sorted(results)}"
    )

    # Folios should be 1..num_threads
    assert sorted(results) == list(range(1, num_threads + 1)), (
        f"Expected folios 1..{num_threads}, got {sorted(results)}"
    )

    # After all calls, next_folio should be num_threads + 1
    series = database.get_series(
        database.list_series(issuer_id)[0]["id"]
    )
    assert series["next_folio"] == num_threads + 1


# ---------------------------------------------------------------------------
# 6. test_series_list_api
# ---------------------------------------------------------------------------

def test_series_list_api(tmp_path):
    """Verify that we can list series via the database (the API layer is tested
    indirectly since there is no GET /api/issuers/<id>/series endpoint yet).

    We test:
      - Creating a series via the database (same as POST /issuers/<id>/series)
      - Listing series scoped to an issuer
      - Cross-issuer isolation
    """
    database = make_db(tmp_path)

    # Two issuers
    issuer_a = database.save_issuer(issuer_payload("Issuer A", "AAA010101AAA"))
    issuer_b = database.save_issuer(issuer_payload("Issuer B", "BBB010101BBB"))

    # Series for issuer A
    database.create_series(issuer_a, "FAC", 1)
    database.create_series(issuer_a, "NCR", 100)

    # Series for issuer B
    database.create_series(issuer_b, "FAC", 50)

    # List series for issuer A
    series_a = database.list_series(issuer_a)
    assert len(series_a) == 2
    series_a_names = {row["series"] for row in series_a}
    assert series_a_names == {"FAC", "NCR"}
    for row in series_a:
        assert row["issuer_id"] == issuer_a

    # List series for issuer B
    series_b = database.list_series(issuer_b)
    assert len(series_b) == 1
    assert series_b[0]["series"] == "FAC"
    assert series_b[0]["issuer_id"] == issuer_b
    assert series_b[0]["next_folio"] == 50

    # Verify cross-issuer isolation: series A does not appear in B's list
    series_b_ids = {row["id"] for row in series_b}
    for row in series_a:
        assert row["id"] not in series_b_ids
