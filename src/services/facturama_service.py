"""Facturama API service wrapper."""
import logging
from typing import Any, Optional

from facturama import Facturama

from src.utils.config import Config

logger = logging.getLogger(__name__)


class FacturamaServiceError(Exception):
    """Raised when a Facturama API call fails."""
    pass


class FacturamaService:
    """Wrapper around the Facturama Python SDK."""

    def __init__(self, config: Config):
        self.config = config
        self._client: Optional[Facturama] = None

    def _get_client(self) -> Facturama:
        """Lazily initialize and return the Facturama client."""
        if self._client is None:
            self._client = Facturama(
                self.config.facturama_user,
                self.config.facturama_password,
                self.config.facturama_api_url,
            )
        return self._client

    def _handle_response(self, response: Any, operation: str) -> Any:
        """Validate and unwrap API response."""
        if response is None:
            raise FacturamaServiceError(f"{operation} returned None")
        if hasattr(response, "error"):
            raise FacturamaServiceError(f"{operation} failed: {response.error}")
        return response

    # ─── CFDI Operations ───────────────────────────────────────────

    def create_cfdi(self, payload: dict) -> dict:
        """Create a new CFDI (invoice)."""
        client = self._get_client()
        result = client.Cfdi.Post(payload)
        return self._handle_response(result, "Create CFDI")

    def list_cfdis(self, query: Optional[str] = None) -> list:
        """List issued CFDIs."""
        client = self._get_client()
        params = {"keyword": query} if query else {}
        result = client.Cfdi.Get(params=params)
        return self._handle_response(result, "List CFDIs")

    def get_cfdi(self, cfdi_id: str) -> dict:
        """Retrieve a specific CFDI by ID."""
        client = self._get_client()
        result = client.Cfdi.Get(cfdi_id)
        return self._handle_response(result, f"Get CFDI {cfdi_id}")

    def cancel_cfdi(self, cfdi_id: str, reason: str = "02") -> dict:
        """Cancel a CFDI."""
        client = self._get_client()
        result = client.Cfdi.Delete(cfdi_id, {"reason": reason})
        return self._handle_response(result, f"Cancel CFDI {cfdi_id}")

    def download_pdf(self, cfdi_id: str, output_path: str) -> str:
        """Download CFDI PDF and save to file."""
        client = self._get_client()
        client.Cfdi.Get(cfdi_id)
        pdf_bytes = client.Cfdi.GetPdf(cfdi_id)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        return output_path

    def download_xml(self, cfdi_id: str, output_path: str) -> str:
        """Download CFDI XML and save to file."""
        client = self._get_client()
        xml_bytes = client.Cfdi.GetXml(cfdi_id)
        with open(output_path, "wb") as f:
            f.write(xml_bytes)
        return output_path

    # ─── Client Operations ─────────────────────────────────────────

    def create_client(self, client_data: dict) -> dict:
        """Create a new client (recipient)."""
        client = self._get_client()
        result = client.Client.Post(client_data)
        return self._handle_response(result, "Create Client")

    def list_clients(self) -> list:
        """List all clients."""
        client = self._get_client()
        result = client.Client.Get()
        return self._handle_response(result, "List Clients")

    def get_client(self, client_id: str) -> dict:
        """Get a specific client."""
        client = self._get_client()
        result = client.Client.Get(client_id)
        return self._handle_response(result, f"Get Client {client_id}")

    # ─── Product Operations ────────────────────────────────────────

    def create_product(self, product_data: dict) -> dict:
        """Create a new product/service item."""
        client = self._get_client()
        result = client.Product.Post(product_data)
        return self._handle_response(result, "Create Product")

    def list_products(self) -> list:
        """List all products."""
        client = self._get_client()
        result = client.Product.Get()
        return self._handle_response(result, "List Products")
