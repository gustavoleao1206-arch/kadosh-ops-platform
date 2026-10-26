"""Toda rota da API declara quem pode chamá-la — e o teste cobra a declaração.

A matriz de `test_permissions.py` cobre sete rotas escolhidas a dedo. Este arquivo cobre TODAS, e
faz duas perguntas que a matriz não faz:

1. Alguma rota ficou sem autenticação por engano? (o clássico: endpoint novo, dependência esquecida)
2. Alguma rota que deveria ser do dono aceita o sócio?

E, principalmente, faz uma terceira pergunta ao FUTURO: quando alguém acrescentar uma rota e não
disser aqui quem pode chamá-la, o teste falha. Não é burocracia — é o único ponto do sistema em que
"esqueci de pensar em quem pode chamar isso" vira erro em vez de buraco silencioso.

Detalhe que torna estes testes possíveis sem montar corpo válido para 57 rotas: no FastAPI a
dependência de autorização roda ANTES da validação do corpo. `POST /users` com `{}` responde 403
para o sócio e 401 sem sessão — nunca 422. Há um teste abaixo que fixa esse comportamento, para o
dia em que uma atualização do framework inverter a ordem e esvaziar este arquivo em silêncio.
"""

import pytest

from app.main import app
from tests.conftest import ADMIN_EMAIL, ADMIN_PASS, STAFF_EMAIL, STAFF_PASS, login_android

# Rotas que existem para quem AINDA não tem sessão. Toda outra exige autenticação.
PUBLICAS = {
    ("POST", "/api/v1/auth/login"),
    ("GET", "/api/v1/health"),
}

# Rotas do DONO. A regra que as separa: mexer no catálogo, em usuários, em preço combinado, ou
# apagar registro do banco (o resto do sistema arquiva, não apaga).
SO_ADMIN = {
    ("GET", "/api/v1/users"),
    ("POST", "/api/v1/users"),
    ("PATCH", "/api/v1/users/{user_id}"),
    ("POST", "/api/v1/users/{user_id}/reset-password"),
    ("POST", "/api/v1/users/{user_id}/logout-all"),
    ("POST", "/api/v1/services"),
    ("PATCH", "/api/v1/services/{service_id}"),
    ("DELETE", "/api/v1/services/{service_id}"),
    # preço combinado é extensão do catálogo: ler é do sócio, escrever é do dono
    ("PUT", "/api/v1/clients/{client_id}/service-prices/{service_id}"),
    ("DELETE", "/api/v1/clients/{client_id}/service-prices/{service_id}"),
    ("DELETE", "/api/v1/clients/{client_id}"),
    ("DELETE", "/api/v1/vehicles/{vehicle_id}"),
    ("DELETE", "/api/v1/work-orders/{work_order_id}"),
}

# Rotas de operação: o sócio faz tudo o que o balcão precisa. Se a API abre e a tela não, o app
# vira um beco — e ele fica esperando o dono.
STAFF_TAMBEM = {
    ("GET", "/api/v1/auth/me"),
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/logout-all"),
    ("POST", "/api/v1/auth/change-password"),
    ("PATCH", "/api/v1/users/me"),
    ("GET", "/api/v1/clients"),
    ("POST", "/api/v1/clients"),
    ("GET", "/api/v1/clients/{client_id}"),
    ("PATCH", "/api/v1/clients/{client_id}"),
    ("POST", "/api/v1/clients/{client_id}/arquivar"),
    ("POST", "/api/v1/clients/{client_id}/desarquivar"),
    ("GET", "/api/v1/clients/{client_id}/vehicles"),
    ("GET", "/api/v1/clients/{client_id}/service-prices"),
    ("GET", "/api/v1/vehicles"),
    ("POST", "/api/v1/vehicles"),
    ("GET", "/api/v1/vehicles/{vehicle_id}"),
    ("PATCH", "/api/v1/vehicles/{vehicle_id}"),
    ("POST", "/api/v1/vehicles/{vehicle_id}/arquivar"),
    ("POST", "/api/v1/vehicles/{vehicle_id}/desarquivar"),
    ("POST", "/api/v1/vehicles/{vehicle_id}/transferir"),
    ("GET", "/api/v1/services"),
    ("GET", "/api/v1/services/{service_id}"),
    ("GET", "/api/v1/agenda"),
    ("GET", "/api/v1/patio"),
    ("GET", "/api/v1/work-orders"),
    ("POST", "/api/v1/work-orders"),
    ("POST", "/api/v1/work-orders/intake"),
    ("GET", "/api/v1/work-orders/{work_order_id}"),
    ("PATCH", "/api/v1/work-orders/{work_order_id}"),
    ("POST", "/api/v1/work-orders/{work_order_id}/transition"),
    ("POST", "/api/v1/work-orders/{work_order_id}/items"),
    ("DELETE", "/api/v1/work-orders/{work_order_id}/items/{item_id}"),
    ("POST", "/api/v1/work-orders/{work_order_id}/payments"),
    ("POST", "/api/v1/work-orders/{work_order_id}/payments/{payment_id}/estorno"),
    ("GET", "/api/v1/payment-methods"),
    ("GET", "/api/v1/caixa"),
    # financeiro da fase 8: o sócio cobra no balcão, então precisa ver
    ("GET", "/api/v1/extrato"),
    ("GET", "/api/v1/dashboard"),
    ("GET", "/api/v1/relatorios"),
    ("GET", "/api/v1/relatorios/mensal"),
    ("GET", "/api/v1/relatorios/clientes-sumidos"),
    ("GET", "/api/v1/search"),
}

DECLARADAS = PUBLICAS | SO_ADMIN | STAFF_TAMBEM


def rotas_do_app() -> set[tuple[str, str]]:
    """O que a aplicação REALMENTE publica, lido do próprio OpenAPI."""
    return {
        (metodo.upper(), caminho)
        for caminho, operacoes in app.openapi()["paths"].items()
        for metodo in operacoes
        if metodo.upper() in ("GET", "POST", "PATCH", "PUT", "DELETE")
    }


def caminho_de_teste(caminho: str) -> str:
    """Troca os parâmetros por um id inexistente. O que se mede é 401/403, que vem antes do 404."""
    for parametro in ("{user_id}", "{client_id}", "{vehicle_id}", "{service_id}", "{work_order_id}", "{item_id}", "{payment_id}"):
        caminho = caminho.replace(parametro, "999999")
    return caminho


def test_toda_rota_foi_declarada():
    """O teste que fala com o futuro: rota nova sem declaração para o build."""
    reais = rotas_do_app()
    nao_declaradas = reais - DECLARADAS
    assert not nao_declaradas, (
        "Rota(s) sem declaração de quem pode chamar:\n"
        + "\n".join(f'    ("{m}", "{p}"),' for m, p in sorted(nao_declaradas, key=lambda x: x[1]))
        + "\n\nAcrescente cada uma a PUBLICAS, SO_ADMIN ou STAFF_TAMBEM em tests/test_rotas_protegidas.py."
    )


def test_nenhuma_declaracao_sobrando():
    """O contrário: rota removida ou renomeada que ficou de fantasma nesta lista."""
    fantasmas = DECLARADAS - rotas_do_app()
    assert not fantasmas, (
        "Declaração para rota que não existe mais:\n"
        + "\n".join(f'    ("{m}", "{p}"),' for m, p in sorted(fantasmas, key=lambda x: x[1]))
    )


@pytest.mark.parametrize("metodo,caminho", sorted(DECLARADAS - PUBLICAS, key=lambda x: (x[1], x[0])))
def test_sem_sessao_responde_401(client, metodo, caminho):
    """Nenhuma rota de dado responde a quem não entrou.

    O corpo vai vazio de propósito: a autorização roda antes da validação, então 422 aqui seria
    sinal de que a checagem de sessão não está no caminho.
    """
    r = client.request(metodo, caminho_de_teste(caminho), json={})
    assert r.status_code == 401, f"{metodo} {caminho} respondeu {r.status_code} sem sessão"


@pytest.mark.parametrize("metodo,caminho", sorted(SO_ADMIN, key=lambda x: (x[1], x[0])))
def test_socio_nao_alcanca_rota_do_dono(client, staff, metodo, caminho):
    headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    r = client.request(metodo, caminho_de_teste(caminho), json={}, headers=headers)
    assert r.status_code == 403, f"{metodo} {caminho} respondeu {r.status_code} para o sócio"


@pytest.mark.parametrize("metodo,caminho", sorted(SO_ADMIN, key=lambda x: (x[1], x[0])))
def test_dono_passa_pela_autorizacao(client, admin, metodo, caminho):
    """O outro lado: a rota não pode ser inalcançável para o próprio dono.

    Aceita qualquer coisa MENOS 401/403 — os ids são inexistentes e os corpos vazios, então 404 e
    422 são respostas legítimas aqui. O que se mede é só que a porta abre para ele.
    """
    headers = login_android(client, ADMIN_EMAIL, ADMIN_PASS)
    r = client.request(metodo, caminho_de_teste(caminho), json={}, headers=headers)
    assert r.status_code not in (401, 403), f"{metodo} {caminho} barrou o dono com {r.status_code}"


def test_publicas_nao_exigem_sessao(client):
    """As duas portas de entrada continuam abertas — senão ninguém entra no sistema."""
    assert client.get("/api/v1/health").status_code == 200
    # login com credencial errada responde 401 do PRÓPRIO login, não da falta de sessão
    r = client.post("/api/v1/auth/login", json={"email": "ninguem@x.com", "senha": "errada", "client": "web"})
    assert r.status_code in (401, 422)


def test_autorizacao_roda_antes_da_validacao_do_corpo(client, staff):
    """Fixa a ordem de que os testes acima dependem.

    Se uma atualização do FastAPI inverter isso, `POST /users` com `{}` passaria a responder 422 e
    os testes de 401/403 acima viveriam de asserção sempre verdadeira — verdes e inúteis. Este
    teste falha alto nesse dia.
    """
    headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    assert client.post("/api/v1/users", json={}, headers=headers).status_code == 403
    assert client.post("/api/v1/users", json={}).status_code == 401
