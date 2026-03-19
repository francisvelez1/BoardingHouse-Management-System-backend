from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import httpx

from dto.request.login_request    import LoginRequest
from dto.request.register_request import RegisterRequest
from dto.response.auth_response   import LoginResponse
from repository.user_repository   import exists_by_email, exists_by_username, save_user, find_by_email
from services.authentication_service import authentication_service
from config.google_oauth import (
    get_google_client, GOOGLE_AUTH_URL, GOOGLE_TOKEN_URL,
    GOOGLE_USERINFO, GOOGLE_REDIRECT_URI, FRONTEND_URL,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ── Standard Login ───────────────────────────────────────────

@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    auth_result = await authentication_service.authenticate(
        body.username_or_email, body.password
    )
    return LoginResponse(
        message="Login successful",
        **auth_result
    )


@router.post("/logout")
async def logout(request: Request):
    authentication_service.clear_authentication(request)
    return {"message": "Logged out successfully"}


# ── Standard Register ────────────────────────────────────────

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


# ── Forgot / Reset Password ──────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: str

class VerifyOtpRequest(BaseModel):
    email: str
    code:  str

class ResetPasswordRequest(BaseModel):
    reset_token:  str
    new_password: str


@router.post("/forgot-password")
async def forgot_password(body: ForgotPasswordRequest):
    return await authentication_service.forgot_password(body.email)


@router.post("/verify-otp")
async def verify_otp(body: VerifyOtpRequest):
    return await authentication_service.verify_otp(body.email, body.code)


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest):
    return await authentication_service.reset_password(
        body.reset_token, body.new_password
    )


# ── Google OAuth ─────────────────────────────────────────────

@router.get("/google")
async def google_login():
    """Redirect user to Google consent screen."""
    client = get_google_client()
    uri, _ = client.create_authorization_url(GOOGLE_AUTH_URL)
    return RedirectResponse(uri)


@router.get("/google/callback")
async def google_callback(code: str, request: Request):
    """Handle Google redirect — create/login user — redirect to frontend."""
    from models.user import User, RoleName
    from config.jwt_config import jwt_config

    client = get_google_client()

    # Step 1: Exchange authorization code for access token
    try:
        token = await client.fetch_token(
            GOOGLE_TOKEN_URL,
            code         = code,
            redirect_uri = GOOGLE_REDIRECT_URI,
        )
    except Exception as e:
        raise HTTPException(400, f"Failed to exchange Google authorization code: {str(e)}")

    # Step 2: Use httpx directly to fetch Google user info
    try:
        access_token = token.get("access_token")
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                GOOGLE_USERINFO,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            google_user = resp.json()
    except Exception as e:
        raise HTTPException(400, f"Failed to fetch Google user info: {str(e)}")

    email      = google_user.get("email")
    first_name = google_user.get("given_name", "")
    last_name  = google_user.get("family_name", "")
    picture    = google_user.get("picture", "")

    if not email:
        raise HTTPException(400, "Google account has no email")

    # Step 3: Find existing user or auto-register
    user = await find_by_email(email)
    if not user:
        # Auto-generate unique username from email prefix
        base_username = email.split("@")[0]
        username      = base_username
        counter       = 1
        while await exists_by_username(username):
            username = f"{base_username}{counter}"
            counter += 1

        from models.user import User, RoleName
        user = User(
            username        = username,
            email           = email,
            password        = "",
            first_name      = first_name,
            last_name       = last_name,
            profile_picture = picture,
            role            = RoleName.TENANT,
        )
        await save_user(user)

    # Step 4: Issue JWT tokens
    access_token  = jwt_config.generate_token(user.username)
    refresh_token = jwt_config.generate_refresh_token(user.username)

    # Step 5: Redirect to frontend with tokens
    redirect_url = (
        f"{FRONTEND_URL}/auth/google/callback"
        f"?access_token={access_token}"
        f"&refresh_token={refresh_token}"
        f"&username={user.username}"
    )
    return RedirectResponse(redirect_url)