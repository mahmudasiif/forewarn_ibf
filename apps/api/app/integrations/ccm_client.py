"""CCM model client. Input/output schemas are defined by the CCM service itself."""
from app.core.config import settings
from app.integrations.base_model_client import ModelServiceClient


class CCMClient(ModelServiceClient):
    name = "ccm"

    def __init__(self) -> None:
        super().__init__(settings.CCM_SERVICE_URL)


ccm_client = CCMClient()
