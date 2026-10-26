from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.core.deps import DB, AdminUser, Auth, ReqInfo
from app.models import User
from app.schemas.auth import UserOut
from app.schemas.common import Message, Page
from app.schemas.users import UserAdminUpdateIn, UserCreateIn, UserResetPasswordIn, UserSelfUpdateIn
from app.services import auth as auth_service
from app.services import users as users_service

router = APIRouter(prefix="/users", tags=["usuários"])


def _get_or_404(db, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "Usuário não encontrado.")
    return user


@router.get("", response_model=Page[UserOut])
def list_users(
    db: DB,
    _admin: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> Page[UserOut]:
    total = db.scalar(select(func.count()).select_from(User)) or 0
    rows = db.scalars(select(User).order_by(User.nome).offset((page - 1) * page_size).limit(page_size)).all()
    return Page(items=[UserOut.model_validate(u) for u in rows], total=total, page=page, page_size=page_size)


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreateIn, db: DB, admin: AdminUser, info: ReqInfo) -> UserOut:
    try:
        user = users_service.create_user(
            db,
            nome=body.nome,
            email=body.email,
            senha=body.senha,
            role=body.role,
            actor=admin,
            ip=info.ip,
            user_agent=info.user_agent,
        )
    except users_service.UserRuleError as e:
        raise HTTPException(e.status_code, e.detail) from e
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
def update_me(body: UserSelfUpdateIn, auth: Auth, db: DB) -> UserOut:
    auth.user.nome = body.nome
    db.commit()
    db.refresh(auth.user)
    return UserOut.model_validate(auth.user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserAdminUpdateIn, db: DB, admin: AdminUser, info: ReqInfo) -> UserOut:
    target = _get_or_404(db, user_id)
    try:
        user = users_service.update_user(
            db,
            target,
            actor=admin,
            nome=body.nome,
            role=body.role,
            is_active=body.is_active,
            ip=info.ip,
            user_agent=info.user_agent,
        )
    except users_service.UserRuleError as e:
        raise HTTPException(e.status_code, e.detail) from e
    return UserOut.model_validate(user)


@router.post("/{user_id}/reset-password", response_model=Message)
def reset_password(user_id: int, body: UserResetPasswordIn, db: DB, admin: AdminUser, info: ReqInfo) -> Message:
    target = _get_or_404(db, user_id)
    users_service.reset_password(
        db, target, actor=admin, senha_nova=body.senha_nova, ip=info.ip, user_agent=info.user_agent
    )
    return Message(detail="Senha temporária definida. O usuário deverá trocá-la no próximo login.")


@router.post("/{user_id}/logout-all", response_model=Message)
def logout_all_for_user(user_id: int, db: DB, admin: AdminUser, info: ReqInfo) -> Message:
    target = _get_or_404(db, user_id)
    n = auth_service.revoke_all_sessions(db, target.id, actor_id=admin.id, ip=info.ip, user_agent=info.user_agent)
    return Message(detail=f"{n} sessão(ões) de {target.nome} encerrada(s).")
