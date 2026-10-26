"""Regras de autenticação: login, sessão opaca deslizante, logout, troca de senha, logs.

Fronteira de transação: cada função pública aqui é uma transação (faz o próprio commit).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.limiter import login_throttle, origem
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    password_needs_rehash,
    verify_password,
)
from app.models import AuthLog, AuthSession, User

settings = get_settings()


class AuthError(Exception):
    """Credenciais inválidas, usuário inativo ou bloqueio temporário."""

    def __init__(self, detail: str, status_code: int = 401, retry_after: int | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code
        self.retry_after = retry_after


def _now() -> datetime:
    return datetime.now(timezone.utc)


def log_event(
    db: Session,
    evento: str,
    user_id: int | None,
    ip: str | None,
    user_agent: str | None,
    *,
    target_user_id: int | None = None,
) -> None:
    """Registra quem (user_id) fez o quê (evento) em quem (target_user_id). Nunca guarda o texto digitado."""
    db.add(
        AuthLog(
            evento=evento,
            user_id=user_id,
            target_user_id=target_user_id,
            ip=ip,
            user_agent=(user_agent or "")[:300] or None,
        )
    )


def _too_many(wait: int) -> AuthError:
    return AuthError(f"Muitas tentativas para este e-mail. Tente novamente em {wait} s.", 429, retry_after=wait)


def _known_source(db: Session, user: User | None, ip: str | None) -> bool:
    """A conta já entrou com a senha certa a partir desta origem (IP, ou /64 do IPv6) há pouco tempo?

    Lê da trilha de autenticação, e não da memória do limitador, de propósito: sobrevive a um
    redeploy, e o atacante não tem como fabricá-la sem acertar a senha.
    """
    if user is None or not ip:
        return False
    since = _now() - timedelta(days=settings.LOGIN_TRUSTED_SOURCE_DAYS)
    ips = db.scalars(
        select(AuthLog.ip)
        .where(
            AuthLog.evento == "login_ok",
            AuthLog.user_id == user.id,
            AuthLog.created_at >= since,
            AuthLog.ip.is_not(None),
        )
        .distinct()
    ).all()
    target = origem(ip)
    return any(origem(x) == target for x in ips)


def login(
    db: Session, *, email: str, senha: str, client: str, ip: str | None, user_agent: str | None
) -> tuple[User, str, AuthSession]:
    """Valida e-mail/senha e abre uma sessão. Devolve (usuário, token_bruto, sessão).

    As travas vêm ANTES de conferir a senha: tentativa barrada não testa senha nenhuma, nem a certa.
    1. Por origem (e-mail + IP): sempre vale. Quem erra muito daqui espera — só daqui.
    2. Por conta (todas as origens): só vale para origem desconhecida da conta. Segura a força bruta
       espalhada por muitos IPs sem que um terceiro consiga trancar o dono, que entra de casa.
    """
    email = email.lower().strip()
    wait = login_throttle.source_wait(email, ip)
    if wait > 0:
        raise _too_many(wait)

    user = db.scalar(select(User).where(User.email == email))
    # a consulta à trilha só acontece com a conta sob ataque — o caminho normal não paga por ela
    wait = login_throttle.account_wait(email)
    if wait > 0 and not _known_source(db, user, ip):
        raise _too_many(wait)

    ok = verify_password(senha, user.password_hash if user else None)

    if not user or not ok or not user.is_active:
        login_throttle.register_failure(email, ip)
        log_event(db, "login_falha", user.id if user else None, ip, user_agent)
        db.commit()
        raise AuthError("E-mail ou senha incorretos.")

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(senha)

    raw, token_hash = generate_session_token()
    session = AuthSession(
        user_id=user.id,
        token_hash=token_hash,
        client=client,
        user_agent=(user_agent or "")[:300] or None,
        expires_at=_now() + timedelta(days=settings.SESSION_DAYS),
        last_used_at=_now(),
    )
    db.add(session)
    login_throttle.clear_source(email, ip)
    log_event(db, "login_ok", user.id, ip, user_agent)
    db.commit()
    db.refresh(session)
    return user, raw, session


def resolve_session(db: Session, raw_token: str) -> tuple[User, AuthSession, bool] | None:
    """Encontra a sessão pelo hash do token. Devolve (usuário, sessão, renovou?).

    A validade desliza: no máximo uma vez por hora, expires_at volta a ser "agora + SESSION_DAYS".
    Mas desliza até um TETO, contado do login (SESSION_ABSOLUTE_DAYS): sem ele, um token que vaze e
    seja usado uma vez por mês vale para sempre — e ninguém percebe, porque não existe tela que
    liste as sessões vivas. O custo do teto é um login por trimestre; o custo de não tê-lo é acesso
    permanente e silencioso ao faturamento e à agenda de clientes.
    """
    token_hash = hash_session_token(raw_token)
    row = db.execute(
        select(AuthSession, User)
        .join(User, User.id == AuthSession.user_id)
        .where(AuthSession.token_hash == token_hash)
    ).first()
    if row is None:
        return None
    session, user = row
    now = _now()
    if session.revoked_at is not None or session.expires_at <= now or not user.is_active:
        return None
    # o teto não desliza: é contado do login, não do último uso
    if now - session.created_at >= timedelta(days=settings.SESSION_ABSOLUTE_DAYS):
        return None

    touched = False
    if now - session.last_used_at > timedelta(minutes=settings.SESSION_TOUCH_MINUTES):
        session.last_used_at = now
        # a renovação também respeita o teto: perto do fim, a sessão passa a valer só até lá, e o
        # cliente já enxerga a data real em vez de uma promessa de 30 dias que não será cumprida
        limite = session.created_at + timedelta(days=settings.SESSION_ABSOLUTE_DAYS)
        session.expires_at = min(now + timedelta(days=settings.SESSION_DAYS), limite)
        db.commit()
        touched = True
    return user, session, touched


def logout(db: Session, session: AuthSession, ip: str | None, user_agent: str | None) -> None:
    session.revoked_at = _now()
    log_event(db, "logout", session.user_id, ip, user_agent)
    db.commit()


def revoke_all_sessions(
    db: Session, user_id: int, *, actor_id: int | None, ip: str | None, user_agent: str | None
) -> int:
    """'Sair de todos os aparelhos'. Devolve quantas sessões foram encerradas."""
    result = db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    log_event(db, "logout_todos", actor_id, ip, user_agent, target_user_id=user_id)
    db.commit()
    return result.rowcount or 0


def change_password(
    db: Session,
    user: User,
    current_session: AuthSession,
    *,
    senha_atual: str,
    senha_nova: str,
    ip: str | None,
    user_agent: str | None,
) -> None:
    """Troca a própria senha. Encerra as outras sessões do usuário (mantém a atual)."""
    if not verify_password(senha_atual, user.password_hash):
        raise AuthError("Senha atual incorreta.", 400)
    if senha_atual == senha_nova:
        raise AuthError("A nova senha deve ser diferente da atual.", 400)
    user.password_hash = hash_password(senha_nova)
    user.must_change_password = False
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.id != current_session.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=_now())
    )
    log_event(db, "senha_alterada", user.id, ip, user_agent, target_user_id=user.id)
    db.commit()


def purge_sessions(db: Session, *, older_than_days: int = 30) -> int:
    """Remove sessões revogadas ou expiradas há mais de N dias (limpeza periódica)."""
    from sqlalchemy import delete, or_

    limit = _now() - timedelta(days=older_than_days)
    result = db.execute(
        delete(AuthSession).where(or_(AuthSession.revoked_at < limit, AuthSession.expires_at < limit))
    )
    db.commit()
    return result.rowcount or 0
