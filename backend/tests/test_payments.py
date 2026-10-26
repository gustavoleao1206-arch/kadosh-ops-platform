"""Dinheiro: lançamento, estorno, saldo e o fechamento do dia.

Aqui também fica fixado em teste o vocabulário financeiro que a ARQUITETURA.md promete:
Recebido (por pago_em), Faturado (OS concluída por conclusao) e A receber (saldo do pátio +
concluídas).
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.services.periods import day_bounds, today_local


def _os_no_patio(client, headers, *, itens=None, placa="NEW1A11", cliente=None, chave="p-base-0001"):
    """Uma OS já recebida (é a partir daí que entra dinheiro)."""
    body = {
        "cliente": cliente or {"nome": "Chegou Agora", "telefone": "82 96666-1111"},
        "veiculo": {"modelo": "Gol", "placa": placa},
        "itens": itens or [],
        "idempotency_key": chave,
    }
    r = client.post("/api/v1/work-orders/intake", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _pagar(client, headers, wo_id, **over):
    # a chave é obrigatória na API (é dinheiro); quando o teste não se importa com ela, gera uma
    body = {"valor_centavos": 10000, "forma": "pix", "idempotency_key": uuid4().hex, **over}
    return client.post(f"/api/v1/work-orders/{wo_id}/payments", json=body, headers=headers)


def _estornar(client, headers, wo_id, pay_id, motivo="digitei errado"):
    return client.post(
        f"/api/v1/work-orders/{wo_id}/payments/{pay_id}/estorno", json={"motivo": motivo}, headers=headers
    )


# ------------------------------------------------------------------ lançamento


def test_pagamento_parcial_e_quitacao(client, staff_headers, seed_servicos):
    """Sinal na entrada, resto na retirada — o saldo acompanha os dois."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    assert wo["valor_total_centavos"] == 12990
    assert wo["pago_centavos"] == 0 and wo["saldo_centavos"] == 12990

    r = _pagar(client, staff_headers, wo["id"], valor_centavos=5000, forma="pix")
    assert r.status_code == 201, r.text
    depois = r.json()
    assert depois["pago_centavos"] == 5000 and depois["saldo_centavos"] == 7990
    assert [p["forma_label"] for p in depois["pagamentos"]] == ["Pix"]
    assert "Pagamento recebido: R$ 50,00 em Pix" in [e["descricao"] for e in depois["eventos"]]

    quitada = _pagar(client, staff_headers, wo["id"], valor_centavos=7990, forma="dinheiro").json()
    assert quitada["saldo_centavos"] == 0 and quitada["pago_centavos"] == 12990


def test_pagamento_acima_do_saldo_recusa_com_o_valor_na_frase(client, staff_headers, seed_servicos):
    """Não existe troco no sistema: o que se registra é o que fica no caixa."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    r = _pagar(client, staff_headers, wo["id"], valor_centavos=20000)
    assert r.status_code == 409
    assert "R$ 129,90" in r.json()["detail"]
    # e o dedo escorregado de R$ 1.500 no lugar de R$ 150 morre aqui
    assert _pagar(client, staff_headers, wo["id"], valor_centavos=150000).status_code == 409


def test_os_sem_servico_pede_para_lancar_antes(client, staff_headers):
    wo = _os_no_patio(client, staff_headers)
    r = _pagar(client, staff_headers, wo["id"], valor_centavos=5000)
    assert r.status_code == 409 and "serviços" in r.json()["detail"]


def test_os_ja_paga_recusa_novo_lancamento(client, staff_headers, seed_servicos):
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    _pagar(client, staff_headers, wo["id"], valor_centavos=12990)
    r = _pagar(client, staff_headers, wo["id"], valor_centavos=100)
    assert r.status_code == 409 and "já está paga" in r.json()["detail"]


def test_dinheiro_so_entra_a_partir_da_recepcao(client, staff_headers, seed_cliente_veiculo, seed_servicos):
    """Orçamento e agendamento não recebem: o sinal é lançado na recepção com a data real."""
    c, v = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    orc = client.post(
        "/api/v1/work-orders",
        json={"client_id": c["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=staff_headers,
    ).json()
    r = _pagar(client, staff_headers, orc["id"], valor_centavos=5000)
    assert r.status_code == 409 and "recepção" in r.json()["detail"]

    agendada = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": c["id"],
            "vehicle_id": v["id"],
            "scheduled_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "itens": [{"service_id": lavagem["id"]}],
        },
        headers=staff_headers,
    ).json()
    assert _pagar(client, staff_headers, agendada["id"], valor_centavos=5000).status_code == 409


def test_os_encerrada_nao_recebe_pagamento(client, staff_headers, seed_servicos):
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    client.post(
        f"/api/v1/work-orders/{wo['id']}/transition",
        json={"to_status": "cancelado", "motivo": "cliente desistiu"},
        headers=staff_headers,
    )
    r = _pagar(client, staff_headers, wo["id"], valor_centavos=5000)
    assert r.status_code == 409 and "encerrada" in r.json()["detail"]


def test_concluida_ainda_recebe_pagamento(client, staff_headers, seed_servicos):
    """O clique de concluir é o mesmo de entregar, e o cliente paga na retirada."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    concluida = client.post(
        f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "concluido"}, headers=staff_headers
    ).json()
    assert concluida["saldo_centavos"] == 12990 and concluida["aceita_pagamento"] is True
    assert _pagar(client, staff_headers, wo["id"], valor_centavos=12990).status_code == 201


def test_entregar_com_saldo_em_aberto_e_permitido(client, staff_headers, seed_servicos):
    """Cliente pagou a menos e levou o carro: o sistema informa, não impede."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    _pagar(client, staff_headers, wo["id"], valor_centavos=5000)
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "concluido"}, headers=staff_headers
    )
    assert r.status_code == 200 and r.json()["saldo_centavos"] == 7990


def test_pagamento_e_idempotente(client, staff_headers, seed_servicos):
    """Toque repetido com sinal ruim devolve o mesmo estado, não lança duas vezes."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    a = _pagar(client, staff_headers, wo["id"], valor_centavos=5000, idempotency_key="pg-000001")
    b = _pagar(client, staff_headers, wo["id"], valor_centavos=5000, idempotency_key="pg-000001")
    assert a.status_code == 201 and b.status_code == 201
    assert b.json()["pago_centavos"] == 5000 and len(b.json()["pagamentos"]) == 1


def test_chave_repetida_em_outra_os_avisa(client, staff_headers, seed_servicos):
    lavagem, _ = seed_servicos
    a = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}], chave="k-aaaaaa")
    b = _os_no_patio(client, staff_headers, placa="OUT2B22", cliente={"nome": "Outro", "telefone": "82 95555-2222"}, itens=[{"service_id": lavagem["id"]}], chave="k-bbbbbb")
    _pagar(client, staff_headers, a["id"], valor_centavos=5000, idempotency_key="pg-xxxxxx")
    r = _pagar(client, staff_headers, b["id"], valor_centavos=5000, idempotency_key="pg-xxxxxx")
    assert r.status_code == 409 and "outra OS" in r.json()["detail"]


def test_pago_em_retroativo_entra_no_dia_do_dinheiro(client, staff_headers, seed_servicos):
    """Pix que caiu ontem e só foi lançado hoje pertence ao caixa de ontem."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    ontem = today_local() - timedelta(days=1)
    r = _pagar(client, staff_headers, wo["id"], valor_centavos=5000, pago_em=f"{ontem.isoformat()}T21:00:00")
    assert r.status_code == 201, r.text
    hoje = client.get("/api/v1/caixa", headers=staff_headers).json()
    assert hoje["recebido_centavos"] == 0
    de_ontem = client.get("/api/v1/caixa", params={"dia": ontem.isoformat()}, headers=staff_headers).json()
    assert de_ontem["recebido_centavos"] == 5000


def test_pago_em_no_futuro_recusa(client, staff_headers, seed_servicos):
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    amanha = today_local() + timedelta(days=1)
    r = _pagar(client, staff_headers, wo["id"], valor_centavos=5000, pago_em=f"{amanha.isoformat()}T10:00:00")
    assert r.status_code == 422


@pytest.mark.parametrize("corpo", [{"valor_centavos": 0, "forma": "pix"}, {"valor_centavos": 100, "forma": "boleto"}])
def test_corpo_invalido_recusa(client, staff_headers, seed_servicos, corpo):
    """Valor zero e forma inexistente.

    A chave vai preenchida de propósito: sem ela o 422 viria da chave ausente, e este teste
    passaria a guardar coisa nenhuma — que foi o que aconteceu quando a chave virou obrigatória.
    """
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    corpo = {**corpo, "idempotency_key": uuid4().hex}
    assert client.post(f"/api/v1/work-orders/{wo['id']}/payments", json=corpo, headers=staff_headers).status_code == 422


def test_chave_ausente_tambem_recusa(client, staff_headers, seed_servicos):
    """A obrigatoriedade em si, agora com teste próprio — não mais de carona no teste acima."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    corpo = {"valor_centavos": 100, "forma": "pix"}
    assert client.post(f"/api/v1/work-orders/{wo['id']}/payments", json=corpo, headers=staff_headers).status_code == 422


# ------------------------------------------------------------------ estorno


def test_estorno_desfaz_sem_apagar(client, staff_headers, seed_servicos):
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    pago = _pagar(client, staff_headers, wo["id"], valor_centavos=5000).json()
    pay_id = pago["pagamentos"][0]["id"]

    r = _estornar(client, staff_headers, wo["id"], pay_id, motivo="lancei R$ 50 onde era R$ 5")
    assert r.status_code == 200, r.text
    depois = r.json()
    assert depois["pago_centavos"] == 0 and depois["saldo_centavos"] == 12990
    # o lançamento continua visível, marcado
    assert len(depois["pagamentos"]) == 1 and depois["pagamentos"][0]["estornado_em"] is not None
    assert "Pagamento estornado: R$ 50,00 em Pix — lancei R$ 50 onde era R$ 5" in [
        e["descricao"] for e in depois["eventos"]
    ]
    # segunda vez não passa
    assert _estornar(client, staff_headers, wo["id"], pay_id).status_code == 409


def test_estorno_de_terceiro_e_so_do_admin(client, admin_headers, staff_headers, seed_servicos):
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, admin_headers, itens=[{"service_id": lavagem["id"]}])
    do_admin = _pagar(client, admin_headers, wo["id"], valor_centavos=5000).json()
    pay_id = do_admin["pagamentos"][0]["id"]
    assert do_admin["pagamentos"][0]["pode_estornar"] is True  # para o próprio admin

    detalhe_staff = client.get(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).json()
    assert detalhe_staff["pagamentos"][0]["pode_estornar"] is False
    assert _estornar(client, staff_headers, wo["id"], pay_id).status_code == 403
    assert _estornar(client, admin_headers, wo["id"], pay_id).status_code == 200


def test_estorno_exige_motivo_e_pagamento_da_propria_os(client, staff_headers, seed_servicos):
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    pago = _pagar(client, staff_headers, wo["id"], valor_centavos=5000).json()
    pay_id = pago["pagamentos"][0]["id"]
    assert client.post(
        f"/api/v1/work-orders/{wo['id']}/payments/{pay_id}/estorno", json={"motivo": ""}, headers=staff_headers
    ).status_code == 422
    outra = _os_no_patio(client, staff_headers, placa="OUT3C33", cliente={"nome": "Terceiro", "telefone": "82 94444-3333"}, chave="k-outra01")
    assert _estornar(client, staff_headers, outra["id"], pay_id).status_code == 404


def test_os_cancelada_ainda_permite_estornar(client, staff_headers, seed_servicos):
    """Cliente desistiu depois de pagar o sinal: o dono decide devolver, e o botão tem de existir."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    pago = _pagar(client, staff_headers, wo["id"], valor_centavos=5000).json()
    pay_id = pago["pagamentos"][0]["id"]
    client.post(
        f"/api/v1/work-orders/{wo['id']}/transition",
        json={"to_status": "cancelado", "motivo": "cliente desistiu"},
        headers=staff_headers,
    )
    assert _estornar(client, staff_headers, wo["id"], pay_id, motivo="devolvido em dinheiro").status_code == 200


# ------------------------------------------------------------------ o total nunca cai abaixo do pago


def test_total_nao_cai_abaixo_do_que_foi_pago(client, staff_headers, seed_servicos):
    """Desconto e remoção de serviço passam pelo mesmo piso — o saldo nunca fica negativo."""
    lavagem, polimento = seed_servicos
    wo = _os_no_patio(
        client, staff_headers, itens=[{"service_id": lavagem["id"]}, {"service_id": polimento["id"]}]
    )
    _pagar(client, staff_headers, wo["id"], valor_centavos=100000)

    r = client.patch(f"/api/v1/work-orders/{wo['id']}", json={"desconto_centavos": 50000}, headers=staff_headers)
    assert r.status_code == 409 and "R$ 1.000,00" in r.json()["detail"]

    item_id = next(i["id"] for i in wo["itens"] if i["descricao"] == "Polimento Técnico")
    r = client.delete(f"/api/v1/work-orders/{wo['id']}/items/{item_id}", headers=staff_headers)
    assert r.status_code == 409

    # estornado o pagamento, os dois caminhos voltam a funcionar
    pay_id = client.get(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).json()["pagamentos"][0]["id"]
    _estornar(client, staff_headers, wo["id"], pay_id, motivo="cliente pediu para tirar o polimento")
    assert client.delete(f"/api/v1/work-orders/{wo['id']}/items/{item_id}", headers=staff_headers).status_code == 200


# ------------------------------------------------------------------ caixa do dia


def test_caixa_soma_por_forma_e_ignora_estornado(client, staff_headers, seed_servicos):
    lavagem, polimento = seed_servicos
    a = _os_no_patio(client, staff_headers, itens=[{"service_id": polimento["id"]}], chave="c-aaaaaa")
    b = _os_no_patio(
        client,
        staff_headers,
        placa="CXA2B22",
        cliente={"nome": "Cliente B", "telefone": "82 93333-2222"},
        itens=[{"service_id": lavagem["id"]}],
        chave="c-bbbbbb",
    )
    _pagar(client, staff_headers, a["id"], valor_centavos=30000, forma="pix")
    _pagar(client, staff_headers, a["id"], valor_centavos=20000, forma="dinheiro")
    errado = _pagar(client, staff_headers, b["id"], valor_centavos=12990, forma="credito").json()
    _estornar(client, staff_headers, b["id"], errado["pagamentos"][0]["id"], motivo="cartão recusado")

    caixa = client.get("/api/v1/caixa", headers=staff_headers).json()
    assert caixa["recebido_centavos"] == 50000
    assert {f["forma"]: f["total_centavos"] for f in caixa["por_forma"]} == {"dinheiro": 20000, "pix": 30000}
    # o estornado continua na lista, marcado — não some da conferência
    estornados = [x for x in caixa["lancamentos"] if x["estornado_em"]]
    assert len(estornados) == 1 and estornados[0]["estorno_motivo"] == "cartão recusado"
    assert all(x["forma_label"] for x in caixa["lancamentos"])


def test_caixa_lista_quem_ainda_deve(client, staff_headers, seed_servicos):
    """A receber = saldo das OS no pátio ou concluídas (ARQUITETURA.md)."""
    lavagem, polimento = seed_servicos
    no_patio = _os_no_patio(client, staff_headers, itens=[{"service_id": polimento["id"]}], chave="r-aaaaaa")
    _pagar(client, staff_headers, no_patio["id"], valor_centavos=40000)

    concluida = _os_no_patio(
        client,
        staff_headers,
        placa="REC2B22",
        cliente={"nome": "Deve Ainda", "telefone": "82 92222-1111"},
        itens=[{"service_id": lavagem["id"]}],
        chave="r-bbbbbb",
    )
    client.post(
        f"/api/v1/work-orders/{concluida['id']}/transition", json={"to_status": "concluido"}, headers=staff_headers
    )

    caixa = client.get("/api/v1/caixa", headers=staff_headers).json()
    assert caixa["a_receber_centavos"] == (99990 - 40000) + 12990
    devendo = {d["work_order_id"]: d for d in caixa["a_receber"]}
    assert devendo[no_patio["id"]]["saldo_centavos"] == 59990
    assert devendo[concluida["id"]]["saldo_centavos"] == 12990
    assert devendo[concluida["id"]]["status_label"] == "Concluído"


def test_caixa_ignora_orcamento_e_os_quitada(client, staff_headers, seed_servicos):
    lavagem, _ = seed_servicos
    quitada = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}], chave="q-aaaaaa")
    _pagar(client, staff_headers, quitada["id"], valor_centavos=12990)
    caixa = client.get("/api/v1/caixa", headers=staff_headers).json()
    assert caixa["a_receber"] == [] and caixa["a_receber_centavos"] == 0
    assert caixa["recebido_centavos"] == 12990


def test_caixa_e_do_dia_da_loja(client, staff_headers, seed_servicos):
    """O corte do dia é America/Maceio, não UTC — 22h de Maceió ainda é hoje."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    hoje = today_local()
    _pagar(client, staff_headers, wo["id"], valor_centavos=5000, pago_em=f"{hoje.isoformat()}T22:30:00")
    caixa = client.get("/api/v1/caixa", params={"dia": hoje.isoformat()}, headers=staff_headers).json()
    assert caixa["recebido_centavos"] == 5000
    ini, fim = day_bounds(hoje)
    lancado = datetime.fromisoformat(caixa["lancamentos"][0]["pago_em"])
    assert ini <= lancado < fim


def test_formas_de_pagamento_vem_da_api(client, staff_headers):
    formas = client.get("/api/v1/payment-methods", headers=staff_headers).json()
    assert [f["valor"] for f in formas][:2] == ["dinheiro", "pix"]
    assert {f["valor"]: f["label"] for f in formas}["debito"] == "Cartão de débito"


def test_caixa_e_liberado_para_o_socio(client, staff_headers, seed_servicos):
    """Decisão do dono: staff vê o caixa do dia. Só estorno de terceiros é do administrador."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    _pagar(client, staff_headers, wo["id"], valor_centavos=5000)
    r = client.get("/api/v1/caixa", headers=staff_headers)
    assert r.status_code == 200 and r.json()["recebido_centavos"] == 5000


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/v1/work-orders/1/payments", {"valor_centavos": 100, "forma": "pix"}),
        ("post", "/api/v1/work-orders/1/payments/1/estorno", {"motivo": "x"}),
        ("get", "/api/v1/caixa", None),
        ("get", "/api/v1/payment-methods", None),
    ],
)
def test_requer_login(client, method, path, body):
    r = getattr(client, method)(path, json=body) if body else getattr(client, method)(path)
    assert r.status_code == 401


# ------------------------------------------------------------------ correções da revisão


def test_retry_que_quita_a_os_e_idempotente_mesmo_na_corrida(client, staff_headers, seed_servicos, monkeypatch):
    """Duas requisições gêmeas quitando a OS: a segunda devolve o mesmo estado, não 409.

    A primeira leitura da chave acontece antes de qualquer lock — numa corrida ela não enxerga o
    pagamento gêmeo, que ainda não comitou. Aqui essa cegueira é simulada, e quem tem de segurar é
    a segunda leitura, feita sob o lock da OS. Sem ela a validação de saldo dispararia primeiro e o
    retry viraria "Esta OS já está paga": o UNIQUE nunca chega a ser tocado.
    """
    from app.services import payments as pay_svc

    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    total = wo["valor_total_centavos"]
    assert _pagar(client, staff_headers, wo["id"], valor_centavos=total, idempotency_key="R1-000001").status_code == 201

    real = pay_svc._mesma_chave
    chamadas = {"n": 0}

    def cego_na_primeira(db, chave):
        chamadas["n"] += 1
        return None if chamadas["n"] == 1 else real(db, chave)

    monkeypatch.setattr(pay_svc, "_mesma_chave", cego_na_primeira)

    r = _pagar(client, staff_headers, wo["id"], valor_centavos=total, idempotency_key="R1-000001")
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert corpo["pago_centavos"] == total and len(corpo["pagamentos"]) == 1


def test_retry_cego_em_outra_os_ainda_avisa(client, staff_headers, seed_servicos, monkeypatch):
    """A checagem sob o lock não pode aceitar chave de outra OS calada."""
    from app.services import payments as pay_svc

    lavagem, _ = seed_servicos
    a = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}], chave="rc-aaaaa")
    b = _os_no_patio(
        client,
        staff_headers,
        placa="RTY3C33",
        cliente={"nome": "Outro Dono", "telefone": "82 91111-2222"},
        itens=[{"service_id": lavagem["id"]}],
        chave="rc-bbbbb",
    )
    _pagar(client, staff_headers, a["id"], valor_centavos=5000, idempotency_key="R2-000001")

    real = pay_svc._mesma_chave
    chamadas = {"n": 0}

    def cego_na_primeira(db, chave):
        chamadas["n"] += 1
        return None if chamadas["n"] == 1 else real(db, chave)

    monkeypatch.setattr(pay_svc, "_mesma_chave", cego_na_primeira)
    r = _pagar(client, staff_headers, b["id"], valor_centavos=5000, idempotency_key="R2-000001")
    assert r.status_code == 409 and "outra OS" in r.json()["detail"]


def test_os_cancelada_com_sinal_nao_tem_nada_a_receber(client, staff_headers, seed_servicos):
    """Quem está com dinheiro alheio é a loja, não o cliente — e o caixa concorda."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    _pagar(client, staff_headers, wo["id"], valor_centavos=5000)
    client.post(
        f"/api/v1/work-orders/{wo['id']}/transition",
        json={"to_status": "cancelado", "motivo": "cliente desistiu"},
        headers=staff_headers,
    )
    detalhe = client.get(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).json()
    assert detalhe["aceita_pagamento"] is False and detalhe["pago_centavos"] == 5000
    # o painel usa aceita_pagamento para não escrever "A receber" aqui; o caixa já ignorava a OS
    caixa = client.get("/api/v1/caixa", headers=staff_headers).json()
    assert wo["id"] not in [d["work_order_id"] for d in caixa["a_receber"]]
    assert caixa["a_receber_centavos"] == 0


def test_pagamento_sem_chave_de_idempotencia_recusa(client, staff_headers, seed_servicos):
    """É dinheiro: sem chave, um cliente distraído duplicaria pagamento em silêncio."""
    lavagem, _ = seed_servicos
    wo = _os_no_patio(client, staff_headers, itens=[{"service_id": lavagem["id"]}])
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/payments",
        json={"valor_centavos": 5000, "forma": "pix"},
        headers=staff_headers,
    )
    assert r.status_code == 422
