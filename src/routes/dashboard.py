"""Dashboard routes."""

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template

from src.routes.common import config_status, db

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    database = db()
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
        cfdis=recent_cfdis,
        config=config_status(),
        current_date=datetime.now(ZoneInfo("America/Mexico_City")).strftime("%d/%m/%Y"),
    )
