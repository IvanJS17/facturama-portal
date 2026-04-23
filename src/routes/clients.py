"""Client (customer) routes."""

from flask import Blueprint, jsonify, request

bp = Blueprint("clients", __name__, url_prefix="/api/clients")


@bp.route("/", methods=["GET"])
def list_clients():
    """List all clients (placeholder)."""
    return jsonify({"clients": [], "message": "Clients list endpoint"})


@bp.route("/<string:client_id>", methods=["GET"])
def get_client(client_id: str):
    """Get a specific client by ID."""
    return jsonify({"client_id": client_id, "name": "Client Name", "status": "active"})


@bp.route("/", methods=["POST"])
def create_client():
    """Create a new client."""
    data = request.get_json() or {}
    return jsonify({"client_id": "new-client-id", "data": data}), 201


@bp.route("/<string:client_id>", methods=["PUT"])
def update_client(client_id: str):
    """Update a client."""
    data = request.get_json() or {}
    return jsonify({"client_id": client_id, "updated": True, "data": data})


@bp.route("/<string:client_id>", methods=["DELETE"])
def delete_client(client_id: str):
    """Delete a client."""
    return jsonify({"client_id": client_id, "deleted": True})
