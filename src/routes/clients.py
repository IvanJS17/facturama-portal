"""Client routes."""

import json

from flask import Blueprint, abort, jsonify, render_template, request

from src.routes.common import api, db, flash_and_redirect, row_or_404
from src.services.facturama_api import build_client_payload

bp = Blueprint("clients", __name__, url_prefix="/clients")
api_bp = Blueprint("clients_api", __name__, url_prefix="/api/clients")
GENERIC_RFC = "XAXX010101000"


def _require_existing_issuer(payload: dict) -> int:
    """Return a validated issuer id or abort with a client-facing 400."""
    try:
        issuer_id = int(payload.get("issuer_id") or 0)
    except (TypeError, ValueError):
        issuer_id = 0
    if not issuer_id or db().get_issuer(issuer_id) is None:
        abort(400, "Selecciona un emisor válido para el cliente")
    return issuer_id


def _issuer_zip_map() -> dict[str, str]:
    return {str(row["id"]): str(row["zip_code"]) for row in db().list_issuers()}


def _parse_product_ids(payload) -> list[int]:
    raw_ids = payload.getlist("product_ids") if hasattr(payload, "getlist") else payload.get("product_ids", [])
    if isinstance(raw_ids, str):
        raw_ids = [raw_ids]
    parsed: list[int] = []
    for raw in raw_ids or []:
        try:
            parsed.append(int(raw))
        except (TypeError, ValueError):
            continue
    return parsed


def _validate_selected_products_for_issuer(issuer_id: int, product_ids: list[int]) -> None:
    selected_ids = {int(pid) for pid in product_ids if int(pid) > 0}
    if not selected_ids:
        return
    allowed_ids = {int(row["id"]) for row in db().list_products(issuer_id=issuer_id)}
    invalid_ids = [product_id for product_id in selected_ids if product_id not in allowed_ids]
    if not invalid_ids:
        return
    first_invalid = invalid_ids[0]
    if db().get_product(first_invalid) is None:
        raise ValueError("Selected product does not exist")
    raise ValueError("Selected product does not belong to selected issuer")


def _enforce_generic_rfc_defaults(payload: dict) -> dict:
    """Apply server-side generic receptor defaults for RFC XAXX010101000."""
    issuer_id = _require_existing_issuer(payload)
    normalized_rfc = str(payload.get("rfc") or "").strip().upper()
    if normalized_rfc != GENERIC_RFC:
        return payload
    issuer = db().get_issuer(issuer_id)
    issuer_zip_code = str(issuer["zip_code"]) if issuer else ""
    payload["rfc"] = GENERIC_RFC
    payload["legal_name"] = "PÚBLICO EN GENERAL"
    payload["tax_regime"] = "616"
    payload["cfdi_use"] = "S01"
    payload["zip_code"] = issuer_zip_code
    return payload


def _form_to_local(payload: dict, facturama_response: dict | None = None) -> dict:
    facturama_response = facturama_response or {}
    issuer_id = _require_existing_issuer(payload)
    return {
        "facturama_id": str(facturama_response.get("Id") or payload.get("facturama_id", "")),
        "issuer_id": issuer_id,
        "legal_name": payload["legal_name"],
        "rfc": payload["rfc"],
        "email": payload.get("email", ""),
        "tax_regime": payload.get("tax_regime", "601"),
        "cfdi_use": payload.get("cfdi_use", "G03"),
        "zip_code": payload["zip_code"],
        "raw_payload": {"request": build_client_payload(payload), "response": facturama_response},
    }


@bp.get("/")
def list_clients():
    issuer_filter = request.args.get("issuer_id", type=int)
    return render_template(
        "clients/list.html",
        clients=db().list_clients(issuer_id=issuer_filter),
        issuers=db().list_issuers(),
        filter_issuer_id=issuer_filter,
    )


@bp.get("/new")
def new_client():
    selected_issuer_id = request.args.get("issuer_id", type=int)
    if selected_issuer_id is not None:
        row_or_404(db().get_issuer(selected_issuer_id), "Emisor no encontrado")
    return render_template(
        "clients/form.html",
        client=None,
        issuers=db().list_issuers(),
        selected_issuer_id=selected_issuer_id,
        available_products=db().list_products(issuer_id=selected_issuer_id) if selected_issuer_id else [],
        selected_product_ids=[],
        issuer_zip_codes_json=json.dumps(_issuer_zip_map(), ensure_ascii=False, separators=(",", ":")),
    )


@bp.post("/")
def create_client():
    payload = request.form.to_dict()
    payload = _enforce_generic_rfc_defaults(payload)
    product_ids = _parse_product_ids(request.form)
    try:
        _validate_selected_products_for_issuer(int(payload["issuer_id"]), product_ids)
        facturama_response = {}
        if request.form.get("sync_facturama"):
            facturama_response = api().create_client(build_client_payload(payload))
        client_id = db().upsert_client(_form_to_local(payload, facturama_response))
        db().set_client_products(client_id, product_ids)
    except ValueError as exc:
        return flash_and_redirect(
            f"Error de validacion fiscal: {exc}",
            "clients.new_client",
            category="error",
            issuer_id=payload.get("issuer_id"),
        )
    return flash_and_redirect("Cliente guardado.", "clients.edit_client", client_id=client_id)


@bp.get("/<int:client_id>/edit")
def edit_client(client_id: int):
    client = row_or_404(db().get_client(client_id), "Client not found")
    selected_products = db().list_client_products(client_id)
    return render_template(
        "clients/form.html",
        client=client,
        issuers=db().list_issuers(),
        selected_issuer_id=client.get("issuer_id"),
        available_products=db().list_products(issuer_id=client.get("issuer_id")),
        selected_product_ids=[int(row["id"]) for row in selected_products],
        issuer_zip_codes_json=json.dumps(_issuer_zip_map(), ensure_ascii=False, separators=(",", ":")),
    )


@bp.post("/<int:client_id>")
def update_client(client_id: int):
    payload = request.form.to_dict()
    payload = _enforce_generic_rfc_defaults(payload)
    product_ids = _parse_product_ids(request.form)
    existing = row_or_404(db().get_client(client_id), "Client not found")
    try:
        _validate_selected_products_for_issuer(int(payload["issuer_id"]), product_ids)
        facturama_response = {}
        if request.form.get("sync_facturama") and existing.get("facturama_id"):
            facturama_response = api().update_client(existing["facturama_id"], build_client_payload(payload))
        db().upsert_client(_form_to_local(payload, facturama_response), client_id)
        db().set_client_products(client_id, product_ids)
    except ValueError as exc:
        return flash_and_redirect(
            f"Error de validacion fiscal: {exc}",
            "clients.edit_client",
            category="error",
            client_id=client_id,
        )
    return flash_and_redirect("Cliente actualizado.", "clients.list_clients", issuer_id=int(payload["issuer_id"]))


@bp.post("/<int:client_id>/delete")
def delete_client(client_id: int):
    client = row_or_404(db().get_client(client_id), "Client not found")
    if request.form.get("sync_facturama") and client.get("facturama_id"):
        api().delete_client(client["facturama_id"])
    db().delete_client(client_id)
    return flash_and_redirect("Cliente eliminado.", "clients.list_clients", issuer_id=client.get("issuer_id"))


@api_bp.get("/")
def api_list_clients():
    issuer_filter = request.args.get("issuer_id", type=int)
    return jsonify([dict(row) for row in db().list_clients(issuer_id=issuer_filter)])


@api_bp.post("/")
def api_create_client():
    payload = request.get_json() or {}
    payload = _enforce_generic_rfc_defaults(payload)
    facturama_response = api().create_client(build_client_payload(payload)) if payload.get("sync_facturama") else {}
    try:
        client_id = db().upsert_client(_form_to_local(payload, facturama_response))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"id": client_id, "facturama": facturama_response}), 201


@api_bp.get("/facturama")
def api_facturama_clients():
    return jsonify(api().list_clients(search=request.args.get("search", "")))
