from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from services.authentication_service import authentication_service
from models import user

router = APIRouter(prefix="/api/auth", tags=["auth"])



class LoginRequest(BaseModel):
   
    username: str
    password: str


class LoginResponse(BaseModel):
    message: str
    username: str
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Authenticate user and return JWT tokens",
)
async def login(body: LoginRequest):
    """
    NOTE: must supply the stored hash.
    Replace `_get_stored_hash()` with your real DB/repository call.
    """
    # ----- Replace this block with your real DB lookup -----
    stored_hash = _get_stored_hash(body.username)
    if stored_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    # -------------------------------------------------------

    try:
        auth_result = authentication_service.authenticate(
            body.username, body.password, stored_hash
        )
    except HTTPException:
        # Re-raise as 401 - equivalent to catch(Exception e) -> 401 response
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return LoginResponse(
        message="Login successful",
        username=auth_result["username"],
        access_token=auth_result["access_token"],
        refresh_token=auth_result["refresh_token"],
    )


@router.post("/logout", summary="Clear current user session")
async def logout(request: Request):
    """
    Equivalent to calling authentication_service.clearAuthentication()
    Mirrors SecurityContextHolder.clearContext() on logout.
    """
    authentication_service.clear_authentication(request)
    return {"message": "Logged out successfully"}


# ---------------------------------------------------------------------------
# Placeholder - replace with real repository/DB call
# ---------------------------------------------------------------------------

_FAKE_USER_DB: dict[str, str] = {}  # username -> bcrypt hash


def _get_stored_hash(username: str) -> str | None:
   
    return _FAKE_USER_DB.get(username)