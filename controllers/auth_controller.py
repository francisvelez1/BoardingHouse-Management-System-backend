from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from repository.user_repository import exists_by_email, exists_by_username, save_user
from services.authentication_service import authentication_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    message:       str
    username:      str
    access_token:  str
    refresh_token: str
    token_type:    str = "Bearer"


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    auth_result = await authentication_service.authenticate(
        body.username, body.password
    )
    return LoginResponse(
        message="Login successful",
        **auth_result        # unpacks username, access_token, refresh_token, token_type
    )


@router.post("/logout")
async def logout(request: Request):
    authentication_service.clear_authentication(request)
    return {"message": "Logged out successfully"}

class RegisterRequest(BaseModel):
    username:      str
    email:         str
    password:      str
    first_name:    str | None = None
    last_name:     str | None = None

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    #check for duplicates
    if await exists_by_username(body.username):
        raise HTTPException(400, "Username already taken")
    if await exists_by_email(body.email):
        raise HTTPException(400, "Email already in use")

    #hash password and save
    from models.user import user, RoleName
    user = user(
        username        = body.username,
        email           = body.email,
        password        = authentication_service.encode_password(body.password),
        first_name      = body.first_name,
        last_name       = body.last_name,
        role            = RoleName.TENANT,
    )

    await save_user(user)
    return {"message": "Registered successfully", "username": user.username}