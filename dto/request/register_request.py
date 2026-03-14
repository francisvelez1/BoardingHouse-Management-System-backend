from pydantic import BaseModel


class RegisterRequest(BaseModel):
    username:   str
    email:      str
    password:   str
    first_name: str | None = None
    last_name:  str | None = None
    phone:      str | None = None