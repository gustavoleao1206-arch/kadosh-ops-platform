from fastapi import APIRouter, HTTPException, Request, Response

from app.core.config import get_settings
from app.core.cookies import clear_session_cookie, set_session_cookie
from app.core.deps import DB, Auth, ReqInfo
from app.core.limiter import limiter
from app.schemas.auth import ChangePasswordIn, LoginIn, LoginOut, UserOut
from app.schemas.common import Message
from app.services import auth as auth_service

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["autenticação"])


def _raise(e: auth_service.AuthError) -> None:
    headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
    raise HTTPException(e.status_code, e.detail, headers=headers)


@router.post("/login", response_model=LoginOut)
@limiter.limit(settings.LOGIN_RATE_PER_IP)
def login(request: Request, response: Response, body: LoginIn, db: DB, info: ReqInfo) -> LoginOut:
    """Login unificado. Web recebe cookie HttpOnly; Android recebe o token no corpo."""
    try:
        user, raw, session = auth_service.login(
            db, email=body.email, senha=body.senha, client=body.client, ip=info.ip, user_agent=info.user_agent
        )
    except auth_service.AuthError as e:
        _raise(e)

    if body.client == "web":
        set_session_cookie(response, raw)
        token = None
    else:
        token = raw
    return LoginOut(user=UserOut.model_validate(user), token=token, expires_at=session.expires_at)


@router.get("/me", response_model=UserOut)
def me(auth: Auth) -> UserOut:
    return UserOut.model_validate(auth.user)


@router.post("/logout", response_model=Message)
def logout(response: Response, auth: Auth, db: DB, info: ReqInfo) -> Message:
    auth_service.logout(db, auth.session, info.ip, info.user_agent)
    if auth.via_cookie:
        clear_session_cookie(response)
    return Message(detail="Sessão encerrada.")


@router.post("/logout-all", response_model=Message)
def logout_all(response: Response, auth: Auth, db: DB, info: ReqInfo) -> Message:
    """Sair de todos os aparelhos (celular perdido, por exemplo)."""
    n = auth_service.revoke_all_sessions(
        db, auth.user.id, actor_id=auth.user.id, ip=info.ip, user_agent=info.user_agent
    )
    if auth.via_cookie:
        clear_session_cookie(response)
    return Message(detail=f"{n} sessão(ões) encerrada(s).")


@router.post("/change-password", response_model=Message)
def change_password(body: ChangePasswordIn, auth: Auth, db: DB, info: ReqInfo) -> Message:
    try:
        auth_service.change_password(
            db,
            auth.user,
            auth.session,
            senha_atual=body.senha_atual,
            senha_nova=body.senha_nova,
            ip=info.ip,
            user_agent=info.user_agent,
        )
    except auth_service.AuthError as e:
        _raise(e)
    return Message(detail="Senha alterada. As outras sessões foram encerradas.")
