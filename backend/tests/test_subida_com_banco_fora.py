"""O serviço tem de subir mesmo com o banco fora do ar.

Não é hipótese: o PRIMEIRO deploy no Render falhou exatamente assim. O serviço subiu antes de o
Postgres recém-criado aceitar conexão, o `bootstrap_admin` estourou `OperationalError`, o uvicorn
abortou com "Application startup failed" e o deploy foi reprovado — enquanto o banco ficava pronto
meio minuto depois. Não havia nada errado além da ordem.

Uma revisão de segurança chegou a descartar esse cenário como "só existe na janela do
primeiro deploy, com o dono olhando". Estava certa sobre a janela e errada sobre a
consequência: essa janela é o deploy inicial, e ela reprovou o deploy.

Criar o primeiro administrador é conveniência de primeira subida, não pré-requisito para servir.
"""

import logging

import pytest
from sqlalchemy.exc import OperationalError

from app import bootstrap
from app.bootstrap import bootstrap_admin_resiliente


def _erro_de_conexao() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


@pytest.fixture
def com_admin_no_ambiente(monkeypatch):
    """Só existe bootstrap quando as variáveis estão presentes — a janela do primeiro deploy."""
    ajustes = bootstrap.get_settings()
    monkeypatch.setattr(ajustes, "ADMIN_EMAIL", "dono@kadosh.com.br", raising=False)
    monkeypatch.setattr(ajustes, "ADMIN_PASSWORD", "senha-boot-12345", raising=False)
    return ajustes


def test_banco_fora_nao_derruba_a_subida(monkeypatch, com_admin_no_ambiente, caplog):
    """O caso que reprovou o deploy: agora loga e segue, em vez de matar o processo."""
    monkeypatch.setattr(bootstrap, "ESPERA_MAXIMA_S", 0.3)
    monkeypatch.setattr(bootstrap, "ESPERA_INICIAL_S", 0.1)

    tentativas = {"n": 0}

    def sempre_fora():
        tentativas["n"] += 1
        raise _erro_de_conexao()

    monkeypatch.setattr(bootstrap, "bootstrap_admin", sempre_fora)

    with caplog.at_level(logging.ERROR, logger="kadosh.bootstrap"):
        assert bootstrap_admin_resiliente() is False

    assert tentativas["n"] >= 2, "desistiu na primeira recusa — um soluço viraria indisponibilidade"
    assert any("Banco indisponível" in r.message for r in caplog.records), (
        "falhou em silêncio: sem log de erro, o dono não teria como saber por que não consegue entrar"
    )


def test_banco_que_demora_um_pouco_acaba_funcionando(monkeypatch, com_admin_no_ambiente):
    """É o caso real: o Postgres fica pronto alguns segundos depois do serviço."""
    monkeypatch.setattr(bootstrap, "ESPERA_MAXIMA_S", 5.0)
    monkeypatch.setattr(bootstrap, "ESPERA_INICIAL_S", 0.05)

    tentativas = {"n": 0}

    def fora_depois_dentro():
        tentativas["n"] += 1
        if tentativas["n"] < 3:
            raise _erro_de_conexao()
        return True

    monkeypatch.setattr(bootstrap, "bootstrap_admin", fora_depois_dentro)
    assert bootstrap_admin_resiliente() is True
    assert tentativas["n"] == 3


def test_sem_as_variaveis_nao_toca_no_banco(monkeypatch):
    """Regime normal: depois do primeiro login as variáveis saem, e a subida não abre conexão.

    É o que impede que uma manutenção do Render, com o banco reiniciando, custe segundos de espera
    a cada subida por um bootstrap que não tem nada para fazer.
    """
    ajustes = bootstrap.get_settings()
    monkeypatch.setattr(ajustes, "ADMIN_EMAIL", None, raising=False)
    monkeypatch.setattr(ajustes, "ADMIN_PASSWORD", None, raising=False)

    def nao_deveria_ser_chamado():
        raise AssertionError("abriu conexão sem ADMIN_EMAIL/ADMIN_PASSWORD definidos")

    monkeypatch.setattr(bootstrap, "bootstrap_admin", nao_deveria_ser_chamado)
    assert bootstrap_admin_resiliente() is False


def test_erro_de_programacao_continua_subindo(monkeypatch, com_admin_no_ambiente):
    """Só "não consegui falar com o banco" é tolerado.

    Engolir qualquer exceção transformaria um bug real num serviço que sobe calado e sem admin —
    e ninguém iria procurar no log de um processo que aparentemente subiu bem.
    """
    def bug():
        raise TypeError("erro de programação, não de conexão")

    monkeypatch.setattr(bootstrap, "bootstrap_admin", bug)
    with pytest.raises(TypeError):
        bootstrap_admin_resiliente()


def test_a_aplicacao_sobe_de_verdade_com_o_banco_fora(monkeypatch, com_admin_no_ambiente):
    """O teste de ponta: o lifespan completa e a API responde, mesmo sem banco.

    `/health` é quem denuncia — e é ele que o Render consulta. O diagnóstico vira "banco
    indisponível", não um processo que morreu sem explicar por quê.
    """
    from fastapi.testclient import TestClient

    from app.main import app

    monkeypatch.setattr(bootstrap, "ESPERA_MAXIMA_S", 0.2)
    monkeypatch.setattr(bootstrap, "ESPERA_INICIAL_S", 0.1)
    monkeypatch.setattr(bootstrap, "bootstrap_admin", lambda: (_ for _ in ()).throw(_erro_de_conexao()))

    with TestClient(app) as cliente:  # o `with` é o que executa o lifespan
        r = cliente.get("/api/v1/health")
        # o serviço está de pé e respondendo: era isso que faltava
        assert r.status_code in (200, 503)
