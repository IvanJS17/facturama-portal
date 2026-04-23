# Facturama Internal Portal — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build an internal web portal (Flask-based) that connects to Facturama's sandbox API via Python SDK, allowing CFDI creation, retrieval, cancellation, PDF/XML download, and CRUD for clients/products.

**Architecture:** Flask web app with modular service layer wrapping the Facturama Python SDK. Configuration via environment variables (.env). SQLite for local caching of issued CFDIs. Simple Jinja2 templates for the UI.

**Tech Stack:** Python 3.10+, Flask, Facturama Python SDK, SQLite, Gunicorn (production), dotenv, pytest

---

## Phase 1: Project Setup

### Task 1: Create project directory structure

**Objective:** Establish the canonical folder layout for the portal.

**Files:**
- Create: `facturama-portal/` (root)
- Create: `facturama-portal/src/` (application code)
- Create: `facturama-portal/tests/` (pytest tests)
- Create: `facturama-portal/docs/` (documentation)
- Create: `facturama-portal/.env.example`

**Step 1: Create directories**

```bash
mkdir -p facturama-portal/{src/{routes,services,models,utils},tests/{unit,integration},docs}
touch facturama-portal/src/__init__.py
touch facturama-portal/src/routes/__init__.py
touch facturama-portal/src/services/__init__.py
touch facturama-portal/src/models/__init__.py
touch facturama-portal/src/utils/__init__.py
touch facturama-portal/tests/__init__.py
touch facturama-portal/tests/unit/__init__.py
touch facturama-portal/tests/integration/__init__.py
```

**Step 2: Create `.env.example`**

```
# Facturama API Credentials (Sandbox)
FACTURAMA_USER=your_sandbox_user
FACTURAMA_PASSWORD=your_sandbox_password
FACTURAMA_API_URL=https://apisandbox.facturama.mx/

# Flask
FLASK_APP=src.app
FLASK_ENV=development
SECRET_KEY=change-me-in-production

# Database
DATABASE_URL=sqlite:///facturama_portal.db
```

**Step 3: Commit**

```bash
cd facturama-portal
git init
git add .
git commit -m "feat: initial project structure"
```

---

### Task 2: Create `pyproject.toml` and install dependencies

**Objective:** Pin Python version and declare all project dependencies in one place.

**Files:**
- Create: `facturama-portal/pyproject.toml`

**Step 1: Write `pyproject.toml`**

```toml
[project]
name = "facturama-portal"
version = "0.1.0"
description = "Internal portal for Facturama CFDI management (sandbox)"
requires-python = ">=3.10"
dependencies = [
    "flask>=3.0.0",
    "python-dotenv>=1.0.0",
    "facturama @ git+https://github.com/Facturama/facturama-python-sdk.git@master",
    "gunicorn>=21.0.0",
    "requests>=2.31.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "black>=24.0.0",
    "ruff>=0.1.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

**Step 2: Install dependencies**

```bash
cd facturama-portal
pip install -e ".[dev]"
```

**Step 3: Verify installation**

```bash
python -c "import flask; import facturama; print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add pyproject.toml with dependencies"
```

---

## Phase 2: Core Configuration & SDK Integration

### Task 3: Create configuration loader

**Objective:** Load environment variables safely via a config module.

**Files:**
- Create: `facturama-portal/src/utils/config.py`

**Step 1: Write config loader**

```python
"""Configuration loader from environment variables."""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Application configuration."""

    # Facturama
    facturama_user: str
    facturama_password: str
    facturama_api_url: str = "https://apisandbox.facturama.mx/"

    # Flask
    flask_app: str = "src.app"
    flask_env: str = "development"
    secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "sqlite:///facturama_portal.db"

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        return cls(
            facturama_user=os.getenv("FACTURAMA_USER", ""),
            facturama_password=os.getenv("FACTURAMA_PASSWORD", ""),
            facturama_api_url=os.getenv("FACTURAMA_API_URL", "https://apisandbox.facturama.mx/"),
            flask_app=os.getenv("FLASK_APP", "src.app"),
            flask_env=os.getenv("FLASK_ENV", "development"),
            secret_key=os.getenv("SECRET_KEY", "change-me-in-production"),
            database_url=os.getenv("DATABASE_URL", "sqlite:///facturama_portal.db"),
        )

    def validate(self) -> None:
        """Validate required configuration fields."""
        if not self.facturama_user or not self.facturama_password:
            raise ValueError("FACTURAMA_USER and FACTURAMA_PASSWORD are required")
```

**Step 2: Write failing test**

```python
# tests/unit/test_config.py
import pytest
from src.utils.config import Config


def test_config_loads_from_env(monkeypatch):
    monkeypatch.setenv("FACTURAMA_USER", "testuser")
    monkeypatch.setenv("FACTURAMA_PASSWORD", "testpass")
    config = Config.from_env()
    assert config.facturama_user == "testuser"
    assert config.facturama_password == "testpass"


def test_config_validate_raises_on_missing_credentials(monkeypatch):
    monkeypatch.delenv("FACTURAMA_USER", raising=False)
    monkeypatch.delenv("FACTURAMA_PASSWORD", raising=False)
    config = Config.from_env()
    with pytest.raises(ValueError, match="FACTURAMA_USER and FACTURAMA_PASSWORD"):
        config.validate()
```

**Step 3: Run test**

```bash
cd facturama-portal && pytest tests/unit/test_config.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add src/utils/config.py tests/unit/test_config.py
git commit -m "feat: add config loader from environment variables"
```

---

### Task 4: Create Facturama service wrapper

**Objective:** Wrap the Facturama SDK in a reusable service class with error handling.

**Files:**
- Create: `facturama-portal/src/services/facturama_service.py`

**Step 1: Write the service wrapper**

```python
"""Facturama API service wrapper."""
import logging
from typing import Any, Optional

from facturama import Facturama

from src.utils.config import Config

logger = logging.getLogger(__name__)


class FacturamaServiceError(Exception):
    """Raised when a Facturama API call fails."""
    pass


class FacturamaService:
    """Wrapper around the Facturama Python SDK."""

    def __init__(self, config: Config):
        self.config = config
        self._client: Optional[Facturama] = None

    def _get_client(self) -> Facturama:
        """Lazily initialize and return the Facturama client."""
        if self._client is None:
            self._client = Facturama(
                self.config.facturama_user,
                self.config.facturama_password,
                self.config.facturama_api_url,
            )
        return self._client

    def _handle_response(self, response: Any, operation: str) -> Any:
        """Validate and unwrap API response."""
        if response is None:
            raise FacturamaServiceError(f"{operation} returned None")
        if hasattr(response, "error"):
            raise FacturamaServiceError(f"{operation} failed: {response.error}")
        return response

    # ─── CFDI Operations ───────────────────────────────────────────

    def create_cfdi(self, payload: dict) -> dict:
        """Create a new CFDI (invoice).
        
        Args:
            payload: CFDI creation payload per Facturama API docs.
        
        Returns:
            Created CFDI object.
        """
        client = self._get_client()
        result = client.Cfdi.Post(payload)
        return self._handle_response(result, "Create CFDI")

    def list_cfdis(self, query: Optional[str] = None) -> list:
        """List issued CFDIs.
        
        Args:
            query: Optional RFC filter.
        
        Returns:
            List of CFDI objects.
        """
        client = self._get_client()
        params = {"keyword": query} if query else {}
        result = client.Cfdi.Get(params=params)
        return self._handle_response(result, "List CFDIs")

    def get_cfdi(self, cfdi_id: str) -> dict:
        """Retrieve a specific CFDI by ID."""
        client = self._get_client()
        result = client.Cfdi.Get(cfdi_id)
        return self._handle_response(result, f"Get CFDI {cfdi_id}")

    def cancel_cfdi(self, cfdi_id: str, reason: str = "02") -> dict:
        """Cancel a CFDI.
        
        Args:
            cfdi_id: The CFDI identifier.
            reason: Cancellation reason code (default "02" = issuer decision).
        
        Returns:
            Cancellation result.
        """
        client = self._get_client()
        result = client.Cfdi.Delete(cfdi_id, {"reason": reason})
        return self._handle_response(result, f"Cancel CFDI {cfdi_id}")

    def download_pdf(self, cfdi_id: str, output_path: str) -> str:
        """Download CFDI PDF and save to file.
        
        Returns:
            Path to saved PDF file.
        """
        client = self._get_client()
        cfdi = client.Cfdi.Get(cfdi_id)
        self._handle_response(cfdi, f"Get CFDI {cfdi_id}")
        pdf_bytes = client.Cfdi.GetPdf(cfdi_id)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        return output_path

    def download_xml(self, cfdi_id: str, output_path: str) -> str:
        """Download CFDI XML and save to file.
        
        Returns:
            Path to saved XML file.
        """
        client = self._get_client()
        xml_bytes = client.Cfdi.GetXml(cfdi_id)
        with open(output_path, "wb") as f:
            f.write(xml_bytes)
        return output_path

    # ─── Client Operations ─────────────────────────────────────────

    def create_client(self, client_data: dict) -> dict:
        """Create a new client (recipient)."""
        client = self._get_client()
        result = client.Client.Post(client_data)
        return self._handle_response(result, "Create Client")

    def list_clients(self) -> list:
        """List all clients."""
        client = self._get_client()
        result = client.Client.Get()
        return self._handle_response(result, "List Clients")

    def get_client(self, client_id: str) -> dict:
        """Get a specific client."""
        client = self._get_client()
        result = client.Client.Get(client_id)
        return self._handle_response(result, f"Get Client {client_id}")

    # ─── Product Operations ────────────────────────────────────────

    def create_product(self, product_data: dict) -> dict:
        """Create a new product/service item."""
        client = self._get_client()
        result = client.Product.Post(product_data)
        return self._handle_response(result, "Create Product")

    def list_products(self) -> list:
        """List all products."""
        client = self._get_client()
        result = client.Product.Get()
        return self._handle_response(result, "List Products")
```

**Step 2: Write failing tests**

```python
# tests/unit/test_facturama_service.py
import pytest
from unittest.mock import MagicMock, patch
from src.services.facturama_service import FacturamaService, FacturamaServiceError
from src.utils.config import Config


@pytest.fixture
def mock_config():
    config = Config(
        facturama_user="testuser",
        facturama_password="testpass",
        facturama_api_url="https://apisandbox.facturama.mx/",
    )
    return config


def test_service_initializes_without_calling_api(mock_config):
    """Service should not call Facturama on init (lazy client)."""
    with patch("src.services.facturama_service.Facturama") as mock_facturama:
        service = FacturamaService(mock_config)
        mock_facturama.assert_not_called()


def test_handle_response_raises_on_none(mock_config):
    service = FacturamaService(mock_config)
    with pytest.raises(FacturamaServiceError, match="returned None"):
        service._handle_response(None, "Test Op")
```

**Step 3: Run tests**

```bash
cd facturama-portal && pytest tests/unit/test_facturama_service.py -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add src/services/facturama_service.py tests/unit/test_facturama_service.py
git commit -m "feat: add Facturama service wrapper with CFDI/client/product operations"
```

---

## Phase 3: Flask Application

### Task 5: Create Flask app factory and routes

**Objective:** Bootstrap Flask app with blueprint-based routes.

**Files:**
- Create: `facturama-portal/src/app.py`
- Create: `facturama-portal/src/routes/cfdi.py`
- Create: `facturama-portal/src/routes/clients.py`
- Create: `facturama-portal/src/routes/products.py`

**Step 1: Write Flask app factory**

```python
"""Flask application factory."""
import logging
from flask import Flask
from src.utils.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app(config: Config = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    if config is None:
        config = Config.from_env()
        config.validate()

    app.config["SECRET_KEY"] = config.secret_key
    app.config["FACTURAMA_CONFIG"] = config

    # Register blueprints
    from src.routes import cfdi, clients, products

    app.register_blueprint(cfdi.bp)
    app.register_blueprint(clients.bp)
    app.register_blueprint(products.bp)

    @app.route("/health")
    def health():
        return {"status": "ok"}

    logger.info("Flask app initialized")
    return app
```

**Step 2: Write CFDI routes**

```python
"""CFDI routes."""
import os
from flask import Blueprint, jsonify, request, send_file

from src.services.facturama_service import FacturamaService, FacturamaServiceError
from src.utils.config import Config

bp = Blueprint("cfdi", __name__, url_prefix="/api/cfdis")


def get_service() -> FacturamaService:
    config: Config = current_app.config["FACTURAMA_CONFIG"]
    return FacturamaService(config)


from flask import current_app


@bp.route("/", methods=["GET"])
def list_cfdis():
    """List all CFDIs. Optional query param: ?rfc=XXX"""
    try:
        service = get_service()
        rfc = request.args.get("rfc")
        cfdis = service.list_cfdis(query=rfc)
        return jsonify(cfdis)
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/", methods=["POST"])
def create_cfdi():
    """Create a new CFDI."""
    try:
        service = get_service()
        payload = request.json
        cfdi = service.create_cfdi(payload)
        return jsonify(cfdi), 201
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<cfdi_id>", methods=["GET"])
def get_cfdi(cfdi_id):
    """Get a specific CFDI."""
    try:
        service = get_service()
        cfdi = service.get_cfdi(cfdi_id)
        return jsonify(cfdi)
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/<cfdi_id>/cancel", methods=["POST"])
def cancel_cfdi(cfdi_id):
    """Cancel a CFDI."""
    try:
        service = get_service()
        reason = request.json.get("reason", "02") if request.json else "02"
        result = service.cancel_cfdi(cfdi_id, reason)
        return jsonify(result)
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<cfdi_id>/pdf", methods=["GET"])
def download_pdf(cfdi_id):
    """Download CFDI as PDF."""
    try:
        service = get_service()
        output_path = f"/tmp/{cfdi_id}.pdf"
        path = service.download_pdf(cfdi_id, output_path)
        return send_file(path, mimetype="application/pdf")
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<cfdi_id>/xml", methods=["GET"])
def download_xml(cfdi_id):
    """Download CFDI as XML."""
    try:
        service = get_service()
        output_path = f"/tmp/{cfdi_id}.xml"
        path = service.download_xml(cfdi_id, output_path)
        return send_file(path, mimetype="application/xml")
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 500
```

**Step 3: Write client routes**

```python
"""Client routes."""
from flask import Blueprint, jsonify, request

from src.services.facturama_service import FacturamaService, FacturamaServiceError
from src.utils.config import Config
from flask import current_app

bp = Blueprint("clients", __name__, url_prefix="/api/clients")


def get_service() -> FacturamaService:
    config: Config = current_app.config["FACTURAMA_CONFIG"]
    return FacturamaService(config)


@bp.route("/", methods=["GET"])
def list_clients():
    try:
        service = get_service()
        clients = service.list_clients()
        return jsonify(clients)
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/", methods=["POST"])
def create_client():
    try:
        service = get_service()
        data = request.json
        client = service.create_client(data)
        return jsonify(client), 201
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/<client_id>", methods=["GET"])
def get_client(client_id):
    try:
        service = get_service()
        client = service.get_client(client_id)
        return jsonify(client)
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 404
```

**Step 4: Write product routes**

```python
"""Product routes."""
from flask import Blueprint, jsonify, request

from src.services.facturama_service import FacturamaService, FacturamaServiceError
from src.utils.config import Config
from flask import current_app

bp = Blueprint("products", __name__, url_prefix="/api/products")


def get_service() -> FacturamaService:
    config: Config = current_app.config["FACTURAMA_CONFIG"]
    return FacturamaService(config)


@bp.route("/", methods=["GET"])
def list_products():
    try:
        service = get_service()
        products = service.list_products()
        return jsonify(products)
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/", methods=["POST"])
def create_product():
    try:
        service = get_service()
        data = request.json
        product = service.create_product(data)
        return jsonify(product), 201
    except FacturamaServiceError as e:
        return jsonify({"error": str(e)}), 500
```

**Step 5: Verify app starts**

```bash
cd facturama-portal
cp .env.example .env
# Edit .env with sandbox credentials
python -c "from src.app import create_app; app = create_app(); print('App created OK')"
```

**Step 6: Commit**

```bash
git add src/app.py src/routes/cfdi.py src/routes/clients.py src/routes/products.py
git commit -m "feat: add Flask app with CFDI/client/product routes"
```

---

## Phase 4: Testing & Quality

### Task 6: Add integration test scaffold

**Objective:** Provide a test that runs against sandbox (requires real credentials).

**Files:**
- Create: `facturama-portal/tests/integration/test_sandbox.py`

**Step 1: Write integration test**

```python
"""Sandbox integration tests — requires real .env credentials."""
import os
import pytest
from src.app import create_app
from src.utils.config import Config


@pytest.fixture
def app():
    config = Config.from_env()
    config.validate()
    app = create_app(config)
    app.config["TESTING"] = True
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_health_check(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json["status"] == "ok"


@pytest.mark.skipif(
    not os.getenv("FACTURAMA_USER"),
    reason="Requires real sandbox credentials"
)
def test_list_cfdis(client):
    resp = client.get("/api/cfdis/")
    assert resp.status_code == 200
    assert isinstance(resp.json, list)
```

**Step 2: Run tests**

```bash
cd facturama-portal && pytest tests/ -v --ignore=tests/integration
```

Expected: unit tests pass, integration tests skipped

**Step 3: Commit**

```bash
git add tests/integration/test_sandbox.py
git commit -m "test: add integration test scaffold"
```

---

## Phase 5: GitHub Repository Setup

### Task 7: Initialize Git repo and push to GitHub

**Objective:** Create the repo under `IvanJS17` on GitHub and push code.

**Files:**
- Create: `facturama-portal/.gitignore`

**Step 1: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.venv/
*.egg-info/
.pytest_cache/
.coverage
facturama_portal.db
*.sqlite
```

**Step 2: Initialize and push**

```bash
cd facturama-portal
gh repo create facturama-portal --public --clone=false --source=.
git remote add origin https://github.com/IvanJS17/facturama-portal.git
git branch -M main
git push -u origin main
```

---

## Execution Order

1. Task 1 — Create project structure
2. Task 2 — Install dependencies
3. Task 3 — Config loader
4. Task 4 — Facturama service wrapper
5. Task 5 — Flask app and routes
6. Task 6 — Tests
7. Task 7 — Push to GitHub

---

## Appendix: Facturama API Reference (from research)

### Test Credentials (Sandbox)
- **RFC prueba:** `EKU9003173C9`
- **CSDs prueba:** https://apisandbox.facturama.mx/guias/conocimientos/sellos-digitales-pruebas
- **Login:** https://dev.facturama.mx/api/login

### Key API Endpoints (via SDK)
- `POST /Cfdi` — Create CFDI
- `GET /Cfdi` — List CFDIs
- `GET /Cfdi/{id}` — Get CFDI
- `DELETE /Cfdi/{id}` — Cancel CFDI
- `GET /Cfdi/{id}/pdf` — Download PDF
- `GET /Cfdi/{id}/xml` — Download XML
- `POST /Client` — Create client
- `GET /Client` — List clients
- `POST /Product` — Create product
- `GET /Product` — List products

### CFDI 4.0 Structure (minimal payload)
```python
{
    "CfdiType": "I",
    "NameId": "1",
    "Folio": "100",
    "ExpeditionPlace": "78140",
    "PaymentForm": "01",
    "Currency": "MXN",
    "PaymentMethod": "PUE",
    "Issuer": {
        "Rfc": "EKU9003173C9",
        "CfdiUse": "CP01",
        "Name": "TEST RFC",
        "FiscalRegime": "601",
        "TaxZipCode": "78140"
    },
    "Receiver": {
        "Rfc": "OÑ120726RX3",
        "CfdiUse": "G03",
        "Name": "TEST RECEIVER",
        "FiscalRegime": "601",
        "TaxZipCode": "32040"
    },
    "Items": [{
        "Quantity": "1",
        "ProductCode": "84111506",
        "UnitCode": "E48",
        "Unit": "Unidad de servicio",
        "Description": "Test service",
        "UnitPrice": "100.00",
        "Subtotal": "100.00",
        "Taxes": [{"Name": "IVA", "Rate": "0.16", "Total": "16.00", "Base": "100.00"}],
        "Total": "116.00"
    }]
}
```
