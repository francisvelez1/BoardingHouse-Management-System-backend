from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext


# ---------------------------------------------------------------------------
# Password Hashing
# ---------------------------------------------------------------------------

class PasswordEncoder:
  """
  Wraps passlib PBKDF2-SHA256 as the password hasher.
  This avoids bcrypt's 72-byte limit and backend issues on some platforms.
  """

  def __init__(self):
      # Strong, widely supported algorithm without bcrypt's 72-byte limit
      self._context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

  def encode(self, raw_password: str) -> str:
      """Hash a raw password."""
      return self._context.hash(raw_password)

  def matches(self, raw_password: str, hashed_password: str) -> bool:
      """Verify a raw password against a stored hash."""
      return self._context.verify(raw_password, hashed_password)


password_encoder = PasswordEncoder()


# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------

CORS_CONFIG = {
    "allow_origins": ["http://localhost:5173"],   # Vite dev server
    "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["*"],
    "allow_credentials": True,
}


def configure_cors(app: FastAPI) -> None:
    """
    Registers CORSMiddleware with the same settings as WebConfig.java.
    """
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_CONFIG["allow_origins"],
        allow_methods=CORS_CONFIG["allow_methods"],
        allow_headers=CORS_CONFIG["allow_headers"],
        allow_credentials=CORS_CONFIG["allow_credentials"],
    )


# ---------------------------------------------------------------------------
# Route Access Rules
# ---------------------------------------------------------------------------

# Public routes - no JWT required
PUBLIC_ROUTES = {
    # Auth endpoints
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/forgot-password",
     "/api/auth/verify-otp",       
    "/api/auth/reset-password",   

    # Traditional pages
    "/login",
    "/register",

    # Health check
    "/health",

    # FastAPI built-in docs (remove in production if needed)
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}


# Protected routes - JWT required
PROTECTED_ROUTES = {
    "/home",
}