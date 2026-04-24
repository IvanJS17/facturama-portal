"""Flask application factory and configuration."""

from flask import Flask, render_template
from dotenv import load_dotenv

from src.models import PortalDatabase
from src.services.facturama_api import FacturamaAPIError
from src.utils.config import Config

load_dotenv()


def create_app() -> Flask:
    """Create and configure the Flask application."""
    config = Config.from_env()
    app = Flask(__name__)

    app.config["SECRET_KEY"] = config.secret_key
    app.config["FACTURAMA_API_URL"] = config.facturama_api_url
    app.config["DATABASE_URL"] = config.database_url
    app.config["PORTAL_CONFIG"] = config

    database = PortalDatabase(config.database_url)
    database.init_schema()
    app.extensions["portal_db"] = database

    from src.routes import cfdi, clients, dashboard, issuers, products

    app.register_blueprint(dashboard.bp)
    app.register_blueprint(cfdi.bp)
    app.register_blueprint(cfdi.api_bp)
    app.register_blueprint(clients.bp)
    app.register_blueprint(clients.api_bp)
    app.register_blueprint(issuers.bp)
    app.register_blueprint(issuers.api_bp)
    app.register_blueprint(products.bp)
    app.register_blueprint(products.api_bp)

    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.errorhandler(FacturamaAPIError)
    def facturama_error(error: FacturamaAPIError):
        return render_template("errors/facturama.html", error=error), 502

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5000, debug=True)
