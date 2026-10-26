"""O bootstrap não pode falhar em silêncio.

Aconteceu em produção, no dia do deploy: o dono trocou ADMIN_EMAIL e ADMIN_PASSWORD no painel do
Render esperando que isso mudasse o login. Não muda — o bootstrap só cria o PRIMEIRO administrador,
e a tabela já não estava vazia. Resultado: a conta nova nunca foi criada, a tela respondeu
"e-mail ou senha inválidos", e nada em lugar nenhum explicou o porquê.

Essa é a pior resposta possível, porque parece problema de senha e é problema de cadastro. Os
testes abaixo garantem que os dois enganos silenciosos passem a gritar no log — que é onde quem
está com o deploy na mão vai procurar.
"""

import logging

import pytest
from sqlalchemy import select

from app import bootstrap
from app.bootstrap import bootstrap_admin
from app.core.security import MIN_PASSWORD_LENGTH
from app.models import User


@pytest.fixture
def ambiente(monkeypatch):
    """Deixa ADMIN_EMAIL/ADMIN_PASSWORD como o dono os deixaria no painel do Render."""

    def definir(email: str | None, senha: str | None):
        ajustes = bootstrap.get_settings()
        monkeypatch.setattr(ajustes, "ADMIN_EMAIL", email, raising=False)
        monkeypatch.setattr(ajustes, "ADMIN_PASSWORD", senha, raising=False)
        return ajustes

    return definir


def test_senha_curta_e_erro_com_o_numero_na_mensagem(ambiente, caplog, db):
    """"muito curta" não ajuda ninguém: a mensagem tem de dizer quanto tem e quanto precisa."""
    ambiente("dono@kadosh.com.br", "123456")  # 6 caracteres
    with caplog.at_level(logging.ERROR, logger="kadosh.bootstrap"):
        assert bootstrap_admin() is False

    mensagem = " ".join(r.getMessage() for r in caplog.records)
    assert "6 caracteres" in mensagem
    assert str(MIN_PASSWORD_LENGTH) in mensagem
    assert "NENHUM administrador foi criado" in mensagem
    # e nada foi criado de fato
    assert db.scalars(select(User)).all() == []


def test_trocar_admin_email_com_a_tabela_cheia_avisa_e_ensina_o_caminho(ambiente, caplog, db, admin):
    """O engano exato que aconteceu: trocar ADMIN_EMAIL não cria conta nova."""
    ambiente("novo-admin@example.com", "senha-longa-o-bastante")
    with caplog.at_level(logging.WARNING, logger="kadosh.bootstrap"):
        assert bootstrap_admin() is False

    mensagem = " ".join(r.getMessage() for r in caplog.records)
    assert "novo-admin@example.com" in mensagem
    assert "NÃO está cadastrado" in mensagem
    # o aviso tem de dizer o que FAZER, não só o que deu errado
    assert "create-user" in mensagem
    # e continua sem criar nada: a regra do "só o primeiro admin" permanece
    assert len(db.scalars(select(User)).all()) == 1


def test_admin_email_que_ja_existe_nao_gera_ruido(ambiente, caplog, db, admin):
    """Regime normal (as variáveis ficaram lá depois do primeiro login): silêncio.

    Avisar a cada subida sobre uma situação correta treinaria o dono a ignorar o log — e aí o aviso
    de verdade passa despercebido junto.
    """
    ambiente(admin.email, "senha-longa-o-bastante")
    with caplog.at_level(logging.WARNING, logger="kadosh.bootstrap"):
        assert bootstrap_admin() is False
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_tabela_vazia_cria_e_avisa_para_remover_as_variaveis(ambiente, caplog, db):
    """O caminho feliz continua funcionando — e lembrando de tirar a senha do ambiente."""
    ambiente("dono@kadosh.com.br", "senha-longa-o-bastante")
    with caplog.at_level(logging.WARNING, logger="kadosh.bootstrap"):
        assert bootstrap_admin() is True

    criado = db.scalar(select(User).where(User.email == "dono@kadosh.com.br"))
    assert criado is not None
    assert criado.role == "admin"
    # nasce exigindo troca: a senha veio do ambiente, não da cabeça do dono
    assert criado.must_change_password is True

    mensagem = " ".join(r.getMessage() for r in caplog.records)
    assert "REMOVA" in mensagem
