from pydantic import BaseModel


class LoginResponse(BaseModel):
    message:       str
    username:      str
    access_token:  str
    refresh_token: str
    token_type:    str = "Bearer"