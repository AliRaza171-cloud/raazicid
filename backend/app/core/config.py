"""All settings come from environment variables (or backend/.env). See .env.example."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "RAAZICID API"
    ENV: str = "development"

    # Neon gives you this URL. Use the psycopg driver: postgresql+psycopg://user:pass@host/db?sslmode=require
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/raazicid"

    # Auth (used from Phase 2)
    JWT_SECRET: str = "change-me"
    ACCESS_TOKEN_MINUTES: int = 30
    REFRESH_TOKEN_DAYS: int = 30

    # Web app origins allowed to call the API (comma separated)
    CORS_ORIGINS: str = "http://localhost:5173"

    # Third-party services (filled in as each phase needs them)
    CLOUDINARY_CLOUD_NAME: str = ""
    CLOUDINARY_API_KEY: str = ""
    CLOUDINARY_API_SECRET: str = ""
    GOOGLE_MAPS_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    RELIEFWEB_APPNAME: str = ""
    HDX_APP_IDENTIFIER: str = ""

    # Photo classifier (Phase 5): folder with raazicid_classifier.pt + labels.json from ml/train_classifier.ipynb
    CLASSIFIER_DIR: str = "models"
    # Claude model for rider document review (Phase 5) and RAG answers (Phase 6)
    CLAUDE_MODEL: str = "claude-sonnet-5-5"

    # RAG embeddings (PyTorch / sentence-transformers). 384 = size of the MiniLM models.
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DIM: int = 384

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
