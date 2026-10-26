"""Dependências das rotas: banco, usuário atual (cookie ou Bearer), papéis, anti-CSRF.

Regras:
- Rotas que usam o banco são `def` (rodam no threadpool); nunca `async def` com Session síncrona.
- Fronteira de transação: uma função PÚBLICA de service = uma transação (ela comita). Helpers internos
  (recalcular total, registrar evento, adicionar item) nunca comitam — só `flush()`.
"""

from collections.abc import Generator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.cookies import set_session_cookie
from app.core.limiter import client_ip
from app.db.session import get_db as _get_db
from app.models import AuthSession, User
from app.services import auth as auth_service

settings = get_settings()

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# Com must_change_password=true, só estas rotas ficam liberadas.
PATHS_ALLOWED_BEFORE_PASSWORD_CHANGE = {
    "/api/v1/auth/me",
    "/api/v1/auth/change-password",
    "/api/v1/auth/logout",
    "/api/v1/auth/logout-all",
}


def get_db() -> Generator[Session, None, None]:
    yield from _get_db()


DB = Annotated[Session, Depends(get_db)]


@dataclass
class RequestInfo:
    ip: str | None
    user_agent: str | None


def get_request_info(request: Request) -> RequestInfo:
    return RequestInfo(ip=client_ip(request), user_agent=request.headers.get("user-agent"))


ReqInfo = Annotated[RequestInfo, Depends(get_request_info)]


@dataclass
class CurrentAuth:
    user: User
    session: AuthSession
    via_cookie: bool


def _extract_token(request: Request) -> tuple[str | None, bool]:
    """Bearer tem prioridade (app Android); senão, cookie (painel web)."""
    authz = request.headers.get("authorization")
    if authz and authz.lower().startswith("bearer "):
        return authz[7:].strip() or None, False
    cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if cookie:
        return cookie, True
    return None, False


def _csrf_check(request: Request) -> None:
    """Para autenticação por cookie em métodos que alteram dados: só mesma origem.

    Navegadores modernos sempre enviam Sec-Fetch-Site; quando não vier, exigimos Origin igual ao host.
    Requisições com Bearer (app) não passam por aqui — não há CSRF sem cookie.
    Em desenvolvimento, o Vite usa `server.proxy` para a API ficar na mesma origem (não usar CORS).
    """
    if request.method in SAFE_METHODS:
        return
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site in ("same-origin", "none"):
        return
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if sec_fetch_site is None and origin and host and origin.split("://", 1)[-1] == host:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Requisição bloqueada (origem não permitida).")


def get_current_auth(request: Request, response: Response, db: DB) -> CurrentAuth:
    raw, via_cookie = _extract_token(request)
    if not raw:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Sessão ausente. Faça login.", headers={"WWW-Authenticate": "Bearer"}
        )
    if via_cookie:
        _csrf_check(request)  # antes de tocar no banco: requisição forjada não renova a sessão

    resolved = auth_service.resolve_session(db, raw)
    if resolved is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sessão inválida ou expirada. Faça login novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user, session, touched = resolved
    if via_cookie and touched:
        set_session_cookie(response, raw)  # a validade deslizante vale também para o navegador
    if user.must_change_password and request.url.path not in PATHS_ALLOWED_BEFORE_PASSWORD_CHANGE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Troque sua senha antes de continuar.")
    return CurrentAuth(user=user, session=session, via_cookie=via_cookie)


Auth = Annotated[CurrentAuth, Depends(get_current_auth)]


def get_current_user(auth: Auth) -> User:
    return auth.user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(auth: Auth, db: DB, info: ReqInfo) -> User:
    if not auth.user.is_admin:
        auth_service.log_event(db, "acesso_negado", auth.user.id, info.ip, info.user_agent)
        db.commit()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Apenas administradores podem fazer isso.")
    return auth.user


AdminUser = Annotated[User, Depends(require_admin)]
