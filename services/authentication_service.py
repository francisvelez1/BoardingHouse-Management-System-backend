from fastapi import HTTPException, status

from config.security_config import password_encoder
from config.jwt_config import jwt_config
from repository.user_repository import find_by_username

class AuthenticationService:
    

    async def authenticate(self, username: str, password: str) -> dict:
       
        user = await find_by_username(username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Credentials",
            )

        # Verify password - equivalent to DaoAuthenticationProvider doing the same internally
        if not password_encoder.matches(password, user.password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
            )

        # Issue tokens - replaces storing auth in SecurityContextHolder for stateless JWT flow
        access_token = jwt_config.generate_token(username)
        refresh_token = jwt_config.generate_refresh_token(username)

        return {
            "username":      username,
            "access_token":  access_token,
            "refresh_token": refresh_token,
            "token_type":    "Bearer",
        }
    def encode_password(self, raw_password: str) -> str:
        if not raw_password:
            raise ValueError("Password cannot be empty")
        return password_encoder.encode(raw_password)

    def matches_password(self, raw_password: str, encoded_password: str) -> bool:
        return password_encoder.matches(raw_password, encoded_password)

    def clear_authentication(self, request) -> None:
        request.state.username = None
        request.state.authenticated = False




# Singleton service instance (equivalent to Spring's @Service singleton bean)
authentication_service = AuthenticationService()