from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os


class Settings(BaseSettings):
    # Pydantic v2: ignorer les variables d'env inconnues (ex: VITE_API_URL)
    model_config = SettingsConfigDict(
        extra="ignore",
        env_file=os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.env")),
        env_prefix="",
    )
    app_name: str = "Infoclip Contrats"
    api_prefix: str = "/api"
    jwt_secret: str = Field(default="changeme")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 12 * 60

    database_url: str = Field(default_factory=lambda: f"sqlite:///{os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../contracts.db'))}")

    storage_dir: str = Field(default_factory=lambda: os.path.abspath(os.path.join(os.path.dirname(__file__), "../../storage/contracts")))

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_pass: str | None = None
    smtp_from: str = "alertes@contrats.local"

    openai_api_key: str | None = None
    sharepoint_tenant_id: str | None = None
    sharepoint_client_id: str | None = None
    sharepoint_client_secret: str | None = None
    sharepoint_site_id: str | None = None
    sharepoint_drive_id: str | None = None
    sharepoint_callback_secret: str | None = None
    sharepoint_questions_list_name: str = "ContractQuestions"
    sharepoint_portfolio_questions_list_name: str = "PortfolioQuestions"


settings = Settings()
