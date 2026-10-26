"""Configuração por variáveis de ambiente (arquivo backend/.env em desenvolvimento, painel do Render em produção).

Nenhum segredo fica no código. Veja backend/.env.example.
Em produção, alguns valores são forçados (cookie Secure, docs desligadas) — "fechado por padrão".
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    # .env com caminho absoluto: funciona mesmo rodando `alembic` ou `python -m app.cli` de outra pasta.
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), env_file_encoding="utf-8", extra="ignore")

    ENV: Literal["development", "test", "production"] = "development"
    APP_NAME: str = "Kadosh Ops"
    APP_TIMEZONE: str = "America/Maceio"

    # Postgres local portátil: porta 5433 (a 5432 está ocupada por outro programa nesta máquina).
    DATABASE_URL: str = "postgresql+psycopg://kadosh:kadosh_dev@localhost:5433/kadosh_dev"

    # Sessão opaca no servidor (sem JWT). Validade deslizante.
    SESSION_DAYS: int = 30
    SESSION_TOUCH_MINUTES: int = 60  # renova expires_at no máximo uma vez por hora
    # Teto ABSOLUTO da sessão, contado do login. Sem ele a validade deslizante nunca acaba: um
    # token que vaze e seja usado uma vez por mês vale para sempre, e o dono não tem como perceber
    # (não há tela que liste sessões). 90 dias custa ao sócio um login por trimestre.
    SESSION_ABSOLUTE_DAYS: int = 90
    SESSION_COOKIE_NAME: str = "kadosh_session"
    COOKIE_SECURE: bool = False  # forçado para True em produção

    # Atrás do proxy do Render o IP real vem em X-Forwarded-For. None = igual a "é produção".
    TRUST_PROXY_HEADERS: bool | None = None

    # Limites de login (ver core/limiter.py)
    LOGIN_RATE_PER_IP: str = "5/minute"
    # Por origem, o par (e-mail, IP): a partir daí, atraso progressivo (1 s, 2 s, 4 s… até o teto).
    LOGIN_FREE_ATTEMPTS_PER_SOURCE: int = 5
    # Por conta, somando todas as origens; só vale para origem que a conta nunca usou para entrar.
    # PRECISA ficar acima do que uma origem sozinha acumula numa hora (17 falhas com 5 livres e teto
    # de 900 s), senão um único IP volta a conseguir trancar o dono fora de casa.
    LOGIN_FREE_FAILURES_PER_ACCOUNT: int = 20
    LOGIN_MAX_BLOCK_SECONDS: int = 900
    # "Origem conhecida": IP (ou /64 do IPv6) com login certo desta conta nos últimos N dias. Igual ao
    # teto da sessão: quem usa o app entra pelo menos uma vez nesse intervalo.
    LOGIN_TRUSTED_SOURCE_DAYS: int = 90

    # Bootstrap do primeiro admin (só usado quando a tabela users está vazia)
    ADMIN_EMAIL: str | None = None
    ADMIN_PASSWORD: str | None = None

    # Documentação da API (Swagger) — forçada para False em produção
    DOCS_ENABLED: bool = True

    # Limite do corpo das requisições (bytes), inclusive em transferência "chunked"
    MAX_BODY_BYTES: int = 1_000_000

    # Caminho do build do painel web (servido pelo próprio backend quando existir)
    WEB_DIST_DIR: str = Field(default="../web/dist")

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def _force_psycopg_driver(cls, v: str) -> str:
        """O Render entrega `postgres://…`; sem `+psycopg` o SQLAlchemy tentaria o psycopg2 (não instalado)."""
        for prefix in ("postgres://", "postgresql://"):
            if isinstance(v, str) and v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix):]
        return v

    @model_validator(mode="after")
    def _harden(self) -> "Settings":
        if os.environ.get("RENDER") and not self.is_production:
            raise ValueError("Rodando no Render sem ENV=production. Defina ENV=production nas variáveis do serviço.")
        if self.is_production:
            self.COOKIE_SECURE = True
            self.DOCS_ENABLED = False
        if self.TRUST_PROXY_HEADERS is None:
            self.TRUST_PROXY_HEADERS = self.is_production
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
