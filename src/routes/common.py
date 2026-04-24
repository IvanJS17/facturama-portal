"""Shared route helpers."""

from __future__ import annotations

from typing import Any

from flask import current_app, flash, redirect, request, url_for

from src.models import PortalDatabase, to_dict
from src.services.facturama_api import FacturamaAPI
from src.utils.config import Config


def db() -> PortalDatabase:
    return current_app.extensions["portal_db"]


def api() -> FacturamaAPI:
    return FacturamaAPI(current_app.config["PORTAL_CONFIG"], db())


def wants_json() -> bool:
    return request.path.startswith("/api/") or request.accept_mimetypes.best == "application/json"


def config_status() -> dict[str, Any]:
    config: Config = current_app.config["PORTAL_CONFIG"]
    return {
        "api_url": config.facturama_api_url,
        "has_credentials": bool(config.facturama_user and config.facturama_password),
    }


def row_or_404(row, message: str):
    if row is None:
        from flask import abort

        abort(404, message)
    return to_dict(row)


def flash_and_redirect(message: str, endpoint: str, category: str = "success", **values: Any):
    flash(message, category)
    return redirect(url_for(endpoint, **values))
