"""Issuer profile routes for Multiemisor billing."""

from __future__ import annotations

import base64

from flask import Blueprint, current_app, jsonify, render_template, request

from src.routes.common import api, db, flash_and_redirect, row_or_404, wants_json
from src.services.csd_parser import CSDParserError, parse_csd_certificate
from src.services.facturama_api import FacturamaAPIError

bp = Blueprint("issuers", __name__, url_prefix="/issuers")
api_bp = Blueprint("issuer_api", __name__, url_prefix="/api/issuers")

CSD_UPLOAD_MAX_FILE_BYTES = 64 * 1024


def _has_extension(filename: str, expected_extension: str) -> bool:
    return str(filename or "").strip().lower().endswith(expected_extension)


def _read_limited_upload(file_storage, max_bytes: int) -> bytes:
    content_length = getattr(file_storage, "content_length", None)
    if content_length is not None and int(content_length) > max_bytes:
        raise ValueError(f"El archivo {file_storage.filename} excede el tamano maximo permitido.")

    uploaded = file_storage.stream.read(max_bytes + 1)
    if len(uploaded) > max_bytes:
        raise ValueError(f"El archivo {file_storage.filename} excede el tamano maximo permitido.")
    return uploaded


def _extract_csd_payload_from_request():
    certificate_file = request.files.get("certificate_file")
    private_key_file = request.files.get("private_key_file")
    private_key_password = request.form.get("csd_password", "").strip()

    has_any_csd_input = bool(
        certificate_file
        or private_key_file
        or private_key_password
    )
    if not has_any_csd_input:
        return None

    if not certificate_file or not private_key_file or not private_key_password:
        raise ValueError("Debes adjuntar .cer, .key y password del CSD.")
    if not _has_extension(certificate_file.filename, ".cer"):
        raise ValueError("El certificado debe tener extension .cer.")
    if not _has_extension(private_key_file.filename, ".key"):
        raise ValueError("La llave privada debe tener extension .key.")

    certificate_bytes = _read_limited_upload(certificate_file, CSD_UPLOAD_MAX_FILE_BYTES)
    private_key_bytes = _read_limited_upload(private_key_file, CSD_UPLOAD_MAX_FILE_BYTES)
    if not certificate_bytes or not private_key_bytes:
        raise ValueError("Los archivos CSD no pueden estar vacios.")

    cert_metadata = parse_csd_certificate(certificate_bytes)
    cert_rfc = str(cert_metadata.get("rfc", "")).strip().upper()
    if not cert_rfc:
        raise ValueError("No se pudo obtener RFC del certificado .cer.")

    return {
        "cert_metadata": cert_metadata,
        "cert_rfc": cert_rfc,
        "certificate_bytes": certificate_bytes,
        "private_key_bytes": private_key_bytes,
        "private_key_password": private_key_password,
    }


def _upload_csd_and_persist_metadata(issuer_id: int, csd_payload: dict) -> tuple[str, str]:
    certificate_b64 = base64.b64encode(csd_payload["certificate_bytes"]).decode("ascii")
    private_key_b64 = base64.b64encode(csd_payload["private_key_bytes"]).decode("ascii")
    try:
        api().upload_csd(certificate_b64, private_key_b64, csd_payload["private_key_password"])
    except ValueError:
        db().save_issuer_csd_metadata(issuer_id, csd_payload["cert_metadata"])
        return ("info", "El CSD ya existia en Facturama; se actualizo metadata local.")
    except FacturamaAPIError as exc:
        raise ValueError("No se pudo subir el CSD a Facturama. Intenta nuevamente.") from exc

    db().save_issuer_csd_metadata(issuer_id, csd_payload["cert_metadata"])
    return ("success", "Sello CSD actualizado.")


@bp.get("/")
def list_issuers():
    q = (request.args.get("q") or "").strip()
    sort = (request.args.get("sort") or "name_asc").strip()
    return render_template(
        "issuers/list.html",
        issuers=db().list_issuers(q=q, sort=sort),
        q=q,
        sort=sort,
        has_clients_routes=(
            "clients.list_clients" in current_app.view_functions
            and "clients.new_client" in current_app.view_functions
        ),
        has_bulk_csd_route="issuers.bulk_csd_onboarding" in current_app.view_functions,
    )


@bp.get("/new")
def new_issuer():
    return render_template(
        "issuers/form.html",
        issuer=None,
        series_list=[],
        has_clients_routes=(
            "clients.list_clients" in current_app.view_functions
            and "clients.new_client" in current_app.view_functions
        ),
        has_bulk_csd_route="issuers.bulk_csd_onboarding" in current_app.view_functions,
    )


@bp.post("/")
def create_issuer():
    payload = request.form.to_dict()
    csd_payload = None
    try:
        csd_payload = _extract_csd_payload_from_request()
    except (ValueError, CSDParserError) as exc:
        return flash_and_redirect(f"Error de validacion fiscal: {exc}", "issuers.new_issuer", category="error")

    if csd_payload:
        payload["rfc"] = csd_payload["cert_rfc"]
        payload["legal_name"] = str(csd_payload["cert_metadata"].get("subject", "")).strip() or payload.get(
            "legal_name",
            "",
        )
    try:
        issuer_id = db().save_issuer(payload)
    except (ValueError, KeyError) as exc:
        return flash_and_redirect(f"Error de validacion fiscal: {exc}", "issuers.new_issuer", category="error")
    if csd_payload:
        try:
            _upload_csd_and_persist_metadata(issuer_id, csd_payload)
        except ValueError as exc:
            db().delete_issuer(issuer_id)
            return flash_and_redirect(str(exc), "issuers.new_issuer", category="error")
    return flash_and_redirect("Emisor guardado.", "issuers.edit_issuer", issuer_id=issuer_id)


@bp.get("/<int:issuer_id>/edit")
def edit_issuer(issuer_id: int):
    issuer = row_or_404(db().get_issuer(issuer_id), "Issuer not found")
    product_search = (request.args.get("product_search") or "").strip().lower()
    issuer_products = db().list_products(issuer_id=issuer_id)
    if product_search:
        issuer_products = [
            row
            for row in issuer_products
            if product_search in str(row["name"]).lower()
            or product_search in str(row["identification_number"]).lower()
        ]
    return render_template(
        "issuers/form.html",
        issuer=issuer,
        series_list=db().list_series(issuer_id),
        issuer_products=issuer_products,
        product_search=product_search,
        has_products_routes=(
            "products.new_product" in current_app.view_functions
            and "products.edit_product" in current_app.view_functions
        ),
        has_cfdi_routes="cfdi.list_cfdis" in current_app.view_functions,
        latest_csd=db().get_latest_issuer_csd(issuer_id),
        has_clients_routes=(
            "clients.list_clients" in current_app.view_functions
            and "clients.new_client" in current_app.view_functions
        ),
        has_bulk_csd_route="issuers.bulk_csd_onboarding" in current_app.view_functions,
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
    try:
        csd_payload = _extract_csd_payload_from_request()
    except (ValueError, CSDParserError) as exc:
        return flash_and_redirect(str(exc), "issuers.edit_issuer", category="error", issuer_id=issuer_id)
    if not csd_payload:
        return flash_and_redirect(
            "Debes adjuntar .cer, .key y password del CSD.",
            "issuers.edit_issuer",
            category="error",
            issuer_id=issuer_id,
        )

    issuer_rfc = str(issuer.get("rfc", "")).strip().upper()
    cert_rfc = str(csd_payload["cert_rfc"]).strip().upper()
    if not cert_rfc or cert_rfc != issuer_rfc:
        return flash_and_redirect(
            "RFC del certificado no coincide con el RFC del emisor.",
            "issuers.edit_issuer",
            category="error",
            issuer_id=issuer_id,
        )

    try:
        category, message = _upload_csd_and_persist_metadata(issuer_id, csd_payload)
    except ValueError as exc:
        return flash_and_redirect(str(exc), "issuers.edit_issuer", category="error", issuer_id=issuer_id)
    return flash_and_redirect(message, "issuers.edit_issuer", category=category, issuer_id=issuer_id)


@bp.get("/bulk-csd")
def bulk_csd_onboarding():
    return render_template("issuers/bulk_csd.html", row_results=None)


@bp.post("/bulk-csd")
def bulk_csd_onboarding_submit():
    row_results = []
    created_count = 0
    row_indexes: set[int] = set()
    for key in request.files.keys():
        for prefix in ("certificate_file_", "private_key_file_"):
            if key.startswith(prefix) and key.removeprefix(prefix).isdigit():
                row_indexes.add(int(key.removeprefix(prefix)))
    for key in request.form.keys():
        if key.startswith("csd_password_") and key.removeprefix("csd_password_").isdigit():
            row_indexes.add(int(key.removeprefix("csd_password_")))
    indexes = sorted(row_indexes)
    default_tax_regime = (request.form.get("default_tax_regime") or "").strip()
    default_zip_code = (request.form.get("default_zip_code") or "").strip()
    default_email = (request.form.get("default_email") or "").strip()

    for index in indexes:
        cert_file = request.files.get(f"certificate_file_{index}")
        key_file = request.files.get(f"private_key_file_{index}")
        password = (request.form.get(f"csd_password_{index}") or "").strip()
        try:
            if not cert_file or not key_file or not password:
                raise ValueError("Debes adjuntar .cer, .key y password del CSD.")
            if not _has_extension(cert_file.filename, ".cer"):
                raise ValueError("El certificado debe tener extension .cer.")
            if not _has_extension(key_file.filename, ".key"):
                raise ValueError("La llave privada debe tener extension .key.")

            cert_bytes = _read_limited_upload(cert_file, CSD_UPLOAD_MAX_FILE_BYTES)
            key_bytes = _read_limited_upload(key_file, CSD_UPLOAD_MAX_FILE_BYTES)
            if not cert_bytes or not key_bytes:
                raise ValueError("Los archivos CSD no pueden estar vacios.")

            cert_metadata = parse_csd_certificate(cert_bytes)
            cert_rfc = str(cert_metadata.get("rfc", "")).strip().upper()
            if not cert_rfc:
                raise ValueError("No se pudo obtener RFC del certificado .cer.")

            issuer_payload = {
                "legal_name": str(cert_metadata.get("subject", "")).strip(),
                "rfc": cert_rfc,
                "tax_regime": (request.form.get(f"tax_regime_{index}") or default_tax_regime),
                "zip_code": (request.form.get(f"zip_code_{index}") or default_zip_code),
                "email": (request.form.get(f"email_{index}") or default_email),
                "active": True,
            }
            issuer_id = db().save_issuer(issuer_payload)
            try:
                _upload_csd_and_persist_metadata(
                    issuer_id,
                    {
                        "cert_metadata": cert_metadata,
                        "cert_rfc": cert_rfc,
                        "certificate_bytes": cert_bytes,
                        "private_key_bytes": key_bytes,
                        "private_key_password": password,
                    },
                )
            except ValueError:
                db().delete_issuer(issuer_id)
                raise
            created_count += 1
            row_results.append({"row": index, "status": "OK", "message": cert_rfc})
        except (ValueError, KeyError, CSDParserError) as exc:
            row_results.append({"row": index, "status": "ERROR", "message": str(exc)})

    summary_message = f"Procesadas {len(indexes)} filas. Exitosas: {created_count}. Errores: {len(indexes) - created_count}."
    return render_template("issuers/bulk_csd.html", row_results=row_results, summary_message=summary_message)


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
