from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.core.security import MIN_PASSWORD_LENGTH
from app.schemas.base import InSchema, OutSchema


class LoginIn(InSchema):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=200)
    # web: recebe cookie HttpOnly. android: recebe o token no corpo e guarda no cofre do aparelho.
    client: Literal["web", "android"] = "web"

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserOut(OutSchema):
    id: int
    nome: str
    email: str
    role: str
    is_active: bool
    must_change_password: bool
    created_at: datetime


class LoginOut(OutSchema):
    user: UserOut
    # Só preenchido para client=android. No web o token viaja apenas no cookie.
    token: str | None = None
    expires_at: datetime


class ChangePasswordIn(InSchema):
    senha_atual: str = Field(min_length=1, max_length=200)
    senha_nova: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)
