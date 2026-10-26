"""Cookie de sessão do painel web (HttpOnly, SameSite=Strict, Secure em produção)."""

from fastapi import Response

from app.core.config import get_settings


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_DAYS * 24 * 3600,
        httponly=True,
        secure=settings.COOKIE_SECURE or settings.is_production,
        samesite="strict",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")
