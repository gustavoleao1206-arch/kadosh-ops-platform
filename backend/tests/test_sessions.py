"""Sessão opaca deslizante: expiração, renovação (no máximo 1×/hora), revogação, cookie reemitido."""

from datetime import timedelta

from sqlalchemy import select, update

from app.models import AuthSession
from app.services.auth import _now
from tests.conftest import ADMIN_EMAIL, ADMIN_PASS, STAFF_EMAIL, STAFF_PASS, login_android, login_web


def test_login_sets_30_day_expiry(client, admin):
    r = client.post("/api/v1/auth/login", json={"email": ADMIN_EMAIL, "senha": ADMIN_PASS, "client": "android"})
    from datetime import datetime

    exp = datetime.fromisoformat(r.json()["expires_at"])
    assert timedelta(days=29, hours=23) < exp - _now() < timedelta(days=30, minutes=1)


def test_expired_session_is_rejected(client, admin, db):
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    db.execute(update(AuthSession).values(expires_at=_now() - timedelta(seconds=1)))
    db.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_session_slides_at_most_once_per_hour(client, admin, db):
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    s = db.scalar(select(AuthSession))
    before = s.expires_at
    client.get("/api/v1/auth/me", headers=headers)
    db.refresh(s)
    assert s.expires_at == before  # usada há menos de uma hora: não renova

    s.last_used_at = _now() - timedelta(hours=2)
    s.expires_at = _now() + timedelta(days=1)
    db.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    db.refresh(s)
    assert s.expires_at > _now() + timedelta(days=29)
    assert _now() - s.last_used_at < timedelta(minutes=1)


def test_web_cookie_is_reissued_when_session_slides(client, admin, db):
    login_web(client, ADMIN_EMAIL, ADMIN_PASS)
    r = client.get("/api/v1/auth/me")
    assert "set-cookie" not in r.headers  # sem renovação, sem novo cookie
    s = db.scalar(select(AuthSession))
    s.last_used_at = _now() - timedelta(hours=2)
    db.commit()
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 200
    assert "kadosh_session=" in r.headers.get("set-cookie", "")
    assert "max-age=2592000" in r.headers["set-cookie"].lower()


def test_cross_site_request_does_not_slide_session(client, admin, db):
    login_web(client, ADMIN_EMAIL, ADMIN_PASS)
    s = db.scalar(select(AuthSession))
    s.last_used_at = _now() - timedelta(hours=2)
    before = s.expires_at
    db.commit()
    r = client.patch("/api/v1/users/me", json={"nome": "Forjado"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    db.refresh(s)
    assert s.expires_at == before


def test_inactive_user_with_live_session_is_rejected(client, staff, db):
    headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    staff.is_active = False
    db.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_deactivation_marks_sessions_revoked(client, admin_headers, staff, db):
    login_android(client, STAFF_EMAIL, STAFF_PASS)
    login_android(client, STAFF_EMAIL, STAFF_PASS)
    r = client.patch(f"/api/v1/users/{staff.id}", json={"is_active": False}, headers=admin_headers)
    assert r.status_code == 200
    sessions = db.scalars(select(AuthSession).where(AuthSession.user_id == staff.id)).all()
    assert len(sessions) == 2 and all(s.revoked_at is not None for s in sessions)
    # reativar NÃO ressuscita os tokens antigos
    client.patch(f"/api/v1/users/{staff.id}", json={"is_active": True}, headers=admin_headers)


def test_purge_sessions_removes_old_ones(client, admin, db):
    from app.services.auth import purge_sessions

    h1 = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    client.post("/api/v1/auth/logout", headers=h1)
    db.execute(
        update(AuthSession).where(AuthSession.revoked_at.is_not(None)).values(revoked_at=_now() - timedelta(days=40))
    )
    db.commit()
    assert purge_sessions(db) == 1
    assert db.scalar(select(AuthSession.id).where(AuthSession.revoked_at.is_(None))) is not None
