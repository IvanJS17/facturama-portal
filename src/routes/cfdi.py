"""CFDI routes."""

from flask import Blueprint, jsonify, render_template, request, send_file

from src.models import to_dict
from src.routes.common import api, db, flash_and_redirect, row_or_404
from src.services.facturama_api import build_cfdi_payload

bp = Blueprint("cfdi", __name__, url_prefix="/cfdi")
api_bp = Blueprint("cfdi_api", __name__, url_prefix="/api/cfdi")


@bp.get("/")
def list_cfdis():
    return render_template("cfdis/list.html", cfdis=db().list_cfdis())


@bp.get("/new")
def new_cfdi():
    database = db()
    return render_template(
        "cfdis/new.html",
        issuers=database.list_issuers(),
        clients=database.list_clients(),
        products=database.list_products(),
    )


@bp.post("/")
def create_cfdi():
    database = db()
    payload = request.form.to_dict()
    issuer = row_or_404(database.get_issuer(int(payload["issuer_id"])), "Issuer not found")
    client = row_or_404(database.get_client(int(payload["client_id"])), "Client not found")
    product = row_or_404(database.get_product(int(payload["product_id"])), "Product not found")
    cfdi_payload = build_cfdi_payload(payload, issuer, client, product)
    result = api().create_cfdi(cfdi_payload)
    api().cache_cfdi_result(result, issuer["id"], cfdi_payload)
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
    file_path = api().download_cfdi(str(cfdi_record.get("facturama_id", cfdi_id)), "pdf")
    return send_file(file_path, as_attachment=True)


@bp.get("/<int:cfdi_id>/xml")
def cfdi_xml(cfdi_id: int):
    cfdi_record = to_dict(db().get_cfdi(cfdi_id))
    file_path = api().download_cfdi(str(cfdi_record.get("facturama_id", cfdi_id)), "xml")
    return send_file(file_path, as_attachment=True)


@api_bp.get("/")
def api_list_cfdis():
    if request.args.get("remote"):
        filters = {
            "type": request.args.get("type", "issued"),
            "keyword": request.args.get("keyword", ""),
            "status": request.args.get("status", "all"),
        }
        return jsonify(api().list_cfdis(filters))
    return jsonify([dict(row) for row in db().list_cfdis()])


@api_bp.post("/")
def api_create_cfdi():
    payload = request.get_json() or {}
    issuer = row_or_404(db().get_issuer(int(payload["issuer_id"])), "Issuer not found")
    client = row_or_404(db().get_client(int(payload["client_id"])), "Client not found")
    product = row_or_404(db().get_product(int(payload["product_id"])), "Product not found")
    cfdi_payload = build_cfdi_payload(payload, issuer, client, product)
    result = api().create_cfdi(cfdi_payload)
    api().cache_cfdi_result(result, issuer["id"], cfdi_payload)
    return jsonify(result), 201


@api_bp.delete("/<string:cfdi_id>")
def api_cancel_cfdi(cfdi_id: str):
    result = api().cancel_cfdi(cfdi_id, request.args.get("motive", "02"), request.args.get("uuid_replacement", ""))
    db().mark_cfdi_cancelled(cfdi_id, result if isinstance(result, dict) else {"response": result})
    return jsonify({"cancelled": True, "facturama": result})
