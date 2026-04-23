"""Flask application factory and configuration."""

import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Configuration
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key")
    app.config["FACTURAMA_API_URL"] = os.getenv(
        "FACTURAMA_API_URL", "https://www.api.facturama.com"
    )
    app.config["FACTURAMA_API_KEY"] = os.getenv("FACTURAMA_API_KEY", "")

    # Register blueprints
    from src.routes import cfdi, clients, products

    app.register_blueprint(cfdi.bp)
    app.register_blueprint(clients.bp)
    app.register_blueprint(products.bp)

    @app.route("/health")
    def health():
        return {"status": "ok"}

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
