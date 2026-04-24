"""Dashboard routes."""

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
    )
