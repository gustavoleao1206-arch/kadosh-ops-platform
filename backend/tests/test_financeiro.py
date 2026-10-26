"""Extrato, relatório por mês, série mensal e dashboard.

O teste central é `test_caixa_extrato_relatorio_e_dashboard_fecham`: o mesmo dinheiro, contado por
quatro telas diferentes, tem de dar o MESMO número — com estorno e desconto no meio. É a única
defesa real contra o pior modo de falha deste módulo, que não é erro de conta: é o dono abrir duas
telas, ver dois valores e parar de confiar no sistema inteiro.
"""

from datetime import datetime, timedelta, timezone

from app.services.periods import today_local
from tests.conftest import STAFF_EMAIL, STAFF_PASS, login_android


def _os_paga(client, headers, cliente, veiculo, servico, *, valor, forma, chave, pago_em=None):
    """Abre uma OS, recebe o carro e lança um pagamento. Devolve a OS com o pagamento dentro."""
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": servico["id"], "valor_centavos": valor}],
        },
        headers=headers,
    ).json()
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "recebido"}, headers=headers)
    corpo = {"valor_centavos": valor, "forma": forma, "idempotency_key": chave}
    if pago_em:
        corpo["pago_em"] = pago_em
    r = client.post(f"/api/v1/work-orders/{wo['id']}/payments", json=corpo, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- extrato


def test_extrato_soma_o_intervalo_e_quebra_por_forma(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=10000, forma="pix", chave="ext-a-001")
    _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=5000, forma="dinheiro", chave="ext-b-001")

    hoje = today_local().isoformat()
    r = client.get(f"/api/v1/extrato?de={hoje}&ate={hoje}", headers=admin_headers)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["total_centavos"] == 15000
    assert corpo["estornos_centavos"] == 0
    assert {f["forma"]: f["total_centavos"] for f in corpo["por_forma"]} == {"pix": 10000, "dinheiro": 5000}
    assert corpo["total"] == 2
    assert len(corpo["lancamentos"]) == 2
    # o rótulo do período vem pronto do backend
    assert corpo["periodo"]["label"]


def test_extrato_lista_o_estornado_mas_nao_soma(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """O mesmo critério do caixa: a linha continua visível (riscada) e fica fora do total."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    os_paga = _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=10000, forma="pix", chave="ext-est-1")
    pid = os_paga["pagamentos"][0]["id"]
    client.post(
        f"/api/v1/work-orders/{os_paga['id']}/payments/{pid}/estorno",
        json={"motivo": "Pix não caiu"},
        headers=admin_headers,
    )

    hoje = today_local().isoformat()
    corpo = client.get(f"/api/v1/extrato?de={hoje}&ate={hoje}", headers=admin_headers).json()
    assert corpo["total_centavos"] == 0
    assert corpo["estornos_centavos"] == 10000
    assert corpo["por_forma"] == []
    # continua na lista, com a marca do estorno e o motivo
    assert len(corpo["lancamentos"]) == 1
    assert corpo["lancamentos"][0]["estornado_em"] is not None
    assert corpo["lancamentos"][0]["estorno_motivo"] == "Pix não caiu"


def test_extrato_filtra_por_forma(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=10000, forma="pix", chave="ext-f-001")
    _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=5000, forma="dinheiro", chave="ext-f-002")

    hoje = today_local().isoformat()
    corpo = client.get(f"/api/v1/extrato?de={hoje}&ate={hoje}&forma=pix", headers=admin_headers).json()
    assert corpo["total_centavos"] == 10000
    assert corpo["total"] == 1
    assert corpo["lancamentos"][0]["forma"] == "pix"
    assert corpo["lancamentos"][0]["forma_label"] == "Pix"


def test_extrato_pagina(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    for i in range(3):
        _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=1000 + i, forma="pix", chave=f"pag-{i}-xx")

    hoje = today_local().isoformat()
    p1 = client.get(f"/api/v1/extrato?de={hoje}&ate={hoje}&page=1&page_size=2", headers=admin_headers).json()
    p2 = client.get(f"/api/v1/extrato?de={hoje}&ate={hoje}&page=2&page_size=2", headers=admin_headers).json()
    assert len(p1["lancamentos"]) == 2 and len(p2["lancamentos"]) == 1
    assert p1["total"] == p2["total"] == 3
    # o total do período NÃO é o total da página: some as três, não as duas primeiras
    assert p1["total_centavos"] == p2["total_centavos"] == 3003
    assert {linha["id"] for linha in p1["lancamentos"]}.isdisjoint({linha["id"] for linha in p2["lancamentos"]})


def test_extrato_recusa_intervalo_invertido_e_forma_inventada(client, admin_headers):
    hoje = today_local()
    ontem = (hoje - timedelta(days=1)).isoformat()
    r = client.get(f"/api/v1/extrato?de={hoje.isoformat()}&ate={ontem}", headers=admin_headers)
    assert r.status_code == 422
    r = client.get(
        f"/api/v1/extrato?de={hoje.isoformat()}&ate={hoje.isoformat()}&forma=bitcoin", headers=admin_headers
    )
    assert r.status_code == 422


def test_extrato_recusa_periodo_maior_que_um_ano(client, admin_headers):
    hoje = today_local()
    antigo = (hoje - timedelta(days=400)).isoformat()
    r = client.get(f"/api/v1/extrato?de={antigo}&ate={hoje.isoformat()}", headers=admin_headers)
    assert r.status_code == 422


def test_extrato_liberado_para_o_socio(client, staff, seed_cliente_veiculo, seed_servicos):
    headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    hoje = today_local().isoformat()
    assert client.get(f"/api/v1/extrato?de={hoje}&ate={hoje}", headers=headers).status_code == 200


# --------------------------------------------------------------------------- relatórios


def test_relatorio_de_um_mes_especifico(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """O seletor de mês do painel: `periodo=mes_especifico&mes=AAAA-MM`."""
    hoje = today_local()
    r = client.get(
        f"/api/v1/relatorios?periodo=mes_especifico&mes={hoje.year:04d}-{hoje.month:02d}",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    periodo = r.json()["periodo"]
    assert periodo["chave"] == "mes_especifico"
    assert periodo["de"] == hoje.replace(day=1).isoformat()
    # o rótulo em português sai do backend, não do painel
    assert str(hoje.year) in periodo["label"]


def test_mes_especifico_sem_mes_e_422(client, admin_headers):
    assert client.get("/api/v1/relatorios?periodo=mes_especifico", headers=admin_headers).status_code == 422
    r = client.get("/api/v1/relatorios?periodo=mes_especifico&mes=2026-13", headers=admin_headers)
    assert r.status_code == 422


def test_relatorio_quebra_por_forma_e_mostra_estornos(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=20000, forma="credito", chave="rel-a-001")
    estornada = _os_paga(
        client, admin_headers, cliente, veiculo, lavagem, valor=7000, forma="pix", chave="rel-b-001"
    )
    pid = estornada["pagamentos"][0]["id"]
    client.post(
        f"/api/v1/work-orders/{estornada['id']}/payments/{pid}/estorno",
        json={"motivo": "cliente desistiu"},
        headers=admin_headers,
    )

    corpo = client.get("/api/v1/relatorios?periodo=mes", headers=admin_headers).json()
    assert {f["forma"]: f["total_centavos"] for f in corpo["por_forma"]} == {"credito": 20000}
    assert corpo["totais"]["recebido_centavos"] == 20000
    assert corpo["totais"]["estornos_centavos"] == 7000


def test_serie_mensal(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=13000, forma="pix", chave="serie-1x")

    r = client.get("/api/v1/relatorios/mensal?meses=3", headers=admin_headers)
    assert r.status_code == 200, r.text
    meses = r.json()["meses"]
    assert len(meses) == 3
    # do mais antigo para o mais recente: é a ordem em que o gráfico desenha
    assert [m["mes"] for m in meses] == sorted(m["mes"] for m in meses)
    hoje = today_local()
    atual = meses[-1]
    assert atual["mes"] == f"{hoje.year:04d}-{hoje.month:02d}"
    assert atual["recebido_centavos"] == 13000
    assert atual["label_curto"]  # rótulo curto para o eixo


def test_serie_mensal_respeita_o_teto(client, admin_headers):
    assert client.get("/api/v1/relatorios/mensal?meses=25", headers=admin_headers).status_code == 422
    assert client.get("/api/v1/relatorios/mensal?meses=0", headers=admin_headers).status_code == 422


# --------------------------------------------------------------------------- dashboard


def test_dashboard_traz_dia_mes_e_cobranca(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    cliente, veiculo = seed_cliente_veiculo
    lavagem, polimento = seed_servicos
    _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=10000, forma="pix", chave="dash-001x")

    # uma OS entregue devendo — tem de aparecer em "atrasados"
    devendo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": polimento["id"], "valor_centavos": 40000}],
        },
        headers=admin_headers,
    ).json()
    client.post(
        f"/api/v1/work-orders/{devendo['id']}/transition", json={"to_status": "recebido"}, headers=admin_headers
    )
    client.post(
        f"/api/v1/work-orders/{devendo['id']}/transition", json={"to_status": "concluido"}, headers=admin_headers
    )

    r = client.get("/api/v1/dashboard", headers=admin_headers)
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["hoje"]["recebido_centavos"] == 10000
    assert corpo["hoje"]["dia"] == today_local().isoformat()
    assert corpo["mes"]["label"]
    assert corpo["mes"]["recebido_centavos"] == 10000
    assert corpo["cobranca"]["atrasados"]["qtd"] == 1
    assert corpo["cobranca"]["atrasados"]["total_centavos"] == 40000
    # a OS quitada não conta como pendência
    assert corpo["cobranca"]["pendentes"]["qtd"] == 0
    # o mês anterior vem junto para a tela desenhar a comparação
    assert corpo["mes"]["mes_anterior"]["faturado_centavos"] == 0


def test_dashboard_liberado_para_o_socio(client, staff):
    headers = login_android(client, STAFF_EMAIL, STAFF_PASS)
    assert client.get("/api/v1/dashboard", headers=headers).status_code == 200


def test_dashboard_de_loja_vazia_nao_quebra(client, admin_headers):
    """Primeiro dia de uso: tudo zero, nenhuma divisão por zero no ticket médio."""
    corpo = client.get("/api/v1/dashboard", headers=admin_headers).json()
    assert corpo["hoje"]["recebido_centavos"] == 0
    assert corpo["mes"]["ticket_medio_centavos"] == 0
    assert corpo["cobranca"]["pendentes"] == {"qtd": 0, "total_centavos": 0}


# --------------------------------------------------------------------------- a conciliação


def test_caixa_extrato_relatorio_e_dashboard_fecham(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """O MESMO dinheiro contado por quatro telas, com estorno e desconto no meio.

    Se este teste falhar, não é um número que está errado: é o dono abrindo duas telas e vendo
    valores diferentes — o modo de falha que destrói a confiança no sistema inteiro.
    """
    cliente, veiculo = seed_cliente_veiculo
    lavagem, polimento = seed_servicos

    _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=12000, forma="pix", chave="conc-a-001")
    _os_paga(client, admin_headers, cliente, veiculo, lavagem, valor=8000, forma="dinheiro", chave="conc-b-001")

    # uma que entra e é estornada: some dos totais, continua na lista
    estornada = _os_paga(
        client, admin_headers, cliente, veiculo, polimento, valor=30000, forma="credito", chave="conc-c-001"
    )
    pid = estornada["pagamentos"][0]["id"]
    client.post(
        f"/api/v1/work-orders/{estornada['id']}/payments/{pid}/estorno",
        json={"motivo": "cartão negado depois"},
        headers=admin_headers,
    )

    # uma com desconto, paga parcialmente
    com_desconto = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": polimento["id"], "valor_centavos": 50000}],
        },
        headers=admin_headers,
    ).json()
    client.post(
        f"/api/v1/work-orders/{com_desconto['id']}/transition",
        json={"to_status": "recebido"},
        headers=admin_headers,
    )
    client.patch(
        f"/api/v1/work-orders/{com_desconto['id']}",
        json={"desconto_centavos": 5000, "desconto_motivo": "cliente antigo"},
        headers=admin_headers,
    )
    client.post(
        f"/api/v1/work-orders/{com_desconto['id']}/payments",
        json={"valor_centavos": 15000, "forma": "pix", "idempotency_key": "conc-d-parcial"},
        headers=admin_headers,
    )

    esperado = 12000 + 8000 + 15000
    hoje = today_local().isoformat()

    caixa = client.get(f"/api/v1/caixa?dia={hoje}", headers=admin_headers).json()
    extrato = client.get(f"/api/v1/extrato?de={hoje}&ate={hoje}", headers=admin_headers).json()
    relatorio = client.get("/api/v1/relatorios?periodo=mes", headers=admin_headers).json()
    dashboard = client.get("/api/v1/dashboard", headers=admin_headers).json()
    mensal = client.get("/api/v1/relatorios/mensal?meses=1", headers=admin_headers).json()["meses"][0]

    assert caixa["recebido_centavos"] == esperado
    assert extrato["total_centavos"] == esperado
    assert relatorio["totais"]["recebido_centavos"] == esperado
    assert dashboard["hoje"]["recebido_centavos"] == esperado
    assert dashboard["mes"]["recebido_centavos"] == esperado
    assert mensal["recebido_centavos"] == esperado

    # o estornado aparece do mesmo jeito nos dois lugares que listam lançamento
    assert extrato["estornos_centavos"] == 30000
    assert relatorio["totais"]["estornos_centavos"] == 30000

    # a quebra por forma é a mesma no caixa, no extrato e no relatório
    por_forma = {"pix": 12000 + 15000, "dinheiro": 8000}
    assert {f["forma"]: f["total_centavos"] for f in caixa["por_forma"]} == por_forma
    assert {f["forma"]: f["total_centavos"] for f in extrato["por_forma"]} == por_forma
    assert {f["forma"]: f["total_centavos"] for f in relatorio["por_forma"]} == por_forma

    # e o "a receber" do caixa bate com as pendências do dashboard
    pendencias = dashboard["cobranca"]["pendentes"]["total_centavos"] + dashboard["cobranca"]["atrasados"]["total_centavos"]
    assert caixa["a_receber_centavos"] == pendencias


def test_devedores_do_caixa_falam_a_lingua_da_regua(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """A lista "a receber" do caixa mostra a mesma situação (e cor) que a OS mostra aberta."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": lavagem["id"], "valor_centavos": 9000}],
        },
        headers=admin_headers,
    ).json()
    client.post(f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "recebido"}, headers=admin_headers)
    entregue = client.post(
        f"/api/v1/work-orders/{wo['id']}/transition", json={"to_status": "concluido"}, headers=admin_headers
    ).json()

    caixa = client.get("/api/v1/caixa", headers=admin_headers).json()
    linha = next(d for d in caixa["a_receber"] if d["work_order_id"] == wo["id"])
    assert linha["situacao_cobranca"] == entregue["situacao_cobranca"] == "atrasado"
    assert linha["situacao_cobranca_label"] == "Atrasado"
    assert linha["situacao_cobranca_tone"] == "danger"


def test_desconto_com_motivo_fica_no_historico(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """"Por que este cliente levou R$ 50?" é a pergunta que aparece três meses depois."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={
            "client_id": cliente["id"],
            "vehicle_id": veiculo["id"],
            "itens": [{"service_id": lavagem["id"], "valor_centavos": 20000}],
        },
        headers=admin_headers,
    ).json()
    r = client.patch(
        f"/api/v1/work-orders/{wo['id']}",
        json={"desconto_centavos": 5000, "desconto_motivo": "cliente de anos"},
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["valor_total_centavos"] == 15000
    evento = next(e for e in r.json()["eventos"] if e["tipo"] == "desconto")
    assert evento["motivo"] == "cliente de anos"
    assert "cliente de anos" in evento["descricao"]


def test_motivo_sozinho_e_recusado(client, admin_headers, seed_cliente_veiculo, seed_servicos):
    """Sem mudança de valor não nasce evento — o motivo não teria onde ser gravado."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    wo = client.post(
        "/api/v1/work-orders",
        json={"client_id": cliente["id"], "vehicle_id": veiculo["id"], "itens": [{"service_id": lavagem["id"]}]},
        headers=admin_headers,
    ).json()
    r = client.patch(
        f"/api/v1/work-orders/{wo['id']}", json={"desconto_motivo": "sem valor junto"}, headers=admin_headers
    )
    assert r.status_code == 422


def test_pagamento_retroativo_cai_no_dia_certo_no_extrato(
    client, admin_headers, seed_cliente_veiculo, seed_servicos
):
    """Pix de ontem lançado hoje: o extrato conta pelo dia em que o dinheiro entrou."""
    cliente, veiculo = seed_cliente_veiculo
    lavagem, _ = seed_servicos
    ontem = datetime.now(timezone.utc) - timedelta(days=1)
    _os_paga(
        client,
        admin_headers,
        cliente,
        veiculo,
        lavagem,
        valor=6000,
        forma="pix",
        chave="retro-01x",
        pago_em=ontem.isoformat(),
    )

    hoje_d = today_local()
    ontem_d = (hoje_d - timedelta(days=1)).isoformat()
    hoje = hoje_d.isoformat()

    so_hoje = client.get(f"/api/v1/extrato?de={hoje}&ate={hoje}", headers=admin_headers).json()
    so_ontem = client.get(f"/api/v1/extrato?de={ontem_d}&ate={ontem_d}", headers=admin_headers).json()
    os_dois = client.get(f"/api/v1/extrato?de={ontem_d}&ate={hoje}", headers=admin_headers).json()

    assert so_hoje["total_centavos"] == 0
    assert so_ontem["total_centavos"] == 6000
    assert os_dois["total_centavos"] == 6000
    # e bate com o caixa do mesmo dia
    caixa_ontem = client.get(f"/api/v1/caixa?dia={ontem_d}", headers=admin_headers).json()
    assert caixa_ontem["recebido_centavos"] == so_ontem["total_centavos"]
