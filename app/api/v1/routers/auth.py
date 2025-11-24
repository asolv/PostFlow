# app/api/auth.py
from datetime import timezone, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.db import postgres
from app.core.security import hash_password, verify_password, create_access_token
from app.schemas.user_schema import UserCreate, UserLogin, Token
from app.dependencies.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token)
def register_user(body: UserCreate):
    """
    관리자/초기 설정용: 사용자 등록 + 바로 토큰 발급.
    - username 중복이면 덮어쓰기(비번/만료일 갱신)
    """
    # naive datetime이면 UTC로 가정
    expires_at = body.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    password_hash = hash_password(body.password)
    postgres.create_user(
        username=body.username,
        password_hash=password_hash,
        expires_at=expires_at,
        is_active=True,
    )

    access_token = create_access_token({"sub": body.username})
    return Token(access_token=access_token)


@router.post("/login", response_model=Token)
def login(body: UserLogin):
    """
    클라이언트에서 호출할 로그인 API.
    JSON 예:
      { "username": "test", "password": "1234" }
    """
    user = postgres.get_user(body.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="잘못된 ID 또는 비밀번호입니다.",
        )

    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="잘못된 ID 또는 비밀번호입니다.",
        )

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

    access_token = create_access_token({"sub": user["username"]})
    return Token(access_token=access_token)


@router.get("/me")
def read_me(current_user: Annotated[dict, Depends(get_current_user)]):
    """
    토큰/만료일 잘 동작하는지 확인용.
    """
    return {
        "username": current_user["username"],
        "expires_at": current_user["expires_at"],
        "is_active": current_user["is_active"],
    }
