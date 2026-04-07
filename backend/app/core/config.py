import os
import re
from typing import Optional

from dotenv import load_dotenv
from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 🔥 CRITICAL: Load .env BEFORE Settings initialization
load_dotenv()

_AWS_REGION_RE = re.compile(r"\b[a-z]{2}(?:-gov)?-[a-z0-9-]+-\d\b")


def _sanitize_aws_region(value: str | None, default: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return default
    # Extract the first valid region token and drop anything else (guards against
    # accidental copy/paste or injection strings in env files).
    m = _AWS_REGION_RE.search(raw)
    if m:
        return m.group(0)
    return default


class Settings(BaseSettings):
    app_name: str = "QC-BKP Modern Platform"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"

    # 🔥 FIX: Support both individual fields AND DATABASE_URL from .env
    DATABASE_URL: str | None = Field(
        default=None, validation_alias=AliasChoices("DATABASE_URL")
    )

    pg_host: str = Field(default="127.0.0.1", validation_alias=AliasChoices("PG_HOST"))
    pg_port: int = Field(default=5432, validation_alias=AliasChoices("PG_PORT"))
    pg_user: str = Field(default="postgres", validation_alias=AliasChoices("PG_USER"))
    pg_password: str = Field(
        default="postgres", validation_alias=AliasChoices("PG_PASSWORD")
    )
    pg_database: str = Field(
        default="qc_bkp_modern", validation_alias=AliasChoices("PG_DATABASE")
    )
    pg_admin_database: str = Field(
        default="postgres", validation_alias=AliasChoices("PG_ADMIN_DATABASE")
    )

    legacy_db_host: str = Field(
        default="127.0.0.1", validation_alias=AliasChoices("LEGACY_DB_HOST")
    )
    legacy_db_port: int = Field(
        default=3306, validation_alias=AliasChoices("LEGACY_DB_PORT")
    )
    legacy_db_name: str = Field(
        default="teamrigh_qc", validation_alias=AliasChoices("LEGACY_DB_NAME")
    )
    legacy_db_user: str = Field(
        default="teamrigh_qc", validation_alias=AliasChoices("LEGACY_DB_USER")
    )
    legacy_db_pass: str = Field(
        default="", validation_alias=AliasChoices("LEGACY_DB_PASS")
    )

    s3_region: str = Field(
        default="ap-south-1",
        validation_alias=AliasChoices("S3_REGION", "AWS_REGION"),
    )
    s3_bucket: str | None = Field(
        default=None,
        validation_alias=AliasChoices("S3_BUCKET", "AWS_S3_BUCKET"),
    )
    s3_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("S3_ACCESS_KEY", "AWS_ACCESS_KEY_ID"),
    )
    s3_secret_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("S3_SECRET_KEY", "AWS_SECRET_ACCESS_KEY"),
    )
    s3_endpoint_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("S3_ENDPOINT_URL", "AWS_ENDPOINT_URL"),
    )

    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY"),
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL"),
    )
    openai_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_BASE_URL"),
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias=AliasChoices("OPENAI_EMBEDDING_MODEL"),
    )
    openai_rag_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_RAG_MODEL"),
    )

    ocr_space_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OCR_SPACE_API_KEY"),
    )
    ocr_space_endpoint: str = Field(
        default="https://api.ocr.space/parse/image",
        validation_alias=AliasChoices("OCR_SPACE_ENDPOINT"),
    )

    aws_textract_region: str = Field(
        default="ap-south-1",
        validation_alias=AliasChoices(
            "AWS_TEXTRACT_REGION", "TEXTRACT_REGION", "AWS_REGION", "S3_REGION"
        ),
    )
    aws_textract_access_key_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AWS_TEXTRACT_ACCESS_KEY_ID",
            "TEXTRACT_ACCESS_KEY_ID",
            "AWS_ACCESS_KEY_ID",
            "S3_ACCESS_KEY",
        ),
    )
    aws_textract_secret_access_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AWS_TEXTRACT_SECRET_ACCESS_KEY",
            "TEXTRACT_SECRET_ACCESS_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "S3_SECRET_KEY",
        ),
    )
    aws_textract_session_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AWS_TEXTRACT_SESSION_TOKEN", "TEXTRACT_SESSION_TOKEN", "AWS_SESSION_TOKEN"
        ),
    )
    aws_textract_endpoint_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "AWS_TEXTRACT_ENDPOINT_URL",
            "TEXTRACT_ENDPOINT_URL",
            "AWS_ENDPOINT_URL",
            "S3_ENDPOINT_URL",
        ),
    )

    # 🎯 Phase 0: Hybrid OCR Configuration (PaddleOCR + OpenAI + Textract + Tesseract)
    # OpenAI model for handwriting interpretation (prescriptions)
    openai_vision_model: str = Field(
        default="gpt-5.1",
        validation_alias=AliasChoices("OPENAI_VISION_MODEL"),
    )
    paddle_model_type: str = Field(
        default="v3",
        validation_alias=AliasChoices("PADDLE_MODEL_TYPE"),
    )
    tesseract_cmd_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TESSERACT_CMD_PATH"),
    )
    ocr_confidence_threshold: float = Field(
        default=0.6,
        validation_alias=AliasChoices("OCR_CONFIDENCE_THRESHOLD"),
    )
    ocr_page_limit: int = Field(
        default=50,
        validation_alias=AliasChoices("OCR_PAGE_LIMIT"),
    )

    auth_session_hours: int = Field(
        default=12,
        validation_alias=AliasChoices("AUTH_SESSION_HOURS"),
    )
    bootstrap_admin_username: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BOOTSTRAP_ADMIN_USERNAME"),
    )
    bootstrap_admin_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices("BOOTSTRAP_ADMIN_PASSWORD"),
    )
    ocr_space_engine: int = Field(
        default=2,
        validation_alias=AliasChoices("OCR_SPACE_ENGINE"),
    )

    teamrightworks_integration_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "TEAMRIGHTWORKS_INTEGRATION_TOKEN", "INTEGRATION_TEAMRIGHTWORKS_TOKEN"
        ),
    )
    teamrightworks_integration_actor: str = Field(
        default="integration:teamrightworks",
        validation_alias=AliasChoices(
            "TEAMRIGHTWORKS_INTEGRATION_ACTOR", "INTEGRATION_TEAMRIGHTWORKS_ACTOR"
        ),
    )
    teamrightworks_sync_trigger_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TEAMRIGHTWORKS_SYNC_TRIGGER_URL"),
    )
    teamrightworks_sync_trigger_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TEAMRIGHTWORKS_SYNC_TRIGGER_KEY"),
    )
    teamrightworks_sync_default_password: str = Field(
        default="ChangeMe123A",
        validation_alias=AliasChoices("TEAMRIGHTWORKS_SYNC_DEFAULT_PASSWORD"),
    )
    ml_auto_retrain_on_qc_yes: bool = Field(
        default=True,
        validation_alias=AliasChoices("ML_AUTO_RETRAIN_ON_QC_YES"),
    )
    ml_auto_retrain_min_interval_minutes: int = Field(
        default=30,
        validation_alias=AliasChoices("ML_AUTO_RETRAIN_MIN_INTERVAL_MINUTES"),
    )
    drug_lookup_api_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("DRUG_LOOKUP_API_ENABLED"),
    )
    drug_lookup_api_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DRUG_LOOKUP_API_URL"),
    )

    @field_validator("s3_region", mode="before")
    @classmethod
    def _validate_s3_region(cls, value: str | None):
        return _sanitize_aws_region(value, "ap-south-1")

    @field_validator("aws_textract_region", mode="before")
    @classmethod
    def _validate_textract_region(cls, value: str | None):
        return _sanitize_aws_region(value, "ap-south-1")
    drug_lookup_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("DRUG_LOOKUP_API_KEY"),
    )
    drug_lookup_api_timeout_seconds: float = Field(
        default=8.0,
        validation_alias=AliasChoices("DRUG_LOOKUP_API_TIMEOUT_SECONDS"),
    )
    drug_lookup_use_rxnav_fallback: bool = Field(
        default=True,
        validation_alias=AliasChoices("DRUG_LOOKUP_USE_RXNAV_FALLBACK"),
    )
    medicine_rectify_scheduler_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("MEDICINE_RECTIFY_SCHEDULER_ENABLED"),
    )
    medicine_rectify_scheduler_tz: str = Field(
        default="Asia/Kolkata",
        validation_alias=AliasChoices("MEDICINE_RECTIFY_SCHEDULER_TZ"),
    )
    medicine_rectify_scheduler_hour: int = Field(
        default=1,
        validation_alias=AliasChoices("MEDICINE_RECTIFY_SCHEDULER_HOUR"),
    )
    medicine_rectify_scheduler_minute: int = Field(
        default=0,
        validation_alias=AliasChoices("MEDICINE_RECTIFY_SCHEDULER_MINUTE"),
    )
    medicine_rectify_min_score: float = Field(
        default=0.82,
        validation_alias=AliasChoices("MEDICINE_RECTIFY_MIN_SCORE"),
    )
    medicine_rectify_sleep_ms: int = Field(
        default=0,
        validation_alias=AliasChoices("MEDICINE_RECTIFY_SLEEP_MS"),
    )
    razorpay_ifsc_verify_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("RAZORPAY_IFSC_VERIFY_ENABLED"),
    )
    razorpay_ifsc_api_base_url: str = Field(
        default="https://ifsc.razorpay.com",
        validation_alias=AliasChoices("RAZORPAY_IFSC_API_BASE_URL"),
    )
    razorpay_ifsc_timeout_seconds: float = Field(
        default=8.0,
        validation_alias=AliasChoices("RAZORPAY_IFSC_TIMEOUT_SECONDS"),
    )
    medicine_rectify_timeout_seconds: int = Field(
        default=10800,
        validation_alias=AliasChoices("MEDICINE_RECTIFY_TIMEOUT_SECONDS"),
    )

    # ABDM HPR (Healthcare Professionals Registry) Integration
    abdm_hpr_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("ABDM_HPR_ENABLED"),
    )
    abdm_hpr_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ABDM_HPR_BASE_URL"),
    )
    abdm_hpr_client_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ABDM_HPR_CLIENT_ID"),
    )
    abdm_hpr_client_secret: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ABDM_HPR_CLIENT_SECRET"),
    )
    abdm_hpr_auth_token_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ABDM_HPR_AUTH_TOKEN_URL"),
    )
    abdm_hpr_timeout_seconds: float = Field(
        default=10.0,
        validation_alias=AliasChoices("ABDM_HPR_TIMEOUT_SECONDS"),
    )
    abdm_hpr_token_ttl_seconds: int = Field(
        default=300,
        validation_alias=AliasChoices("ABDM_HPR_TOKEN_TTL_SECONDS"),
    )
    abdm_hpr_cache_ttl_seconds: int = Field(
        default=3600,
        validation_alias=AliasChoices("ABDM_HPR_CACHE_TTL_SECONDS"),
    )
    abdm_hpr_login_enforcement_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("ABDM_HPR_LOGIN_ENFORCEMENT_ENABLED"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 🔥 FIX: Prefer DATABASE_URL from .env, fallback to constructed URI
    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.DATABASE_URL:
            # If DATABASE_URL is set, use it (but ensure it has the right driver)
            if self.DATABASE_URL.startswith("postgresql://"):
                return self.DATABASE_URL.replace(
                    "postgresql://", "postgresql+psycopg://", 1
                )
            return self.DATABASE_URL

        # Otherwise construct from individual fields
        return (
            f"postgresql+psycopg://{self.pg_user}:{self.pg_password}@"
            f"{self.pg_host}:{self.pg_port}/{self.pg_database}?connect_timeout=5"
        )

    @property
    def psycopg_admin_uri(self) -> str:
        env_uri = os.getenv("PSYCOPG_ADMIN_URI")
        if env_uri:
            return env_uri

        # Use Unix socket for localhost connections (more reliable)
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}@"
            f"/{self.pg_admin_database}?host=/var/run/postgresql"
        )

    @property
    def psycopg_database_uri(self) -> str:
        env_uri = os.getenv("PSYCOPG_DATABASE_URI")
        if env_uri:
            return env_uri

        # Use Unix socket for localhost connections (more reliable)
        return (
            f"postgresql://{self.pg_user}:{self.pg_password}@"
            f"/{self.pg_database}?host=/var/run/postgresql"
        )


# 🔥 Initialize settings AFTER load_dotenv()
settings = Settings()
