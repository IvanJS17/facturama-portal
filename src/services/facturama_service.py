"""Backward-compatible service alias."""

from src.services.facturama_api import FacturamaAPI, FacturamaAPIError


FacturamaService = FacturamaAPI
FacturamaServiceError = FacturamaAPIError

__all__ = ["FacturamaAPI", "FacturamaAPIError", "FacturamaService", "FacturamaServiceError"]
