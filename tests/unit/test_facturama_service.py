import pytest
from unittest.mock import patch
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
    """Service should not call Facturama on init (lazy client)."""
    with patch("src.services.facturama_service.Facturama") as mock_facturama:
        service = FacturamaService(mock_config)
        mock_facturama.assert_not_called()


def test_handle_response_raises_on_none(mock_config):
    service = FacturamaService(mock_config)
    with pytest.raises(FacturamaServiceError, match="returned None"):
        service._handle_response(None, "Test Op")
