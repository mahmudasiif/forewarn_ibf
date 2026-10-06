"""Settings for the CCM model service."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    MODEL_NAME: str = "ccm"
    MODEL_VERSION: str = "v2.9.3"

    #: Root of the CCM package's CycloneDataBase, mounted read-only. Holds the
    #: union boundaries and the polder/structure/housing lookup tables every
    #: run needs. Same folder scripts/import_ccm.py reads in the API.
    CCM_DATA_DIR: Path = Path("/data/ccm/CycloneDataBase")

    #: Where uploaded scenario files are unpacked while a run executes.
    CCM_RUN_DIR: Path = Path("/tmp/ccm-runs")


settings = Settings()
