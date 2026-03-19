# ============================================================
#  ResidEase — Google OAuth Config (Authlib)
# ============================================================

from dotenv import load_dotenv
import os

load_dotenv()  # ← explicitly load .env file

from authlib.integrations.httpx_client import AsyncOAuth2Client

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080/api/auth/google/callback")
FRONTEND_URL         = os.getenv("FRONTEND_URL", "http://localhost:5173")

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO  = "https://www.googleapis.com/oauth2/v3/userinfo"

SCOPES = "openid email profile"


def get_google_client() -> AsyncOAuth2Client:
    if not GOOGLE_CLIENT_ID:
        raise RuntimeError("GOOGLE_CLIENT_ID is not set in .env")
    if not GOOGLE_CLIENT_SECRET:
        raise RuntimeError("GOOGLE_CLIENT_SECRET is not set in .env")

    return AsyncOAuth2Client(
        client_id     = GOOGLE_CLIENT_ID,
        client_secret = GOOGLE_CLIENT_SECRET,
        redirect_uri  = GOOGLE_REDIRECT_URI,
        scope         = SCOPES,
    )