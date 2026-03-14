from fastapi import APIRouter, HTTPException, Request, status

from dto.request.login_request    import LoginRequest
from dto.request.register_request import RegisterRequest
from dto.response.auth_response   import LoginResponse
from repository.user_repository   import exists_by_email, exists_by_username, save_user
from services.authentication_service import authentication_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    auth_result = await authentication_service.authenticate(
        body.username, body.password
    )
    return LoginResponse(
        message="Login successful",
        **auth_result   # unpacks: username, access_token, refresh_token, token_type
    )


@router.post("/logout")
async def logout(request: Request):
    authentication_service.clear_authentication(request)
    return {"message": "Logged out successfully"}


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest):
    if await exists_by_username(body.username):
        raise HTTPException(400, "Username already taken")
    if await exists_by_email(body.email):
        raise HTTPException(400, "Email already in use")

    from models.user import User, RoleName
    user = User(
        username   = body.username,
        email      = body.email,
        password   = authentication_service.encode_password(body.password),
        first_name = body.first_name,
        last_name  = body.last_name,
        phone      = body.phone,
        role       = RoleName.TENANT,
    )

    await save_user(user)
    return {"message": "Registered successfully", "username": user.username}