"""SAT catalog search API endpoints."""

from flask import Blueprint, jsonify, request, current_app

bp = Blueprint("sat_api", __name__, url_prefix="/api/sat")


@bp.route("/clave-prod-serv/search")
def search_clave_prod_serv():
    """Search SAT product/service codes."""
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])
    
    from src.routes.common import db
    database = db()
    results = database.search_sat_clave_prod_serv(query, limit=20)
    return jsonify([dict(row) for row in results])


@bp.route("/clave-unidad/search")
def search_clave_unidad():
    """Search SAT unit codes."""
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])
    
    from src.routes.common import db
    database = db()
    results = database.search_sat_clave_unidad(query, limit=20)
    return jsonify([dict(row) for row in results])


@bp.route("/regimen-fiscal/search")
def search_regimen_fiscal():
    """Search SAT tax regimes."""
    query = request.args.get("q", "").strip()
    person_type = request.args.get("type", None)  # 'fisica' or 'moral'
    
    from src.routes.common import db
    database = db()
    results = database.search_sat_regimen_fiscal(query, person_type=person_type, limit=20)
    return jsonify([dict(row) for row in results])


@bp.route("/forma-pago/search")
def search_forma_pago():
    """Search SAT payment forms."""
    query = request.args.get("q", "").strip()
    if len(query) < 1:
        return jsonify([])
    
    from src.routes.common import db
    database = db()
    results = database.search_sat_forma_pago(query, limit=20)
    return jsonify([dict(row) for row in results])


@bp.route("/metodo-pago/search")
def search_metodo_pago():
    """Search SAT payment methods."""
    query = request.args.get("q", "").strip()
    if len(query) < 1:
        return jsonify([])
    
    from src.routes.common import db
    database = db()
    results = database.search_sat_metodo_pago(query, limit=20)
    return jsonify([dict(row) for row in results])
