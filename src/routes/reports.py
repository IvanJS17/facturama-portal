"""Report routes and API endpoints."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from flask import Blueprint, abort, jsonify, render_template, request, send_file
from weasyprint import HTML

from src.routes.common import db, row_or_404, wants_json
from src.services.reports import ReportService

bp = Blueprint("reports", __name__, url_prefix="/reports")
api_bp = Blueprint("reports_api", __name__, url_prefix="/api/reports")


def _service() -> ReportService:
    return ReportService(db())


def _required_int(name: str) -> int:
    value = request.args.get(name)
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} is required") from exc


def _collect_params(report_type: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if report_type == "monthly":
        params["year"] = _required_int("year")
        params["month"] = _required_int("month")
    elif report_type == "weekly":
        params["year"] = _required_int("year")
        params["week"] = _required_int("week")
    elif report_type == "product":
        params["product_id"] = _required_int("product_id")
        if request.args.get("start"):
            params["start"] = request.args.get("start")
        if request.args.get("end"):
            params["end"] = request.args.get("end")
    elif report_type == "client":
        params["client_id"] = _required_int("client_id")
        if request.args.get("start"):
            params["start"] = request.args.get("start")
        if request.args.get("end"):
            params["end"] = request.args.get("end")
    elif report_type == "yearly":
        params["year"] = _required_int("year")
    elif report_type == "custom":
        params["start"] = request.args.get("start")
        params["end"] = request.args.get("end")
        if not params["start"] or not params["end"]:
            raise ValueError("start and end are required")
    elif report_type == "comparative":
        params["year"] = _required_int("year")
        params["month_a"] = _required_int("month_a")
        params["month_b"] = _required_int("month_b")
    else:
        raise ValueError("Unsupported report type")
    return params


@bp.get("/")
def report_selector():
    return render_template("reports/index.html", issuers=db().list_issuers())


@api_bp.get("/data")
def report_data():
    try:
        issuer_id = _required_int("issuer_id")
        row_or_404(db().get_issuer(issuer_id), "Issuer not found")
        report_type = (request.args.get("type") or "custom").strip().lower()
        params = _collect_params(report_type)
        payload = _service().build_report(issuer_id, report_type, params)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify(payload)


@api_bp.get("/preview")
def report_preview():
    try:
        issuer_id = _required_int("issuer_id")
        row_or_404(db().get_issuer(issuer_id), "Issuer not found")
        report_type = (request.args.get("type") or "custom").strip().lower()
        params = _collect_params(report_type)
        payload = _service().build_report(issuer_id, report_type, params)
    except ValueError as exc:
        if wants_json():
            return jsonify({"error": str(exc)}), 400
        abort(400, description=str(exc))
    return render_template("reports/preview.html", report=payload)


@api_bp.get("/pdf")
def report_pdf():
    try:
        issuer_id = _required_int("issuer_id")
        row_or_404(db().get_issuer(issuer_id), "Issuer not found")
        report_type = (request.args.get("type") or "custom").strip().lower()
        params = _collect_params(report_type)
        payload = _service().build_report(issuer_id, report_type, params)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    html = render_template("reports/pdf.html", report=payload)
    pdf_bytes = HTML(string=html).write_pdf()
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"report-{issuer_id}-{report_type}.pdf",
    )
