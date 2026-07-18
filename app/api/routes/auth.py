from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import create_user, get_user_by_email
from app.schemas.auth import Token, UserLogin
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/auth", tags=["Auth"])


def _raise_invalid_credentials() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
    )


def _authenticate_user(db: Session, email: str, password: str) -> User:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        _raise_invalid_credentials()

    return user


def _create_token_response(user: User) -> Token:
    access_token = create_access_token(str(user.id))
    return Token(access_token=access_token, token_type="bearer")


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(
    user_in: UserCreate,
    db: Annotated[Session, Depends(get_db)],
) -> UserRead:
    existing_user = get_user_by_email(db, user_in.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    hashed_password = hash_password(user_in.password)
    user = create_user(
        db,
        email=user_in.email,
        hashed_password=hashed_password,
    )
    return UserRead.model_validate(user)


@router.post("/login", response_model=Token, status_code=status.HTTP_200_OK)
def login_user(
    credentials: UserLogin,
    db: Annotated[Session, Depends(get_db)],
) -> Token:
    user = _authenticate_user(db, credentials.email, credentials.password)

    return _create_token_response(user)


@router.post("/token", response_model=Token, status_code=status.HTTP_200_OK)
def issue_token(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[Session, Depends(get_db)],
) -> Token:
    user = _authenticate_user(db, form_data.username, form_data.password)

    return _create_token_response(user)


@router.get("/me", response_model=UserRead, status_code=status.HTTP_200_OK)
def read_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserRead:
    return UserRead.model_validate(current_user)
