"""Issuer profile routes for Multiemisor billing."""

from flask import Blueprint, jsonify, render_template, request

from src.routes.common import db, flash_and_redirect, row_or_404, wants_json

bp = Blueprint("issuers", __name__, url_prefix="/issuers")
api_bp = Blueprint("issuer_api", __name__, url_prefix="/api/issuers")


@bp.get("/")
def list_issuers():
    return render_template("issuers/list.html", issuers=db().list_issuers())


@bp.get("/new")
def new_issuer():
    return render_template("issuers/form.html", issuer=None, series_list=[])


@bp.post("/")
def create_issuer():
    issuer_id = db().save_issuer(request.form.to_dict())
    return flash_and_redirect("Emisor guardado.", "issuers.edit_issuer", issuer_id=issuer_id)


@bp.get("/<int:issuer_id>/edit")
def edit_issuer(issuer_id: int):
    issuer = row_or_404(db().get_issuer(issuer_id), "Issuer not found")
    return render_template("issuers/form.html", issuer=issuer, series_list=db().list_series(issuer_id))


@bp.post("/<int:issuer_id>")
def update_issuer(issuer_id: int):
    payload = request.form.to_dict()
    payload["active"] = "active" in request.form
    db().save_issuer(payload, issuer_id)
    return flash_and_redirect("Emisor actualizado.", "issuers.list_issuers")


@bp.post("/<int:issuer_id>/delete")
def delete_issuer(issuer_id: int):
    db().delete_issuer(issuer_id)
    return flash_and_redirect("Emisor eliminado.", "issuers.list_issuers")


@bp.post("/<int:issuer_id>/series")
def create_series(issuer_id: int):
    row_or_404(db().get_issuer(issuer_id), "Issuer not found")
    series = request.form.get("series", "FAC")
    start_folio_raw = request.form.get("start_folio", "1")
    try:
        start_folio = max(int(start_folio_raw), 1)
    except ValueError:
        start_folio = 1
    db().create_series(issuer_id, series, start_folio=start_folio)
    return flash_and_redirect("Serie creada.", "issuers.edit_issuer", issuer_id=issuer_id)


@api_bp.get("/")
def api_list_issuers():
    return jsonify([dict(row) for row in db().list_issuers()])


@api_bp.post("/")
def api_create_issuer():
    payload = request.get_json() if wants_json() else request.form.to_dict()
    issuer_id = db().save_issuer(payload)
    return jsonify({"id": issuer_id}), 201
