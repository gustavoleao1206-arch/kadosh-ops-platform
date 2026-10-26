"""Relatórios do período.

Aqui o "Faturado" do vocabulário da ARQUITETURA.md ganha código e teste pela primeira vez — até a
fase 5 ele era só documentação. O que estes testes protegem é a diferença entre ele e o "Recebido":
duas contas que divergem de propósito e que ninguém pode somar.
"""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text

from app.services.periods import month_bounds, today_local


def _os_concluida(client, headers, *, servico, placa, chave, valor=None, desconto=0, cliente=None):
    """Uma OS que passou pelo pátio e foi entregue — é isso que conta como faturado."""
    corpo = {
        "cliente": cliente or {"nome": "Cliente Relatorio", "telefone": "82 97777-0001"},
        "veiculo": {"modelo": "Gol", "placa": placa},
        "itens": [{"service_id": servico["id"], **({"valor_centavos": valor} if valor else {})}],
        "idempotency_key": chave,
    }
    wo = client.post("/api/v1/work-orders/intake", json=corpo, headers=headers).json()
    if desconto:
        client.patch(f"/api/v1/work-orders/{wo['id']}", json={"desconto_centavos": desconto}, headers=headers)
    r = client.post(
        f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "concluido"}, headers=headers
    )
    assert r.status_code == 200, r.text
    return r.json()


def _pagar(client, headers, wo_id, valor, forma="pix", pago_em=None):
    corpo = {"valor_centavos": valor, "forma": forma, "idempotency_key": uuid4().hex}
    if pago_em:
        corpo["pago_em"] = pago_em
    r = client.post(f"/api/v1/work-orders/{wo_id}/payments", json=corpo, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _mover(db, tabela, campo, ident, quando):
    """Empurra uma data para trás no banco — o jeito de montar "mês passado" sem esperar um mês."""
    db.execute(text(f"UPDATE {tabela} SET {campo} = :q WHERE id = :i"), {"q": quando, "i": ident})
    db.commit()


def test_faturado_e_recebido_divergem_de_proposito(client, staff_headers, seed_servicos, db):
    """Serviço entregue num mês e pago no outro: as duas contas discordam, e as duas estão certas."""
    lavagem, _ = seed_servicos
    wo = _os_concluida(client, staff_headers, servico=lavagem, placa="REL1A11", chave="rel-00001")

    # o pagamento aconteceu no mês passado (sinal), a entrega foi neste mês
    mes_passado = (today_local().replace(day=1) - timedelta(days=5)).isoformat()
    _pagar(client, staff_headers, wo["id"], 12990, pago_em=f"{mes_passado}T10:00:00")

    atual = client.get("/api/v1/relatorios", headers=staff_headers).json()
    assert atual["totais"]["faturado_centavos"] == 12990  # entregue agora
    assert atual["totais"]["recebido_centavos"] == 0  # o dinheiro entrou antes
    # e o faturado avisa que ele já está pago, mesmo tendo sido pago noutro mês
    assert atual["totais"]["faturado_recebido_centavos"] == 12990
    assert atual["totais"]["faturado_a_receber_centavos"] == 0

    anterior = client.get("/api/v1/relatorios", params={"periodo": "mes_passado"}, headers=staff_headers).json()
    assert anterior["totais"]["recebido_centavos"] == 12990
    assert anterior["totais"]["faturado_centavos"] == 0


def test_faturado_se_decompoe_e_as_partes_fecham(client, staff_headers, seed_servicos):
    """Carro entregue devendo: o faturado se parte em recebido + a receber, sem sobra."""
    lavagem, polimento = seed_servicos
    a = _os_concluida(client, staff_headers, servico=lavagem, placa="REL2B22", chave="rel-00002")
    _pagar(client, staff_headers, a["id"], 5000)  # pagou menos e levou
    _os_concluida(
        client,
        staff_headers,
        servico=polimento,
        placa="REL3C33",
        chave="rel-00003",
        cliente={"nome": "Outro Cliente", "telefone": "82 97777-0002"},
    )

    t = client.get("/api/v1/relatorios", headers=staff_headers).json()["totais"]
    assert t["faturado_centavos"] == 12990 + 99990
    assert t["faturado_recebido_centavos"] == 5000
    assert t["faturado_a_receber_centavos"] == t["faturado_centavos"] - 5000
    assert t["recebido_centavos"] == 5000
    assert t["os_concluidas"] == 2


def test_ticket_medio_e_liquido_de_desconto(client, staff_headers, seed_servicos):
    """O desconto entra no total da OS, então o ticket médio já sai líquido."""
    lavagem, _ = seed_servicos
    _os_concluida(client, staff_headers, servico=lavagem, placa="REL4D44", chave="rel-00004", desconto=2990)
    t = client.get("/api/v1/relatorios", headers=staff_headers).json()["totais"]
    assert t["faturado_centavos"] == 10000 and t["desconto_centavos"] == 2990
    assert t["ticket_medio_centavos"] == 10000


def test_ranking_por_servico_usa_o_nome_do_catalogo_e_nao_rateia_desconto(
    client, admin_headers, staff_headers, seed_servicos
):
    """Serviço renomeado não parte a linha em duas, e a receita mostrada é bruta."""
    lavagem, polimento = seed_servicos
    _os_concluida(client, staff_headers, servico=lavagem, placa="REL5E55", chave="rel-00005")
    _os_concluida(
        client,
        staff_headers,
        servico=lavagem,
        placa="REL6F66",
        chave="rel-00006",
        desconto=1000,
        cliente={"nome": "Terceiro", "telefone": "82 97777-0003"},
    )
    _os_concluida(
        client,
        staff_headers,
        servico=polimento,
        placa="REL7G77",
        chave="rel-00007",
        cliente={"nome": "Quarto", "telefone": "82 97777-0004"},
    )
    # o dono renomeia o serviço depois das OS já concluídas
    client.patch(f"/api/v1/services/{lavagem['id']}", json={"nome": "Lavagem Simples (nova)"}, headers=admin_headers)

    corpo = client.get("/api/v1/relatorios", headers=staff_headers).json()
    linhas = {l["nome"]: l for l in corpo["por_servico"]}
    assert "Lavagem Simples (nova)" in linhas and "Lavagem Simples" not in linhas
    assert linhas["Lavagem Simples (nova)"]["quantidade"] == 2
    # receita BRUTA: o desconto de R$ 10 não é rateado no item
    assert linhas["Lavagem Simples (nova)"]["total_centavos"] == 12990 * 2
    # o ranking vem do maior para o menor
    assert [l["nome"] for l in corpo["por_servico"]][0] == "Polimento Técnico"
    # e a soma bruta menos o desconto fecha com o faturado
    bruto = sum(l["total_centavos"] for l in corpo["por_servico"])
    assert bruto - corpo["totais"]["desconto_centavos"] == corpo["totais"]["faturado_centavos"]


def test_cancelamento_conta_pelo_evento_mesmo_depois_de_remarcar(client, staff_headers, seed_cliente_veiculo):
    """Quem não compareceu e remarcou continua tendo faltado — o status atual esquece, o evento não."""
    c, v = seed_cliente_veiculo
    quando = datetime.now(timezone.utc) + timedelta(days=1)
    wo = client.post(
        "/api/v1/work-orders",
        json={"client_id": c["id"], "vehicle_id": v["id"], "scheduled_at": quando.isoformat()},
        headers=staff_headers,
    ).json()
    client.post(
        f"/api/v1/work-orders/{wo['id']}/transition",
        json={"to_status": "nao_compareceu", "motivo": "não apareceu"},
        headers=staff_headers,
    )
    # remarca: o status volta para agendado, mas a falta aconteceu
    client.patch(
        f"/api/v1/work-orders/{wo['id']}",
        json={"scheduled_at": (quando + timedelta(days=2)).isoformat()},
        headers=staff_headers,
    )
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "agendado"}, headers=staff_headers)

    t = client.get("/api/v1/relatorios", headers=staff_headers).json()["totais"]
    assert t["nao_comparecimentos"] == 1
    assert client.get(f"/api/v1/work-orders/{wo['id']}", headers=staff_headers).json()["status"] == "agendado"


def test_dia_da_semana_usa_o_fuso_da_loja(client, staff_headers, seed_servicos, db):
    """23h de Maceió é 02h UTC do dia seguinte: o balde tem de seguir a loja, não o UTC."""
    lavagem, _ = seed_servicos
    wo = _os_concluida(client, staff_headers, servico=lavagem, placa="REL8H88", chave="rel-00008")
    # domingo 06/09/2026, 23h30 em Maceió = segunda 07/09 02h30 UTC
    _mover(db, "work_orders", "conclusao", wo["id"], datetime(2026, 9, 7, 2, 30, tzinfo=timezone.utc))

    corpo = client.get(
        "/api/v1/relatorios",
        params={"periodo": "personalizado", "de": "2026-09-01", "ate": "2026-09-30"},
        headers=staff_headers,
    ).json()
    por_dia = {d["dia_label"]: d["os_concluidas"] for d in corpo["por_dia_semana"]}
    assert por_dia["Domingo"] == 1 and por_dia["Segunda"] == 0
    assert [d["dia_label"] for d in corpo["por_dia_semana"]][0] == "Segunda"


def test_periodo_invalido_avisa_em_portugues(client, staff_headers):
    r = client.get(
        "/api/v1/relatorios",
        params={"periodo": "personalizado", "de": "2026-09-30", "ate": "2026-09-01"},
        headers=staff_headers,
    )
    assert r.status_code == 422 and "anterior" in r.json()["detail"]

    r = client.get("/api/v1/relatorios", params={"periodo": "personalizado"}, headers=staff_headers)
    assert r.status_code == 422 and "duas datas" in r.json()["detail"]

    r = client.get(
        "/api/v1/relatorios",
        params={"periodo": "personalizado", "de": "2024-01-01", "ate": "2026-01-01"},
        headers=staff_headers,
    )
    assert r.status_code == 422 and "um ano" in r.json()["detail"]

    assert client.get("/api/v1/relatorios", params={"periodo": "decada"}, headers=staff_headers).status_code == 422


def test_loja_nova_se_distingue_de_mes_parado(client, staff_headers, seed_servicos):
    """Sem nenhuma OS concluída na vida, o vazio é outro — e a tela precisa saber a diferença."""
    corpo = client.get("/api/v1/relatorios", headers=staff_headers).json()
    assert corpo["tem_historico"] is False and corpo["totais"]["faturado_centavos"] == 0
    assert len(corpo["por_dia_semana"]) == 7  # a semana aparece inteira, mesmo zerada

    lavagem, _ = seed_servicos
    _os_concluida(client, staff_headers, servico=lavagem, placa="REL9I99", chave="rel-00009")
    depois = client.get("/api/v1/relatorios", params={"periodo": "mes_passado"}, headers=staff_headers).json()
    assert depois["tem_historico"] is True and depois["totais"]["faturado_centavos"] == 0


def test_clientes_sumidos_traz_telefone_e_ignora_quem_nunca_fechou(client, staff_headers, seed_servicos, db):
    """Cadastro novo não é cliente perdido; quem gastou mais aparece primeiro."""
    lavagem, polimento = seed_servicos
    sumido = _os_concluida(
        client,
        staff_headers,
        servico=polimento,
        placa="SUM1A11",
        chave="sum-00001",
        cliente={"nome": "Sumiu Faz Tempo", "telefone": "82 95555-1111"},
    )
    _mover(db, "work_orders", "conclusao", sumido["id"], datetime.now(timezone.utc) - timedelta(days=200))
    # cliente recente: não deve aparecer
    _os_concluida(
        client,
        staff_headers,
        servico=lavagem,
        placa="SUM2B22",
        chave="sum-00002",
        cliente={"nome": "Veio Ontem", "telefone": "82 95555-2222"},
    )
    # cadastro sem OS nenhuma: também não
    client.post("/api/v1/clients", json={"nome": "So Cadastrado", "telefone": "82 95555-3333"}, headers=staff_headers)

    corpo = client.get("/api/v1/relatorios/clientes-sumidos", headers=staff_headers).json()
    assert [c["nome"] for c in corpo["itens"]] == ["Sumiu Faz Tempo"] and corpo["total"] == 1
    primeiro = corpo["itens"][0]
    assert primeiro["telefone"] and primeiro["atendimentos"] == 1
    assert primeiro["total_gasto_centavos"] == 99990
    assert 195 <= primeiro["dias_sem_voltar"] <= 205

    # com um corte maior, ninguém sumiu ainda
    maior = client.get("/api/v1/relatorios/clientes-sumidos", params={"dias": 365}, headers=staff_headers).json()
    assert maior["itens"] == [] and maior["total"] == 0


def test_relatorio_e_liberado_para_o_socio(client, staff_headers):
    """Mesma doutrina do /caixa: staff vê e opera tudo."""
    assert client.get("/api/v1/relatorios", headers=staff_headers).status_code == 200
    assert client.get("/api/v1/relatorios/clientes-sumidos", headers=staff_headers).status_code == 200


def test_requer_login(client):
    assert client.get("/api/v1/relatorios").status_code == 401
    assert client.get("/api/v1/relatorios/clientes-sumidos").status_code == 401


# ------------------------------------------------------------------ correções da revisão


def test_periodo_sem_entrega_ainda_mostra_o_que_entrou(client, staff_headers, seed_servicos, db):
    """Mês que só recebeu dívida do mês anterior não é mês vazio.

    Este é o payload que a tela escondia inteiro: faturado 0 com recebido > 0 é exatamente a
    divergência que o relatório existe para mostrar.
    """
    lavagem, _ = seed_servicos
    wo = _os_concluida(client, staff_headers, servico=lavagem, placa="VAZ1A11", chave="vaz-00001")
    # a entrega foi no mês passado; o cliente veio pagar hoje
    fim_do_mes_passado = datetime.combine(
        today_local().replace(day=1) - timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    ) + timedelta(hours=15)
    _mover(db, "work_orders", "conclusao", wo["id"], fim_do_mes_passado)
    _pagar(client, staff_headers, wo["id"], 12990)

    t = client.get("/api/v1/relatorios", headers=staff_headers).json()["totais"]
    assert t["os_concluidas"] == 0 and t["faturado_centavos"] == 0
    assert t["recebido_centavos"] == 12990  # a tela precisa continuar mostrando isto


def test_cliente_com_carro_no_patio_nao_e_cliente_sumido(client, staff_headers, seed_servicos, db):
    """A última conclusão pode ser de 200 dias atrás com o carro na loja neste minuto."""
    lavagem, polimento = seed_servicos
    antigo = _os_concluida(
        client,
        staff_headers,
        servico=polimento,
        placa="PAT1A11",
        chave="pat-00001",
        cliente={"nome": "Voltou Hoje", "telefone": "82 94444-1111"},
    )
    _mover(db, "work_orders", "conclusao", antigo["id"], datetime.now(timezone.utc) - timedelta(days=200))
    assert client.get("/api/v1/relatorios/clientes-sumidos", headers=staff_headers).json()["total"] == 1

    # o mesmo cliente traz o carro hoje: sai da lista enquanto a OS estiver viva
    cid = client.get(f"/api/v1/work-orders/{antigo['id']}", headers=staff_headers).json()["client_id"]
    veiculos = client.get(f"/api/v1/clients/{cid}/vehicles", headers=staff_headers).json()
    client.post(
        "/api/v1/work-orders/intake",
        json={"cliente": {"id": cid}, "veiculo": {"id": veiculos[0]["id"]}, "itens": [{"service_id": lavagem["id"]}], "idempotency_key": "pat-00002"},
        headers=staff_headers,
    )
    assert client.get("/api/v1/relatorios/clientes-sumidos", headers=staff_headers).json()["itens"] == []


def test_data_absurda_vira_422_e_nao_500(client, staff_headers):
    """`d + timedelta(days=1)` em date.max estourava OverflowError e virava 500 sem mensagem."""
    for rota, params in (
        ("/api/v1/relatorios", {"periodo": "personalizado", "de": "9999-12-30", "ate": "9999-12-31"}),
        ("/api/v1/caixa", {"dia": "9999-12-31"}),
        ("/api/v1/agenda", {"dia": "9999-12-31"}),
        ("/api/v1/work-orders", {"de": "9999-12-31"}),
    ):
        r = client.get(rota, params=params, headers=staff_headers)
        assert r.status_code == 422, f"{rota} devolveu {r.status_code}"
        assert "2000" in r.json()["detail"] or "sistema" in r.json()["detail"]
