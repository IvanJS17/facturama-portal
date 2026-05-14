"""Issuer profile routes for Multiemisor billing."""

from __future__ import annotations

import base64

from flask import Blueprint, jsonify, render_template, request

from src.routes.common import api, db, flash_and_redirect, row_or_404, wants_json
from src.services.csd_parser import CSDParserError, parse_csd_certificate

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
    try:
        issuer_id = db().save_issuer(request.form.to_dict())
    except ValueError as exc:
        return flash_and_redirect(f"Error de validacion fiscal: {exc}", "issuers.new_issuer", category="error")
    return flash_and_redirect("Emisor guardado.", "issuers.edit_issuer", issuer_id=issuer_id)


@bp.get("/<int:issuer_id>/edit")
def edit_issuer(issuer_id: int):
    issuer = row_or_404(db().get_issuer(issuer_id), "Issuer not found")
    return render_template(
        "issuers/form.html",
        issuer=issuer,
        series_list=db().list_series(issuer_id),
        latest_csd=db().get_latest_issuer_csd(issuer_id),
    )


@bp.post("/<int:issuer_id>")
def update_issuer(issuer_id: int):
    payload = request.form.to_dict()
    payload["active"] = "active" in request.form
    try:
        db().save_issuer(payload, issuer_id)
    except ValueError as exc:
        return flash_and_redirect(
            f"Error de validacion fiscal: {exc}",
            "issuers.edit_issuer",
            category="error",
            issuer_id=issuer_id,
        )
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


@bp.post("/<int:issuer_id>/csd")
def upload_issuer_csd(issuer_id: int):
    issuer = row_or_404(db().get_issuer(issuer_id), "Issuer not found")
    certificate_file = request.files.get("certificate_file")
    private_key_file = request.files.get("private_key_file")
    private_key_password = request.form.get("csd_password", "").strip()

    if not certificate_file or not private_key_file or not private_key_password:
        return flash_and_redirect(
            "Debes adjuntar .cer, .key y password del CSD.",
            "issuers.edit_issuer",
            category="error",
            issuer_id=issuer_id,
        )

    certificate_bytes = certificate_file.read()
    private_key_bytes = private_key_file.read()
    if not certificate_bytes or not private_key_bytes:
        return flash_and_redirect(
            "Los archivos CSD no pueden estar vacios.",
            "issuers.edit_issuer",
            category="error",
            issuer_id=issuer_id,
        )

    try:
        cert_metadata = parse_csd_certificate(certificate_bytes)
    except CSDParserError as exc:
        return flash_and_redirect(str(exc), "issuers.edit_issuer", category="error", issuer_id=issuer_id)

    issuer_rfc = str(issuer.get("rfc", "")).strip().upper()
    cert_rfc = str(cert_metadata.get("rfc", "")).strip().upper()
    if not cert_rfc or cert_rfc != issuer_rfc:
        return flash_and_redirect(
            "RFC del certificado no coincide con el RFC del emisor.",
            "issuers.edit_issuer",
            category="error",
            issuer_id=issuer_id,
        )

    certificate_b64 = base64.b64encode(certificate_bytes).decode("ascii")
    private_key_b64 = base64.b64encode(private_key_bytes).decode("ascii")
    try:
        api().upload_csd(certificate_b64, private_key_b64, private_key_password)
    except ValueError:
        # Duplicate CSD in Facturama is a user-controlled state, not a server error.
        db().save_issuer_csd_metadata(issuer_id, cert_metadata)
        return flash_and_redirect(
            "El CSD ya existia en Facturama; se actualizo metadata local.",
            "issuers.edit_issuer",
            category="info",
            issuer_id=issuer_id,
        )

    db().save_issuer_csd_metadata(issuer_id, cert_metadata)
    return flash_and_redirect("Sello CSD actualizado.", "issuers.edit_issuer", issuer_id=issuer_id)


@api_bp.get("/")
def api_list_issuers():
    return jsonify([dict(row) for row in db().list_issuers()])


@api_bp.post("/")
def api_create_issuer():
    payload = request.get_json() if wants_json() else request.form.to_dict()
    try:
        issuer_id = db().save_issuer(payload)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"id": issuer_id}), 201
