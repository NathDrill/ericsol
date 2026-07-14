from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User
from app.services.security import verify_password, create_access_token
from app.schemas.auth import Token, UserOut


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token(subject=str(user.id))
    return Token(access_token=token)


from fastapi import Header
from jose import jwt, JWTError
from app.core.config import settings


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        sub = payload.get("sub")
        user = db.query(User).get(int(sub))
        if not user:
            raise HTTPException(status_code=401, detail="Invalid token user")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
