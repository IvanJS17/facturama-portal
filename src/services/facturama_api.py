"""High-level Facturama API integration for Multiemisor workflows."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import facturama
from facturama import CfdiMultiEmisor, Client, FacturamaError, Product

from src.models import PortalDatabase
from src.utils.config import Config

logger = logging.getLogger(__name__)


class FacturamaAPIError(RuntimeError):
    """Raised when Facturama rejects or cannot complete an operation."""


def _first_value(data: dict[str, Any], *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in data and data[key] not in (None, ""):
            return data[key]
    return default


class FacturamaAPI:
    """Wrapper around the classmethod-based Facturama Python SDK."""

    def __init__(self, config: Config, database: PortalDatabase | None = None):
        self.config = config
        self.database = database

    def configure_sdk(self) -> None:
        """Configure SDK module globals before each API call."""
        facturama._credentials = (self.config.facturama_user, self.config.facturama_password)
        base_url = self.config.facturama_api_url.rstrip("/")
        facturama.url_base = base_url
        facturama.sandbox = "sandbox" in base_url
        facturama.api_lite = True

    def _call(self, operation: str, func, *args: Any, **kwargs: Any) -> Any:
        self.config.validate()
        self.configure_sdk()
        try:
            return func(*args, **kwargs)
        except FacturamaError as exc:
            logger.exception("Facturama operation failed: %s", operation)
            raise FacturamaAPIError(f"{operation} failed: {exc}") from exc
        except Exception as exc:
            logger.exception("Unexpected Facturama operation failure: %s", operation)
            raise FacturamaAPIError(f"{operation} failed: {exc}") from exc

    def list_clients(self, start: int = 0, length: int = 100, search: str = "") -> list[dict[str, Any]]:
        return self._call("List clients", Client.list, start, length, search)

    def create_client(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("Create client", Client.create, payload)

    def update_client(self, facturama_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("Update client", Client.update, payload, facturama_id)

    def delete_client(self, facturama_id: str) -> Any:
        return self._call("Delete client", Client.delete, facturama_id)

    def list_products(self, start: int = 0, length: int = 100, search: str = "") -> list[dict[str, Any]]:
        return self._call("List products", Product.list, start, length, search)

    def create_product(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("Create product", Product.create, payload)

    def update_product(self, facturama_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call("Update product", Product.update, payload, facturama_id)

    def delete_product(self, facturama_id: str) -> Any:
        return self._call("Delete product", Product.delete, facturama_id)

    def create_cfdi(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a CFDI 4.0 through API Lite Multiemisor."""
        return self._call("Create CFDI", CfdiMultiEmisor.create3, payload)

    def list_cfdis(self, filters: dict[str, Any]) -> list[dict[str, Any]]:
        return self._call("List CFDIs", CfdiMultiEmisor.list, filters)

    def get_cfdi(self, cfdi_id: str) -> dict[str, Any]:
        return self._call("Get CFDI", CfdiMultiEmisor.detail, cfdi_id)

    def cancel_cfdi(self, cfdi_id: str, motive: str = "02", uuid_replacement: str = "") -> Any:
        return self._call("Cancel CFDI", CfdiMultiEmisor.delete, cfdi_id, motive, uuid_replacement or None)

    def download_cfdi(self, cfdi_id: str, file_type: str, output_dir: str = "downloads") -> Path:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        extension = file_type.lower()
        if extension not in {"pdf", "xml", "html"}:
            raise ValueError("file_type must be pdf, xml, or html")
        file_path = output / f"{cfdi_id}.{extension}"
        method = {
            "pdf": CfdiMultiEmisor.saveAsPdf,
            "xml": CfdiMultiEmisor.saveAsXML,
            "html": CfdiMultiEmisor.saveAsHtml,
        }[extension]
        self._call(f"Download CFDI {extension.upper()}", method, cfdi_id, str(file_path))
        return file_path

    def cache_cfdi_result(
        self,
        result: dict[str, Any],
        issuer_id: int | None,
        request_payload: dict[str, Any],
        local_data: dict[str, Any] | None = None,
    ) -> None:
        """Persist a compact local record for listing and audit purposes."""
        if not self.database:
            return
        local_data = local_data or {}
        receiver = request_payload.get("Receiver", {})
        cfdi_id = str(_first_value(result, "Id", "id", "CfdiId", "cfdi_id"))
        uuid = str(_first_value(result, "Complement", "Uuid", "UUID", "FolioFiscal"))
        if isinstance(result.get("Complement"), dict):
            uuid = str(_first_value(result["Complement"], "TaxStampUuid", "Uuid", "UUID"))
        cfdi_record = {
            "facturama_id": cfdi_id,
            "uuid": uuid,
            "issuer_id": issuer_id,
            "client_id": local_data.get("client_id"),
            "recipient_rfc": receiver.get("Rfc", ""),
            "recipient_name": receiver.get("Name", ""),
            "total": _first_value(result, "Total", "total", default=request_payload.get("Total", 0)),
            "status": _first_value(result, "Status", "status", default="active"),
            "cfdi_type": request_payload.get("CfdiType", "I"),
            "payment_form": request_payload.get("PaymentForm", ""),
            "payment_method": request_payload.get("PaymentMethod", ""),
            "raw_payload": {"request": request_payload, "response": result},
        }
        if "items" in local_data:
            cfdi_record["items"] = local_data["items"]
        self.database.save_cfdi(cfdi_record)


def build_client_payload(form: dict[str, Any]) -> dict[str, Any]:
    """Map a portal client form into Facturama Client payload shape."""
    return {
        "Email": form.get("email", "").strip(),
        "Rfc": form["rfc"].strip().upper(),
        "Name": form["legal_name"].strip(),
        "CfdiUse": form.get("cfdi_use", "G03").strip(),
        "FiscalRegime": form.get("tax_regime", "601").strip(),
        "TaxZipCode": form["zip_code"].strip(),
    }


def build_product_payload(form: dict[str, Any]) -> dict[str, Any]:
    """Map a portal product form into Facturama Product payload shape."""
    price = float(form.get("price") or 0)
    return {
        "IdentificationNumber": form.get("identification_number", "").strip(),
        "Name": form["name"].strip(),
        "Description": form.get("description", form["name"]).strip(),
        "Price": price,
        "CodeProdServ": form.get("product_code", "01010101").strip(),
        "UnitCode": form.get("unit_code", "E48").strip(),
        "Unit": form.get("unit", "Servicio").strip(),
        "TaxObject": form.get("tax_object", "02").strip(),
        "Taxes": json.loads(form.get("taxes_json") or "[]"),
    }


def build_cfdi_payload(
    form: dict[str, Any],
    issuer: dict[str, Any],
    client: dict[str, Any],
    product: dict[str, Any],
) -> dict[str, Any]:
    """Build a Facturama API Lite Multiemisor CFDI 4.0 payload."""
    quantity = float(form.get("quantity") or 1)
    unit_price = float(form.get("unit_price") or product["price"])
    subtotal = round(quantity * unit_price, 2)
    iva = round(subtotal * float(form.get("iva_rate") or 0.16), 2)
    total = round(subtotal + iva, 2)
    return {
        "NameId": form.get("name_id", "1").strip(),
        "CfdiType": form.get("cfdi_type", "I").strip(),
        "ExpeditionPlace": issuer["zip_code"],
        "PaymentForm": form.get("payment_form", "03").strip(),
        "PaymentMethod": form.get("payment_method", "PUE").strip(),
        "Currency": form.get("currency", "MXN").strip(),
        "Issuer": {
            "Rfc": issuer["rfc"],
            "Name": issuer["legal_name"],
            "FiscalRegime": issuer["tax_regime"],
        },
        "Receiver": {
            "Rfc": client["rfc"],
            "Name": client["legal_name"],
            "CfdiUse": client["cfdi_use"],
            "FiscalRegime": client["tax_regime"],
            "TaxZipCode": client["zip_code"],
        },
        "Items": [
            {
                "ProductCode": product["product_code"],
                "IdentificationNumber": product["identification_number"],
                "Description": form.get("description", product["name"]).strip(),
                "Unit": product["unit"],
                "UnitCode": product["unit_code"],
                "UnitPrice": unit_price,
                "Quantity": quantity,
                "Subtotal": subtotal,
                "TaxObject": product["tax_object"],
                "Taxes": [
                    {
                        "Name": "IVA",
                        "Rate": float(form.get("iva_rate") or 0.16),
                        "Total": iva,
                        "Base": subtotal,
                        "IsRetention": False,
                    }
                ],
                "Total": total,
            }
        ],
        "Subtotal": subtotal,
        "Total": total,
    }
