from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext


# ---------------------------------------------------------------------------
# Password Hashing
# ---------------------------------------------------------------------------

class PasswordEncoder:
    """Wraps passlib BCrypt - equivalent to Spring's BCryptPasswordEncoder"""

    def __init__(self):
        self._context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def encode(self, raw_password: str) -> str:
        """Equivalent to passwordEncoder.encode()"""
        return self._context.hash(raw_password)

    def matches(self, raw_password: str, hashed_password: str) -> bool:
        """Equivalent to passwordEncoder.matches()"""
        return self._context.verify(raw_password, hashed_password)



password_encoder = PasswordEncoder()


# ---------------------------------------------------------------------------
# CORS Configuration
# ---------------------------------------------------------------------------

CORS_CONFIG = {
    "allow_origins": ["http://localhost:5173"],   # Vite dev server (same as Java config)
    "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["*"],
    "allow_credentials": True,
}
#-------

#---------

def configure_cors(app: FastAPI) -> None:
    """
    Equivalent to:
      .cors(cors -> cors.configurationSource(webConfig.corsConfigurationSource()))
    Registers CORSMiddleware with the same settings as WebConfig.java
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
# Equivalent to .authorizeHttpRequests() in SecurityConfig.securityFilterChain()
# ---------------------------------------------------------------------------

# Public routes - no JWT required
# Equivalent to: .requestMatchers("/api/auth/**", "/login", "/register", ...).permitAll()
PUBLIC_ROUTES = {
     # Auth endpoints
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/forgot-password",

    # Traditional pages
    "/login",
    "/register",

    # Health check
    "/health",

    # FastAPI built-in docs (remove these in production if needed)
    "/docs",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
}