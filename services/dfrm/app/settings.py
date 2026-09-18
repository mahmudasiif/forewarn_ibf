from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    MODEL_NAME: str = "dfrm"
    MODEL_VERSION: str = "5.2.0"
    #: Root holding the bundled DFRM_Database (shapefiles + spreadsheets),
    #: mounted read-only in the container. Overridable for local runs.
    DFRM_ASSETS_DIR: str = "/app/assets"
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
