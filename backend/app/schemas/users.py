from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.core.security import MIN_PASSWORD_LENGTH
from app.schemas.base import InSchema


class UserCreateIn(InSchema):
    nome: str = Field(min_length=2, max_length=120)
    email: EmailStr
    senha: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)
    role: Literal["admin", "staff"] = "staff"

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserAdminUpdateIn(InSchema):
    """O que o admin pode alterar em outro usuário. Separado do perfil próprio de propósito."""

    nome: str | None = Field(default=None, min_length=2, max_length=120)
    role: Literal["admin", "staff"] | None = None
    is_active: bool | None = None


class UserResetPasswordIn(InSchema):
    senha_nova: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=200)


class UserSelfUpdateIn(InSchema):
    """O que qualquer usuário pode alterar em si mesmo: só o nome."""

    nome: str = Field(min_length=2, max_length=120)
