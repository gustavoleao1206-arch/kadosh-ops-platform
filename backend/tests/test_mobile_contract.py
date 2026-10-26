"""O contrato que o app Android consome.

O painel web quebra na cara do dono, que avisa. O app quebra no pátio, na mão do sócio, com o
cliente esperando — e só se descobre quando alguém liga reclamando. Estes testes percorrem a
jornada inteira do celular (`mobile/lib/`) e afirmam, campo a campo, o que o Dart lê: se um
`valor_centavos` sumir da resposta ou vier nulo, o `as int` do app explode em runtime e o teste
aqui é quem tem de gritar primeiro.

Tudo como **staff** — é o papel do sócio. Rota que só o admin abre não serve para o app.
"""

from uuid import uuid4

import pytest

from tests.conftest import STAFF_EMAIL, STAFF_PASS, login_android


def chave() -> str:
    return uuid4().hex


def exige(obj: dict, campos: dict, onde: str) -> None:
    """Afirma presença e tipo de cada campo que o Dart lê. `None` na tupla = pode vir nulo."""
    for campo, tipos in campos.items():
        assert campo in obj, f"{onde}: falta '{campo}' — o app lê esse campo"
        valor = obj[campo]
        if valor is None:
            assert type(None) in tipos, f"{onde}.{campo} veio nulo, e o app não trata nulo aqui"
        else:
            assert isinstance(valor, tipos), f"{onde}.{campo} é {type(valor).__name__}, esperado {tipos}"


ACAO = {"status": (str,), "label": (str,), "acao_label": (str,), "tone": (str,), "requer_motivo": (bool,), "principal": (bool,)}
ITEM = {"id": (int,), "descricao": (str,), "valor_centavos": (int,)}
OS = {
    "id": (int,),
    "numero": (int, type(None)),
    "status": (str,),
    "status_label": (str,),
    "status_tone": (str,),
    "valor_total_centavos": (int,),
    "pago_centavos": (int,),
    "saldo_centavos": (int,),
    "previsao_conclusao": (str, type(None)),
    "cliente": (dict,),
    "veiculo": (dict, type(None)),
    "itens": (list,),
    "acoes": (list,),
    # também na lista: o card do celular escreve sobre dinheiro e a casa proíbe decidir isso
    # pelo sinal do saldo
    "aceita_pagamento": (bool,),
}


def confere_os(os_json: dict, onde: str) -> None:
    exige(os_json, OS, onde)
    exige(os_json["cliente"], {"nome": (str,), "telefone": (str, type(None))}, f"{onde}.cliente")
    if os_json["veiculo"] is not None:
        exige(
            os_json["veiculo"],
            {"placa": (str, type(None)), "marca": (str, type(None)), "modelo": (str,)},
            f"{onde}.veiculo",
        )
    for item in os_json["itens"]:
        exige(item, ITEM, f"{onde}.itens[]")
    for acao in os_json["acoes"]:
        exige(acao, ACAO, f"{onde}.acoes[]")
    principais = [a for a in os_json["acoes"] if a["principal"]]
    assert len(principais) <= 1, f"{onde}: mais de uma ação principal — o app destacaria dois botões"


@pytest.fixture
def recebido(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    """Um carro no pátio, como a tela de recepção do app o cria."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    r = client.post(
        "/api/v1/work-orders/intake",
        json={
            "idempotency_key": chave(),
            "cliente": {"id": cliente["id"]},
            "veiculo": {"id": veiculo["id"]},
            "itens": [{"service_id": lavagem["id"]}],
        },
        headers=staff_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ------------------------------------------------------------------ login


def test_login_android_devolve_token_e_usuario(client, staff):
    r = client.post(
        "/api/v1/auth/login", json={"email": STAFF_EMAIL, "senha": STAFF_PASS, "client": "android"}
    )
    assert r.status_code == 200, r.text
    corpo = r.json()
    # api.dart lê exatamente estes dois; `user` sem nome deixaria a tela sem saudação
    assert isinstance(corpo["token"], str) and corpo["token"]
    assert isinstance(corpo["user"], dict) and "nome" in corpo["user"]


def test_me_e_logout_respondem_ao_bearer(client, staff):
    headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    # main.dart valida a sessão guardada com /auth/me antes de abrir o pátio
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.post("/api/v1/auth/logout", json={}, headers=headers).status_code in (200, 204)
    # sessão encerrada: o app cai na tela de login em vez de mostrar pátio vazio
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


# ------------------------------------------------------------------ pátio


def test_patio_traz_os_tres_grupos_que_o_app_desenha(client, staff_headers, recebido):
    r = client.get("/api/v1/patio", headers=staff_headers)
    assert r.status_code == 200, r.text
    corpo = r.json()
    for grupo in ("recebido", "em_execucao", "aguardando_retirada"):
        assert isinstance(corpo[grupo], list), f"patio.{grupo} sumiu — o app itera esses três"
    assert len(corpo["recebido"]) == 1
    confere_os(corpo["recebido"][0], "patio.recebido[0]")


def test_patio_traz_acoes_no_card(client, staff_headers, recebido):
    """Sem `acoes` na lista, o card do pátio fica sem botão e o sócio precisa abrir OS por OS."""
    card = client.get("/api/v1/patio", headers=staff_headers).json()["recebido"][0]
    assert card["acoes"], "OS recebida sem ações — o card do pátio ficaria sem próximo passo"
    principal = next((a for a in card["acoes"] if a["principal"]), None)
    assert principal is not None, "nenhuma ação principal: o app não saberia qual botão destacar"
    assert principal["status"] == "em_execucao"
    assert principal["acao_label"], "acao_label vazio — o botão sairia sem texto"


def test_transicao_pelo_card_usa_expected_status(client, staff_headers, recebido):
    r = client.post(
        f"/api/v1/work-orders/{recebido['id']}/transition",
        json={"to_status": "em_execucao", "expected_status": "recebido"},
        headers=staff_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "em_execucao"
    # o segundo toque (rede ruim, o primeiro chegou) tem de ser recusado, não repetido em silêncio
    repetido = client.post(
        f"/api/v1/work-orders/{recebido['id']}/transition",
        json={"to_status": "em_execucao", "expected_status": "recebido"},
        headers=staff_headers,
    )
    assert repetido.status_code == 409
    # e o app confere o estado antes de gritar erro: aqui ele descobre que já foi
    assert client.get(f"/api/v1/work-orders/{recebido['id']}", headers=staff_headers).json()["status"] == "em_execucao"


# ------------------------------------------------------------------ recepção


def test_busca_por_placa_traz_o_cliente_junto(client, staff_headers, seed_cliente_veiculo):
    """receber.dart preenche cliente e veículo com o primeiro resultado — precisa do `cliente` embutido."""
    r = client.get("/api/v1/search", params={"q": "BRA2E19"}, headers=staff_headers)
    assert r.status_code == 200, r.text
    veiculos = r.json()["veiculos"]
    assert veiculos, "placa cadastrada não encontrada pela busca"
    exige(veiculos[0], {"id": (int,), "modelo": (str,), "marca": (str, type(None)), "cliente": (dict,)}, "search.veiculos[0]")
    exige(veiculos[0]["cliente"], {"id": (int,), "nome": (str,)}, "search.veiculos[0].cliente")


def test_catalogo_de_servicos_para_os_chips(client, staff_headers, seed_servicos):
    r = client.get("/api/v1/services", params={"apenas_ativos": "true", "page_size": "30"}, headers=staff_headers)
    assert r.status_code == 200, r.text
    itens = r.json()["items"]
    assert itens
    for s in itens:
        exige(s, {"id": (int,), "nome": (str,), "valor_base_centavos": (int,)}, "services.items[]")


def test_recepcao_de_cliente_novo_com_o_corpo_do_app(client, staff_headers, seed_servicos):
    """O corpo que receber.dart monta quando a placa não existe: nome, modelo, placa e serviços."""
    lavagem, _ = seed_servicos
    r = client.post(
        "/api/v1/work-orders/intake",
        json={
            "idempotency_key": chave(),
            "cliente": {"nome": "Cliente do Balcão", "telefone": "82 98888-0002"},
            "veiculo": {"placa": "ABC1D23", "modelo": "Gol"},
            "itens": [{"service_id": lavagem["id"]}],
        },
        headers=staff_headers,
    )
    assert r.status_code == 201, r.text
    confere_os(r.json(), "intake")
    assert r.json()["status"] == "recebido"


def test_recepcao_sem_servico_e_aceita(client, staff_headers, seed_cliente_veiculo):
    """O carro chega antes de alguém decidir o serviço. Se isso fosse 422, o sócio ficava travado."""
    cliente, veiculo = seed_cliente_veiculo
    r = client.post(
        "/api/v1/work-orders/intake",
        json={
            "idempotency_key": chave(),
            "cliente": {"id": cliente["id"]},
            "veiculo": {"id": veiculo["id"]},
            "itens": [],
        },
        headers=staff_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["valor_total_centavos"] == 0
    # e sem serviço não existe previsão: o carro não pode nascer atrasado no card
    assert r.json()["previsao_conclusao"] is None


def test_toque_repetido_em_receber_nao_abre_duas_os(client, staff_headers, seed_cliente_veiculo):
    """A chave é gerada uma vez ao abrir a tela; o segundo toque devolve a mesma OS."""
    cliente, veiculo = seed_cliente_veiculo
    corpo = {
        "idempotency_key": chave(),
        "cliente": {"id": cliente["id"]},
        "veiculo": {"id": veiculo["id"]},
        "itens": [],
    }
    primeira = client.post("/api/v1/work-orders/intake", json=corpo, headers=staff_headers)
    segunda = client.post("/api/v1/work-orders/intake", json=corpo, headers=staff_headers)
    assert primeira.status_code == 201 and segunda.status_code == 201
    assert primeira.json()["id"] == segunda.json()["id"]


# ------------------------------------------------------------------ dinheiro


def test_formas_de_pagamento_vem_rotuladas(client, staff_headers):
    """os.dart desenha um chip por forma. Nenhum literal "Pix" mora no app."""
    r = client.get("/api/v1/payment-methods", headers=staff_headers)
    assert r.status_code == 200, r.text
    formas = r.json()
    assert formas
    for f in formas:
        exige(f, {"valor": (str,), "label": (str,)}, "payment-methods[]")


def test_detalhe_da_os_traz_o_que_a_tela_de_entrega_usa(client, staff_headers, recebido):
    r = client.get(f"/api/v1/work-orders/{recebido['id']}", headers=staff_headers)
    assert r.status_code == 200, r.text
    corpo = r.json()
    confere_os(corpo, "work-order")
    exige(corpo, {"pagamentos": (list,), "observacoes_entrada": (str, type(None))}, "work-order")
    assert corpo["aceita_pagamento"] is True, "OS recebida tem de aceitar pagamento — é a tela da entrega"


def test_pagamento_pelo_app_e_o_lancamento_que_volta(client, staff_headers, recebido):
    total = recebido["valor_total_centavos"]
    r = client.post(
        f"/api/v1/work-orders/{recebido['id']}/payments",
        json={"valor_centavos": total, "forma": "pix", "idempotency_key": chave()},
        headers=staff_headers,
    )
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["pago_centavos"] == total and corpo["saldo_centavos"] == 0
    pagamento = corpo["pagamentos"][0]
    exige(
        pagamento,
        {
            "id": (int,),
            "valor_centavos": (int,),
            "forma_label": (str,),
            "pago_em": (str,),
            "estornado_em": (str, type(None)),
        },
        "work-order.pagamentos[0]",
    )


def test_toque_repetido_em_lancar_nao_cobra_duas_vezes(client, staff_headers, recebido):
    """A chave só é trocada depois do sucesso — o retry cai na mesma e devolve o mesmo estado."""
    corpo = {"valor_centavos": recebido["valor_total_centavos"], "forma": "pix", "idempotency_key": chave()}
    url = f"/api/v1/work-orders/{recebido['id']}/payments"
    primeira = client.post(url, json=corpo, headers=staff_headers)
    segunda = client.post(url, json=corpo, headers=staff_headers)
    assert primeira.status_code == 201 and segunda.status_code == 201
    assert segunda.json()["pago_centavos"] == recebido["valor_total_centavos"]
    assert len(segunda.json()["pagamentos"]) == 1


def test_caixa_do_dia_para_o_socio(client, staff_headers, recebido):
    """caixa.dart lê o JSON cru, sem modelo — cada campo aqui é um `as int`/`as String` no Dart."""
    client.post(
        f"/api/v1/work-orders/{recebido['id']}/payments",
        json={"valor_centavos": 5000, "forma": "dinheiro", "idempotency_key": chave()},
        headers=staff_headers,
    )
    r = client.get("/api/v1/caixa", headers=staff_headers)
    assert r.status_code == 200, r.text
    corpo = r.json()
    exige(
        corpo,
        {
            "recebido_centavos": (int,),
            "por_forma": (list,),
            "lancamentos": (list,),
            "a_receber_centavos": (int,),
            "a_receber": (list,),
        },
        "caixa",
    )
    assert corpo["recebido_centavos"] == 5000
    for f in corpo["por_forma"]:
        exige(f, {"forma_label": (str,), "total_centavos": (int,)}, "caixa.por_forma[]")
    for lanc in corpo["lancamentos"]:
        exige(
            lanc,
            {
                "cliente_nome": (str,),
                "forma_label": (str,),
                "valor_centavos": (int,),
                "pago_em": (str,),
                "estornado_em": (str, type(None)),
            },
            "caixa.lancamentos[]",
        )
    for d in corpo["a_receber"]:
        exige(d, {"cliente_nome": (str,), "status_label": (str,), "saldo_centavos": (int,)}, "caixa.a_receber[]")


# ------------------------------------------------------------------ o que o sócio NÃO pode


def test_socio_alcanca_tudo_que_o_app_chama(client, staff_headers, recebido):
    """Uma rota de admin no caminho do app viraria 403 na mão do sócio, no meio do expediente."""
    for rota in ("/api/v1/patio", "/api/v1/caixa", "/api/v1/payment-methods", "/api/v1/services", "/api/v1/auth/me"):
        assert client.get(rota, headers=staff_headers).status_code == 200, f"{rota} recusou o sócio"
    assert client.get(f"/api/v1/work-orders/{recebido['id']}", headers=staff_headers).status_code == 200
    assert client.get("/api/v1/search", params={"q": "BRA"}, headers=staff_headers).status_code == 200


# ------------------------------------------------------------------ o que o app passou a fazer


def test_socio_lanca_servico_na_os_pelo_app(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    """O serviço é combinado no pátio, com o carro já dentro.

    Sem esta rota aberta ao sócio, a tela da OS seria um beco: total zero, nada a fazer, e o
    backend ainda recusa receber pagamento numa OS sem serviço.
    """
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders/intake",
        json={
            "idempotency_key": chave(),
            "cliente": {"id": cliente["id"]},
            "veiculo": {"id": veiculo["id"]},
            "itens": [],
        },
        headers=staff_headers,
    ).json()
    assert wo["valor_total_centavos"] == 0

    corpo = [{"service_id": lavagem["id"], "idempotency_key": chave()}]
    r = client.post(f"/api/v1/work-orders/{wo['id']}/items", json=corpo, headers=staff_headers)
    assert r.status_code == 200, r.text
    confere_os(r.json(), "items")
    assert r.json()["valor_total_centavos"] == 12990

    # e o toque repetido do mesmo lançamento não dobra o total
    de_novo = client.post(f"/api/v1/work-orders/{wo['id']}/items", json=corpo, headers=staff_headers)
    assert de_novo.json()["valor_total_centavos"] == 12990


def test_app_encontra_o_agendamento_do_carro(client, staff_headers, seed_cliente_veiculo):
    """A recepção pergunta se o carro tem hora marcada antes de abrir OS nova.

    Sem esta consulta o app abria uma segunda OS, a agendada ficava pendurada e depois contava
    como não comparecimento — com o carro no pátio.
    """
    cliente, veiculo = seed_cliente_veiculo
    agendada = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "status": "agendado",
            "scheduled_at": "2099-01-10T09:00:00",
        },
        headers=staff_headers,
    )
    assert agendada.status_code == 201, agendada.text

    r = client.get(
        "/api/v1/work-orders",
        params=[("vehicle_id", veiculo["id"]), ("status", "agendado"), ("status", "confirmado")],
        headers=staff_headers,
    )
    assert r.status_code == 200, r.text
    itens = r.json()["items"]
    assert [i["id"] for i in itens] == [agendada.json()["id"]]
    exige(itens[0], {"id": (int,), "scheduled_at": (str, type(None))}, "work-orders.items[0]")


def test_receber_agendamento_nao_abre_os_nova(client, staff_headers, seed_cliente_veiculo):
    cliente, veiculo = seed_cliente_veiculo
    agendada = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "status": "agendado",
            "scheduled_at": "2099-01-10T09:00:00",
        },
        headers=staff_headers,
    ).json()

    r = client.post(
        "/api/v1/work-orders/intake",
        json={"idempotency_key": chave(), "work_order_id": agendada["id"], "itens": []},
        headers=staff_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["id"] == agendada["id"]
    assert r.json()["status"] == "recebido"


def test_socio_estorna_o_proprio_lancamento(client, staff_headers, recebido):
    """`pode_estornar` vem calculado no payload; o app só desenha o botão quando ele é `true`."""
    pago = client.post(
        f"/api/v1/work-orders/{recebido['id']}/payments",
        json={"valor_centavos": 5000, "forma": "dinheiro", "idempotency_key": chave()},
        headers=staff_headers,
    ).json()
    lancamento = pago["pagamentos"][0]
    assert lancamento["pode_estornar"] is True

    r = client.post(
        f"/api/v1/work-orders/{recebido['id']}/payments/{lancamento['id']}/estorno",
        json={"motivo": "Lancei o valor errado"},
        headers=staff_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["pago_centavos"] == 0
    assert r.json()["pagamentos"][0]["estornado_em"] is not None


def test_desfazer_a_entrega_e_recusado_ao_socio(client, staff_headers, recebido):
    """O app deixou de oferecer "Desfazer" aqui — este teste guarda o motivo.

    Reabrir OS concluída é do administrador e ainda pede motivo. O botão aparecia sempre e, na
    última ação do dia, era garantido falhar com o carro já entregue.
    """
    wo_id = recebido["id"]
    for destino in ("em_execucao", "aguardando_retirada", "concluido"):
        client.post(
            f"/api/v1/work-orders/{wo_id}/transition", json={"to_status": destino}, headers=staff_headers
        )
    detalhe = client.get(f"/api/v1/work-orders/{wo_id}", headers=staff_headers).json()
    assert detalhe["status"] == "concluido"
    # a API já não oferece a volta ao sócio: o app não pode inventar um botão que ela não deu
    assert [a["status"] for a in detalhe["acoes"]] == []

    r = client.post(
        f"/api/v1/work-orders/{wo_id}/transition",
        json={"to_status": "aguardando_retirada"},
        headers=staff_headers,
    )
    assert r.status_code == 403


def test_senha_temporaria_bloqueia_o_app_ate_a_troca(client, db, staff):
    """O caminho documentado para criar o usuário do sócio liga `must_change_password`.

    Sem a tela de troca no app, o login passava, o pátio abria e tudo respondia 403 para sempre.
    """
    from app.core.security import hash_password

    staff.must_change_password = True
    staff.password_hash = hash_password("temporaria-123")
    db.commit()

    r = client.post(
        "/api/v1/auth/login",
        json={"email": STAFF_EMAIL, "senha": "temporaria-123", "client": "android"},
    )
    assert r.status_code == 200, r.text
    # o app lê esta flag para abrir a tela de troca em vez do pátio
    assert r.json()["user"]["must_change_password"] is True
    headers = {"Authorization": f"Bearer {r.json()['token']}"}
    assert client.get("/api/v1/patio", headers=headers).status_code == 403

    troca = client.post(
        "/api/v1/auth/change-password",
        json={"senha_atual": "temporaria-123", "senha_nova": "senha-nova-do-socio"},
        headers=headers,
    )
    assert troca.status_code == 200, troca.text
    assert client.get("/api/v1/patio", headers=headers).status_code == 200
