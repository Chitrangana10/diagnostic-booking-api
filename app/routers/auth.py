from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.limiter import limiter
from app.models import User
from app.schemas.auth import LoginRequest, SignupRequest, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
def signup(request: Request, data: SignupRequest, db: Session = Depends(get_db)):
    exists = db.scalar(select(User).where(User.email == data.email))
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")

    user = User(
        name=data.name, email=data.email, password_hash=hash_password(data.password)
    )
    db.add(user)
    db.commit()
    return user


@router.post("/login", response_model=TokenOut)
@limiter.limit("5/minute")
def login(request: Request, data: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email))
    # same message for unknown email and wrong password, so we don't leak which emails exist
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    return TokenOut(access_token=create_access_token(user.id))
