from pydantic import BaseModel


class CurrentUser(BaseModel):
    id: str
    display_name: str
    verified_email: str
    csrf_token: str
