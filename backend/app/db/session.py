"""Engine e sessão do SQLAlchemy (modo síncrono — as rotas são `def` e rodam no threadpool)."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # detecta conexões derrubadas pelo provedor antes de usá-las
    pool_size=5,
    max_overflow=5,
    pool_recycle=300,
    # A sessão do banco fala sempre UTC: o fuso do servidor (local, CI ou Render) deixa de influenciar
    # o que a API devolve. A conversão para America/Maceio é feita no app (services/periods.py).
    connect_args={"options": "-c timezone=UTC"},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
