from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MODEL_NAME: str = "preparedness"
    MODEL_VERSION: str = "0.1.0"

    #: Static GIS/CSV/xlsx/docx assets from the CCM handover, mounted read-only.
    #: The vendored pipeline resolves every shapefile and workbook under here.
    ASSETS_DIR: str = "/app/assets"

    #: Comma-separated Gemini keys (key-pool failover, as in the handover). When
    #: empty the base guideline is served WITHOUT LLM polish — the whole model
    #: still runs, guidance just is not rewritten. Never required.
    GOOGLE_API_KEYS: str = ""
    GEMINI_MODEL: str = "gemini-3-flash-preview"

    #: Whether to attempt LLM polish by default. Ignored (treated as False) when
    #: no key is configured.
    POLISH_DEFAULT: bool = True

    LOG_LEVEL: str = "INFO"

    @property
    def google_api_key_list(self) -> list[str]:
        return [k.strip() for k in self.GOOGLE_API_KEYS.split(",") if k.strip()]

    @property
    def llm_available(self) -> bool:
        return bool(self.google_api_key_list)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
