"""Product routes."""

from flask import Blueprint, jsonify, request

bp = Blueprint("products", __name__, url_prefix="/api/products")


@bp.route("/", methods=["GET"])
def list_products():
    """List all products (placeholder)."""
    return jsonify({"products": [], "message": "Products list endpoint"})


@bp.route("/<string:product_id>", methods=["GET"])
def get_product(product_id: str):
    """Get a specific product by ID."""
    return jsonify(
        {"product_id": product_id, "name": "Product Name", "price": 0.0, "status": "active"}
    )


@bp.route("/", methods=["POST"])
def create_product():
    """Create a new product."""
    data = request.get_json() or {}
    return jsonify({"product_id": "new-product-id", "data": data}), 201


@bp.route("/<string:product_id>", methods=["PUT"])
def update_product(product_id: str):
    """Update a product."""
    data = request.get_json() or {}
    return jsonify({"product_id": product_id, "updated": True, "data": data})


@bp.route("/<string:product_id>", methods=["DELETE"])
def delete_product(product_id: str):
    """Delete a product."""
    return jsonify({"product_id": product_id, "deleted": True})
