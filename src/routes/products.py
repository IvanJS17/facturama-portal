"""Product and service item routes."""

from flask import Blueprint, abort, jsonify, render_template, request

from src.routes.common import api, db, flash_and_redirect, row_or_404
from src.services.facturama_api import build_product_payload

bp = Blueprint("products", __name__, url_prefix="/products")
api_bp = Blueprint("products_api", __name__, url_prefix="/api/products")


def _require_existing_issuer(payload: dict) -> int:
    try:
        issuer_id = int(payload.get("issuer_id") or 0)
    except (TypeError, ValueError):
        issuer_id = 0
    if not issuer_id or db().get_issuer(issuer_id) is None:
        abort(400, "Selecciona un emisor válido para el producto")
    return issuer_id


def _form_to_local(payload: dict, facturama_response: dict | None = None) -> dict:
    facturama_response = facturama_response or {}
    issuer_id = _require_existing_issuer(payload)
    return {
        "facturama_id": str(facturama_response.get("Id") or payload.get("facturama_id", "")),
        "issuer_id": issuer_id,
        "name": payload["name"],
        "identification_number": payload.get("identification_number", ""),
        "product_code": payload.get("product_code", "01010101"),
        "unit_code": payload.get("unit_code", "E48"),
        "unit": payload.get("unit", "Servicio"),
        "price": float(payload.get("price") or 0),
        "tax_object": payload.get("tax_object", "02"),
        "raw_payload": {"request": build_product_payload(payload), "response": facturama_response},
    }


@bp.get("/")
def list_products():
    issuer_filter = request.args.get("issuer_id", type=int)
    return render_template(
        "products/list.html",
        products=db().list_products(issuer_id=issuer_filter),
        invoiced_products=db().list_invoiced_products(issuer_id=issuer_filter),
        issuers=db().list_issuers(),
        filter_issuer_id=issuer_filter,
    )


@bp.get("/new")
def new_product():
    selected_issuer_id = request.args.get("issuer_id", type=int)
    if selected_issuer_id is not None:
        row_or_404(db().get_issuer(selected_issuer_id), "Emisor no encontrado")
    return render_template(
        "products/form.html",
        product=None,
        issuers=db().list_issuers(),
        selected_issuer_id=selected_issuer_id,
    )


@bp.post("/")
def create_product():
    payload = request.form.to_dict()
    facturama_response = {}
    if request.form.get("sync_facturama"):
        facturama_response = api().create_product(build_product_payload(payload))
    product_id = db().upsert_product(_form_to_local(payload, facturama_response))
    return flash_and_redirect("Producto guardado.", "products.edit_product", product_id=product_id)


@bp.get("/<int:product_id>/edit")
def edit_product(product_id: int):
    product = row_or_404(db().get_product(product_id), "Product not found")
    return render_template(
        "products/form.html",
        product=product,
        issuers=db().list_issuers(),
        selected_issuer_id=product.get("issuer_id"),
    )


@bp.post("/<int:product_id>")
def update_product(product_id: int):
    payload = request.form.to_dict()
    existing = row_or_404(db().get_product(product_id), "Product not found")
    facturama_response = {}
    if request.form.get("sync_facturama") and existing.get("facturama_id"):
        facturama_response = api().update_product(existing["facturama_id"], build_product_payload(payload))
    db().upsert_product(_form_to_local(payload, facturama_response), product_id)
    return flash_and_redirect("Producto actualizado.", "products.list_products", issuer_id=int(payload["issuer_id"]))


@bp.post("/<int:product_id>/delete")
def delete_product(product_id: int):
    product = row_or_404(db().get_product(product_id), "Product not found")
    if request.form.get("sync_facturama") and product.get("facturama_id"):
        api().delete_product(product["facturama_id"])
    db().delete_product(product_id)
    return flash_and_redirect("Producto eliminado.", "products.list_products", issuer_id=product.get("issuer_id"))


@api_bp.get("/")
def api_list_products():
    issuer_filter = request.args.get("issuer_id", type=int)
    return jsonify([dict(row) for row in db().list_products(issuer_id=issuer_filter)])


@api_bp.post("/")
def api_create_product():
    payload = request.get_json() or {}
    facturama_response = api().create_product(build_product_payload(payload)) if payload.get("sync_facturama") else {}
    product_id = db().upsert_product(_form_to_local(payload, facturama_response))
    return jsonify({"id": product_id, "facturama": facturama_response}), 201


@api_bp.get("/facturama")
def api_facturama_products():
    return jsonify(api().list_products(search=request.args.get("search", "")))
