import pytest
from unittest.mock import patch

from src.models import PortalDatabase
from src.services.facturama_service import FacturamaService, FacturamaServiceError
from src.utils.config import Config


@pytest.fixture
def mock_config():
    return Config(
        facturama_user="testuser",
        facturama_password="testpass",
        facturama_api_url="https://apisandbox.facturama.mx/",
    )


def test_service_initializes_without_calling_api(mock_config):
    """Service should not call Facturama on init; SDK calls are lazy."""
    with patch("src.services.facturama_api.Client.list") as mock_client_list:
        FacturamaService(mock_config)
        mock_client_list.assert_not_called()


def test_api_call_wraps_unexpected_errors(mock_config):
    service = FacturamaService(mock_config)
    with patch("src.services.facturama_api.Client.create", side_effect=RuntimeError("boom")):
        with pytest.raises(FacturamaServiceError, match="Create client failed: boom"):
            service.create_client(
                {
                    "Email": "cliente@example.com",
                    "Rfc": "XAXX010101000",
                    "Name": "CLIENTE",
                    "CfdiUse": "G03",
                    "FiscalRegime": "601",
                    "TaxZipCode": "01000",
                }
            )


def test_cache_cfdi_result_persists_client_and_item_links(tmp_path, mock_config):
    database = PortalDatabase(f"sqlite:///{tmp_path / 'portal.db'}")
    database.init_schema()
    issuer_id = database.save_issuer(
        {
            "legal_name": "Issuer A",
            "rfc": "AAA010101AAA",
            "tax_regime": "601",
            "zip_code": "01000",
            "email": "",
            "active": True,
        }
    )
    client_id = database.upsert_client(
        {
            "issuer_id": issuer_id,
            "facturama_id": "",
            "legal_name": "Cliente A",
            "rfc": "CLA010101ABC",
            "email": "",
            "tax_regime": "601",
            "cfdi_use": "G03",
            "zip_code": "01000",
            "raw_payload": {},
        }
    )
    product_id = database.upsert_product(
        {
            "issuer_id": issuer_id,
            "facturama_id": "",
            "name": "Servicio A",
            "identification_number": "A-1",
            "product_code": "01010101",
            "unit_code": "E48",
            "unit": "Servicio",
            "price": 100,
            "tax_object": "02",
            "raw_payload": {},
        }
    )
    service = FacturamaService(mock_config, database)

    service.cache_cfdi_result(
        {"Id": "remote-1", "Total": 116, "Complement": {"TaxStampUuid": "uuid-1"}},
        issuer_id,
        {
            "Receiver": {"Rfc": "CLA010101ABC", "Name": "Cliente A"},
            "CfdiType": "I",
            "PaymentForm": "03",
            "PaymentMethod": "PUE",
            "Total": 116,
        },
        local_data={
            "client_id": client_id,
            "items": [
                {
                    "product_id": product_id,
                    "issuer_id": issuer_id,
                    "client_id": client_id,
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
        },
    )

    cfdis = database.list_cfdis(recipient_rfc="CLA010101ABC", status="active")
    assert len(cfdis) == 1
    assert cfdis[0]["client_id"] == client_id
    assert database.list_invoiced_products(issuer_id=issuer_id)[0]["billed_client_names"] == "Cliente A"
