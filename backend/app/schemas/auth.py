from pydantic import BaseModel, EmailStr


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    is_superuser: bool

    class Config:
        from_attributes = True

