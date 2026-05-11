"""Report routes and API endpoints."""

from __future__ import annotations

from io import BytesIO
import datetime

from flask import Blueprint, abort, jsonify, render_template, request, send_file
from weasyprint import HTML

from src.routes.common import db, row_or_404, wants_json
from src.services.reports import ReportService, _month_name_es

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
    elif report_type == "emisor":
        params["year"] = _required_int("year")
        period_type = request.args.get("period_type", "monthly")
        params["period_type"] = period_type
        if period_type == "monthly":
            params["month"] = _required_int("month")
        elif period_type == "quarterly":
            if request.args.get("quarter"):
                params["quarter"] = request.args.get("quarter")
            else:
                params["month"] = _required_int("month")
        if request.args.get("quarter"):
            params["quarter"] = request.args.get("quarter")
    else:
        raise ValueError("Unsupported report type")
    return params


@bp.get("/")
def report_selector():
    current_year = datetime.datetime.utcnow().year
    year_options = list(range(current_year - 2, current_year + 1))
    return render_template(
        "reports/index.html",
        issuers=db().list_issuers(),
        products=db().list_products(),
        clients=db().list_clients(),
        year_options=year_options,
    )


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


@bp.get("/preview")
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

    # Build period label
    period_label = ""
    if report_type == "monthly":
        period_label = f"{_month_name_es(int(params['month']))} {params['year']}"
    elif report_type == "yearly":
        period_label = str(params["year"])
    elif report_type == "weekly":
        period_label = f"Semana {params['week']}, {params['year']}"
    elif report_type in ("custom", "product", "client"):
        period_label = f"{params.get('start', '...')} – {params.get('end', '...')}"
    elif report_type == "emisor":
        period_label = payload.get("period_label", "")

    report_title = f"Reporte {report_type.capitalize()}"
    type_names = {
        "monthly": "Mensual", "weekly": "Semanal", "yearly": "Anual",
        "custom": "Personalizado", "product": "por Producto", "client": "por Cliente",
        "comparative": "Comparativo", "emisor": "Consolidado por Emisor",
    }
    if report_type in type_names:
        report_title = f"Reporte {type_names[report_type]}"

    # Chart data
    product_labels = [row["product_name"] for row in payload.get("by_product", [])]
    product_values = [float(row.get("total", 0)) for row in payload.get("by_product", [])]
    trend_labels = [row["month"] for row in payload.get("monthly_trend", [])]
    trend_values = [float(row.get("total", 0)) for row in payload.get("monthly_trend", [])]

    query_params = dict(request.args)

    if report_type == "emisor":
        return render_template(
            "reports/emisor_preview.html",
            report_title=report_title,
            period_label=period_label,
            issuer=payload["issuer"],
            summary=payload["summary"],
            cfdis=payload["cfdis"],
            by_product=payload.get("by_product", []),
            by_client=payload.get("by_client", []),
            monthly_trend=payload.get("monthly_trend", []),
            top_products=payload.get("top_products", []),
            top_clients=payload.get("top_clients", []),
            previous_summary=payload.get("previous_summary", {}),
            product_labels=product_labels,
            product_values=product_values,
            trend_labels=trend_labels,
            trend_values=trend_values,
            query_params=query_params,
        )

    return render_template(
        "reports/preview.html",
        report_title=report_title,
        period_label=period_label,
        issuer=payload["issuer"],
        summary=payload["summary"],
        cfdis=payload["cfdis"],
        by_product=payload.get("by_product", []),
        by_client=payload.get("by_client", []),
        product_labels=product_labels,
        product_values=product_values,
        trend_labels=trend_labels,
        trend_values=trend_values,
        query_params=query_params,
    )


@bp.get("/pdf")
def report_pdf():
    try:
        issuer_id = _required_int("issuer_id")
        row_or_404(db().get_issuer(issuer_id), "Issuer not found")
        report_type = (request.args.get("type") or "custom").strip().lower()
        params = _collect_params(report_type)
        payload = _service().build_report(issuer_id, report_type, params)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    # Build period label and title (same logic as preview)
    from datetime import datetime as dt

    period_label = ""
    if report_type == "monthly":
        period_label = f"{_month_name_es(int(params['month']))} {params['year']}"
    elif report_type == "yearly":
        period_label = str(params["year"])
    elif report_type == "weekly":
        period_label = f"Semana {params['week']}, {params['year']}"
    elif report_type in ("custom", "product", "client"):
        period_label = f"{params.get('start', '...')} – {params.get('end', '...')}"
    elif report_type == "emisor":
        period_label = payload.get("period_label", "")

    type_names = {
        "monthly": "Mensual", "weekly": "Semanal", "yearly": "Anual",
        "custom": "Personalizado", "product": "por Producto", "client": "por Cliente",
        "comparative": "Comparativo", "emisor": "Consolidado por Emisor",
    }
    report_title = f"Reporte {type_names.get(report_type, report_type.capitalize())}"

    # Generate chart images
    chart_product = None
    chart_trend = None
    try:
        from src.utils.report_graphs import generate_product_pie, generate_trend_bar
        prod_labels = [row["product_name"] for row in payload.get("by_product", [])]
        prod_values = [float(row.get("total", 0)) for row in payload.get("by_product", [])]
        if prod_labels:
            chart_product = generate_product_pie(prod_labels, prod_values)
        trend_labels = [row["month"] for row in payload.get("monthly_trend", [])]
        trend_values = [float(row.get("total", 0)) for row in payload.get("monthly_trend", [])]
        if trend_labels:
            chart_trend = generate_trend_bar(trend_labels, trend_values)
    except Exception:
        pass  # Charts are optional

    generation_date = dt.utcnow().strftime("%d/%m/%Y %H:%M")

    if report_type == "emisor":
        html = render_template(
            "reports/emisor_pdf_template.html",
            report_title=report_title,
            period_label=period_label,
            issuer=payload["issuer"],
            summary=payload["summary"],
            cfdis=payload["cfdis"],
            by_product=payload.get("by_product", []),
            by_client=payload.get("by_client", []),
            monthly_trend=payload.get("monthly_trend", []),
            top_products=payload.get("top_products", []),
            top_clients=payload.get("top_clients", []),
            previous_summary=payload.get("previous_summary", {}),
            chart_product=chart_product,
            chart_trend=chart_trend,
            generation_date=generation_date,
        )
    else:
        html = render_template(
            "reports/pdf_template.html",
            report_title=report_title,
            period_label=period_label,
            issuer=payload["issuer"],
            summary=payload["summary"],
            cfdis=payload["cfdis"],
            by_product=payload.get("by_product", []),
            by_client=payload.get("by_client", []),
            chart_product=chart_product,
            chart_trend=chart_trend,
            generation_date=generation_date,
        )
    pdf_bytes = HTML(string=html).write_pdf()
    return send_file(
        BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"reporte-{issuer_id}-{report_type}.pdf",
    )
