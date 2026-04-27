"""Dashboard routes."""

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template

from src.routes.common import config_status, db

bp = Blueprint("dashboard", __name__)


@bp.get("/")
def index():
    database = db()
    return render_template(
        "dashboard.html",
        issuers=database.list_issuers(),
        clients=database.list_clients(),
        products=database.list_products(),
        cfdis=database.list_cfdis(),
        config=config_status(),
        current_date=datetime.now(ZoneInfo("America/Mexico_City")).strftime("%d/%m/%Y"),
    )
