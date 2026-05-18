from datetime import datetime, timedelta
import logging
import random

from fastapi import HTTPException, status

from config.email_config import send_otp_email
from config.security_config import password_encoder
from config.jwt_config import jwt_config
from models.user import User
from repository.otp_repository import find_otp, mark_otp_used, save_otp
from repository.user_repository import find_by_email, find_by_username


logger = logging.getLogger(__name__)


async def record_successful_login(user: "User") -> None:
    """
    Stamp `user.last_login` with the current UTC time.

    Called from every successful authentication path (standard
    username/password login and the Google OAuth callback) so the Admin
    dashboard's "Last login" column reflects real session activity
    instead of always showing "Never".

    Failures here are logged and swallowed — the user must never see
    their login rejected just because the audit stamp couldn't be
    persisted.
    """
    try:
        now = datetime.utcnow()
        user.last_login = now
        user.updated_at = now
        await user.save()
    except Exception as exc:
        logger.warning(
            "Failed to record last_login for user=%s: %s",
            getattr(user, "username", "<unknown>"), exc,
        )


class AuthenticationService:

    async def authenticate(self, username_or_email: str, password: str) -> dict:
        # Try username first, then fall back to email
        user = await find_by_username(username_or_email)
        if not user:
            user = await find_by_email(username_or_email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        # Check password against stored hash
        if not password_encoder.matches(password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        # Stamp last_login *before* issuing tokens so the Admin dashboard
        # reflects this session immediately on its next refresh.
        await record_successful_login(user)

        # Issue JWT tokens — include role in claims for require_roles() to work
        role_value    = user.role.value if hasattr(user.role, "value") else str(user.role)
        access_token  = jwt_config.generate_token(user.username, extra_claims={"roles": [role_value]})
        refresh_token = jwt_config.generate_refresh_token(user.username)

        return {
            "username":      user.username,
            "access_token":  access_token,
            "refresh_token": refresh_token,
            "token_type":    "Bearer",
            "role":          role_value,
            "id":            str(user.id) if user.id else None,
            "email":         user.email,
        }

    def encode_password(self, raw_password: str) -> str:
        if not raw_password:
            raise ValueError("Password cannot be empty")
        return password_encoder.encode(raw_password)

    def matches_password(self, raw_password: str, encoded_password: str) -> bool:
        return password_encoder.matches(raw_password, encoded_password)

    def clear_authentication(self, request) -> None:
        request.state.username      = None
        request.state.authenticated = False

    async def forgot_password(self, email: str):
        user = await find_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="This email is not registered.",
            )

        otp_code   = str(random.randint(100000, 999999))
        expires_at = datetime.utcnow() + timedelta(minutes=10)

        await save_otp(email, otp_code, expires_at)
        await send_otp_email(email, otp_code)

        return {"message": "If that email exists, an OTP has been sent"}

    async def verify_otp(self, email: str, code: str):
        otp = await find_otp(email, code)
        if not otp:
            raise HTTPException(400, "Invalid OTP code")
        if datetime.utcnow() > otp.expires_at:
            raise HTTPException(400, "OTP has expired")
        await mark_otp_used(otp)
        reset_token = jwt_config.generate_token(email)
        return {"reset_token": reset_token}

    async def reset_password(self, reset_token: str, new_password: str):
        email = jwt_config.get_username_from_token(reset_token)  # ✅ renamed: sub holds email
        if not email:
            raise HTTPException(400, "Invalid or expired reset token")
        user = await find_by_email(email)
        if not user:
            raise HTTPException(404, "User not found")
        user.password   = self.encode_password(new_password)
        user.updated_at = datetime.utcnow()
        await user.save()
        return {"message": "Password reset successfully"}


# Singleton service instance
authentication_service = AuthenticationService()