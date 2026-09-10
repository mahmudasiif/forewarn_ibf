"""Auth request/response models (Pydantic). The API contract for this module."""
from pydantic import BaseModel, ConfigDict


class AuthBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
