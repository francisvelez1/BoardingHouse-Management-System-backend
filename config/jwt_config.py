import base64
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from jose import JWTError, jwt
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv


class JwtSettings(BaseSettings):
    # Because of env_prefix="JWT_", Pydantic looks for:
    # JWT_SECRET, JWT_EXPIRATION, and JWT_REFRESH_EXPIRATION
    
    secret: str = Field(..., alias="JWT_SECRET")
    expiration: int = Field(default=3600, alias="JWT_EXPIRATION")          # Default 1h
    refresh_expiration: int = Field(default=604800, alias="JWT_REFRESH_EXPIRATION") # Default 7d
    model_config = {
        "env_prefix": "JWT_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",         # ignore unrelated .env keys
    }


class JwtConfig:

    ALGORITHM = "HS256"

    def __init__(self, settings: JwtSettings):
        self.settings = settings

    def _get_signing_key(self) -> str:
        """Equivalent to getSigningKey() — decodes Base64 secret"""
        try:
            decoded = base64.b64decode(self.settings.secret)
            return decoded.decode("utf-8", errors="replace")
        except Exception:
            # If secret is not Base64, use it as-is
            return self.settings.secret

    def generate_token(self, username: str, extra_claims: Optional[dict] = None) -> str:
        """
        Equivalent to generateToken(UserDetails) and generateToken(Map, UserDetails)
        """
        claims = extra_claims or {}
        return self._create_token(claims, username, self.settings.expiration)

    def generate_refresh_token(self, username: str) -> str:
        """Equivalent to generateRefreshToken(UserDetails)"""
        return self._create_token({}, username, self.settings.refresh_expiration)

    def _create_token(self, claims: dict, subject: str, expiration_ms: int) -> str:
        """Equivalent to createToken() — builds and signs the JWT"""
        now = datetime.utcnow()
        expire = now + timedelta(milliseconds=expiration_ms)

        payload = {
            **claims,
            "sub": subject,
            "iat": now,
            "exp": expire,
        }

        return jwt.encode(payload, self._get_signing_key(), algorithm=self.ALGORITHM)

    def validate_token(self, token: str, username: str) -> bool:
        """Equivalent to validateToken(String token, UserDetails userDetails)"""
        try:
            token_username = self.get_username_from_token(token)
            return token_username == username and not self._is_token_expired(token)
        except JWTError:
            return False

    def get_username_from_token(self, token: str) -> str:
        """Equivalent to getUsernameFromToken()"""
        return self.get_claim_from_token(token, lambda claims: claims.get("sub"))

    def get_expiration_from_token(self, token: str) -> datetime:
        """Equivalent to getExpirationDateFromToken()"""
        return self.get_claim_from_token(
            token,
            lambda claims: datetime.utcfromtimestamp(claims.get("exp"))
        )

    def get_claim_from_token(self, token: str, resolver: Callable[[dict], Any]) -> Any:
        """Equivalent to getClaimFromToken() — generic claim extractor"""
        claims = self._get_all_claims(token)
        return resolver(claims)

    def _get_all_claims(self, token: str) -> dict:
        """Equivalent to getAllClaimsFromToken() — decodes and verifies the JWT"""
        return jwt.decode(token, self._get_signing_key(), algorithms=[self.ALGORITHM])

    def _is_token_expired(self, token: str) -> bool:
        """Equivalent to isTokenExpired()"""
        expiration = self.get_expiration_from_token(token)
        return expiration < datetime.utcnow()


# ── Singleton instance (initialized lazily, safe to import) ──────────────────
def get_jwt_config() -> JwtConfig:
    """Call this to get the JWT config instance. Reads .env at call time."""
    settings = JwtSettings()
    return JwtConfig(settings)


# Default instance for direct import
jwt_config = get_jwt_config()