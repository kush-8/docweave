from typing import Literal
from pydantic import BaseModel


class Health(BaseModel):
    status: Literal["ok"]


class ApiError(BaseModel):
    code: str
    message: str
    request_id: str
    retryable: bool
