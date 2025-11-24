# app/dependencies/auth.py
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from app.db import postgres
from app.core.security import decode_access_token
from app.schemas.user_schema import TokenData

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> dict:
    """
    Authorization: Bearer <token> 에서 사용자 dict 반환.
    - 토큰 무효 / 만료 → 401
    - 사용자 비활성 / 권한 만료 → 403
    """
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="토큰이 유효하지 않습니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        token_data: TokenData = decode_access_token(token)
    except JWTError:
        raise credentials_exc

    if not token_data.username:
        raise credentials_exc

    user = postgres.get_user(token_data.username)
    if not user:
        raise credentials_exc

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="비활성화된 계정입니다.",
        )

    expires_at = user["expires_at"]
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    if expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="사용자 권한이 만료되었습니다.",
        )

    return user  # dict(username, password_hash, expires_at, is_active, created_at)
