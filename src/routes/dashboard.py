"""Dashboard routes."""

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, current_app, render_template

from src.routes.common import config_status, db

bp = Blueprint("dashboard", __name__)


def _csd_severity(days_to_expiration: int) -> str:
    if days_to_expiration < 0:
        return "expired"
    if days_to_expiration <= 30:
        return "0-30"
    if days_to_expiration <= 60:
        return "31-60"
    return "61-90"


@bp.get("/")
def index():
    database = db()
    now_mx = datetime.now(ZoneInfo("America/Mexico_City"))
    reference_date = current_app.config.get("CSD_ALERT_REFERENCE_DATE", now_mx.date().isoformat())
    alert_days = int(current_app.config.get("CSD_EXPIRATION_ALERT_DAYS", 90) or 90)
    expiring_csds_rows = database.list_expiring_issuer_csds(reference_date=reference_date, window_days=alert_days)
    expiring_csds = []
    for row in expiring_csds_rows:
        days_to_expiration = int(row["days_to_expiration"])
        expiring_csds.append(
            {
                "issuer_id": row["issuer_id"],
                "issuer_name": row["issuer_name"],
                "issuer_rfc": row["issuer_rfc"],
                "certificate_number": row["certificate_number"],
                "certificate_valid_to": row["certificate_valid_to"],
                "days_to_expiration": days_to_expiration,
                "severity": _csd_severity(days_to_expiration),
            }
        )
    cfdis = database.list_cfdis()
    recent_cfdis = []
    for cfdi in cfdis:
        folio = getattr(cfdi, "folio", None)
        if folio is None and hasattr(cfdi, "keys") and "folio" in cfdi.keys():
            folio = cfdi["folio"]
        recent_cfdis.append(
            {
                "id": cfdi["id"],
                "issuer_name": cfdi["issuer_name"],
                "issuer_rfc": cfdi["issuer_rfc"],
                "client_name": cfdi["client_name"],
                "recipient_name": cfdi["recipient_name"],
                "recipient_rfc": cfdi["recipient_rfc"],
                "facturama_id": cfdi["facturama_id"],
                "folio": folio,
                "total": cfdi["total"],
                "status": cfdi["status"],
            }
        )

    return render_template(
        "dashboard.html",
        issuers=database.list_issuers(),
        clients=database.list_clients(),
        products=database.list_products(),
        expiring_csds=expiring_csds,
        cfdis=recent_cfdis,
        config=config_status(),
        current_date=now_mx.strftime("%d/%m/%Y"),
    )
