from typing import Annotated, NoReturn

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def _raise_unauthorized() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    try:
        payload = decode_access_token(token)
    except ExpiredSignatureError, JWTError:
        _raise_unauthorized()

    subject = payload.get("sub")
    if subject is None:
        _raise_unauthorized()

    try:
        user_id = int(subject)
    except TypeError, ValueError:
        _raise_unauthorized()

    user = get_user_by_id(db, user_id)
    if user is None:
        _raise_unauthorized()

    return user
