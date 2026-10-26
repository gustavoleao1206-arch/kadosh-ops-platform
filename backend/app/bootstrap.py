"""Cria o primeiro administrador na primeira subida — e só então.

Regra: só roda quando a tabela users está VAZIA; nunca atualiza um usuário existente (um redeploy
não pode devolver a senha antiga). Depois do primeiro login, remova ADMIN_EMAIL/ADMIN_PASSWORD do Render.
"""

import logging
import time

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.config import get_settings
from app.core.security import MIN_PASSWORD_LENGTH, hash_password
from app.db.session import SessionLocal
from app.models import User

log = logging.getLogger("kadosh.bootstrap")

# Quanto esperar o banco na subida, ao todo. Trinta segundos cobrem o caso real que motivou isto
# (Postgres recém-criado ainda aceitando conexões) e o soluço de um reinício por manutenção, sem
# transformar um banco de fato fora num serviço que demora minutos para admitir que não vai subir.
ESPERA_MAXIMA_S = 30.0
ESPERA_INICIAL_S = 1.0


def bootstrap_admin() -> bool:
    settings = get_settings()
    if not settings.ADMIN_EMAIL or not settings.ADMIN_PASSWORD:
        return False
    if len(settings.ADMIN_PASSWORD) < MIN_PASSWORD_LENGTH:
        log.error(
            "ADMIN_PASSWORD tem %s caracteres; o mínimo é %s. NENHUM administrador foi criado — "
            "corrija a variável no ambiente e reinicie o serviço.",
            len(settings.ADMIN_PASSWORD),
            MIN_PASSWORD_LENGTH,
        )
        return False

    with SessionLocal() as db:
        total = db.scalar(select(func.count()).select_from(User)) or 0
        if total > 0:
            # Já existe gente cadastrada: o bootstrap não mexe em nada, de propósito — um redeploy
            # não pode devolver senha antiga nem ressuscitar acesso removido.
            #
            # Mas há um jeito silencioso de se enganar aqui, e ele já aconteceu em produção: trocar
            # ADMIN_EMAIL no painel do Render esperando que isso "mude o login". Não muda. A conta
            # antiga continua sendo a única que existe, a nova nunca é criada, e a tela de login
            # responde "e-mail ou senha inválidos" sem dizer por quê — que é a pior resposta
            # possível, porque parece problema de senha e não de cadastro.
            alvo = settings.ADMIN_EMAIL.lower()
            if not db.scalar(select(User.id).where(User.email == alvo).limit(1)):
                log.warning(
                    "ADMIN_EMAIL aponta para %s, que NÃO está cadastrado — e já existem %s "
                    "usuário(s). O bootstrap só cria o primeiro administrador, então esta conta "
                    "não será criada e o login com ela vai falhar. Para criar de fato:  "
                    "python -m app.cli create-user \"Nome\" %s admin",
                    alvo,
                    total,
                    alvo,
                )
            return False
        db.add(
            User(
                nome="Administrador",
                email=settings.ADMIN_EMAIL.lower(),
                password_hash=hash_password(settings.ADMIN_PASSWORD),
                role="admin",
                is_active=True,
                must_change_password=True,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()  # outro processo subiu ao mesmo tempo e já criou
            return False
    log.warning(
        "Primeiro administrador criado (%s). Troque a senha no primeiro login e REMOVA "
        "ADMIN_EMAIL/ADMIN_PASSWORD do ambiente.",
        settings.ADMIN_EMAIL,
    )
    return True


def bootstrap_admin_resiliente() -> bool:
    """`bootstrap_admin`, mas sem poder derrubar a subida do serviço.

    Motivo concreto, não hipótese: no primeiro deploy o serviço subiu antes de o Postgres
    recém-criado aceitar conexão. O `OperationalError` subiu pelo lifespan, o uvicorn abortou com
    "Application startup failed" e o Render reprovou o deploy — enquanto o banco ficava pronto meio
    minuto depois. Não havia nada errado além da ordem.

    Espera com recuo exponencial e, se ainda assim não conectar, LOGA e devolve False. Criar o
    primeiro administrador é conveniência de primeira subida, não pré-requisito para servir: a
    tabela continua vazia e a próxima subida tenta de novo. Quem denuncia banco fora é o /health.

    Só `OperationalError` é tolerado — é o erro de "não consegui falar com o banco". Erro de
    programação continua subindo, porque esse a gente quer ver alto e na hora.
    """
    if not get_settings().ADMIN_EMAIL or not get_settings().ADMIN_PASSWORD:
        return False  # nada a fazer: nem toca no banco

    espera = ESPERA_INICIAL_S
    gasto = 0.0
    while True:
        try:
            return bootstrap_admin()
        except OperationalError as e:
            if gasto + espera > ESPERA_MAXIMA_S:
                log.error(
                    "Banco indisponível na subida (%.0fs de tentativas): %s. O serviço vai subir "
                    "assim mesmo; o primeiro administrador será criado na próxima reinicialização. "
                    "Confira /api/v1/health.",
                    gasto,
                    e.orig or e,
                )
                return False
            log.warning("Banco ainda não aceita conexão; nova tentativa em %.0fs.", espera)
            time.sleep(espera)
            gasto += espera
            espera *= 2
