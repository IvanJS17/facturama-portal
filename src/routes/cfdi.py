"""CFDI routes."""

from typing import Any

from flask import Blueprint, abort, jsonify, render_template, request, send_file

from src.models import to_dict
from src.routes.common import api, db, flash_and_redirect
from src.services.facturama_api import FacturamaAPIError, build_cfdi_payload

bp = Blueprint("cfdi", __name__, url_prefix="/cfdi")
api_bp = Blueprint("cfdi_api", __name__, url_prefix="/api/cfdi")


def _required_int(payload: dict[str, Any], key: str, label: str) -> int:
    raw_value = payload.get(key)
    try:
        return int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} is required") from exc


def _load_cfdi_selection(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    database = db()
    issuer_id = _required_int(payload, "issuer_id", "Issuer")
    client_id = _required_int(payload, "client_id", "Client")
    product_id = _required_int(payload, "product_id", "Product")
    series_id = _required_int(payload, "series_id", "Series")

    issuer = to_dict(database.get_issuer(issuer_id))
    if issuer is None:
        raise ValueError("Selected issuer was not found")

    client = to_dict(database.get_client_for_issuer(client_id, issuer_id))
    if client is None:
        raise ValueError("Selected client does not belong to selected issuer")

    product = to_dict(database.get_product_for_issuer(product_id, issuer_id))
    if product is None:
        raise ValueError("Selected product does not belong to selected issuer")

    series = to_dict(database.get_series(series_id))
    if series is None:
        raise ValueError("Selected series was not found")
    if int(series["issuer_id"]) != issuer_id:
        raise ValueError("Selected series does not belong to selected issuer")

    return issuer, client, product, series


def _local_cfdi_links(
    cfdi_payload: dict[str, Any],
    issuer: dict[str, Any],
    client: dict[str, Any],
    product: dict[str, Any],
) -> dict[str, Any]:
    item = cfdi_payload["Items"][0]
    return {
        "client_id": client["id"],
        "items": [
            {
                "product_id": product["id"],
                "issuer_id": issuer["id"],
                "client_id": client["id"],
                "description": item.get("Description", ""),
                "name": product.get("name", item.get("Description", "")),
                "product_code": item.get("ProductCode", ""),
                "identification_number": item.get("IdentificationNumber", ""),
                "quantity": item.get("Quantity", 0),
                "unit_price": item.get("UnitPrice", 0),
                "subtotal": item.get("Subtotal", 0),
                "total": item.get("Total", 0),
            }
        ],
    }


@bp.get("/")
def list_cfdis():
    recipient_rfc = request.args.get("recipient_rfc", "").strip()
    status = request.args.get("status", "").strip()
    return render_template(
        "cfdis/list.html",
        cfdis=db().list_cfdis(recipient_rfc=recipient_rfc, status=status),
        recipient_rfc=recipient_rfc,
        status=status,
    )


@bp.get("/new")
def new_cfdi():
    database = db()
    issuers = database.list_issuers()
    for issuer in issuers:
        if not database.list_series(int(issuer["id"])):
            database.create_series(int(issuer["id"]), "FAC", 1)

    all_series: list[Any] = []
    for issuer in issuers:
        all_series.extend(database.list_series(int(issuer["id"])))

    return render_template(
        "cfdis/new.html",
        issuers=issuers,
        clients=database.list_clients(),
        products=database.list_products(),
        series_list=all_series,
    )


@bp.post("/")
def create_cfdi():
    payload = request.form.to_dict()
    try:
        issuer, client, product, series = _load_cfdi_selection(payload)
    except ValueError as exc:
        abort(400, description=str(exc))
    folio = db().get_next_folio(int(issuer["id"]), str(series["series"]))
    payload["serie"] = str(series["series"])
    payload["folio"] = str(folio)
    cfdi_payload = build_cfdi_payload(payload, issuer, client, product)
    portal_api = api()
    result = portal_api.create_cfdi(cfdi_payload)
    portal_api.cache_cfdi_result(
        result,
        issuer["id"],
        cfdi_payload,
        local_data=_local_cfdi_links(cfdi_payload, issuer, client, product),
    )
    return flash_and_redirect("CFDI emitido.", "cfdi.list_cfdis")


@bp.get("/<int:cfdi_id>/detail")
def cfdi_detail(cfdi_id: int):
    local_record = to_dict(db().get_cfdi(cfdi_id))
    remote_record = None
    if request.args.get("refresh"):
        remote_record = api().get_cfdi(str(local_record.get("facturama_id", cfdi_id)))
    return render_template("cfdis/detail.html", cfdi=local_record, remote_record=remote_record, cfdi_id=cfdi_id)


@bp.post("/<int:cfdi_id>/cancel")
def cancel_cfdi(cfdi_id: int):
    cfdi_record = to_dict(db().get_cfdi(cfdi_id))
    response = api().cancel_cfdi(
        str(cfdi_record.get("facturama_id", cfdi_id)),
        request.form.get("motive", "02"),
        request.form.get("uuid_replacement", ""),
    )
    db().mark_cfdi_cancelled(cfdi_id, response if isinstance(response, dict) else {"response": response})
    return flash_and_redirect("CFDI cancelado.", "cfdi.cfdi_detail", cfdi_id=cfdi_id)


@bp.get("/<int:cfdi_id>/pdf")
def cfdi_pdf(cfdi_id: int):
    cfdi_record = to_dict(db().get_cfdi(cfdi_id))
    try:
        file_path = api().download_cfdi(str(cfdi_record.get("facturama_id", cfdi_id)), "pdf")
    except FileNotFoundError:
        abort(404, description="PDF file not found")
    except FacturamaAPIError as exc:
        if "404" in str(exc):
            abort(404, description="PDF file not found")
        raise
    if not file_path.is_file():
        abort(404, description="PDF file not found")
    return send_file(file_path, as_attachment=True)


@bp.get("/<int:cfdi_id>/xml")
def cfdi_xml(cfdi_id: int):
    cfdi_record = to_dict(db().get_cfdi(cfdi_id))
    try:
        file_path = api().download_cfdi(str(cfdi_record.get("facturama_id", cfdi_id)), "xml")
    except FileNotFoundError:
        abort(404, description="XML file not found")
    except FacturamaAPIError as exc:
        if "404" in str(exc):
            abort(404, description="XML file not found")
        raise
    if not file_path.is_file():
        abort(404, description="XML file not found")
    return send_file(file_path, as_attachment=True)


@bp.get("/<int:cfdi_id>/acuse/<string:file_format>")
def cfdi_acuse(cfdi_id: int, file_format: str):
    if file_format.lower() not in {"pdf", "html"}:
        abort(400, description="Invalid format. Use pdf or html.")
    cfdi_record = to_dict(db().get_cfdi(cfdi_id))
    try:
        file_path = api().download_cfdi_acuse(str(cfdi_record.get("facturama_id", cfdi_id)), file_format)
    except FileNotFoundError:
        abort(404, description="Cancellation acknowledgment file not found")
    except FacturamaAPIError as exc:
        if "404" in str(exc):
            abort(404, description="Cancellation acknowledgment file not found")
        raise
    if not file_path.is_file():
        abort(404, description="Cancellation acknowledgment file not found")
    return send_file(file_path, as_attachment=True)


@api_bp.get("/")
def api_list_cfdis():
    if request.args.get("remote"):
        filters = {"type": request.args.get("type", "issuedLite")}
        for key in (
            "status",
            "folio",
            "folioStart",
            "folioEnd",
            "dateStart",
            "dateEnd",
            "rfcIssuer",
            "rfc",
            "taxEntityName",
            "orderNumber",
            "page",
        ):
            value = request.args.get(key)
            if value not in (None, ""):
                filters[key] = value
        return jsonify(api().list_cfdis(filters))
    recipient_rfc = request.args.get("recipient_rfc", "").strip()
    status = request.args.get("status", "").strip()
    return jsonify([dict(row) for row in db().list_cfdis(recipient_rfc=recipient_rfc, status=status)])


@api_bp.post("/")
def api_create_cfdi():
    payload = request.get_json() or {}
    try:
        issuer, client, product, series = _load_cfdi_selection(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    folio = db().get_next_folio(int(issuer["id"]), str(series["series"]))
    payload["serie"] = str(series["series"])
    payload["folio"] = str(folio)
    cfdi_payload = build_cfdi_payload(payload, issuer, client, product)
    portal_api = api()
    result = portal_api.create_cfdi(cfdi_payload)
    portal_api.cache_cfdi_result(
        result,
        issuer["id"],
        cfdi_payload,
        local_data=_local_cfdi_links(cfdi_payload, issuer, client, product),
    )
    return jsonify(result), 201


@api_bp.delete("/<string:cfdi_id>")
def api_cancel_cfdi(cfdi_id: str):
    result = api().cancel_cfdi(cfdi_id, request.args.get("motive", "02"), request.args.get("uuid_replacement", ""))
    db().mark_cfdi_cancelled(cfdi_id, result if isinstance(result, dict) else {"response": result})
    return jsonify({"cancelled": True, "facturama": result})
