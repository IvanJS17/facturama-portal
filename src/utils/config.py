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
