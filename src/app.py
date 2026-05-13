"""Flask application factory and configuration."""

from flask import Flask, flash, redirect, render_template, request, session, url_for
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
    app.config["ADMIN_PASSWORD"] = config.admin_password

    database = PortalDatabase(config.database_url)
    database.init_schema()
    app.extensions["portal_db"] = database

    from src.routes import cfdi, clients, dashboard, issuers, products, reports

    app.register_blueprint(dashboard.bp)
    app.register_blueprint(cfdi.bp)
    app.register_blueprint(cfdi.api_bp)
    app.register_blueprint(clients.bp)
    app.register_blueprint(clients.api_bp)
    app.register_blueprint(issuers.bp)
    app.register_blueprint(issuers.api_bp)
    app.register_blueprint(products.bp)
    app.register_blueprint(products.api_bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(reports.api_bp)

    @app.before_request
    def require_authentication():
        if request.path in {"/health", "/login"} or request.path.startswith("/static/"):
            return None

        if session.get("is_authenticated"):
            return None

        next_url = request.full_path if request.query_string else request.path
        return redirect(url_for("login", next=next_url))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if session.get("is_authenticated"):
            return redirect(url_for("dashboard.index"))

        if request.method == "POST":
            password = request.form.get("password", "")
            if password == app.config.get("ADMIN_PASSWORD"):
                session["is_authenticated"] = True
                flash("Sesion iniciada correctamente.", "success")
                next_url = request.args.get("next")
                if next_url and next_url.startswith("/"):
                    return redirect(next_url)
                return redirect(url_for("dashboard.index"))

            flash("Contrasena incorrecta.", "error")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("Sesion cerrada.", "info")
        return redirect(url_for("login"))

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
