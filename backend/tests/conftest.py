"""Testes contra um Postgres real (kadosh_test). O schema é criado pelos modelos e limpo entre testes."""

import os

# Configura o ambiente ANTES de importar a aplicação (as settings são cacheadas).
# Valores explícitos (string vazia vence o backend/.env): os testes nunca dependem do .env do desenvolvedor.
os.environ["ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://kadosh:kadosh_dev@localhost:5433/kadosh_test"
)
os.environ["COOKIE_SECURE"] = "false"
os.environ["DOCS_ENABLED"] = "true"
os.environ["ADMIN_EMAIL"] = ""
os.environ["ADMIN_PASSWORD"] = ""
os.environ["LOGIN_RATE_PER_IP"] = "5/minute"
os.environ["LOGIN_FREE_ATTEMPTS_PER_SOURCE"] = "5"
os.environ["LOGIN_FREE_FAILURES_PER_ACCOUNT"] = "20"
os.environ["LOGIN_MAX_BLOCK_SECONDS"] = "900"
os.environ["LOGIN_TRUSTED_SOURCE_DAYS"] = "90"
os.environ["MAX_BODY_BYTES"] = "1000000"
os.environ["SESSION_DAYS"] = "30"
os.environ["SESSION_TOUCH_MINUTES"] = "60"
os.environ["TRUST_PROXY_HEADERS"] = "false"
os.environ.pop("RENDER", None)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.limiter import limiter, login_throttle  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402

assert engine.url.database and engine.url.database.endswith("_test"), "recusando drop_all fora de um banco *_test"

ADMIN_EMAIL, ADMIN_PASS = "admin@teste.com.br", "senha-admin-123"
STAFF_EMAIL, STAFF_PASS = "staff@teste.com.br", "senha-staff-123"

SAME_ORIGIN = {"Sec-Fetch-Site": "same-origin"}


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.drop_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS unaccent"))
    Base.metadata.create_all(engine)  # inclui a sequence work_order_numero_seq (está no metadata)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def _clean_tables():
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout = '5s'"))  # falha rápido se um teste vazar uma transação
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
        conn.execute(text("ALTER SEQUENCE work_order_numero_seq RESTART WITH 1"))
    limiter.reset()
    limiter.enabled = False  # o limite por IP só é ligado nos testes que o verificam (fixture rate_limit_on)
    login_throttle.reset()
    yield


@pytest.fixture
def rate_limit_on():
    limiter.enabled = True
    yield
    limiter.enabled = False


@pytest.fixture
def db():
    """Objetos carregados aqui NÃO refletem alterações feitas pela API — use db.refresh(obj) antes de afirmar."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def admin(db) -> User:
    user = User(nome="Admin Teste", email=ADMIN_EMAIL, password_hash=hash_password(ADMIN_PASS), role="admin")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def staff(db) -> User:
    user = User(nome="Staff Teste", email=STAFF_EMAIL, password_hash=hash_password(STAFF_PASS), role="staff")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login_android(client: TestClient, email: str, senha: str) -> dict:
    """Devolve cabeçalhos Authorization prontos para o app."""
    r = client.post("/api/v1/auth/login", json={"email": email, "senha": senha, "client": "android"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    assert token
    return {"Authorization": f"Bearer {token}"}


def login_web(client: TestClient, email: str, senha: str) -> None:
    """Login por cookie; o TestClient guarda o cookie sozinho."""
    r = client.post("/api/v1/auth/login", json={"email": email, "senha": senha, "client": "web"})
    assert r.status_code == 200, r.text
    assert r.json()["token"] is None
    assert "kadosh_session" in r.cookies


@pytest.fixture
def admin_headers(client, admin):
    return login_android(client, ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture
def staff_headers(client, staff):
    return login_android(client, STAFF_EMAIL, STAFF_PASS)


@pytest.fixture
def seed_cliente_veiculo(client, staff_headers):
    """Ruan + Civic — o par usado nos testes de OS."""
    c = client.post("/api/v1/clients", json={"nome": "Ruan", "telefone": "82 99911-0001"}, headers=staff_headers).json()
    v = client.post(
        "/api/v1/vehicles",
        json={"client_id": c["id"], "marca": "Honda", "modelo": "Civic EX", "cor": "Prata", "ano": 2001, "placa": "BRA2E19"},
        headers=staff_headers,
    ).json()
    return c, v


@pytest.fixture
def seed_servicos(client, admin_headers):
    """Dois serviços do catálogo: lavagem (60 min) e polimento (480 min)."""
    lavagem = client.post(
        "/api/v1/services",
        json={"nome": "Lavagem Simples", "valor_base_centavos": 12990, "duracao_estimada_min": 60},
        headers=admin_headers,
    ).json()
    polimento = client.post(
        "/api/v1/services",
        json={"nome": "Polimento Técnico", "valor_base_centavos": 99990, "duracao_estimada_min": 480},
        headers=admin_headers,
    ).json()
    return lavagem, polimento
