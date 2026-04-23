"""CFDI (electronic invoice) routes."""

from flask import Blueprint, jsonify, request

bp = Blueprint("cfdi", __name__, url_prefix="/api/cfdi")


@bp.route("/", methods=["GET"])
def list_cfdis():
    """List all CFDIs (placeholder)."""
    return jsonify({"cfdis": [], "message": "CFDI list endpoint"})


@bp.route("/<string:cfdi_id>", methods=["GET"])
def get_cfdi(cfdi_id: str):
    """Get a specific CFDI by ID."""
    return jsonify({"cfdi_id": cfdi_id, "status": "active"})


@bp.route("/", methods=["POST"])
def create_cfdi():
    """Create a new CFDI (placeholder)."""
    data = request.get_json() or {}
    return jsonify({"cfdi_id": "new-cfdi-id", "data": data}), 201


@bp.route("/<string:cfdi_id>", methods=["DELETE"])
def delete_cfdi(cfdi_id: str):
    """Delete a CFDI by ID."""
    return jsonify({"cfdi_id": cfdi_id, "deleted": True})
